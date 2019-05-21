from django.db import models
from asgiref.sync import async_to_sync
from . import fetch
from django.contrib.postgres.fields import HStoreField, JSONField
from django.utils.functional import cached_property
from lxml import etree


class Organisation(models.Model):
    id = models.TextField(primary_key=True)

    def __str__(self):
        return self.id

    @classmethod
    def fetch(cls):
        """
        Trigger a fetch of all Organisation
        objects
        """
        async_to_sync(fetch.organisation_list)()
        return cls.objects.all()


class RequestSource(models.Model):
    """
    Acts as a cache and processing hub for any requests made, particularly for XML extraction
    """

    class Meta:
        unique_together = (("method", "params", "url"),)

    METHOD_CHOICES = (("GET", "GET"), ("POST", "POST"))
    EXPECTED_CONTENT_CHOICES = (("json", "json"), ("xml", "xml"), ("html", "html"))

    method = models.CharField(max_length=6, choices=METHOD_CHOICES, default="GET")
    params = HStoreField(null=True)
    url = models.URLField()
    expected_content_type = models.CharField(
        max_length=6,
        choices=EXPECTED_CONTENT_CHOICES,
        default="html",
        null=True,
        blank=True,
    )

    success = models.NullBooleanField(default=None, null=True, blank=True)

    html = models.TextField(null=True, blank=True)
    json = JSONField(null=True, blank=True)
    xml = models.TextField(
        null=True, blank=True
    )  # Actually this is going to be an XML field

    def __str__(self):
        return f"{self.url}"

    @cached_property
    def __etree(self) -> etree._Element:
        if not self.xml:
            return None
        return etree.fromstring(self.xml)

    def fetch(self):
        raise NotImplementedError(
            "This is to be implemented as an async task. For now, call relevant functions in fetch.py"
        )

