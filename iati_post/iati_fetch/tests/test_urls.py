from django.test import TestCase

from iati_fetch import consumers


class ImportActivity(TestCase):
    def test_animals_can_speak(self):
        """Animals that can speak are correctly identified"""
        pass
        url = "https://aidstream.org/files/xml/ask-activities.xml"
        consumers.IatiXMLRequest(url=url)
        # async_to_sync(requester.to_instances)()
        # print(Activity.objects.first())
