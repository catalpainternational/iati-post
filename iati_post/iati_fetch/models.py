import json
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.postgres.fields import HStoreField, JSONField
from django.core.cache import cache
from django.db import models
from django.utils.functional import cached_property
from lxml import etree

from . import fetch
from .make_hashable import request_hash

logger = logging.getLogger(__name__)


class Organisation(models.Model):
    """
    Helper functions

    Organisation.call_fetch()
    This will trigger a call to the IATI API to cache a list of organisations

    Organisation.call_process()
    This will fetch cached orgs from redis and update the database
    """

    id = models.TextField(primary_key=True)
    iatiorganisation = JSONField(null=True)

    def __str__(self):
        return self.id

    @staticmethod
    def call_fetch():
        """
        Call IATI, are there new organisations?
        """
        async_to_sync(get_channel_layer().send)(
            "iati", dict(type="organisation.list.fetch")
        )

    @staticmethod
    def call_process():
        """
        Call an update of the organisation list
        """
        async_to_sync(get_channel_layer().send)(
            "iati", dict(type="organisation.list.process")
        )

    def json(self):
        """
        The cached result of an IATI search for documents
        Raises a KeyError if not existing yet, and fires off
        a request to fetch
        """
        params = {"fq": f"organization:{self.pk}"}
        url = fetch.package_search_url

        data = cache.get(request_hash(params, url))
        if not data:

            message = (
                "request",
                dict(
                    type="get",
                    params={"fq": f"organization:{self.pk}"},
                    url=fetch.package_search_url,
                ),
            )

            # Trigger, via channels, a request to pull this organisation's data and
            # then raise a KeyError
            async_to_sync(get_channel_layer().send)(*message)

            return {
                "waiting": "No json found, but a request has been made and should be ready soon - try again in a few seconds"
            }
        return json.loads(data)

    def list_xmls(self):
        """
        Return a list of XML files which are resources for this organisation
        """

        resources = []
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


class Activity(models.Model):

    identifier = models.TextField(primary_key=True)
    xml = models.TextField()
    json = JSONField()  # We will use 'xmltodict' to convert an activity into JSON data
