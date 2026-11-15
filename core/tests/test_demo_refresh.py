"""refresh_demo_school keeps the staging demo school's data current."""

import datetime
import os
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from core import demo_refresh
from core.models import AcademicYear, business_today


def last_instructional_day(year, on_or_before):
    day = on_or_before
    while not year.is_instructional_day(day):
        day -= datetime.timedelta(days=1)
    return day


def seed_demo_school():
    creds = Path(tempfile.mkdtemp()) / "creds.csv"
    call_command("seed_school_demo", credentials_file=str(creds), allow_non_debug=True,
                 verbosity=0)
    call_command("seed_school_demo_results", allow_non_debug=True, verbosity=0)
    call_command("seed_school_demo_extras", allow_non_debug=True, verbosity=0)


class GuardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_demo_school()

    def test_refuses_without_env_flag(self):
        with mock.patch.dict(os.environ, {"EVERCLASS_DEMO_SCHOOL": ""}):
            with self.assertRaises(CommandError):
                demo_refresh.check_guard(business_today())

    def test_refuses_without_demo_admin(self):
        get_user_model().objects.filter(username="demo_admin").update(username="someone_else")
        with mock.patch.dict(os.environ, {"EVERCLASS_DEMO_SCHOOL": "1"}):
            with self.assertRaises(CommandError):
                demo_refresh.check_guard(business_today())

    def test_out_of_season(self):
        year = AcademicYear.objects.get()
        with mock.patch.dict(os.environ, {"EVERCLASS_DEMO_SCHOOL": "1"}):
            with self.assertRaises(demo_refresh.NotInSeason):
                demo_refresh.check_guard(year.end_date + datetime.timedelta(days=1))

    def test_passes_and_returns_admin_and_year(self):
        year = AcademicYear.objects.get()
        today = last_instructional_day(year, business_today())
        with mock.patch.dict(os.environ, {"EVERCLASS_DEMO_SCHOOL": "1"}):
            admin, found = demo_refresh.check_guard(today)
        self.assertEqual(admin.username, "demo_admin")
        self.assertEqual(found, year)


class RealismTests(SimpleTestCase):
    def test_deterministic(self):
        d = datetime.date(2026, 11, 2)
        self.assertEqual(demo_refresh.is_absent(5, 1, d), demo_refresh.is_absent(5, 1, d))

    def test_rates_are_believable(self):
        days = [datetime.date(2026, 7, 1) + datetime.timedelta(days=i) for i in range(120)]
        rates = [sum(demo_refresh.is_absent(s, 1, d) for d in days) / len(days)
                 for s in range(1, 111)]
        self.assertTrue(0.02 <= sum(rates) / len(rates) <= 0.08)
        self.assertGreaterEqual(sum(r >= 0.09 for r in rates), 3)
        self.assertLess(max(rates), 0.25)

    def test_note_never_empty(self):
        self.assertTrue(all(demo_refresh.absence_note(s, datetime.date(2026, 8, d))
                            for s in range(50) for d in range(1, 29)))
