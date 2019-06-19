import json
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.postgres.fields import HStoreField, JSONField
from django.core.cache import cache
from django.db import models
from django.utils.functional import cached_property
import time
from . import fetch
from .make_hashable import request_hash

logger = logging.getLogger(__name__)


def wait_for_cache(rhash):
    '''
    Primitive cache checker for an async cache putter in another thread
    '''
    try_num = 0
    sent = False
    while not cache.has_key(rhash):
        try_num += 1
        timeout = 2**try_num / 10
        logger.debug('waiting %s seconds', timeout)
        time.sleep(timeout)
    return cache.get(rhash)


class Organisation(models.Model):
    """
    Helper functions

    Organisation.refresh()
    This will trigger a call to the IATI API to cache a list of organisations

    """

    id = models.TextField(primary_key=True)  # This is the IATI identifier for an organisation
    abbreviation:str = models.TextField(null=True)  # This is the abbreviation for a "lookup" in the IATI system
    element = JSONField(null=True) # This is the <iati-organisation> tag as JSON

    def __str__(self):
        return self.id

    @staticmethod
    async def refresh():
        """
        Call an update of the organisation list
        """
        await get_channel_layer().send(
            "iati", dict(type="organisation.list.fetch")
        )

    @classmethod
    def list(cls):
        async_to_sync(cls.refresh)()
        rhash = request_hash(params={}, url=fetch.organisation_list_url)
        response = wait_for_cache(rhash)
        r = json.loads(response)
        return r["result"]
              

    @classmethod
    def fetch_json(cls, abbreviation:str, wait=True):
        """
        The cached result of an IATI dataset on a particular organisation.
        Returns JSON or fires off a request to fetch it.
        """
        request = dict(
                type='get',
                method="GET",
                params={"fq": f"organization:{abbreviation}"},
                url=fetch.package_search_url
            )

        async_to_sync(get_channel_layer().send)("request", request)
        logger.debug('Sent request')
        rhash = request_hash(**request)
        if wait:
            return json.loads(wait_for_cache(rhash))
        else:
            logger.info(f'Signal sent to retrieve {rhash}')

    @classmethod
    def list_xmls(cls, abbreviation:str):
        """
        Return a list of XML files which are resources for this organisation
        """

        resources = []
        json_data = cls.fetch_json(abbreviation)
        if 'waiting' in json_data:
            logger.debug('Waiting: No JSON found')
            return []
        for result in cls.fetch_json(abbreviation)["result"]["results"]:
            for resource in result["resources"]:
                # Add this to the list of xmlsources to cache / parse
                resources.append(resource["url"])
        return resources

    @classmethod
    def fetch_xmls(cls, abbreviation:str):
        """
        Send a number of messages, via Channels, to cache the content of this organisation's xml files
        """
        for url in cls.list_xmls(abbreviation):
            if not cache.has_key(request_hash(params={}, url=url)):
                async_to_sync(get_channel_layer().send)(
                    "request", dict(type="get", params={}, url=url)
                )
            else:
                logger.debug("Skip call on %s  - ought to exist already", url)

    @classmethod
    def from_xml(cls, organisation_element:dict, abbr: str=None):

        # What happens if there is more than one `organisation` element? We would need to iterate through
        name = organisation_element["name"]["narrative"]
        id = organisation_element['organisation-identifier']
        o, _created = cls.objects.get_or_create(id=id, defaults=dict(element=organisation_element, abbreviation=abbr ))
        if not _created:
            o.iatiorganisation = organisation_element
            o.abbreviation = abbr
            o.save()
        
        return o


class Activity(models.Model):

    identifier = models.TextField(primary_key=True)
    element = JSONField()  # We will use 'xmltodict' to convert an activity into JSON data

    def from_xml(activity_element: dict):
        act, created = self.objects.get_or_create(
            pk=activity_element["iati-identifier"], defaults=dict(json=activity_element)
        )
        if not created:
            act.json = activity_element
            act.save()
        return act