import json
import logging

from channels.consumer import AsyncConsumer, SyncConsumer
from channels.generic.websocket import AsyncWebsocketConsumer

from . import requesters

from aiohttp import ClientSession

logging.captureWarnings(True)
logger = logging.getLogger(__name__)


class RequestConsumer(SyncConsumer):
    """
    Methods to fetch and cache URLs. Will cache contents
    of the given URL under a key composed of the URL and parameters.
    """

    async def get(self, event):
        """
        Simple fetcher for a URL.
        Returns cache content if there is a request hash;
        otherwise fetches to the cache
        and sends an 'ok' message
        """
        request = requesters.BaseRequest.from_event()
        async with ClientSession() as session:
            await request.get(session=session)

    async def clear_cache(self, event):
        request = requesters.BaseRequest.from_event()
        await request.drop()


class IatiRequestConsumer(AsyncConsumer):
    """
    Fetch and cache IATI-related URLS
    """

    async def parse_xml(self, event):
        """
        Read an IATI xml file from cache and attempt to populate 
        Organisation(s) / Activit[y/ies] from it

        Args:
            event: This should have a "url" like 'https://files.transparency.org/content/download/2279/14136/file/IATI_TIS_Organisation.xml'

        """
        url = requesters.IatiXMLRequest(event["url"])
        await url.to_instances()

    async def organisation_list_fetch(self, _):
        """
        This should put the list of organisations  to
        the redis response cache
        """
        orgs = requesters.OrganisationRequestList()
        await orgs.get()


class EchoConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()

    async def receive(self, text_data=None, bytes_data=None):
        await self.send(text_data=text_data + " world!")

    async def disconnect(self, close_code):
        await self.close()


class FetchUrl(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()

    async def receive(self, text_data=None, bytes_data=None):
        request = requesters.BaseRequest(url="http://example.com")
        async with ClientSession() as session:
            response_text = await request.get(session=session)
        await self.send(text_data=response_text)

    async def disconnect(self, close_code):
        await self.close()


class IatiConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()

    async def receive(self, text_data=None, bytes_data=None):
        request = requesters.OrganisationRequestList()
        async with ClientSession() as session:
            response_text = await request.get(session=session)
        await self.send(text_data=json.dumps(response_text))

    async def disconnect(self, close_code):
        await self.close()


class IatiActivitiesConsumer(AsyncWebsocketConsumer):
    """
    Creates and GETs an requesters.IatiXMLRequest object for one activities XML
    TODO: This takes no options. It should take the URL of the activity to be collected.
    """
    async def connect(self):
        await self.accept()

    async def receive(self, text_data=None, bytes_data=None):
        """
        Make a request for https://aidstream.org/files/xml/ask-activities.xml
        """
        request = requesters.IatiXMLRequest(
            url="https://aidstream.org/files/xml/ask-activities.xml"
        )
        async with ClientSession() as session:
            response_text = await request.get(session=session)
        await self.send(text_data=json.dumps(response_text))

    async def disconnect(self, close_code):
        await self.close()
