import datetime

from django.test import TestCase

from core import home_today
from core.forms import SchoolForm
from core.models import School


class RegisterCutoffTests(TestCase):
    def test_default_is_ten_oclock(self):
        school = School.objects.create(name="X")
        self.assertEqual(school.register_cutoff, datetime.time(10, 0))

    def test_falls_back_to_ten_without_a_school(self):
        self.assertEqual(home_today.register_cutoff(), datetime.time(10, 0))

    def test_returns_the_schools_value(self):
        School.objects.create(name="X", register_cutoff=datetime.time(9, 15))
        self.assertEqual(home_today.register_cutoff(), datetime.time(9, 15))

    def test_school_form_saves_the_cutoff(self):
        form = SchoolForm(data={"name": "X", "notification_channel": "PORTAL_ONLY",
                                "register_cutoff": "09:30"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().register_cutoff, datetime.time(9, 30))

    def test_school_form_blank_cutoff_keeps_the_default(self):
        form = SchoolForm(data={"name": "X", "notification_channel": "PORTAL_ONLY",
                                "register_cutoff": ""})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().register_cutoff, datetime.time(10, 0))
