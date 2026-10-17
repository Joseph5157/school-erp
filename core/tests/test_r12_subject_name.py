"""R12: Subject name captured at assessment finalization (ADR 0019)."""

from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from core import assessment_reports, publication
from core.models import Assessment, ResultStatus, StudentResult, TermPublication
from core.tests.phase4_fixtures import Phase4Fixture
from core.tests.test_phase4_reports import ReportFixture
from core.tests.test_phase6_publication import PublicationFixture

TODAY = date(2026, 10, 10)
NEW_NAME = "Algebra Plus"

# Scheme 1 fingerprint of the fixed entry below, computed with the pre-R12 code.
# Existing PUBLISHED versions carry such hashes, so they must never change.
SCHEME_1_ENTRY = {
    "result_id": 7, "subject_label": "Mathematics", "assessment_label": "UT1",
    "assessment_date": date(2026, 7, 15), "maximum_marks": Decimal("20.00"),
    "pass_mark": None, "status": "MARKED", "score": Decimal("15.00"),
    "percentage": Decimal("75.00"), "grade_label": "B", "pass_fail_label": "Pass",
}
SCHEME_1_REMARK = {"id": 3, "text": "Steady progress."}
SCHEME_1_GOLDEN = "2c9061399001136e19f4cb68cf035692fec2d315ee0b0d261691580b575ee898"


class FingerprintSchemeTests(SimpleTestCase):
    def test_scheme_1_hash_is_unchanged(self):
        self.assertEqual(
            publication.fingerprint([SCHEME_1_ENTRY], SCHEME_1_REMARK, scheme=1), SCHEME_1_GOLDEN
        )

    def test_scheme_2_is_a_different_scheme_of_the_same_content(self):
        self.assertEqual(publication.FINGERPRINT_SCHEME, 2)
        two = publication.fingerprint([SCHEME_1_ENTRY], SCHEME_1_REMARK)
        self.assertNotEqual(two, SCHEME_1_GOLDEN)

    def test_released_label_is_part_of_the_fingerprint(self):
        renamed = {**SCHEME_1_ENTRY, "subject_label": NEW_NAME}
        for scheme in (1, 2):
            with self.subTest(scheme=scheme):
                self.assertNotEqual(
                    publication.fingerprint([SCHEME_1_ENTRY], None, scheme=scheme),
                    publication.fingerprint([renamed], None, scheme=scheme),
                )


@mock.patch("core.models.business_today", new=lambda: TODAY)
class FinalizedLabelTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        self.ravi, self.ravi_a = self.make_student("Ravi Rao")
        self.assign(self.rao, self.maths, self.six_a)
        self.assessment = self.make_assessment(maximum="20")
        self.assessment.save_draft_result(
            enrollment=self.ravi_a, status=ResultStatus.MARKED, score="17", actor=self.rao
        )

    def rename(self):
        self.maths_subject.name = NEW_NAME
        self.maths_subject.save()

    def reload(self):
        return Assessment.objects.select_related("offering__subject").get(pk=self.assessment.pk)

    def test_draft_has_no_label_and_follows_the_live_name(self):
        self.assertEqual(self.reload().subject_label, "")
        self.assertEqual(self.reload().subject_display, "Mathematics")
        self.rename()
        self.assertEqual(self.reload().subject_display, NEW_NAME)

    def test_finalize_captures_the_name(self):
        self.assessment.finalize(actor=self.admin)
        self.assertEqual(self.reload().subject_label, "Mathematics")
        self.assertEqual(self.reload().subject_display, "Mathematics")

    def test_rename_after_finalize_keeps_the_captured_name(self):
        self.assessment.finalize(actor=self.admin)
        self.rename()
        finalized = self.reload()
        self.assertEqual(finalized.subject_label, "Mathematics")
        self.assertEqual(finalized.subject_display, "Mathematics")
        self.assertEqual(finalized.offering.subject.name, NEW_NAME)

    def test_new_drafts_follow_the_rename_and_finalize_with_the_new_name(self):
        self.assessment.finalize(actor=self.admin)
        self.rename()
        later = self.make_assessment(name="Unit Test 2", on=date(2026, 8, 1))
        self.assertEqual(Assessment.objects.get(pk=later.pk).subject_display, NEW_NAME)
        later.save_draft_result(
            enrollment=self.ravi_a, status=ResultStatus.ABSENT, actor=self.rao
        )
        later.finalize(actor=self.admin)
        self.assertEqual(self.reload().subject_display, "Mathematics")
        self.assertEqual(Assessment.objects.get(pk=later.pk).subject_label, NEW_NAME)

    def test_correction_does_not_touch_the_captured_name(self):
        self.assessment.finalize(actor=self.admin)
        self.rename()
        result = StudentResult.objects.get(assessment=self.assessment)
        result.correct(new_status=ResultStatus.MARKED, new_score="18", actor=self.admin,
                       reason="Recount")
        self.assertEqual(self.reload().subject_label, "Mathematics")

    def test_captured_name_is_locked_once_finalized(self):
        self.assessment.finalize(actor=self.admin)
        finalized = self.reload()
        finalized.subject_label = "Something else"
        with self.assertRaises(ValidationError):
            finalized.full_clean()

    def test_database_ties_the_label_to_the_status(self):
        for fields in (
            {"status": Assessment.Status.FINALIZED, "finalized_by": self.admin,
             "finalized_at": timezone.now()},  # finalized without a label
            {"subject_label": "Mathematics"},  # label on a draft
        ):
            with self.subTest(fields=list(fields)), self.assertRaises(IntegrityError), (
                transaction.atomic()
            ):
                Assessment.objects.filter(pk=self.assessment.pk).update(**fields)

    def test_finalized_row_with_blank_label_falls_back_to_the_live_name(self):
        # Defensive only: the constraint forbids this once the migration has run.
        finalized = self.reload()
        finalized.status = Assessment.Status.FINALIZED
        finalized.subject_label = ""
        self.assertEqual(finalized.subject_display, "Mathematics")


class PublicationRenameTests(PublicationFixture, TestCase):
    def rename(self):
        self.maths_subject.name = NEW_NAME
        self.maths_subject.save()

    def publish_scheme_1(self):
        with mock.patch.object(publication, "FINGERPRINT_SCHEME", 1):
            return self.publish()

    def visible(self, pub):
        return publication.guardian_visible(pub), publication.guardian_visible_many([pub])[pub.pk]

    def test_new_publications_use_scheme_2_and_the_captured_label(self):
        asha = next(p for p in self.publish() if p.student == self.asha)
        self.assertEqual(asha.fingerprint_scheme, 2)
        self.assertEqual(asha.entries.get().subject_label, "Mathematics")

    def test_scheme_2_card_survives_a_rename(self):
        pub = next(p for p in self.publish() if p.student == self.asha)
        self.rename()
        self.assertEqual(self.visible(pub), (True, True))
        self.assertEqual([p.pk for p in self.cards()], [pub.pk])
        page = self.portal.get(reverse("portal:report-card",
                                       args=[self.asha_grant.public_id, pub.public_id]))
        self.assertContains(page, "Mathematics")
        self.assertNotContains(page, NEW_NAME)

    def test_scheme_1_card_survives_a_rename(self):
        pub = next(p for p in self.publish_scheme_1() if p.student == self.asha)
        self.assertEqual(pub.fingerprint_scheme, 1)
        self.assertEqual(self.visible(pub), (True, True))
        self.rename()
        self.assertEqual(self.visible(pub), (True, True))
        self.assertEqual([p.pk for p in self.cards()], [pub.pk])

    def test_real_result_change_still_hides_the_card_after_a_rename(self):
        scheme_1 = next(p for p in self.publish_scheme_1() if p.student == self.asha)
        self.rename()
        StudentResult.objects.filter(pk=self.result.pk).update(score=Decimal("16"))
        self.assertEqual(self.visible(scheme_1), (False, False))

    def test_real_result_change_hides_a_scheme_2_card(self):
        pub = next(p for p in self.publish() if p.student == self.asha)
        StudentResult.objects.filter(pk=self.result.pk).update(score=Decimal("16"))
        self.assertEqual(self.visible(pub), (False, False))

    def test_remark_change_still_hides_the_card_after_a_rename(self):
        pub = next(p for p in self.publish_scheme_1() if p.student == self.asha)
        self.rename()
        type(self.remark).objects.filter(pk=self.remark.pk).update(remark="Edited.")
        self.assertEqual(self.visible(pub), (False, False))

    def test_a_rename_does_not_ask_for_republication(self):
        self.publish_scheme_1()
        self.rename()
        self.assertEqual({row["action"] for row in self.plan()["rows"]}, {publication.SKIP_ALREADY})
        self.assertEqual(TermPublication.objects.count(), 2)

    def test_scheme_2_rename_does_not_ask_for_republication(self):
        self.publish()
        self.rename()
        self.assertEqual({row["action"] for row in self.plan()["rows"]}, {publication.SKIP_ALREADY})

    def test_preview_shows_the_captured_name_for_finalized_work(self):
        self.rename()
        rows = {row["student"]: row for row in self.plan()["rows"]}
        self.assertEqual(rows[self.asha]["content"]["entries"][0]["subject_label"], "Mathematics")

    def test_staff_preview_lists_pending_drafts_by_their_live_name(self):
        self.rename()
        self.make_assessment(name="UT2", on=date(2026, 8, 1))  # DRAFT
        self.client.login(username="admin", password="pass-12345")
        page = self.client.get(reverse("core:term-publication", args=[self.term1.pk]),
                               {"section": self.six_a.pk})
        self.assertContains(page, f"{NEW_NAME} UT2")


@mock.patch("core.models.business_today", new=lambda: TODAY)
class RenameMatrixTests(ReportFixture, TestCase):
    """After a rename, finalized work shows the captured name and drafts the new one."""

    def setUp(self):
        self.build_reports()
        self.maths_subject.name = NEW_NAME
        self.maths_subject.save()
        self.client.login(username="admin", password="pass-12345")

    def finalized_page(self, response):
        self.assertContains(response, "Mathematics")
        self.assertNotContains(response, NEW_NAME)

    def test_report_pages(self):
        self.finalized_page(self.client.get(reverse("core:report-result-sheet",
                                                    args=[self.ut1.pk])))
        self.finalized_page(self.client.get(reverse("core:report-student-results",
                                                    args=[self.ravi.pk])))
        self.finalized_page(self.client.get(reverse("core:report-term-report-card",
                                                    args=[self.ravi.pk, self.term1.pk])))

    def test_assessment_detail_and_list(self):
        self.finalized_page(self.client.get(reverse("core:assessment-detail", args=[self.ut1.pk])))
        page = self.client.get(reverse("core:academic-year-assessments", args=[self.year.pk]),
                               {"status": Assessment.Status.FINALIZED})
        self.finalized_page(page)

    def test_a_draft_follows_the_rename(self):
        self.assertContains(self.client.get(reverse("core:assessment-detail",
                                                    args=[self.draft.pk])), NEW_NAME)
        self.assertContains(self.client.get(reverse("core:report-result-sheet",
                                                    args=[self.draft.pk])), "not finalized yet")

    def test_student_history_orders_by_the_captured_name(self):
        history = assessment_reports.student_history(self.ravi)
        self.assertEqual([r.assessment.subject_display for r in history],
                         ["Mathematics", "Mathematics"])

    def test_report_card_groups_by_subject_and_captured_name(self):
        groups = assessment_reports.term_report_card(self.ravi, self.term1)["subjects"]
        self.assertEqual([group.name for group in groups], ["Mathematics"])
        self.assertEqual(next(iter(groups)).subject, self.maths_subject)

    def test_a_subject_renamed_mid_year_gets_one_group_per_captured_name(self):
        self.draft.finalize(actor=self.admin)  # Meera's draft, finalized after the rename
        card = assessment_reports.term_report_card(self.meera, self.term1)
        self.assertEqual([group.name for group in card["subjects"]], [NEW_NAME, "Mathematics"])
        self.assertEqual({group.subject for group in card["subjects"]}, {self.maths_subject})

    def test_teacher_views_use_the_captured_name(self):
        self.client.logout()
        self.client.login(username="rao", password="pass-12345")
        self.finalized_page(self.client.get(reverse("core:my-student-detail",
                                                    args=[self.ravi.pk])))


class MigrationTests(TransactionTestCase):
    BEFORE = [("core", "0073_assessmentteacherassignment_change_permission")]
    AFTER = [("core", "0076_assessment_subject_label_constraint")]

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def _migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def _seed(self, apps):
        Year, Grade = apps.get_model("core", "AcademicYear"), apps.get_model("core", "ClassGrade")
        Term, Section = apps.get_model("core", "AcademicTerm"), apps.get_model("core", "Section")
        Subject = apps.get_model("core", "Subject")
        Offering = apps.get_model("core", "AcademicSubjectOffering")
        User = apps.get_model("accounts", "User")
        year = Year.objects.create(name="Legacy", start_date=date(2026, 6, 1),
                                   end_date=date(2027, 3, 31))
        term = Term.objects.create(academic_year=year, name="T1", start_date=date(2026, 6, 1),
                                   end_date=date(2026, 9, 30), display_order=1)
        grade = Grade.objects.create(name="Legacy grade")
        section = Section.objects.create(class_grade=grade, name="A")
        subject = Subject.objects.create(name="Mathematics")  # the current, renamed name
        offering = Offering.objects.create(academic_year=year, class_grade=grade, subject=subject)
        admin = User.objects.create(username="legacy-admin")
        now = timezone.now()

        def assessment(name, finalized):
            extra = {"status": "FINALIZED", "finalized_by": admin, "finalized_at": now} \
                if finalized else {}
            return apps.get_model("core", "Assessment").objects.create(
                term=term, offering=offering, section=section, name=name,
                assessment_date=date(2026, 7, 15), maximum_marks=Decimal("20"), **extra)

        return {
            "year": year, "grade": grade, "section": section, "admin": admin, "term": term,
            "plain": assessment("No publication", True),
            "published": assessment("Published", True),
            "draft": assessment("Draft", False),
        }

    def _publish(self, apps, seeded, version, label, status, published_at):
        Student = apps.get_model("core", "Student")
        Applicant = apps.get_model("core", "Applicant")
        student = Student.objects.filter(full_name="Legacy Student").first()
        if student is None:
            student = Student.objects.create(
                full_name="Legacy Student",
                applicant=Applicant.objects.create(full_name="Legacy Student"))
            seeded["enrollment"] = apps.get_model("core", "AcademicEnrollment").objects.create(
                student=student, academic_year=seeded["year"], class_grade=seeded["grade"],
                section=seeded["section"], start_date=date(2026, 6, 1))
            seeded["result"] = apps.get_model("core", "StudentResult").objects.create(
                assessment=seeded["published"], academic_enrollment=seeded["enrollment"],
                status="ABSENT", entered_by=seeded["admin"])
        pub = apps.get_model("core", "TermPublication").objects.create(
            student=student, term=seeded["term"], placement=seeded["enrollment"],
            version=version, status=status, term_label="T1", academic_year_label="Legacy",
            class_grade_label="Legacy grade", section_label="A", fingerprint="x" * 64,
            published_by=seeded["admin"], published_at=published_at)
        apps.get_model("core", "TermPublicationEntry").objects.create(
            publication=pub, result=seeded["result"], display_order=0, subject_label=label,
            assessment_label="Published", assessment_date=date(2026, 7, 15),
            maximum_marks=Decimal("20"), status="ABSENT")

    def test_backfill_uses_the_live_name_when_nothing_was_published(self):
        apps = self._migrate(self.BEFORE)
        seeded = self._seed(apps)
        apps = self._migrate(self.AFTER)
        Assessment = apps.get_model("core", "Assessment")
        self.assertEqual(Assessment.objects.get(pk=seeded["plain"].pk).subject_label,
                         "Mathematics")
        self.assertEqual(Assessment.objects.get(pk=seeded["draft"].pk).subject_label, "")

    def test_backfill_recovers_the_earliest_published_label_deterministically(self):
        if connection.vendor == "sqlite":
            self.skipTest("Publication history triggers block the test flush on SQLite.")
        apps = self._migrate(self.BEFORE)
        seeded = self._seed(apps)
        early, late = timezone.now() - timedelta(days=9), timezone.now()
        # Two different released labels: the earliest wins, whatever the insert order.
        self._publish(apps, seeded, 2, "Maths (late)", "PUBLISHED", late)
        self._publish(apps, seeded, 1, "Maths (early)", "SUPERSEDED", early)
        apps = self._migrate(self.AFTER)
        Assessment = apps.get_model("core", "Assessment")
        self.assertEqual(Assessment.objects.get(pk=seeded["published"].pk).subject_label,
                         "Maths (early)")
        self.assertEqual(Assessment.objects.get(pk=seeded["plain"].pk).subject_label,
                         "Mathematics")

    def test_constraint_is_in_force_after_the_migration(self):
        apps = self._migrate(self.BEFORE)
        seeded = self._seed(apps)
        apps = self._migrate(self.AFTER)
        Assessment = apps.get_model("core", "Assessment")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Assessment.objects.filter(pk=seeded["plain"].pk).update(subject_label="")
