from __future__ import annotations

import logging
from typing import Tuple

from django.contrib.postgres.fields import JSONField
from django.db import models

logger = logging.getLogger(__name__)


class Organisation(models.Model):

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
        pk = organisation_element["organisation-identifier"]
        o, _created = cls.objects.get_or_create(
            pk=pk, defaults=dict(element=organisation_element, abbreviation=abbr)
        )
        if not _created:
            o.iatiorganisation = organisation_element
            o.abbreviation = abbr
            o.save()
        return o


class Activity(models.Model):

    identifier = models.TextField(primary_key=True)
    element = JSONField()

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


class CodelistManager(models.Manager):
    def names(self):
        return self.get_queryset().values_list("element__@name", flat=True)

    def get_by_name(self, name: str) -> "Codelist":
        return self.get_queryset().get(**{"element__@name": name})


class Codelist(models.Model):
    """
    IATI codelist items
    """

    element = JSONField(null=True)
    objects = CodelistManager()

    @classmethod
    def from_dict(cls, element):
        """
        Takes the content of an IATI Codelist XML and adapts it
        to suit the Codelist and CodelistItem models
        """

        # Handle some odd nesting
        codelist = element["codelist"]
        codelist_wrapper = codelist.pop("codelist-items")
        codelists = codelist_wrapper["codelist-item"]

        # This happens when only one element is in a list
        if isinstance(codelists, dict):
            codelists = [codelists]

        instance, _ = cls.objects.get_or_create(element=codelist)
        CodelistItem.objects.bulk_create(
            [CodelistItem(element=item, codelist=instance) for item in codelists]
        )
        logger.debug(
            'Codelist "%s" saved with %s items',
            instance.element["@name"],
            len(codelists),
        )


class CodelistItemManager(models.Manager):
    def by_name(self, name):
        return self.get_queryset().filter(**{"codelist__element__@name": name})

    def withdrawn(self):
        """
        Returns IATI codes with a "withdrawal date" which is not null
        """
        return self.get_queryset().filter(
            **{"element__@withdrawal-date__isnull": False}
        )


class CodelistItem(models.Model):
    element = JSONField(null=True)
    codelist = models.ForeignKey(Codelist, on_delete=models.CASCADE)
    objects = CodelistItemManager()

    @property
    def name(self):
        try:
            narrative = self.element["name"]["narrative"]
        except KeyError:
            logger.warn('No "name" property could be determined')
            return ""

        if isinstance(narrative, str):
            return narrative
        elif isinstance(narrative, list):
            return narrative[0]
        else:
            logger.warn('No "name" property could be determined')
            return ""
