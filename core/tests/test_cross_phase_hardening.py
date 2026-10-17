"""R11: the repaired phases (R1-R10) working together. Integration evidence only.

Every test here crosses at least two earlier repairs; nothing is new behavior.
See docs/R11_CROSS_PHASE_HARDENING.md for the matrix.
"""

import re
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from core import assessment_reports, imports, notification_producers
from core import guardian_accounts as ga
from core.authorization import can_write_term_remarks, guardian_can_view, guardian_grants
from core.models import (
    TEACHERS_GROUP_NAME,
    AssessmentTeacherAssignment,
    AttendanceRegister,
    AttendanceStatus,
    Guardian,
    GuardianAccount,
    GuardianStudentAccess,
    Notification,
    ResultStatus,
    SectionClassTeacher,
    Student,
    StudentGuardian,
    StudentResult,
    TermPublication,
)
from core.tests.phase4_fixtures import Phase4Fixture
from core.tests.test_phase7_alerts import AlertFixture
from core.tests.test_phase7_import import NO_GUARDIAN, ImportFixture, student_row, workbook
from core.tests.test_subject_teacher_authorization import HandoverFixture

METHOD = GuardianAccount.VerificationMethod.EXISTING_RECORDS
TODAY = date(2026, 10, 12)


# --- R7 x assessments, results and publication ------------------------------


class TermEditAndPublicationTests(AlertFixture, TestCase):
    """Term 2 is still open for edits; Term 1 is finalized (and published on demand)."""

    def edit_term(self, term, **changes):
        term.refresh_from_db()
        data = {"name": term.name, "start_date": term.start_date, "end_date": term.end_date,
                "display_order": term.display_order, **changes}
        return self.client.post(reverse("core:term-update", args=[term.pk]), data)

    def card_html(self, url):
        page = self.portal.get(url).content
        return re.sub(rb'name="csrfmiddlewaretoken" value="[^"]*"', b"", page)

    def card_names(self, student, term):
        card = assessment_reports.term_report_card(student, term)
        return sorted(
            result.assessment.name for results in card["subjects"].values() for result in results
        )

    def test_legal_edit_before_finalization_keeps_association_and_report(self):
        draft = self.make_assessment(name="Nov UT", on=date(2026, 11, 15), term=self.term2)
        StudentResult.objects.create(
            assessment=draft, academic_enrollment=self.asha_e, status=ResultStatus.MARKED,
            score=Decimal("12"), entered_by=self.rao,
        )
        before = self.card_names(self.asha, self.term2)
        response = self.edit_term(self.term2, end_date=date(2026, 12, 1))
        self.assertEqual(response.status_code, 302)
        draft.refresh_from_db()
        self.assertEqual(draft.term_id, self.term2.pk)
        self.assertEqual(self.card_names(self.asha, self.term2), before)
        self.force_finalize(draft)
        self.assertEqual(self.card_names(self.asha, self.term2), ["Nov UT"])

    def test_edit_after_publication_is_rejected_and_the_card_is_unchanged(self):
        self.publish()
        [publication] = self.cards()
        card_url = reverse("portal:report-card",
                           args=[self.asha_grant.public_id, publication.public_id])
        page_before = self.card_html(card_url)
        names_before = self.card_names(self.asha, self.term1)

        response = self.edit_term(self.term1, end_date=date(2026, 9, 1))

        self.assertEqual(response.status_code, 200)  # form re-rendered with the error
        self.assertTrue(response.context["form"].errors)
        self.term1.refresh_from_db()
        self.assertEqual(self.term1.end_date, date(2026, 9, 30))
        self.assertEqual(self.card_names(self.asha, self.term1), names_before)
        self.assertEqual(self.card_html(card_url), page_before)
        stored = TermPublication.objects.get(pk=publication.pk)
        self.assertEqual((stored.term_label, stored.version), (publication.term_label, 1))

    def test_boundary_day_assessment_survives_a_legal_edit_and_blocks_a_shrink(self):
        last_day = self.make_assessment(name="Last day", on=date(2026, 12, 31), term=self.term2)
        self.assertEqual(self.edit_term(self.term2, start_date=date(2026, 10, 5)).status_code, 302)
        last_day.refresh_from_db()
        self.assertEqual(last_day.term_id, self.term2.pk)
        refused = self.edit_term(self.term2, end_date=date(2026, 12, 30))
        self.assertEqual(refused.status_code, 200)
        self.term2.refresh_from_db()
        self.assertEqual(self.term2.end_date, date(2026, 12, 31))
        self.assertEqual(self.term2.start_date, date(2026, 10, 5))


# --- R8 / R10 x teacher access ----------------------------------------------


class AdmissionNumberAcrossHandoverTests(HandoverFixture, TestCase):
    """rao taught Maths 6A until 30 Sep; iyer since 1 Oct (today is 12 Oct)."""

    def setUp(self):
        super().setUp()
        self.asha.admission_number = "A-1023"
        self.asha.save()
        self.profile = reverse("core:my-student-detail", args=[self.asha.pk])

    def test_new_owner_sees_the_number_and_the_former_owner_is_refused(self):
        self.assertContains(self.b_client.get(self.profile), "A-1023")
        denied = self.a_client.get(self.profile)
        self.assertEqual(denied.status_code, 403)
        self.assertNotContains(denied, "A-1023", status_code=403)

    def test_former_owner_gets_no_number_from_the_list_or_from_other_sections(self):
        other, _ = self.make_student("Bina", section=self.six_b)
        other.admission_number = "B-2044"
        other.save()
        listing = self.a_client.get(reverse("core:my-students"))
        self.assertNotContains(listing, "A-1023")
        self.assertNotContains(listing, "B-2044")
        for client in (self.a_client, self.b_client):
            denied = client.get(reverse("core:my-student-detail", args=[other.pk]))
            self.assertEqual(denied.status_code, 403)
            self.assertNotContains(denied, "B-2044", status_code=403)

    def test_a_class_teacher_keeps_the_student_through_subject_handovers(self):
        SectionClassTeacher.assign(
            teacher=self.make_user("kulkarni", self.teachers), academic_year=self.year,
            section=self.six_a, start_date=self.year.start_date,
        )
        client = self.login("kulkarni")
        self.assertContains(client.get(self.profile), "A-1023")
        self.row_b.end(date(2026, 10, 31))
        AssessmentTeacherAssignment.assign(
            teacher=self.rao, offering=self.maths, section=self.six_a,
            start_date=date(2026, 11, 1),
        )
        self.assertContains(client.get(self.profile), "A-1023")
        # rao's new row starts in November, so today he still has no access.
        self.assertEqual(self.a_client.get(self.profile).status_code, 403)


# --- R10 x Phase 5 workflows -------------------------------------------------


class HandoverAcrossPhase5Tests(HandoverFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.sept = self.make_assessment(name="Sept UT", on=date(2026, 9, 15), term=self.term1)
        self.owner = self.make_user("kulkarni", self.teachers)
        SectionClassTeacher.assign(
            teacher=self.owner, academic_year=self.year, section=self.six_a,
            start_date=self.year.start_date,
        )
        self.owner_client = self.login("kulkarni")
        self.home = reverse("core:my-home")

    def test_dashboard_marks_panel_moves_to_the_current_owner(self):
        mine = [a.name for a in self.b_client.get(self.home).context["assessments"]]
        former = [a.name for a in self.a_client.get(self.home).context["assessments"]]
        self.assertEqual(mine, ["Sept UT"])
        self.assertEqual(former, [])

    def test_class_teacher_duties_ignore_subject_handovers(self):
        panel = self.owner_client.get(self.home).context
        self.assertEqual([row["duty"].section for row in panel["attendance"]], [self.six_a])
        self.assertEqual([r["term"] for r in panel["remarks"]], [self.term1, self.term2])
        for teacher, allowed in ((self.owner, True), (self.rao, False), (self.iyer, False)):
            with self.subTest(teacher=teacher.username):
                self.assertEqual(can_write_term_remarks(teacher, self.term1, self.six_a), allowed)

    def test_report_cards_follow_the_class_teacher_not_the_subject_owner(self):
        self.finalized("Aug UT", date(2026, 8, 20), self.term1)
        self.finalized("Oct UT", date(2026, 10, 5), self.term2)
        for term, name in ((self.term1, "Aug UT"), (self.term2, "Oct UT")):
            with self.subTest(term=term.name):
                url = reverse("core:my-report-card", args=[term.pk, self.asha.pk])
                page = self.owner_client.get(url)
                self.assertEqual(page.status_code, 200)
                self.assertContains(page, name)
                self.assertEqual(self.a_client.get(url).status_code, 403)
                self.assertEqual(self.b_client.get(url).status_code, 403)


# --- R9 x Phases 1 / 6 / 7 ---------------------------------------------------


class GuardianlessImportThenGuardianTests(ImportFixture):
    def test_guardian_added_later_gives_no_portal_access_until_account_and_grant(self):
        batch = self.batch_for(workbook([student_row("Asha", g1=NO_GUARDIAN)]))
        imports.commit_batch(batch, user=self.admin, warnings_reviewed=True)
        asha = Student.objects.get(full_name="Asha")
        self.assertIsNotNone(asha.current_enrollment)

        guardian = Guardian.objects.create(full_name="Sita Devi", phone="9848022338")
        response = self.client.post(
            reverse("core:student-guardian-add", args=[asha.pk]),
            {"guardian": guardian.pk, "relationship_type": "MOTHER"},
        )
        self.assertEqual(response.status_code, 302)
        link = StudentGuardian.objects.get(student=asha)
        self.assertEqual(link.guardian, guardian)
        self.assertFalse(GuardianAccount.objects.exists())
        self.assertFalse(GuardianStudentAccess.objects.exists())

        account, _ = ga.create_guardian_account(
            guardian=guardian, username="sita", method=METHOD, note="known", actor=self.admin
        )
        self.assertFalse(guardian_can_view(account.user, asha))  # account alone is not a grant
        self.assertFalse(guardian_grants(account.user).exists())
        ga.grant_student_access(student_guardian=link, actor=self.admin)
        self.assertTrue(guardian_can_view(account.user, asha))


class StagedNotificationTests(AlertFixture, TestCase):
    """Absence alerts need relationship + account + grant, then consent decides the send."""

    def absent_today(self, name):
        student, enrollment = self.make_student(name)
        register, _ = AttendanceRegister.objects.get_or_create(
            academic_year=self.year, class_grade=self.grade6, section=self.six_a, date=TODAY,
        )
        entry = register.save_draft_entry(enrollment=enrollment, status=AttendanceStatus.ABSENT)
        return student, lambda: notification_producers.absence_corrected(entry, actor=self.admin)

    def alerts(self, student):
        return list(Notification.objects.filter(student=student, type=Notification.Type.ABSENCE))

    def relate(self, student, guardian):
        return StudentGuardian.objects.create(
            student=student, guardian=guardian, relationship_type="MOTHER"
        )

    def open_account(self, guardian, username):
        ga.create_guardian_account(
            guardian=guardian, username=username, method=METHOD, note="known", actor=self.admin
        )

    def test_recipients_appear_only_when_the_whole_chain_exists(self):
        chitra, alert = self.absent_today("Chitra")
        alert()
        self.assertEqual(self.alerts(chitra), [])  # no relationship -> no recipient

        lata = Guardian.objects.create(full_name="Lata", phone="9876500001")
        link = self.relate(chitra, lata)
        alert()
        self.assertEqual(self.alerts(chitra), [])  # relationship only

        self.open_account(lata, "lata")
        alert()
        self.assertEqual(self.alerts(chitra), [])  # + account, still no grant

        ga.grant_student_access(student_guardian=link, actor=self.admin)
        alert()
        [skipped] = self.alerts(chitra)  # + grant, no opt-in
        self.assertEqual(skipped.status, Notification.Status.SKIPPED_NO_CONSENT)

        dev, alert = self.absent_today("Dev")
        mala = Guardian.objects.create(full_name="Mala", phone="9876500002")
        dev_link = self.relate(dev, mala)
        self.open_account(mala, "mala")
        ga.grant_student_access(student_guardian=dev_link, actor=self.admin)
        self.consent(mala)  # + opt-in
        alert()
        [prepared] = self.alerts(dev)
        self.assertEqual(prepared.status, Notification.Status.PREPARED)
        self.assertEqual(prepared.guardian, mala)


class GuardianlessPublicationTests(AlertFixture, TestCase):
    def test_a_guardianless_students_published_results_reach_no_one(self):
        chitra, chitra_e = self.make_student("Chitra")
        ut2 = self.make_assessment(name="UT2", on=date(2026, 8, 1))
        for enrollment in (self.asha_e, chitra_e):
            self.mark(ut2, enrollment, "9")
        self.force_finalize(ut2)
        Notification.objects.all().delete()

        created = self.publish()

        published = {p.student: p for p in created}
        self.assertIn(chitra, published)  # the Term is published; she simply has no audience
        self.assertEqual(Notification.objects.filter(student=chitra).count(), 0)
        self.assertEqual({p.student for p in self.cards()}, {self.asha})
        url = reverse("portal:report-card",
                      args=[self.asha_grant.public_id, published[chitra].public_id])
        self.assertEqual(self.portal.get(url).status_code, 404)


# --- Permissions after migrations 0070-0073 ----------------------------------

ADMIN_PERMISSIONS = [
    "core.view_assessmentteacherassignment",
    "core.add_assessmentteacherassignment",
    "core.change_assessmentteacherassignment",
    "core.delete_assessmentteacherassignment",
    "core.run_import",
    "core.view_importbatch",
    "core.add_studentguardian",
    "core.change_studentguardian",
]


class RepairedWorkflowPermissionTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        self.student, self.enrollment = self.make_student("Asha")
        self.assignment = self.assign(self.rao, self.maths, self.six_a)
        self.admin_client = self.client_class()
        self.admin_client.login(username="admin", password="pass-12345")
        self.teacher_client = self.client_class()
        self.teacher_client.login(username="rao", password="pass-12345")
        self.routes = [
            reverse("core:academic-year-teacher-assignments", args=[self.year.pk]),
            reverse("core:teacher-assignment-create", args=[self.year.pk]),
            reverse("core:teacher-assignment-end", args=[self.assignment.pk]),
            reverse("core:import-list"),
            reverse("core:import-upload"),
            reverse("core:student-guardian-add", args=[self.student.pk]),
        ]

    def test_administrators_hold_the_critical_permissions_and_teachers_do_not(self):
        for codename in ADMIN_PERMISSIONS:
            with self.subTest(codename=codename):
                self.assertTrue(self.admin.has_perm(codename))
                self.assertFalse(self.rao.has_perm(codename))
        self.assertFalse(
            self.teachers.permissions.filter(
                codename__in=[c.split(".")[1] for c in ADMIN_PERMISSIONS]
            ).exists(),
            TEACHERS_GROUP_NAME,
        )

    def test_representative_routes_open_for_administrators_and_close_for_teachers(self):
        for url in self.routes:
            with self.subTest(url=url):
                self.assertEqual(self.admin_client.get(url).status_code, 200)
                self.assertEqual(self.teacher_client.get(url).status_code, 403)

    def test_teachers_cannot_post_the_administrator_actions(self):
        end = reverse("core:teacher-assignment-end", args=[self.assignment.pk])
        remove = reverse("core:teacher-assignment-delete", args=[self.assignment.pk])
        self.assertEqual(
            self.teacher_client.post(end, {"end_date": "2026-09-30"}).status_code, 403
        )
        self.assertEqual(self.teacher_client.post(remove).status_code, 403)
        self.assignment.refresh_from_db()
        self.assertIsNone(self.assignment.end_date)
