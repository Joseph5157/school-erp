"""U2 teacher daily screens: take attendance, My day, attendance history."""

from datetime import date
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from core.forms import AttendanceCaptureForm
from core.models import AttendanceRegister, SectionClassTeacher
from core.tests.phase4_fixtures import Phase4Fixture

MONDAY = date(2026, 10, 12)


class U2Fixture(Phase4Fixture):
    def setUp(self):
        self.build_phase4()
        for patch in (mock.patch("core.views.business_today", new=lambda: MONDAY),
                      mock.patch("core.models.business_today", new=lambda: MONDAY)):
            patch.start()
            self.addCleanup(patch.stop)
        self.duty = SectionClassTeacher.assign(
            teacher=self.rao, academic_year=self.year, section=self.six_a,
            start_date=date(2026, 6, 1),
        )
        _, self.asha = self.make_student("Asha")
        _, self.ravi = self.make_student("Ravi")
        _, self.bina = self.make_student("Bina")
        self.teacher = self.client_class()
        self.teacher.login(username="rao", password="pass-12345")
        self.url = reverse("core:my-attendance", args=[self.six_a.pk])

    def register(self):
        return AttendanceRegister.objects.get(section=self.six_a, date=MONDAY)

    def draft(self, notes=None, **statuses):
        """Open today's register and save entries, e.g. draft(asha="PRESENT")."""
        self.teacher.post(self.url, {"action": "open"})
        data = {"action": "save"}
        for name, status in statuses.items():
            data[f"status_{getattr(self, name).pk}"] = status
        for name, note in (notes or {}).items():
            data[f"note_{getattr(self, name).pk}"] = note
        self.teacher.post(self.url, data)
        return self.register()


class CaptureCountsTests(U2Fixture, TestCase):
    def test_counts_use_saved_entries(self):
        register = self.draft(asha="PRESENT", ravi="ABSENT")
        form = AttendanceCaptureForm(register=register)
        self.assertEqual(form.counts(), {"all": 3, "present": 1, "absent": 1, "unmarked": 1})

    def test_counts_use_bound_data(self):
        register = self.draft(asha="PRESENT")
        data = {f"status_{self.asha.pk}": "ABSENT", f"status_{self.ravi.pk}": "ABSENT",
                f"status_{self.bina.pk}": ""}
        form = AttendanceCaptureForm(data, register=register)
        self.assertEqual(form.counts(), {"all": 3, "present": 0, "absent": 2, "unmarked": 1})
