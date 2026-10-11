"""Phase 6 Gate 8: end-to-end Guardian Portal journeys and protections."""

from datetime import date
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import Group
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.models import SecurityEvent
from core import guardian_accounts as ga
from core.models import (
    AttendanceRegister,
    AttendanceStatus,
    Guardian,
    GuardianAccessReview,
    GuardianAccount,
    GuardianStudentAccess,
    ResultStatus,
    StudentGuardian,
    StudentResult,
    TermPublication,
    TermRemark,
)
from core.tests.phase4_fixtures import Phase4Fixture

EXPECTED_TRIGGERS = {
    "core_sectionclassteacher",
    "core_guardianaccount",
    "core_guardianstudentaccess",
    "core_guardianaccessreview",
    "core_termpublication",
    "core_termpublicationentry",
    "accounts_securityevent",
}


class JourneyFixture(Phase4Fixture):
    def setUp(self):
        self.today = date(2026, 10, 12)
        for target in ("core.views.business_today", "core.models.business_today"):
            patch = mock.patch(target, new=lambda: self.today)
            patch.start()
            self.addCleanup(patch.stop)
        self.build_phase4()
        self.client.login(username="admin", password="pass-12345")
        self.asha, self.asha_e = self.make_student("Asha Rao")
        self.ravi, self.ravi_e = self.make_student("Ravi Rao")
        self.meena = Guardian.objects.create(full_name="Meena Rao", phone="98450-12345")
        self.asha_link = StudentGuardian.objects.create(student=self.asha, guardian=self.meena,
                                                        relationship_type="MOTHER")
        self.ravi_link = StudentGuardian.objects.create(student=self.ravi, guardian=self.meena,
                                                        relationship_type="MOTHER")

    def submitted_register(self, on_date, asha, ravi):
        register = AttendanceRegister.objects.create(
            academic_year=self.year, class_grade=self.grade6, section=self.six_a, date=on_date)
        register.save_draft_entry(enrollment=self.asha_e, status=asha)
        register.save_draft_entry(enrollment=self.ravi_e, status=ravi)
        register.submit(actor=self.admin)
        return register


class GuardianJourneyTests(JourneyFixture, TestCase):
    def test_reconciled_phase_6_journey(self):
        # 1. The administrator verifies identity and creates the account.
        response = self.client.post(
            reverse("core:guardian-account-create", args=[self.meena.pk]),
            {"username": "Meena.Rao", "identity_verification_method": "IN_PERSON_DOCUMENTS",
             "identity_verification_note": "Aadhaar seen at the office"})
        password = response.context["password"]
        self.assertIn("no-store", response["Cache-Control"])

        # 2. Offline password, forced change at first sign-in.
        guardian = self.client_class(REMOTE_ADDR="203.0.113.5")
        guardian.post(reverse("login"), {"username": "meena.rao", "password": password})
        self.assertRedirects(guardian.get(reverse("portal:home")), reverse("password_change"),
                             fetch_redirect_response=False)
        guardian.post(reverse("password_change"), {
            "old_password": password, "new_password1": "Garden-Path-2026",
            "new_password2": "Garden-Path-2026"})

        # 3. Nothing visible until an explicit grant; grant one of two children.
        self.assertEqual(guardian.get(reverse("portal:home")).context["children"], [])
        self.client.post(reverse("core:guardian-access-grant", args=[self.asha_link.pk]))
        grant = GuardianStudentAccess.objects.get()
        home = guardian.get(reverse("portal:home"))
        self.assertEqual([c["student"] for c in home.context["children"]], [self.asha])
        self.assertNotContains(home, "Ravi Rao")

        # 4. Submitted attendance visible; draft hidden.
        self.submitted_register(date(2026, 10, 5), AttendanceStatus.PRESENT,
                                AttendanceStatus.ABSENT)
        draft = AttendanceRegister.objects.create(
            academic_year=self.year, class_grade=self.grade6, section=self.six_a,
            date=date(2026, 10, 6))
        draft.save_draft_entry(enrollment=self.asha_e, status=AttendanceStatus.ABSENT)
        attendance = guardian.get(reverse("portal:attendance", args=[grant.public_id]))
        self.assertEqual([d["date"] for d in attendance.context["days"]], [date(2026, 10, 5)])

        # 5. Finalized results stay hidden until published.
        ut1 = self.make_assessment(name="UT1", on=date(2026, 7, 15))
        result = StudentResult.objects.create(assessment=ut1, academic_enrollment=self.asha_e,
                                              status=ResultStatus.MARKED, score=Decimal("15"),
                                              entered_by=self.rao)
        StudentResult.objects.create(assessment=ut1, academic_enrollment=self.ravi_e,
                                     status=ResultStatus.ABSENT, entered_by=self.rao)
        self.force_finalize(ut1)
        TermRemark.objects.create(term=self.term1, student=self.asha, remark="Steady.",
                                  written_by=self.rao)
        cards_url = reverse("portal:report-cards", args=[grant.public_id])
        self.assertEqual(guardian.get(cards_url).context["publications"], [])

        # 6. Preview flags an incomplete Student; publish.
        ut2 = self.make_assessment(name="UT2", on=date(2026, 8, 1))
        publish_url = reverse("core:term-publication", args=[self.term1.pk])
        preview = self.client.get(publish_url, {"section": self.six_a.pk})
        self.assertContains(preview, "Incomplete")
        self.assertEqual(TermPublication.objects.count(), 0)
        ut2.delete()  # the school drops the unfinished test; preview again
        preview = self.client.get(publish_url, {"section": self.six_a.pk})
        self.client.post(publish_url, {"section": self.six_a.pk,
                                       "token": preview.context["plan"]["token"]})
        cards = guardian.get(cards_url).context["publications"]
        self.assertEqual(len(cards), 1)
        card_url = reverse("portal:report-card", args=[grant.public_id, cards[0].public_id])
        self.assertContains(guardian.get(card_url), "15.00 / 20.00")

        # 7. Correction hides the Term until republished; v1 stays reconstructable.
        self.client.post(reverse("core:result-correct", args=[result.pk]),
                         {"status": "MARKED", "score": "17", "reason": "Recount"})
        self.assertEqual(guardian.get(cards_url).context["publications"], [])
        self.assertEqual(guardian.get(card_url).status_code, 404)
        preview = self.client.get(publish_url, {"section": self.six_a.pk})
        self.client.post(publish_url, {"section": self.six_a.pk,
                                       "token": preview.context["plan"]["token"]})
        v2 = guardian.get(cards_url).context["publications"][0]
        self.assertEqual(v2.version, 2)
        v1 = TermPublication.objects.get(student=self.asha, version=1)
        self.assertEqual(v1.entries.get().score, Decimal("15"))
        self.assertContains(self.client.get(reverse("core:publication-detail", args=[v1.pk])),
                            "15.00 / 20.00")

        # 8. Section move requires an explicit decision; retain.
        enroll_url = reverse("core:student-enroll", args=[self.asha.pk])
        data = {"academic_year": self.year.pk, "class_grade": self.grade6.pk,
                "section": self.six_b.pk, "start_date": "2026-10-12"}
        self.assertContains(self.client.post(enroll_url, data), "Placement ended")
        self.client.post(enroll_url, {**data, "access_review": "1",
                                      f"decision_{grant.pk}": "RETAINED"})
        profile = guardian.get(reverse("portal:child", args=[grant.public_id]))
        self.assertEqual(profile.context["profile"]["placement"]["section"], "B")

        # 9. Year end: fail closed until an explicit decision.
        self.today = date(2027, 4, 5)
        guardian.force_login(grant.student_guardian.guardian.accounts.get().user)
        self.assertEqual(guardian.get(reverse("portal:child", args=[grant.public_id]))
                         .status_code, 404)
        queue = self.client.get(reverse("core:guardian-access-reviews"))
        self.assertEqual([row["grant"] for row in queue.context["rows"]], [grant])
        self.client.post(reverse("core:guardian-access-review-decide", args=[grant.pk]),
                         {"decision": "RETAINED"})
        self.assertEqual(guardian.get(reverse("portal:child", args=[grant.public_id]))
                         .status_code, 200)

        # 10. Link revoked: access and sessions end; history intact.
        account = GuardianAccount.objects.get()
        self.client.post(reverse("core:guardian-account-revoke", args=[account.pk]),
                         {"reason": "Requested by the school"})
        response = guardian.get(reverse("portal:home"))
        self.assertTrue(response["Location"].startswith(reverse("login")))
        self.assertEqual(GuardianAccount.objects.count(), 1)
        self.assertEqual(GuardianStudentAccess.objects.count(), 1)
        self.assertEqual(TermPublication.objects.filter(student=self.asha).count(), 2)
        self.assertGreaterEqual(GuardianAccessReview.objects.count(), 2)
        history = set(SecurityEvent.objects.filter(event_class="HISTORY")
                      .values_list("event_type", flat=True))
        self.assertTrue({"ACCOUNT_CREATED", "ACCESS_GRANTED", "TERM_PUBLISHED",
                         "PUBLICATION_STALE", "ACCESS_RETAINED", "ACCESS_REVIEW_PENDING",
                         "ACCOUNT_LINK_REVOKED"} <= history)


class TeacherParentJourneyTests(JourneyFixture, TestCase):
    def test_one_login_two_areas(self):
        users_before = type(self.rao).objects.count()
        ga.link_existing_login(guardian=self.meena, username="RAO", method="EXISTING_RECORDS",
                               note="Staff member", actor=self.admin)
        grant = ga.grant_student_access(student_guardian=self.asha_link, actor=self.admin)
        self.assertEqual(type(self.rao).objects.count(), users_before)
        client = self.client_class()
        client.login(username="rao", password="pass-12345")
        self.assertRedirects(client.get(reverse("home")), reverse("choose-area"),
                             fetch_redirect_response=False)
        self.assertEqual(client.get(reverse("core:my-home")).status_code, 200)
        self.assertEqual(client.get(reverse("portal:child", args=[grant.public_id]))
                         .status_code, 200)
        self.assertEqual(client.get(reverse("core:guardian-list")).status_code, 403)
        self.rao.groups.remove(Group.objects.get(name="Teachers"))
        self.assertRedirects(client.get(reverse("home")), reverse("portal:home"),
                             fetch_redirect_response=False)


class CrossFamilyIsolationTests(JourneyFixture, TestCase):
    def test_two_families_never_see_each_other(self):
        other = Guardian.objects.create(full_name="Other Parent")
        kiran, _ = self.make_student("Kiran Other")
        other_grant = ga.grant_student_access(
            student_guardian=StudentGuardian.objects.create(student=kiran, guardian=other,
                                                            relationship_type="FATHER"),
            actor=self.admin)
        own_grant = ga.grant_student_access(student_guardian=self.asha_link, actor=self.admin)
        clients = {}
        for guardian, username in ((self.meena, "meena"), (other, "other")):
            _, password = ga.create_guardian_account(guardian=guardian, username=username,
                                                     method="EXISTING_RECORDS", note="known",
                                                     actor=self.admin)
            client = self.client_class()
            client.login(username=username, password=password)
            account = guardian.accounts.get()
            account.user.must_change_password = False
            account.user.save()
            clients[username] = client
        for name in ("child", "attendance", "report-cards"):
            with self.subTest(page=name):
                self.assertEqual(clients["meena"].get(
                    reverse(f"portal:{name}", args=[other_grant.public_id])).status_code, 404)
                self.assertEqual(clients["other"].get(
                    reverse(f"portal:{name}", args=[own_grant.public_id])).status_code, 404)
                self.assertEqual(clients["meena"].get(
                    reverse(f"portal:{name}", args=[own_grant.public_id])).status_code, 200)


class DatabaseProtectionInventoryTests(TestCase):
    """Every historical table carries its database triggers on this backend."""

    def test_triggers_installed(self):
        with connection.cursor() as cursor:
            if connection.vendor == "postgresql":
                cursor.execute("SELECT DISTINCT event_object_table FROM "
                               "information_schema.triggers")
            else:
                cursor.execute("SELECT DISTINCT tbl_name FROM sqlite_master WHERE type='trigger'")
            tables = {row[0] for row in cursor.fetchall()}
        self.assertTrue(EXPECTED_TRIGGERS <= tables, EXPECTED_TRIGGERS - tables)


class PortalQueryCountTests(JourneyFixture, TestCase):
    def test_portal_pages_do_not_grow(self):
        grant = ga.grant_student_access(student_guardian=self.asha_link, actor=self.admin)
        account, password = ga.create_guardian_account(
            guardian=self.meena, username="meena", method="EXISTING_RECORDS", note="known",
            actor=self.admin)
        account.user.must_change_password = False
        account.user.save()
        client = self.client_class()
        client.login(username="meena", password=password)
        urls = [reverse("portal:home"), reverse("portal:child", args=[grant.public_id]),
                reverse("portal:attendance", args=[grant.public_id]),
                reverse("portal:report-cards", args=[grant.public_id])]

        def counts():
            result = []
            for url in urls:
                with CaptureQueriesContext(connection) as ctx:
                    self.assertEqual(client.get(url).status_code, 200)
                result.append(len(ctx.captured_queries))
            return result

        self.submitted_register(date(2026, 10, 5), AttendanceStatus.PRESENT,
                                AttendanceStatus.PRESENT)
        small = counts()
        for day in (date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 8)):
            self.submitted_register(day, AttendanceStatus.ABSENT, AttendanceStatus.PRESENT)
        self.assertEqual(counts(), small)
