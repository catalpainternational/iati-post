import asyncio
import json
import logging
import time
import aioredis
import xmltodict
from aiohttp import ClientSession, TCPConnector
from asgiref.sync import async_to_sync, sync_to_async
from channels.consumer import AsyncConsumer, SyncConsumer
from channels.db import database_sync_to_async
from channels.generic.websocket import WebsocketConsumer
from django.apps import apps
from django.conf import settings
from django.core.cache import cache

from iati_fetch.make_hashable import request_hash

logger = logging.getLogger(__name__)

api_root = "https://iatiregistry.org/api/3/"
organisation_list_url = f"{api_root}action/organization_list"
package_search_url = f"{api_root}action/package_search"


@sync_to_async
def cache_response(params: dict, url: str, response_text: str):
    rhash = request_hash(params=params, url=url)
    cache.set(rhash, response_text)
    logger.debug("Saved response to %s", rhash)
    logger.debug("Response length is: %s", len(response_text))


def save_organisations(element: dict):
    """
    Return an Organisation model derived from an iati-organisations XML file
    A suitable example can be found at 'https://files.transparency.org/content/download/2279/14136/file/IATI_TIS_Organisation.xml'
    Expects to receive content as per "iati-organisations"
    """
    model = apps.get_model("iati_fetch", "Organisation")
    model.from_xml(element["iati-organisation"])


def save_activities(element: dict):
    """
    Save an 'iati-activities/iati-activity' represented in JSON to db
    """
    model = apps.get_model("iati_fetch", "Activity")
    activity = element["iati-activity"]
    if isinstance(activity, dict):
        model.from_xml(activity)
    else:
        for a in activity:
            model.from_xml(activity)


async def fetch_to_cache(params, url, method: str = "GET") -> "Response":
    """
    Just because we can async.
    Equivalent code could be written with requests, however if we do extend this to
    multiple requests async will be useful.
    """

    async with ClientSession(connector=TCPConnector(ssl=False)) as session:
        logger.debug("Session initiated; awaiting request")

        async with session.request(method=method, url=url, params=params) as response:
            logger.debug("fetch_to_cache received %s", response.status)
            if response.status != 200:
                logger.debug("not caching due to a non 200: %s", response.status)
                response_text = await response.text()

            elif response.status == 200:
                response_text = await response.text()
                await cache_response(
                    params=params, url=url, response_text=response_text
                )
            else:
                logger.debug("Unhandled response code")

def event_to_request(e):
    return dict(
        url = event.get("url", "http://example.com"),
        params = event.get("params", {})
    )

async def fetch(url, params):
    '''
    'Cache' content of a URL
    This is a wrapper around 'fetch_to_cache'
    '''
    rhash = request_hash(url=url, params=params)

    if cache.has_key(rhash):
        logger.debug("Response exists. Drop cache value to renew")
        return

    response = await fetch_to_cache(params=params, url=url)

    message = {
        **event,
        "type": "response_cached",
        "hash": rhash,
        "response": {"status": response.status, 'content_type': response.content_type, 'encoding': response.get_encoding() },
    }
    # This is a general-purpose "response handler"
    # Abstracted out of here as it's not directly related to fetching
    get_channel_layer.send("request-process", message)

class RequestConsumer(SyncConsumer):
    """
    Methods to fetch and cache URLs. Will cache contents of the given URL under a key composed of the URL and parameters.
    """

    def get(self, event):
        """
        Simple fetcher for a URL.
        Returns cache content if there is a request hash; otherwise fetches to the cache
        and sends an 'ok' message
        """
        return async_to_sync(fetch)(**event_to_request(event))

    def clear_cache(self, event):
        url = event.get("url", "http://example.com")
        params = event.get("params", {})
        logger.debug("Clear cache for %s request received", url)
        rhash = request_hash(url=url, params=params)
        if cache.has_key(rhash):
            cache.delete(rhash)
            return


class RequestProcessConsumer(SyncConsumer):
    def response_cached(self, event):
        logger.debug(event)
        '''
        This handler directs cached responses to
        processors depending on content type
        '''
        url = event.get("url")
        params = event.get("params", {})


        if event['response']['content_type'] == 'text/html':
            pass
        elif event['response']['content_type'] == 'text/xml':
            async_to_sync(self.channel_layer.send)("iati", {'type': 'parse.xml', 'url': url, 'params': params})


class IatiRequestConsumer(SyncConsumer):
    """
    Fetch and cache IATI-related URLS
    """

    def parse_xml(self, event):
        """
        Read an IATI xml file from cache and attempt to populate Organisation(s) / Activit[y/ies] from it
            async_to_sync(get_channel_layer().send)('iati', {'type': 'parse_xml', 'url': 'https://files.transparency.org/content/download/2279/14136/file/IATI_TIS_Organisation.xml', 'params': {}})
        """
        params = event.get("params")
        url = event["url"]

        rhash = request_hash(url=url, params=params)
        request_text = cache.get(rhash)

        if not request_text:
            request = async_to_sync(fetch_to_cache)(url=url, params=params)
            request_text = cache.get(rhash)

        if not request_text:
            logger.error("Empty request")
            return

        try:
            request_as_json = xmltodict.parse(request_text)
        except:
            raise
            logger.error("Badly formed XML")
            logger.error(request_text[150])
            return

        if "iati-organisations" in request_as_json:
            save_organisations(request_as_json["iati-organisations"])
        if "iati-activities" in request_as_json:
            save_activities(request_as_json["iati-activities"])

    def organisation_list_fetch(self, event):
        """
        This should put the list of organisations  to
        the redis response cache
        """
        async_to_sync(self.channel_layer.send)(
            "request",
            {
                "type": "get",
                "method": "GET",
                "url": organisation_list_url,
                "expected_content_type": "json",
            },
        )