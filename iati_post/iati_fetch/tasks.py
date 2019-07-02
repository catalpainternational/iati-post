from . import requesters
import asyncio
from aiohttp import ClientSession, TCPConnector
from typing import List
from channels.db import database_sync_to_async

from iati_fetch.models import (
    Activity,
    Organisation,
    ActivityFormatException
)
from xml.parsers.expat import ExpatError

import logging

logger = logging.getLogger(__name__)

async def xml_requests_list(organisations: list = None, session:ClientSession = None) -> List[requesters.XMLRequest]:
    """
    Return a list of all of the XML requests associated
    with an organisation  abbreviation
    """
    requests_list = []

    if not session:
        async with ClientSession(connector=TCPConnector(ssl=False)) as session:
            return await xml_requests_list(organisations, session)

    if not organisations:
        orl = requesters.OrganisationRequestList()
        organisations = await orl.to_list()

    for abbr in organisations:
        detail_request = requesters.OrganisationRequestDetail(organisation_handle=abbr)
        xml_requests = await detail_request.iati_xml_requests(session=session)
        for xml_request in xml_requests:
            assert xml_request.organisation_handle
            requests_list.append(xml_request)

    return requests_list


async def xml_requests_get(
    organisations: list = None, exclude_uncached=False, exclude_cached=False
) -> List[requesters.IatiXMLRequest]:
    """
    Fetches all of the XML requests associated with particular organisations
    """
    if not organisations:
        orl = requesters.OrganisationRequestList()
        organisations = await orl.to_list()

    assert isinstance(organisations, list)
    # Limit parallel requests avoiding an OSError: too many open files
    sem = asyncio.Semaphore(2000)
    tasks = []
    async with ClientSession(connector=TCPConnector(ssl=False)) as session:
        xml_requests = await xml_requests_list(organisations, session)

        for request in xml_requests:
            cached = request.is_cached()
            if (cached and exclude_cached) or (not cached and exclude_uncached):
                logger.debug('Not included: %s', request)
                continue
            tasks.append(request.bound_get(sem, session=session))
        task_count = len(tasks)
        print(f"Gathering {task_count} tasks")
        await asyncio.gather(*tasks)
    return xml_requests


async def xml_requests_process(
    organisations: list = None, exclude_cached: bool = False, include_activities=True, include_organisations=True
):
    # Collect & cache all of the Organisation information from IATI
    xml_requests = await xml_requests_get(organisations, exclude_cached)
    for req in xml_requests:
        
        # Search for tags in the JSON-dumped data
        activity_elements: List[dict] = []
        organisation_elements: List[dict] = []
        
        if include_activities:
            activity_elements = await req.activities()
        if activity_elements:
            try:
                await database_sync_to_async(Activity.from_xml)(activity_elements)
            except ActivityFormatException:
                logger.error("Failed to import %s", activity_elements)
                logger.error("%s", req)
            except (ExpatError, TypeError) as e:
                logger.error("%s Failure on file %s", e, req)
                pass
        if  include_organisations:
            organisation_elements = await req.organisations()
        if organisation_elements:
            try:
                await database_sync_to_async(Organisation.from_xml)(organisation_elements, abbr = req.organisation_handle)
            except KeyError:
                logger.error("Failed to import %s", organisation_elements)
                logger.error("%s", req)
                raise
            except (ExpatError, TypeError) as e:
                logger.error("%s Failure on file %s", e, req)
                pass
