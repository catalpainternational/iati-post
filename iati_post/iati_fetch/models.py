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
        cls,
        organisation_element: dict,
        abbr: str,
        update: bool = False,
        attempt: int = 0,
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

        ab_instance = OrganisationAbbreviation.objects.get_or_create(pk=abbr)[0]
        try:
            o, _created = cls.objects.get_or_create(
                pk=pk,
                abbreviation=ab_instance,
                defaults=dict(element=organisation_element),
            )
        except IntegrityError:
            if attempt < 3:
                attempt += 1
                return cls.from_xml(organisation_element, abbr, update, attempt=attempt)
            logger.error("Broke while trying to do organisation update")
            return cls.objects.filter(pk=pk).first()
        if _created:
            logger.debug(f"Created {o}")
        if not _created:
            logger.debug(f"Updating {o}")
            o.iatiorganisation = organisation_element
            o.save()
        return o


class ActivityFormatException(Exception):
    pass


class ActivityLinkedModel(models.Model):
    activity = models.ForeignKey("iati_fetch.Activity", on_delete=models.CASCADE)
    element = JSONField(db_index=True, blank=True, null=True)

    class Meta:
        abstract = True

    @classmethod
    def from_xml(cls, activity_id, element_list):
        for e in element_list:
            cls.objects.create(activity_id=activity_id, element=e)


class Transaction(ActivityLinkedModel):

    activity = models.ForeignKey("iati_fetch.Activity", on_delete=models.CASCADE)
    element = JSONField(db_index=True, blank=True, null=True)

    # These fields can be long enough to cause indexing to fail
    ref = JSONField(blank=True, null=True)
    description = JSONField(blank=True, null=True)

    @classmethod
    def from_xml(cls, activity_id, transactions):
        cls.objects.filter(activity_id=activity_id).delete()
        for t in transactions:
            try:
                transaction_ref = t.pop("@ref", None)
                transaction_description = t.pop("description", None)
                cls.objects.create(
                    activity_id=activity_id,
                    element=t,
                    ref=transaction_ref,
                    description=transaction_description,
                )
            except BaseException:
                logger.error("We have a problem with %s", (t), exc_info=1)
                raise


class ActivityNarrative(models.Model):
    """
    Pull out Narrative fields from the Activity so that we can
    index the non-narratives
    """

    activity = models.ForeignKey("iati_fetch.Activity", on_delete=models.CASCADE)
    path = models.TextField(blank=True, null=True)
    lang = models.TextField(blank=True, null=True)
    text = models.TextField(blank=True, null=True)


class Budget(ActivityLinkedModel):
    pass


class Result(ActivityLinkedModel):
    pass


class DocumentLink(ActivityLinkedModel):
    pass


class Activity(models.Model):

    identifier = models.TextField(primary_key=True)
    element = JSONField(db_index=True, blank=True, null=True)

    def save_narratives(self, narratives, activity_element):

        # Save narrative objects
        narrative_instances = []
        for path, text_or_items in narratives.items():
            for text_item in text_or_items:
                if text_item is None:
                    logger.debug("No text")
                    continue
                text = None
                lang = None

                if isinstance(text_item, str):
                    text = text_item
                    lang = activity_element.get("@xml:lang", None)
                elif isinstance(text_item, dict):
                    lang = text_item.get("@xml:lang", None)
                    text = text_item.get("#text", None)

                if not lang:
                    logger.debug("No lang assume en")
                    lang = "en"

                if text:
                    narrative_instances.append(
                        ActivityNarrative(activity_id=self.pk, lang=lang, text=text)
                    )

                else:
                    # This happens when there is a lang tag but no #text
                    logger.debug("No text")
                    continue

        ActivityNarrative.objects.bulk_create(narrative_instances)

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

    @staticmethod
    def _iid(activity_element):
        iid = activity_element["iati-identifier"]
        if not isinstance(iid, str):
            raise ActivityFormatException("Expected iati-identifier was a bad format")
        if iid == "":
            raise ActivityFormatException("Expected iati-identifier was a bad format")
        return iid

    @classmethod
    def from_xml(
        cls, activity_element: dict, update=True
    ) -> Union[None, Tuple[Activity, bool]]:
        def find_narratives(element, path, narratives={}):
            """
            Narratives can be arbitrary lengths which makes "sensible" activities hard to index.
            Take these fields into a related model.
            """
            for k, v in element.items():
                if k == "narrative":
                    narratives[f"{path}[{k}]"] = element.pop(k)
                elif isinstance(v, dict):
                    narratives.update(find_narratives(v, f"{path}[{k}]", narratives))
                elif isinstance(v, list):
                    for index, _element in enumerate(v):
                        narratives.update(
                            find_narratives(
                                _element, f"{path}[{k}][{index}]", narratives
                            )
                        )
            return narratives

        # Handle nested lists of activities
        if isinstance(activity_element, list):
            for child_element in activity_element:
                cls.from_xml(child_element)
            return

        cls._validate_activity_xml(activity_element)
        iid = cls._iid(activity_element)

        # Pop fields which will become related models
        transactions = activity_element.pop("transaction", [])

        # Pop fields - no models yet for these
        budget = activity_element.pop("budget", [])
        doclink = activity_element.pop("doclink", [])
        result = activity_element.pop("result", [])

        narratives = find_narratives(activity_element, "")

        # Perform save or update
        exists = cls.objects.filter(pk=iid).exists()
        if cls.objects.filter(pk=iid).exists() and not update:
            logger.debug(f"skip update of activity {iid}")
            return

        elif exists:
            cls.objects.filter(pk=iid).update(element=activity_element)
            logger.debug(f"update activity {iid}")

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
            except Exception as e:
                logger.error("Could not save activity: %s", e)
                logger.error("%s", activity_element)
                raise

        # If we successfully saved - save transactions
        if not cls.objects.filter(pk=iid).exists():
            logger.error("Activity %s not saved", iid)
            return

        # Post-create:
        instance = cls.objects.filter(pk=iid).get()
        Transaction.from_xml(iid, transactions)
        Budget.from_xml(iid, budget)
        DocumentLink.from_xml(iid, doclink)
        Result.from_xml(iid, result)
        instance.save_narratives(narratives, activity_element)


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
