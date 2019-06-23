import asyncio

from aiohttp import ClientSession, TCPConnector
from asgiref.sync import async_to_sync
from django.test import TestCase

from . import consumers

# Create your tests here.


class RequestsTestCase(TestCase):
    def test_organisation_list(self):
        """We can fetch the list of organisations. We understand the returned format."""
        l = consumers.OrganisationRequestList()
        result = async_to_sync(l.get)(refresh=True)
        self.assertTrue(isinstance(result["result"], list))

    def test_fetch_organisation(self):
        """
        We can fetch an organisation's details
        """
        l = consumers.OrganisationRequestDetail(organisation_handle="ask")
        result = async_to_sync(l.get)(refresh=True)
        self.assertTrue(isinstance(result, dict))

    @async_to_sync
    async def test_fetch_many_organisations(self):
        """
        We can fetch an organisation's details
        """
        await consumers.OrganisationRequestDetail().to_instances()

    @async_to_sync
    async def test_fetch_many_xmls(self):
        """
        We can fetch an organisation's details
        """
        await consumers.OrganisationRequestDetail().xml_requests_get(
            organisations=["ask"]
        )

    @async_to_sync
    async def test_create_instances_from_iatixml(self):
        await consumers.OrganisationRequestDetail().xml_requests_process(
            organisations=["ask"]
        )

    def test_fetch_organisation_xml(self):
        """
        We can fetch an organisation type XML file
        """
        url = "https://aidstream.org/files/xml/ask-org.xml"
        l = consumers.IatiXMLRequest(url=url)
        result = async_to_sync(l.get)(refresh=True)
        organisation = async_to_sync(l.organisations)()

    def test_activities_xml(self):
        """
        We can fetch an activities type XML file
        """
        url = "https://aidstream.org/files/xml/ask-activities.xml"
        l = consumers.IatiXMLRequest(url=url)
        result = async_to_sync(l.get)(refresh=True)
        activities = async_to_sync(l.activities)()
        print(activities)

    def test_save_one_activity(self):
        import json

        url = "https://aidstream.org/files/xml/ask-activities.xml"
        l = consumers.IatiXMLRequest(url=url)
        result = async_to_sync(l.get)(refresh=False)
        activities = async_to_sync(l.activities)()
        activity_as_json = json.dumps(activities[0])
        async_to_sync(l.to_instances)()

    @async_to_sync
    async def test_multiple_get_one_session(self):
        url_list = {
            "ask_activities": consumers.IatiXMLRequest(
                url="https://aidstream.org/files/xml/ask-activities.xml"
            ),
            "ask_org": consumers.IatiXMLRequest(
                url="https://aidstream.org/files/xml/ask-org.xml"
            ),
            "organisation_ask": consumers.BaseRequest(
                url="https://iatiregistry.org/api/3/action/package_search?fq=organization:ask"
            ),
            "organisation_list": consumers.BaseRequest(
                url="https://iatiregistry.org/api/3/action/organization_list"
            ),
        }

        for i in url_list.values():
            i.drop_sync()

        async with ClientSession(connector=TCPConnector(ssl=False)) as session:
            coros = [i.get() for i in url_list.values()]
            responses = await asyncio.gather(*coros)
            print(responses)
