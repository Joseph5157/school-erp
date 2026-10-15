"""Test-run settings: fast hasher only under `manage.py test`."""

from django.conf import settings
from django.contrib.auth.hashers import get_hasher
from django.test import SimpleTestCase


class TestSettingsTests(SimpleTestCase):
    def test_tests_use_fast_password_hasher(self):
        self.assertTrue(settings.TESTING)
        self.assertEqual(get_hasher().algorithm, "md5")
