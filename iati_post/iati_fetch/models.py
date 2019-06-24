from __future__ import annotations

import json
import logging
import time
from typing import Tuple

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.postgres.fields import HStoreField, JSONField
from django.core.cache import cache
from django.db import models
from django.utils.functional import cached_property

from . import fetch
from .make_hashable import request_hash

logger = logging.getLogger(__name__)


def wait_for_cache(rhash):
    """
    Primitive cache checker for an async cache putter in another thread
    """
    try_num = 0
    sent = False
    while not cache.has_key(rhash):
        try_num += 1
        timeout = 2 ** try_num / 10
        logger.debug("waiting %s seconds", timeout)
        time.sleep(timeout)
    return cache.get(rhash)


class Organisation(models.Model):
    """
    Helper functions

    Organisation.refresh()
    This will trigger a call to the IATI API to cache a list of organisations

    """

    id = models.TextField(
        primary_key=True
    )  # This is the IATI identifier for an organisation
    abbreviation = models.TextField(
        null=True
    )  # This is the abbreviation for a "lookup" in the IATI system
    element = JSONField(null=True)  # This is the <iati-organisation> tag as JSON

    def __str__(self):
        return self.id

    @classmethod
    def from_xml(cls, organisation_element: dict, abbr: str = None):

        if isinstance(organisation_element, list):
            for child_element in organisation_element:
                return cls.from_xml(child_element)
            return

        name = organisation_element["name"]["narrative"]
        id = organisation_element["organisation-identifier"]
        o, _created = cls.objects.get_or_create(
            id=id, defaults=dict(element=organisation_element, abbreviation=abbr)
        )
        if not _created:
            o.iatiorganisation = organisation_element
            o.abbreviation = abbr
            o.save()
        return o


class Activity(models.Model):

    identifier = models.TextField(primary_key=True)
    element = (
        JSONField()
    )  # We will use 'xmltodict' to convert an activity into JSON data

    @classmethod
    def from_xml(cls, activity_element: dict) -> Tuple[Activity, bool]:

        # Handle nested lists of activities
        if isinstance(activity_element, list):
            for child_element in activity_element:
                cls.from_xml(child_element)

        elif "iati-identifier" not in activity_element:
            logger.error("Invalid activity element: %s", str(activity_element)[:200])
            raise KeyError("Wrong type for activity element - no iati-identifier key")

        else:
            act, created = cls.objects.get_or_create(
                pk=activity_element["iati-identifier"],
                defaults=dict(element=dict(activity_element)),
            )
            if not created:
                act.element = activity_element
                act.save()
            return act, created
