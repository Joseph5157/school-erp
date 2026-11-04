"""Guardian access cards, consent placement and attendance records on phones.

Which layout shows is a Bootstrap breakpoint class, checked in a real browser; these tests
pin what each layout says, where the consent section sits, and the reversal-note rule.
"""

import re
from datetime import date, datetime
from html import unescape

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    AttendanceCorrection,
    AttendanceRegister,
    AttendanceStatus,
    Guardian,
    GuardianContactConsent,
    StudentGuardian,
)
from core.tests.phase4_fixtures import Phase4Fixture

DAY = date(2026, 7, 6)


def text_of(html):
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def cards_of(html):
    return [
        text_of(body)
        for region in re.findall(r'<ul class="erp-record-cards"[^>]*role="list">(.*?)</ul>', html, re.S)
        for body in re.findall(r"<li[^>]*>(.*?)</li>", region, re.S)
    ]


def phone_layout(html):
    return html.split('<div class="d-md-none d-print-none')[1:]


class Base(Phase4Fixture):
    def build(self):
        self.build_phase4()
        self.client.login(username="admin", password="pass-12345")


class GuardianPhoneTests(Base, TestCase):
    def setUp(self):
        self.build()
        self.guardian = Guardian.objects.create(full_name="Meena Rao")
        self.student, _ = self.make_student("Asha Rao")
        self.other, _ = self.make_student("Ravi " + "R" * 60)
        StudentGuardian.objects.create(student=self.student, guardian=self.guardian, relationship_type="MOTHER")
        StudentGuardian.objects.create(student=self.other, guardian=self.guardian, relationship_type="MOTHER")
        self.url = reverse("core:guardian-detail", args=[self.guardian.pk])
        self.record = reverse("core:guardian-consent-record", args=[self.guardian.pk])

    def get(self):
        return self.client.get(self.url).content.decode()

    def test_access_rows_have_phone_cards(self):
        cards = cards_of(self.get())
        self.assertEqual(len(cards), 2)
        asha = next(card for card in cards if "Asha Rao" in card)
        self.assertIn("Mother", asha)
        self.assertIn("Not granted", asha)
        self.assertIn("Grant access", asha)
        self.assertIn("R" * 60, " ".join(cards))

    def test_consent_comes_before_back_link(self):
        content = self.get()
        self.assertLess(content.index('id="messaging-consent"'), content.index("Back to Guardians"))

    def test_section_nav_has_messaging_consent(self):
        content = self.get()
        nav = content.split('aria-label="On this page"')[1].split("</nav>")[0]
        self.assertIn('href="#messaging-consent"', nav)
        self.assertIn("Messaging consent", nav)

    def test_reversing_consent_requires_a_note(self):
        data = {"status": "OPTED_IN", "source": "PAPER_FORM", "note": ""}
        self.client.post(self.record, data)  # first decision: note optional
        self.assertEqual(GuardianContactConsent.objects.count(), 1)

        data["status"] = "OPTED_OUT"
        response = self.client.post(self.record, data, follow=True)
        self.assertEqual(GuardianContactConsent.objects.count(), 1)
        self.assertContains(response, "Add a note saying why the decision is changing.")

        self.client.post(self.record, {**data, "note": "   "})
        self.assertEqual(GuardianContactConsent.objects.count(), 1)

        self.client.post(self.record, {**data, "note": "Parent asked by phone"})
        self.assertEqual(GuardianContactConsent.objects.count(), 2)
        self.assertEqual(self.guardian.contact_consents.first().note, "Parent asked by phone")

    def test_repeating_the_same_decision_needs_no_note(self):
        data = {"status": "OPTED_IN", "source": "PAPER_FORM", "note": ""}
        self.client.post(self.record, data)
        self.client.post(self.record, data)
        self.assertEqual(GuardianContactConsent.objects.count(), 2)


class AttendancePhoneTests(Base, TestCase):
    def setUp(self):
        self.build()
        _, self.asha = self.make_student("Asha")
        _, self.ravi = self.make_student("Ravi")
        register = AttendanceRegister.objects.create(
            academic_year=self.year, class_grade=self.grade6, section=self.six_a, date=DAY
        )
        register.save_draft_entry(enrollment=self.asha, status=AttendanceStatus.ABSENT, absence_note="Fever " + "x" * 60)
        register.save_draft_entry(enrollment=self.ravi, status=AttendanceStatus.PRESENT, absence_note="")
        AttendanceRegister.objects.filter(pk=register.pk).update(
            status="SUBMITTED", submitted_by=self.admin,
            submitted_at=timezone.make_aware(datetime(2026, 7, 6, 15, 30)),
        )
        self.register = register
        self.entry = register.entries.get(academic_enrollment=self.asha)

    def test_submitted_attendance_has_phone_rows_with_note_and_correct_link(self):
        html = self.client.get(reverse("core:attendance-register-detail", args=[self.register.pk])).content.decode()
        cards = cards_of(html)
        self.assertEqual(len(cards), 2)
        asha = next(card for card in cards if "Asha" in card)
        self.assertIn("Absent", asha)
        self.assertIn("Absence note Fever", asha)
        self.assertIn("Correct", asha)
        ravi = next(card for card in cards if "Ravi" in card)
        self.assertNotIn("Absence note", ravi)
        card_html = phone_layout(html)[0]
        self.assertIn(reverse("core:attendance-entry-correct", args=[self.entry.pk]), card_html)
        self.assertIn(reverse("core:student-detail", args=[self.asha.student.pk]), card_html)

    def test_correction_history_has_phone_entries(self):
        AttendanceCorrection.objects.create(
            entry=self.entry, previous_status="ABSENT", new_status="PRESENT",
            previous_absence_note="Fever", new_absence_note="", reason="Parent called school",
            corrected_by=self.admin,
        )
        html = self.client.get(reverse("core:attendance-entry-correct", args=[self.entry.pk])).content.decode()
        cards = cards_of(html)
        self.assertEqual(len(cards), 1)
        card = cards[0]
        for part in ("Absent", "to Present", "When", "Parent called school", "By admin", "Fever"):
            self.assertIn(part, card)

    def test_empty_correction_history_message_on_phone(self):
        html = self.client.get(reverse("core:attendance-entry-correct", args=[self.entry.pk])).content.decode()
        self.assertEqual(cards_of(html), [])
        self.assertIn('class="erp-record-empty">No corrections recorded.', html)
