import json
import logging

from aiohttp import ClientSession, TCPConnector
from channels.db import database_sync_to_async
from django.apps import apps
from typing import List

logger = logging.getLogger(__name__)


api_root = "https://iatiregistry.org/api/3/"
organisation_list_url = f"{api_root}action/organization_list"
package_search_url = f"{api_root}action/package_search"


@database_sync_to_async
def truncate_tables():
    """
    Delete all Organisation and RequestSource objects
    """
    models = [
        apps.get_model("iati_fetch", m) for m in ("Organisation", "RequestSource")
    ]
    for model in models:
        model.objects.all().delete()


@database_sync_to_async
def organisation_names():
    model = apps.get_model("iati_fetch", "Organisation")
    return model.objects.values_list("id", flat=True)


async def organisation_json(name: str = "1-uz"):
    """
    Populates a RequestSource with the JSON returned from
    an Organisation's list of related URLS
    """

    @database_sync_to_async
    def create_or_update_request_source(name: str, url: str, json: str = None):
        model = apps.get_model("iati_fetch", "RequestSource")
        request, created = model.objects.get_or_create(
            params__fq=f"organization:{name}",
            url=url,
            defaults={"expected_content_type": "json"},
        )

        if created:
            request.params = {"fq": f"organization:{name}"}
            request.save()

        if json:
            request.json = json
            request.save()
        return request, created

    async def get_json(record_url, record_params):
        async with ClientSession(connector=TCPConnector(ssl=False)) as session:
            async with session.post(record_url, data=record_params) as response:
                json_content = await response.json()
                return json_content

    # Check whether there is a record already
    # If we have a record with JSON, return the record
    record, created = await create_or_update_request_source(name, package_search_url)
    if created or not record.json:
        json_content = await get_json(record.url, record.params)
        record, created = await create_or_update_request_source(
            name, package_search_url, json.dumps(json_content)
        )
    return record


async def organisation_xml(name: str = "1-uz", refresh_all: bool = False):
    @database_sync_to_async
    def update_url_list_for_organisation(RequestSource_json: str) -> list:
        """
        Takes
        """
        logger.debug("Parsing organisation resources list")
        request_urls_to_fetch = []
        for result in json.loads(RequestSource_json)["result"]["results"]:
            for resource in result["resources"]:
                model = apps.get_model("iati_fetch", "RequestSource")
                rs, created = model.objects.get_or_create(
                    method="GET", expected_content_type="xml", url=resource["url"]
                )
                if (created or not rs.xml) or refresh_all:
                    request_urls_to_fetch.append((rs.pk, rs.url))
                    logger.debug("Content to be fetched for %s", rs.url)
                else:
                    logger.debug("Content exists for %s", rs.url)
        logger.debug("Returning %s URLs", len(request_urls_to_fetch))
        return request_urls_to_fetch

    @database_sync_to_async
    def fetch_url_list_for_organisation(RequestSource_json: str) -> List[str]:
        urls = []
        logger.debug("Parsing organisation resources list")
        for result in json.loads(RequestSource_json)["result"]["results"]:
            for resource in result["resources"]:
                model = apps.get_model("iati_fetch", "RequestSource")
                rs, created = model.objects.get_or_create(
                    method="GET", expected_content_type="xml", url=resource["url"]
                )
                if rs.xml:
                    urls.append((rs.pk, rs.url, True))
                else:
                    urls.append((rs.pk, rs.url, False))
        return urls

    @database_sync_to_async
    def create_or_update_xml_source(pk: int, url: str, xml: str = None):
        model = apps.get_model("iati_fetch", "RequestSource")
        request = model.objects.get(pk=pk, url=url)
        if xml:
            request.xml = xml
            request.save()
        return request

    async def fetch_text(url):
        async with ClientSession(connector=TCPConnector(ssl=False)) as session:
            async with session.get(url) as response:
                return await response.text()

    logger.debug("Parsing organisation resources list")
    request_source = await organisation_json(name)

    # Add to our RequestSource library the values from the organisation's resources list
    request_source_ids = await update_url_list_for_organisation(request_source.json)

    for rs_pk, xml_url in request_source_ids:
        logger.debug("XML content fetch %s", xml_url)
        xml_content = await fetch_text(xml_url)
        logger.debug("XML content fetched %s", xml_url)
        await create_or_update_xml_source(rs_pk, xml_url, xml_content)
        logger.debug("XML source saved in database for %s", xml_url)

    return fetch_url_list_for_organisation(request_source.json)


async def organisation_list():
    """
    Fetches the list of IATI organisations.
    Creates 'Organisation' objects if they do not exist yet.
    """

    @database_sync_to_async
    def get_or_set_request_source(json: dict) -> ("RequestSource", bool):
        model = apps.get_model("iati_fetch", "RequestSource")
        rs, created = model.objects.get_or_create(
            url=organisation_list_url,
            defaults={"method": "GET", "params": None, "json": json},
        )
        if json and not created:
            rs.json = json
            rs.save()
        return rs, created

    @database_sync_to_async
    def organisation_requestsource_to_organisation(names):
        for name in names:
            model = apps.get_model("iati_fetch", "Organisation")
            org, created = model.objects.get_or_create(id=name)
            logging.debug("%s %s", org, created)

    logging.debug(f"Fetching {organisation_list_url} (json)")

    async with ClientSession(connector=TCPConnector(ssl=False)) as session:

        async with session.get(organisation_list_url) as response:
            content = await response.json()
            await get_or_set_request_source(content)
            await organisation_requestsource_to_organisation(content["result"])
