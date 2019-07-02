import asyncio
import json
import logging
from dataclasses import dataclass, field
from ssl import SSLError
from typing import Dict, List, Mapping, Union
from xml.parsers.expat import ExpatError

import aiohttp
import jsonpath_rw_ext as jp
import xmltodict
from aiohttp import (
    ClientOSError,
    ClientPayloadError,
    ClientResponseError,
    ClientSession,
    ServerDisconnectedError,
    TCPConnector,
)
from aiohttp.client_exceptions import ClientConnectorError
from asgiref.sync import async_to_sync, sync_to_async
from bs4 import BeautifulSoup
from channels.db import database_sync_to_async
from django.core.cache import cache

from iati_fetch.make_hashable import request_hash
from iati_fetch.models import (
    Activity,
    ActivityFormatException,
    Codelist,
    Organisation,
    OrganisationAbbreviation,
    Request,
    RequestCacheRecord,
)

logging.captureWarnings(True)
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
class DatabaseRequestStore:
    """
    Requests inheriting from BaseRequest have request error/success codes
    remembered in a Django model
    """

    rhash: tuple = field(init=False, repr=False)

    def _on_request_success(self):
        RequestCacheRecord.objects.create(
            request=Request.objects.get_or_create(pk=self.rhash)[0], code=200
        )

    def _on_request_fail(self, e):
        RequestCacheRecord.objects.create(
            request=Request.objects.get_or_create(pk=self.rhash)[0], exception=f"{e}"
        )


@dataclass
class BaseRequest(DatabaseRequestStore):
    """
    This represents a basic http(s) request.
    """

    url: str
    method: str = "GET"
    expected_type: str = "text"  # Or 'json', 'xml'
    params: Union[None, Mapping[str, str]] = None
    rhash: tuple = field(init=False, repr=False)

    def __post_init__(self):
        self.params = self.params or {}
        self.session_params = dict(params=self.params, url=self.url, method=self.method)
        self.rhash = request_hash(**self.session_params)

    @classmethod
    def from_event(cls, event):
        """
        From a "channels" event with a url, method, params; create a Request object
        """
        return cls(**event)

    async def is_cached(self):
        return self.rhash in await AsyncCache  # noqa:W601

    async def _request(self, session):

        async with session.request(
            **self.session_params, timeout=aiohttp.client.ClientTimeout(total=30.0)
        ) as response:
            # Tell database that we're requesting something now

            try:
                response.raise_for_status()
                self._on_request_success()
            except Exception as e:
                self._on_request_fail(e)
                raise ResponseUnsuccessfulException(
                    "not caching due to a non 200: %s", response.status
                ) from e

            # Tell database what the response was

            assert response.status == 200
            if self.expected_type == "json":
                response_text = await response.json()
            else:
                response_text = await response.text()
            return response, response_text

    async def get(
        self,
        session: Union[bool, ClientSession] = False,
        refresh: bool = False,
        cache: bool = True,
    ):
        """
        Public API to fetch the request
        session:
        If session is truthy, create one with no warning
        If falsey, create a session with a warning
        If session is a ClientSession use the provided Session
        """
        has_key = self.rhash in await AsyncCache  # noqa

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
            try:
                if isinstance(session, ClientSession):
                    response, response_text = await self._request(session=session)
                else:
                    if session is not True:
                        logger.warn(
                            'No "Session" object. Creating one session for request may be inefficient.'  # noqa
                        )
                    async with ClientSession(
                        connector=TCPConnector(ssl=False)
                    ) as session:
                        response, response_text = await self._request(session)

            except (
                ResponseUnsuccessfulException,
                ClientPayloadError,
                SSLError,
                ClientResponseError,
                ClientConnectorError,
                ServerDisconnectedError,
                ClientOSError,
            ) as e:
                logger.warn("URL fetch failure %s", self)
                logger.debug(e, exc_info=True)
                return None
            except Exception as e:
                logger.error(e, exc_info=True)
                return None
            if cache:
                await AsyncCache.set(self.rhash, response_text)
                logger.debug("Cache: response saved %s", self.url)
            return response_text

    async def bound_get(self, sema, session=None, wait=0):
        """
        Wrap self.get with a semaphore; allow a wait if desired
        """
        if wait:
            await asyncio.sleep(wait)
        async with sema:
            await self.get(session=session)

    def drop_sync(self):
        cache.delete(self.rhash)

    async def drop(self):
        await AsyncCache.delete(self.rhash)


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

    def to_models(self):
        """
        Create OrganisationAbbreviation models
        """
        in_models = set(OrganisationAbbreviation.objects.values_list("pk", flat=True))
        in_iati_url = set(async_to_sync(self.to_list)())

        additions = in_iati_url - in_models
        withdrawn = in_models - in_iati_url

        # Additions from IATI record
        OrganisationAbbreviation.objects.bulk_create(
            [OrganisationAbbreviation(pk=pk) for pk in additions]
        )
        # No longer in IATI record
        OrganisationAbbreviation.objects.filter(pk__in=withdrawn).update(withdrawn=True)
        # Was missing from IATI last time, but it came back
        OrganisationAbbreviation.objects.filter(withdrawn=True).exclude(
            pk__in=withdrawn
        ).update(withdrawn=False)


@dataclass
class OrganisationRequestDetail(JSONRequest):
    """
    Returns an organisation search request from IATI
    This is a GET request from a URL like
    `https://iatiregistry.org/api/3/action/package_search?fq=organization:ask`
    """

    organisation_handle: Union[str, None] = None
    url: str = package_search_url

    def __post_init__(self):
        self.params = self.params or {}
        self.params["fq"] = f"organization:{self.organisation_handle}"
        super().__post_init__()

    async def iati_xml_sources(self, session) -> List[Dict]:
        resources = []
        got = await self.get(session)
        for result in got["result"]["results"]:
            for resource in result["resources"]:
                if resource["format"] == "IATI-XML":
                    resources.append(resource)
                else:
                    logger.debug(f' {self} Unexpected "Format": not "IATI-XML"')
        return resources

    async def iati_xml_requests(self, session) -> List["IatiXMLRequest"]:
        resources = await self.iati_xml_sources(session)
        return [IatiXMLRequest(url=resource["url"]) for resource in resources]

    async def result__results(self):
        result = await self.result()
        return result["results"]

    @classmethod
    async def xml_requests_get(
        cls, organisations: list = None, exclude_cached: bool = False
    ):
        if not organisations:
            orl = OrganisationRequestList()
            organisations = await orl.to_list()

        assert isinstance(organisations, list)

        sem = asyncio.Semaphore(
            2000
        )  # Limit parallel requests avoiding an OSError: too many open files
        async with ClientSession(connector=TCPConnector(ssl=False)) as session:
            request_count = 0
            tasks = []
            count_orgs = len(organisations)
            print(f"Gathering {count_orgs} Organisations")
            for abbr in organisations:
                instance = cls(organisation_handle=abbr)
                xml_requests = await instance.iati_xml_requests(session=session)

                for request in xml_requests:
                    if exclude_cached:
                        cached = await request.is_cached()
                        if cached:
                            continue
                    request_count += 1
                    tasks.append(request.bound_get(sem, session=session))
            task_count = len(tasks)
            print(f"Gathering {request_count} XML requests")
            print(f"Gathering {task_count} tasks")
            await asyncio.gather(*tasks)

        # async with

        # logger.info(things)

        # async with ClientSession(
        #     connector=TCPConnector(ssl=False), timeout=ClientTimeout(total=60 * 60)
        # ) as session:
        #     tasks = []
        #     for abbr in organisations:
        #         instance = cls(organisation_handle=abbr)
        #         xml_requests = await instance.iati_xml_requests(session=session)
        #         for request in xml_requests:
        #             tasks.append(request.to_instances_semaphored(
        # sem, session=session))

        #     await asyncio.gather(*tasks)


@dataclass
class XMLRequest(BaseRequest):
    async def to_json(self) -> dict:
        """
        Activity objects as xmltojson'd objects
        """
        logger.debug("to_json %s", self)
        got = await self.get()
        # Xml to JSON is not always clear about whether
        # element should be treated as a single element or a list.
        # In any situation where you encounter issues iterating over
        # something and find it's an unexpected type,
        # improve handling by setting force_list to true.

        force_list = {
            "transaction",
            "iati-activity",
            "iati-organisation",
            "narrative",
            "total-budget",
            "budget-line",
            "codelist-item",
        }
        try:
            assert got
            return xmltodict.parse(got, force_list=force_list)
        except (ExpatError, TypeError, AssertionError) as e:
            logger.warn("XML parse error %s", self)
            logger.error(e, exc_info=True)

        logger.debug("to_json %s", self)
        return {}

    async def matches(self, getter) -> list:
        got: dict = await self.to_json()
        matches: list = jp.match(getter, got)
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

        organisations = await self.organisations()
        activities = await self.activities()

        if activities:
            try:
                await database_sync_to_async(Activity.from_xml)(activities)
            except ActivityFormatException:
                logger.error("Failed to import %s", activities)
                logger.error("%s", self)
            except (ExpatError, TypeError) as e:
                logger.error("%s Failure on file %s", e, self)
                pass

        if organisations:
            try:
                await database_sync_to_async(Organisation.from_xml)(organisations)
            except KeyError:
                logger.error("Failed to import %s", organisations)
                logger.error("%s", self)
                raise
            except (ExpatError, TypeError) as e:
                logger.error("%s Failure on file %s", e, self)
                pass

    async def to_instances_semaphored(
        self, sema: asyncio.Semaphore, session: ClientSession
    ):
        async with sema:
            await self.get(session=session)
            await self.to_instances()


@dataclass
class IatiCodelistDetailRequest(XMLRequest):
    async def to_instances(self):
        as_json = await self.to_json()
        await database_sync_to_async(Codelist.from_dict)(element=as_json)


@dataclass
class IatiCodelistListRequest(BaseRequest):
    """
    Calls the IATI codelist endpoint so that we can fetch all of the codelist XML files

    IATI publishes its codelists in 3 formats: XML, JSON, and  CSV.
    XML is "canonical" and includes all data. Past experience has shown that
    the JSON data misses attributes (ie "withdrawn" status.)
    """

    url: str = "http://reference.iatistandard.org/203/codelists/downloads/clv3/xml/"

    async def _process_links(self) -> List[str]:
        """
        Fetch list of all IATI-vocabulary XML files
        """
        xml_refs = []
        got = await self.get()
        soup = BeautifulSoup(got, features="html.parser")
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if href.endswith("xml"):
                xml_refs.append(self.url + href)
        return xml_refs

    async def _xml_requests(self) -> List[XMLRequest]:
        """
        Fetch 'XMLRequest' objects for all the links
        """
        xml_files = await self._process_links()
        return [IatiCodelistDetailRequest(url=x) for x in xml_files]

    async def _fetch_links(self) -> List[XMLRequest]:
        """
        Cache all of the xml files found on the page with a single Session object
        """
        async with ClientSession() as session:
            xml_requests = await self._xml_requests()
            await asyncio.gather(*[r.get(session=session) for r in xml_requests])

            return xml_requests

    async def to_instances(self):
        """
        Save as "Codelist" items
        """
        requests = await self._fetch_links()
        await asyncio.gather(*[r.to_instances() for r in requests])
