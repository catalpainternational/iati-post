import asyncio

from aiohttp import ClientSession, TCPConnector
from asgiref.sync import async_to_sync
from django.test import TestCase

from iati_fetch import requesters, tasks

# Create your tests here.


class RequestsTestCase(TestCase):
    def test_organisation_list(self):
        """We can fetch the list of organisations. We understand the returned format."""
        req = requesters.OrganisationRequestList()
        result = async_to_sync(req.get)(refresh=False)
        self.assertTrue(isinstance(result["result"], list))
        """From cache ought to return the same result"""
        result_again = async_to_sync(req.get)(refresh=False)
        self.assertTrue(isinstance(result_again["result"], list))

    def test_fetch_organisation(self):
        """
        We can fetch an organisation's details
        """
        req = requesters.OrganisationRequestDetail(organisation_handle="ask")
        result = async_to_sync(req.get)(refresh=False)
        self.assertTrue(isinstance(result, dict))

    @async_to_sync
    async def test_fetch_many_xmls(self):
        """
        We can fetch an organisation's details
        """
        await tasks.xml_requests_get(
            organisations=["ask"]
        )

    @async_to_sync
    async def test_create_instances_from_iatixml(self):
        await tasks.xml_requests_get(
            organisations=["ask"]
        )

    def test_fetch_organisation_xml(self):
        """
        We can fetch an organisation type XML file
        """
        url = "https://aidstream.org/files/xml/ask-org.xml"
        req = requesters.IatiXMLRequest(url=url)
        async_to_sync(req.get)(refresh=False)
        async_to_sync(req.organisations)()

    def test_activities_xml(self):
        """
        We can fetch an activities type XML file
        """
        url = "https://aidstream.org/files/xml/ask-activities.xml"
        requester = requesters.IatiXMLRequest(url=url)
        async_to_sync(requester.get)(refresh=False)
        async_to_sync(requester.activities)()

    def test_save_one_activity(self):
        import json

        url = "https://aidstream.org/files/xml/ask-activities.xml"
        requester = requesters.IatiXMLRequest(url=url)
        async_to_sync(requester.get)(refresh=False)
        activities = async_to_sync(requester.activities)()
        json.dumps(activities[0])
        async_to_sync(requester.to_instances)()

    @async_to_sync
    async def test_multiple_get_one_session(self):
        url_list = {
            "ask_activities": requesters.IatiXMLRequest(
                url="https://aidstream.org/files/xml/ask-activities.xml"
            ),
            "ask_org": requesters.IatiXMLRequest(
                url="https://aidstream.org/files/xml/ask-org.xml"
            ),
            "organisation_ask": requesters.BaseRequest(
                url="https://iatiregistry.org/api/3/action/package_search?fq=organization:ask"  # noqa
            ),
            "organisation_list": requesters.BaseRequest(
                url="https://iatiregistry.org/api/3/action/organization_list"
            ),
        }

        for i in url_list.values():
            i.drop_sync()

        async with ClientSession(connector=TCPConnector(ssl=False)) as session:
            coros = [i.get(session=session) for i in url_list.values()]
            await asyncio.gather(*coros)

    @async_to_sync
    async def test_fetch_codelists(self):
        """
        Test that we can populate a lookup table with IATI codelists
        and items
        """
        await requesters.IatiCodelistListRequest().to_instances()
