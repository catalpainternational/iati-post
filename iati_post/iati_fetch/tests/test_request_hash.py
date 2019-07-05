from django.test import TestCase

from iati_fetch import make_hashable

# Create your tests here.


class HashRequestsCase(TestCase):
    def test_default_request_hash(self):

        self.assertEqual(
            make_hashable.request_hash(),
            (("__method__", "GET"), ("__url__", "www.example.com")),
        )
