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


def save_organisations(element: dict, abbreviation: str):
    """
    Return an Organisation model derived from an iati-organisations XML file
    A suitable example can be found at 'https://files.transparency.org/content/download/2279/14136/file/IATI_TIS_Organisation.xml'
    Expects to receive content as per "iati-organisations"
    """
    model = apps.get_model("iati_fetch", "Organisation")
    model.from_xml(element["iati-organisation"], abbreviation)


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
                response, response_text = await self._request(session)
                return response, response_text

    async def get(self, refresh=False, cache=True):

        has_key = await AsyncCache.has_key(self.rhash)

        # Return from cache
        if has_key:
            if not refresh:
                logger.debug("Cache: response returned %s", self.url)
                response_text = await AsyncCache.get(self.rhash)
                return response_text
            logger.debug("Cache: response dropped %s", self.url)
            await self.drop()
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
        if activities:
            if isinstance(activities, list):
                for el in activities:
                    await database_sync_to_async(Activity.from_xml)(el)
            else:
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

    def get(self, event):
        """
        Simple fetcher for a URL.
        Returns cache content if there is a request hash; otherwise fetches to the cache
        and sends an 'ok' message
        """
        request = BaseRequest.from_event()

    def clear_cache(self, event):

        url = event["url"]
        params = event.get("params", {})
        method = event.get("method", "GET")

        logger.debug("Clear cache for %s request received", url)
        rhash = request_hash(url=url, params=params, method=method)
        if cache.has_key(rhash):
            cache.delete(rhash)
            return


class IatiRequestConsumer(SyncConsumer):
    """
    Fetch and cache IATI-related URLS
    """

    def parse_xml(self, event):
        """
        Read an IATI xml file from cache and attempt to populate Organisation(s) / Activit[y/ies] from it
            async_to_sync(get_channel_layer().send)('iati', {'type': 'parse_xml', 'url': 'https://files.transparency.org/content/download/2279/14136/file/IATI_TIS_Organisation.xml'})
        """
        url = event["url"]

        rhash = request_hash(url=url)
        request_text = cache.get(rhash)

        if not request_text:
            request = fetch(url=url)
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
            save_organisations(
                request_as_json["iati-organisations"],
                abbreviation=event.get("abbreviation", None),
            )
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
