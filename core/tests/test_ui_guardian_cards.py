"""The admin Guardians list shows one card per Guardian on phones; wider screens keep the table.

Which of the two is visible is a Bootstrap breakpoint class, checked in a real browser;
these tests pin what each card says, its links, the print rule and the query count.
"""

import re
from html import unescape

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from core.guardian_accounts import portal_state_label
from core.models import (
    Applicant,
    Guardian,
    GuardianAccount,
    GuardianStudentAccess,
    StudentGuardian,
)
from core.tests.test_authorization import AuthorizationClientsMixin

User = get_user_model()
URL = reverse("core:guardian-list")


def admit(name):
    applicant = Applicant.objects.create(full_name=name)
    applicant.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)
    return applicant.progress_to_student()


def card_list(html):
    match = re.search(r'<ul class="erp-guardian-cards[^"]*"[^>]*>(.*?)</ul>', html, re.S)
    return match.group(1) if match else ""


def card_texts(html):
    out = []
    for body in re.findall(r'<li class="erp-guardian-card">(.*?)</li>', card_list(html), re.S):
        out.append(" ".join(unescape(re.sub(r"<[^>]+>", " ", body)).split()))
    return out


class GuardianCardTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.admin_user = User.objects.create_user(username="verifier")

    def guardian(self, name="Rajesh Rao", **kwargs):
        return Guardian.objects.create(full_name=name, **kwargs)

    def link(self, guardian, student_name="Asha Rao", relationship="FATHER"):
        student = admit(student_name)
        return StudentGuardian.objects.create(
            student=student, guardian=guardian, relationship_type=relationship
        )

    def account(self, guardian, username, active=True):
        user = User.objects.create_user(username=username, is_active=active)
        return GuardianAccount.objects.create(
            user=user, guardian=guardian, identity_verified_by=self.admin_user,
            identity_verification_method="OTHER", identity_verification_note="x",
            created_by=self.admin_user,
        )

    def grant(self, link):
        return GuardianStudentAccess.objects.create(
            student_guardian=link, granted_by=self.admin_user
        )

    def get(self, **params):
        return self.administrator.get(URL, params).content.decode()

    def test_card_shows_name_contact_children_and_portal_state(self):
        g = self.guardian(phone="9811111111", email="rajesh@example.com")
        link = self.link(g)
        self.grant_account(g, link)
        text = card_texts(self.get())
        self.assertEqual(len(text), 1)
        for expected in ("Rajesh Rao", "9811111111", "rajesh@example.com",
                         "Asha Rao", "Father", "Access granted"):
            self.assertIn(expected, text[0])
        self.assertIn(f'href="{reverse("core:guardian-detail", args=[g.pk])}"', card_list(self.get()))

    def grant_account(self, guardian, link):
        self.account(guardian, f"login{guardian.pk}")
        self.grant(link)

    def test_phone_and_email_are_tap_links(self):
        self.guardian(phone="9811111111", email="rajesh@example.com")
        cards = card_list(self.get())
        self.assertIn('href="tel:9811111111"', cards)
        self.assertIn('href="mailto:rajesh@example.com"', cards)

    def test_card_without_phone_or_email_has_no_empty_links(self):
        self.guardian()
        cards = card_list(self.get())
        self.assertNotIn("tel:", cards)
        self.assertNotIn("mailto:", cards)

    def test_portal_state_each_value(self):
        self.guardian("A None")
        only = self.guardian("B Only")
        self.account(only, "onlyacct")
        granted = self.guardian("C Granted")
        self.grant_account(granted, self.link(granted, "Kid C"))
        inactive = self.guardian("D Inactive")
        self.account(inactive, "inactiveacct", active=False)
        revoked = self.guardian("E Revoked")
        acct = self.account(revoked, "revokedacct")
        acct.revoked_at = timezone.now()
        acct.revoked_by = self.admin_user
        acct.revocation_reason = "left"
        acct.save()
        response = self.administrator.get(URL)
        labels = {g.full_name: portal_state_label(g) for g in response.context["guardians"]}
        self.assertEqual(labels, {
            "A None": "No account", "B Only": "Account only",
            "C Granted": "Access granted", "D Inactive": "Login inactive",
            "E Revoked": "No account",
        })

    def test_revoked_grant_does_not_count_as_access(self):
        g = self.guardian()
        link = self.link(g)
        self.account(g, "acct")
        access = self.grant(link)
        access.revoked_at = timezone.now()
        access.revoked_by = self.admin_user
        access.revocation_reason = "left"
        access.save()
        guardian = list(self.administrator.get(URL).context["guardians"])[0]
        self.assertEqual(portal_state_label(guardian), "Account only")

    def test_cards_are_hidden_when_printing(self):
        self.guardian()
        html = self.get()
        self.assertIn('class="erp-guardian-cards d-md-none d-print-none"', html)
        self.assertIn('<div class="d-none d-md-block d-print-block">', html)

    def test_query_count_does_not_grow_with_guardians(self):
        def populate(n, start):
            for i in range(start, start + n):
                g = self.guardian(f"Guardian {i}", phone=f"98{i:08d}")
                link = self.link(g, f"Child {i}")
                self.grant_account(g, link)

        populate(2, 0)
        with CaptureQueriesContext(connection) as small:
            self.administrator.get(URL)
        populate(10, 2)
        with CaptureQueriesContext(connection) as large:
            self.administrator.get(URL)
        self.assertEqual(len(small), len(large))

    def test_filtered_empty_shows_one_message(self):
        self.guardian()
        html = self.get(q="zzzz-nothing")
        self.assertEqual(html.count("No guardians match this search"), 1)
        self.assertNotIn("<li", card_list(html))
        self.assertNotIn("d-none d-md-block", html)
        self.assertEqual(card_list(html), "")

    def test_unfiltered_empty_shows_one_message(self):
        html = self.get()
        self.assertEqual(html.count("No Guardians yet."), 1)

    def test_long_unbroken_name_still_renders(self):
        name = "X" * 60
        self.guardian(name)
        self.assertIn(name, " ".join(card_texts(self.get())))
