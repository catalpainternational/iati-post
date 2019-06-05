import json
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.postgres.fields import HStoreField, JSONField
from django.core.cache import cache
from django.db import models
from django.utils.functional import cached_property
from lxml import etree
import time
from . import fetch
from .make_hashable import request_hash

logger = logging.getLogger(__name__)

class Organisation(models.Model):
    """
    Helper functions

    Organisation.refresh()
    This will trigger a call to the IATI API to cache a list of organisations

    """

    id = models.TextField(primary_key=True)
    iatiorganisation = JSONField(null=True)

    def __str__(self):
        return self.id

    @staticmethod
    def refresh():
        """
        Call an update of the organisation list
        """
        async_to_sync(get_channel_layer().send)(
            "iati", dict(type="organisation.list.fetch")
        )

    @classmethod
    def list(cls):
        rhash = request_hash(params={}, url=fetch.organisation_list_url)
        sent = False
        try_num = 0
        while not cache.has_key(rhash):
            try_num += 1
            timeout = 2**try_num
            if not sent:
                cls.refresh()
                sent = True
            logger.debug('waiting %s seconds', timeout)
            time.sleep(timeout)

        response = cache.get(rhash)
        r = json.loads(response)
        return r["result"]
              

    @staticmethod
    def json(organisation_name):
        """
        The cached result of an IATI dataset on a particular organisation.
        Returns JSON or fires off a request to fetch it.
        """
        request = dict(
                method="GET",
                params={"fq": f"organization:{self.pk}"},
                url=fetch.package_search_url
            )
        data = cache.get(request_hash(**request))

        if data:
            return json.loads(data)

        async_to_sync(get_channel_layer().send)("request", request)

        return {
            "waiting": "No json found, but a request has been made and should be ready soon - try again in a few seconds"
        }


    def list_xmls(self):
        """
        Return a list of XML files which are resources for this organisation
        """

        resources = []
        json_data = self.json()
        if 'waiting' in json_data:
            logger.debug('Waiting: No JSON found')
            return []
        for result in self.json()["result"]["results"]:
            for resource in result["resources"]:
                # Add this to the list of xmlsources to cache / parse
                resources.append(resource["url"])
        return resources

    def fetch_xmls(self):
        """
        Send a number of messages, via Channels, to cache the content of this organisation's xml files
        """
        for url in self.list_xmls():
            if not cache.has_key(request_hash(params={}, url=url)):
                async_to_sync(get_channel_layer().send)(
                    "request", dict(type="get", params={}, url=url)
                )
            else:
                logger.debug("Skip call on %s  - ought to exist already", url)

    def from_xml(organisation_element:dict):

        # What happens if there is more than one `organisation` element? We would need to iterate through
        name = organisation_element["name"]["narrative"]
        name = organisation_element['organisation-identifier']
        o, _created = model.objects.get_or_create(id=name, defaults=dict(json=activity_element))
        o.iatiorganisation = organisation_element
        o.save()


class Activity(models.Model):

    identifier = models.TextField(primary_key=True)
    xml = models.TextField()
    json = JSONField()  # We will use 'xmltodict' to convert an activity into JSON data

    def from_xml(activity_element: dict):
        act, created = self.objects.get_or_create(
            pk=activity_element["iati-identifier"], defaults=dict(json=activity_element)
        )
        if not created:
            act.json = activity_element
            act.save()
        return act