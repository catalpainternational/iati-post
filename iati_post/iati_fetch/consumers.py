import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Mapping

import jsonpath_rw_ext as jp
import xmltodict
from aiohttp import ClientSession, TCPConnector
from asgiref.sync import async_to_sync, sync_to_async
from channels.consumer import AsyncConsumer, SyncConsumer
from channels.db import database_sync_to_async
from channels.generic.websocket import WebsocketConsumer
from django.apps import apps
from django.conf import settings
from django.core.cache import cache
from django.utils.functional import cached_property

from iati_fetch.make_hashable import request_hash
from iati_fetch.models import Activity, Organisation

logger = logging.getLogger(__name__)

api_root = "https://iatiregistry.org/api/3/"
organisation_list_url = f"{api_root}action/organization_list"
package_search_url = f"{api_root}action/package_search"


class AsyncCache:
    """
    Wrap Django's cache functions for async operations
    """

    @staticmethod
    async def get(key):
        return await sync_to_async(cache.get)(key)

    @staticmethod
    async def set(*args, **kwargs):
        return await sync_to_async(cache.set)(*args, **kwargs)

    @staticmethod
    async def delete(key):
        return await sync_to_async(cache.delete)(key)

    @staticmethod
    async def has_key(*args, **kwargs):
        return await sync_to_async(cache.has_key)(*args, **kwargs)


class ResponseCacheException(Exception):
    """
    Raised when a response already exists in cache
    """

    pass


class ResponseUnsuccessfulException(Exception):
    """
    Raised when a response already exists in cache
    """

    pass


@dataclass
class BaseRequest:
    url: str
    method: str = "GET"
    expected_type: str = "text"  # Or 'json', 'xml'
    params: Mapping[str, str] = None
    rhash: tuple = field(init=False, repr=False)

    def __post_init__(self):
        self.params = self.params or {}
        self.session_params = dict(params=self.params, url=self.url, method=self.method)
        self.rhash = request_hash(**self.session_params)

    @classmethod
    def from_event(cls):
        """
        From a "channels" event with a url, method, params; create a Request object
        """
        return cls(**event)

    async def _request(self, session):
        async with session.request(**self.session_params) as response:
            if response.status == 200:
                if self.expected_type == "json":
                    response_text = await response.json()
                else:
                    response_text = await response.text()
                return response, response_text
            elif response.status != 200:
                raise ResponseUnsuccessfulException(
                    "not caching due to a non 200: %s", response.status
                )

    async def _fetch(self, session=None):
        if session:
            response, response_text = await self._request(session)
            return response, response_text
        else:
            async with ClientSession(connector=TCPConnector(ssl=False)) as session:
                try:
                    response, response_text = await self._request(session)
                    return response, response_text
                except aiohttp.client_exceptions.ClientConnectorError as e:
                    logger.warn("Connection error: %s", e)

    async def get(self, refresh=False, cache=True):

        has_key = await AsyncCache.has_key(self.rhash)

        # Return from cache
        if has_key:
            if not refresh:
                logger.debug(
                    "Cache: response returned %s %s %s",
                    self.method,
                    self.url,
                    self.params,
                )
                response_text = await AsyncCache.get(self.rhash)
                if self.expected_type == "json" and isinstance(response_text, str):
                    response_text = json.loads(response_text)
                    assert isinstance(response_text, dict) or isinstance(
                        response_text, list
                    )
                return response_text
            logger.debug("Cache: response dropped %s", self.url)
            await self.drop()
        else:
            response, response_text = await self._fetch()
            if cache:
                await AsyncCache.set(self.rhash, response_text)
                logger.debug("Cache: response saved %s", self.url)
            return response_text

    async def bound_get(self, sema, wait=0):
        """
        Wrap self.get with a semaphore; allow a wait if desired
        """
        if wait:
            await asyncio.sleep(wait)
        async with sema:
            await self.get()

    def drop_sync(self):
        cache.delete(self.rhash)

    async def drop(self):
        await AsyncCache.delete(self.rhash)

    async def cache_response(self, response):
        rhash = await self.rhash
        AsyncCache.set(rhash, response_text)
        logger.debug("Saved response len %s to %s", len(response_text), rhash)
        return rhash


@dataclass
class JSONRequest(BaseRequest):
    expected_type: str = "json"

    async def matches(self, getter):
        got = await self.get()
        return jp.match(getter, got)


@dataclass
class OrganisationRequestList(JSONRequest):
    url: str = organisation_list_url

    async def to_list(self):
        result = await self.get()
        return result["result"]


@dataclass
class OrganisationRequestDetail(JSONRequest):
    """
    Returns an organisation search request from IATI
    This is a GET request from a URL like
    `https://iatiregistry.org/api/3/action/package_search?fq=organization:ask`
    """

    organisation_handle: str = None
    url: str = package_search_url

    def __post_init__(self):
        self.params = self.params or {}
        self.params["fq"] = f"organization:{self.organisation_handle}"
        super().__post_init__()

    async def iati_xml_sources(self) -> List[Dict]:
        resources = []
        got = await self.get()
        for result in got["result"]["results"]:
            for resource in result["resources"]:
                if resource["format"] == "IATI-XML":
                    resources.append(resource)
        return resources

    async def iati_xml_requests(self) -> List["IatiXMLRequest"]:
        resources = await self.iati_xml_sources()
        return [IatiXMLRequest(url=resource["url"]) for resource in resources]

    async def result__results(self):
        result = await self.result()
        return result["results"]

    @classmethod
    async def to_instances(cls, organisations: list = None):
        """
        This creates no instances but caches JSON for future processing
        """

        if not organisations:
            orl = OrganisationRequestList()
            organisations = await orl.to_list()

        assert isinstance(organisations, list)

        sem = asyncio.Semaphore(
            200
        )  # Limit parallel requests avoiding an OSError: too many open files
        async with ClientSession(connector=TCPConnector(ssl=False)) as session:
            tasks = []
            for abbr in organisations:
                instance = cls(organisation_handle=abbr)
                tasks.append(instance.bound_get(sem))

            responses = await asyncio.gather(*tasks)

    @classmethod
    async def xml_requests_get(cls, organisations: list = None):
        if not organisations:
            orl = OrganisationRequestList()
            organisations = await orl.to_list()

        assert isinstance(organisations, list)

        sem = asyncio.Semaphore(
            200
        )  # Limit parallel requests avoiding an OSError: too many open files
        async with ClientSession(connector=TCPConnector(ssl=False)) as session:
            tasks = []
            for abbr in organisations:
                instance = cls(organisation_handle=abbr)
                xml_requests = await instance.iati_xml_requests()
                for request in xml_requests:
                    tasks.append(request.bound_get(sem))

            responses = await asyncio.gather(*tasks)

    @classmethod
    async def xml_requests_process(cls, organisations: list = None):
        if not organisations:
            orl = OrganisationRequestList()
            organisations = await orl.to_list()

        assert isinstance(organisations, list)

        sem = asyncio.Semaphore(5)
        async with ClientSession(connector=TCPConnector(ssl=False)) as session:
            tasks = []
            for abbr in organisations:
                instance = cls(organisation_handle=abbr)
                xml_requests = await instance.iati_xml_requests()
                for request in xml_requests:
                    tasks.append(request.to_instances_semaphored(sem))

            responses = await asyncio.gather(*tasks)


@dataclass
class XMLRequest(BaseRequest):
    async def to_json(self):
        """
        Activity objects as xmltojson'd objects
        """
        got = await self.get()
        return xmltodict.parse(got)

    async def matches(self, getter):
        got = await self.to_json()
        matches = jp.match(getter, got)
        return matches


@dataclass
class IatiXMLRequest(XMLRequest):
    async def activities(self):
        return await self.matches("[iati-activities][iati-activity]")

    async def organisations(self):
        return await self.matches("""['iati-organisations']['iati-organisation']""")

    async def to_instances(self):
        """
        Write to Django models
        """
        activities = await self.activities()

        # from_xml ought to handle nested activity cases
        await database_sync_to_async(Activity.from_xml)(activities)

        organisations = await self.organisations()
        if organisations:
            if isinstance(organisations, list):
                for el in organisations:
                    await database_sync_to_async(Organisation.from_xml)(el)
            else:
                await database_sync_to_async(Organisation.from_xml)(el)

    async def to_instances_semaphored(self, sema: asyncio.Semaphore):
        async with sema:
            await self.to_instances()


class RequestConsumer(SyncConsumer):
    """
    Methods to fetch and cache URLs. Will cache contents of the given URL under a key composed of the URL and parameters.
    """

    async def get(self, event):
        """
        Simple fetcher for a URL.
        Returns cache content if there is a request hash; otherwise fetches to the cache
        and sends an 'ok' message
        """
        request = BaseRequest.from_event()
        await request.get()

    async def clear_cache(self, event):
        request = BaseRequest.from_event()
        await request.drop()


class IatiRequestConsumer(AsyncConsumer):
    """
    Fetch and cache IATI-related URLS
    """

    async def parse_xml(self, event):
        """
        Read an IATI xml file from cache and attempt to populate Organisation(s) / Activit[y/ies] from it
            async_to_sync(get_channel_layer().send)('iati', {'type': 'parse_xml', 'url': 'https://files.transparency.org/content/download/2279/14136/file/IATI_TIS_Organisation.xml'})
        """
        url = IatiXMLRequest(event["url"])
        await event.to_instances()

    async def organisation_list_fetch(self, _):
        """
        This should put the list of organisations  to
        the redis response cache
        """
        orgs = OrganisationRequestList()
        await orgs.get()


from channels.consumer import AsyncConsumer

class EchoConsumer(AsyncConsumer):

    async def websocket_connect(self, event):
        await self.send({
            "type": "websocket.accept",
        })

    async def websocket_receive(self, event):
        await self.send({
            "type": "websocket.send",
            "text": event["text"] + ' world',
        })
    
    async def websocket_disconnect(self, event):
        await self.send({
            "type": "websocket.disconnect",
        })