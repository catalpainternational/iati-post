import asyncio
import logging
from typing import List
from xml.parsers.expat import ExpatError

from aiohttp import ClientSession, TCPConnector
from channels.db import database_sync_to_async

from iati_fetch.models import Activity, ActivityFormatException, Organisation

from . import requesters

logger = logging.getLogger(__name__)


async def fetch_requests(*requests, semaphore_count=2000, cached=True, uncached=True):
    """
    This takes a list of Request objects with an asyncronous 'get' function
    and collects them all
    """
    sem = asyncio.Semaphore(semaphore_count)
    tasks = []

    async def only_uncached_requests():
        returned = []
        for r in requests:
            include = await r.is_cached()
            print(include)
        if not include:
            returned.append(r)
        return returned

    async def only_cached_requests():
        returned = []
        for r in requests:
            include = await r.is_cached()
        if include:
            returned.append(r)
        return returned

    if not cached:
        requests = await only_uncached_requests()
    if not uncached:
        requests = await only_cached_requests()

    async with ClientSession(connector=TCPConnector(ssl=False)) as session:
        for request in requests:
            tasks.append(request.bound_get(sem, session=session))
        task_count = len(tasks)
        print(f"Gathering {task_count} tasks")
        await asyncio.gather(*tasks)
    return requests


async def organisation_requests_list(
    organisation_abbreviations: List[str]
) -> List[requesters.OrganisationRequestDetail]:
    return [
        requesters.OrganisationRequestDetail(organisation_handle=abbr)
        for abbr in organisation_abbreviations
    ]


async def organisation_requests_fetch(
    organisations: List[requesters.OrganisationRequestDetail]
) -> None:
    await fetch_requests(*organisations)


async def xml_requests_list(
    organisations: List[requesters.OrganisationRequestDetail]
) -> List[requesters.XMLRequest]:
    """
    Return a list of all of the XML requests associated
    with an organisation  abbreviation
    """
    requests_list = []
    async with ClientSession(connector=TCPConnector(ssl=False)) as session:
        for detail_request in organisations:
            xml_requests = await detail_request.iati_xml_requests(session=session)
            for xml_request in xml_requests:
                assert xml_request.organisation_handle
                requests_list.append(xml_request)

    return requests_list


async def xml_requests_fetch(requests_list: List[requesters.IatiXMLRequest]) -> None:
    return await fetch_requests(*requests_list)


async def xml_requests_get(
    organisations: List[str] = None
) -> List[requesters.IatiXMLRequest]:
    """
    Fetches all of the XML requests associated with particular organisations
    """
    logger.info("Fetching Organisation List")
    if not organisations:
        orl = requesters.OrganisationRequestList()
        organisations = await orl.to_list(session=None)
    logger.info("Convert list into request objects")
    organisation_requests = await organisation_requests_list(organisations)
    logger.info("Grab XML file references for organisations: as URLs")
    await organisation_requests_fetch(organisation_requests)
    logger.info("Grab XML file references for organisations: as XmlRequest objects")
    xml_requests = await xml_requests_list(organisation_requests)
    logger.info("Fetch XML references for organisations")
    # await xml_requests_fetch(xml_requests)
    logger.info("XML requests returning")

    xml_requests.reverse()
    return xml_requests


async def xml_requests_process(
    organisations: list = None, include_activities=True, include_organisations=True
):
    # Collect & cache all of the Organisation information from IATI
    xml_requests = await xml_requests_get(organisations)
    logger.info("XML requests are going to be processed")
    for req in xml_requests:
        # Search for tags in the JSON-dumped data
        activity_elements: List[dict] = []
        organisation_elements: List[dict] = []

        if include_activities:
            activity_elements = await req.activities()
        if activity_elements:
            try:
                logger.info(f"activity_elements process from {req}")
                await database_sync_to_async(Activity.from_xml)(activity_elements)
            except ActivityFormatException:
                logger.error("Failed to import %s", activity_elements)
                logger.error("%s", req)
            except (ExpatError, TypeError) as e:
                logger.error("%s Failure on file %s", e, req)
                raise
                pass
        if include_organisations:
            logger.info(f"organisations process from {req}")
            organisation_elements = await req.organisations()
        if organisation_elements:
            try:
                await database_sync_to_async(Organisation.from_xml)(
                    organisation_elements, abbr=req.organisation_handle
                )
            except KeyError:
                logger.error("Failed to import %s", organisation_elements)
                logger.error("%s", req)
                raise
            except (ExpatError, TypeError) as e:
                logger.error("%s Failure on file %s", e, req)
                pass
