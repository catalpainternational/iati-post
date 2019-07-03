from __future__ import annotations

import logging
from typing import Tuple, Union

from django.contrib.postgres.fields import JSONField
from django.db import IntegrityError, models
from django.utils import timezone

logger = logging.getLogger(__name__)


class OrganisationAbbreviation(models.Model):
    abbreviation = models.TextField(primary_key=True)
    withdrawn = models.BooleanField(default=False)

    def __str__(self):
        return self.abbreviation

class Organisation(models.Model):

    id = models.TextField(primary_key=True)
    element = JSONField(null=True)  # This is the <iati-organisation> tag as JSON
    abbreviation = models.OneToOneField(
        OrganisationAbbreviation, on_delete=models.CASCADE
    )

    def __str__(self):
        return self.id

    @classmethod
    def from_xml(
        cls, organisation_element: dict, abbr: str, update: bool = False, attempt: int=0
    ):
        assert abbr
        if isinstance(organisation_element, list):
            for child_element in organisation_element:
                return cls.from_xml(child_element, abbr, update)
            return
        if "organisation-identifier" not in organisation_element:

            # Sometimes we get an "activity" in our "organisation" data
            if "iati-identifier" in organisation_element:
                logger.error("Masquerading Activity is trying to be an Organisation")
                Activity.from_xml(organisation_element)
                return

            logger.error(
                "Invalid organisation element: %s", str(organisation_element)[:200]
            )
            logger.error(
                "Wrong type for organisation element - noorganisation-identifier key"
            )
            return

        pk = organisation_element["organisation-identifier"]

        exists = cls.objects.filter(pk=pk).exists()

        if exists and not update:
            logger.debug(f"skip update of {pk}")
            return

        ab_instance = OrganisationAbbreviation.objects.get_or_create(pk = abbr)[0]
        try:
            o, _created = cls.objects.get_or_create(
                pk=pk, abbreviation = ab_instance, defaults=dict(element=organisation_element)
            )
        except IntegrityError:
            if attempt < 3:
                attempt += 1 
            return cls.from_xml(organisation_element, abbr, update, attempt=attempt)
        if _created:
            logger.debug(f"Created {o}")
        if not _created:
            logger.debug(f"Updating {o}")
            o.iatiorganisation = organisation_element
            o.save()
        return o


class ActivityFormatException(Exception):
    pass


class Activity(models.Model):

    identifier = models.TextField(primary_key=True)
    element = JSONField()

    @staticmethod
    def _validate_activity_xml(activity_element):
        if not isinstance(activity_element, dict):
            raise ActivityFormatException(
                "Expected activity_element was %s not dictionary",
                type(activity_element),
            )
        if "iati-identifier" not in activity_element:
            raise ActivityFormatException(
                "Expected iati-identifier was missing in activity"
            )

        iid = activity_element["iati-identifier"]
        if not isinstance(iid, str):
            raise ActivityFormatException("Expected iati-identifier was a bad format")
        if iid == "":
            raise ActivityFormatException("Expected iati-identifier was a bad format")
        return iid

    @classmethod
    def from_xml(
        cls, activity_element: dict, update=False
    ) -> Union[None, Tuple[Activity, bool]]:

        # Handle nested lists of activities
        if isinstance(activity_element, list):
            for child_element in activity_element:
                cls.from_xml(child_element)
            return

        iid = cls._validate_activity_xml(activity_element)
        exists = cls.objects.filter(pk=iid).exists()

        if exists and not update:
            logger.debug(f"skip update of activity {iid}")
            return None

        elif exists:
            cls.objects.filter(pk=iid).update(element=activity_element)
            logger.debug(f"update activity {iid}")
            return None
        else:
            try:
                cls.objects.create(pk=iid, element=activity_element)
                logger.debug(f"create activity {iid}")
            except IntegrityError:
                """? race condition ? """
                try:
                    cls.objects.create(pk=iid, element=activity_element)
                except IntegrityError as e:
                    logger.error("Could not save activity: %s", e)
                finally:
                    return None
            finally:
                return None


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
        return (
            self.get_queryset()
            .filter(**{"element__@withdrawal-date__isnull": False})
            .select_related("codelist")
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


class Request(models.Model):
    request_hash = models.TextField(primary_key=True)


class RequestCacheRecord(models.Model):
    request = models.ForeignKey(Request, on_delete=models.CASCADE)
    when = models.DateTimeField()
    response_code = models.IntegerField()
    exception = models.TextField()

    def save(self, *args, **kwargs):
        """ On save, update timestamps """
        self.when = timezone.now().date()
