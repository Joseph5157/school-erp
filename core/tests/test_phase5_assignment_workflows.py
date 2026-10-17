"""Phase 5 Gate 7: assignment overview, teacher load, conservative copy (ADR 0011)."""

from datetime import date
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from core import assignments
from core.models import (
    AcademicSubjectOffering,
    AcademicYear,
    AssessmentTeacherAssignment,
    ClassGrade,
    Section,
    SectionClassTeacher,
    Subject,
)
from core.tests.phase4_fixtures import Phase4Fixture

TODAY = date(2026, 10, 12)


class AssignmentFixture(Phase4Fixture):
    def setUp(self):
        self.build_phase4()
        for patch in (mock.patch("core.views.business_today", new=lambda: TODAY),
                      mock.patch("core.models.business_today", new=lambda: TODAY)):
            patch.start()
            self.addCleanup(patch.stop)
        self.next_year = AcademicYear.objects.create(
            name="2027-28", start_date=date(2027, 6, 1), end_date=date(2028, 3, 31)
        )
        self.client.login(username="admin", password="pass-12345")

    def class_teacher(self, teacher, section, start=date(2026, 6, 1), year=None):
        return SectionClassTeacher.assign(teacher=teacher, academic_year=year or self.year,
                                          section=section, start_date=start)

    def offer(self, subject, year=None, grade=None, sections=None):
        offering = AcademicSubjectOffering.objects.create(
            academic_year=year or self.next_year, class_grade=grade or self.grade6,
            subject=subject,
        )
        if sections:
            offering.set_sections(sections)
        return offering


class OverviewTests(AssignmentFixture, TestCase):
    def test_gaps_and_inactive_holders_are_flagged(self):
        self.class_teacher(self.rao, self.six_a)
        self.assign(self.iyer, self.maths, self.six_a)
        self.iyer.is_active = False
        self.iyer.save()
        data = assignments.overview(self.year, TODAY)
        classes = {row["section"]: row for row in data["class_rows"]}
        self.assertFalse(classes[self.six_a]["gap"])
        self.assertTrue(classes[self.six_b]["gap"])
        slots = {(r["offering"].subject.name, r["section"].name): r for r in data["subject_rows"]}
        # Mathematics applies to all Sections; Sanskrit only to 6B.
        self.assertEqual(set(slots), {("Mathematics", "A"), ("Mathematics", "B"),
                                      ("Sanskrit", "B")})
        self.assertTrue(slots[("Mathematics", "A")]["inactive"])
        self.assertTrue(slots[("Mathematics", "B")]["gap"])
        self.assertEqual((data["class_gaps"], data["subject_gaps"], data["inactive"]), (1, 2, 1))

    def test_deactivation_never_changes_assignment_rows(self):
        row = self.class_teacher(self.rao, self.six_a)
        duty = self.assign(self.rao, self.maths, self.six_a)
        self.rao.groups.remove(self.teachers)
        self.rao.is_active = False
        self.rao.save()
        row.refresh_from_db()
        self.assertIsNone(row.end_date)
        self.assertTrue(AssessmentTeacherAssignment.objects.filter(pk=duty.pk).exists())
        page = self.client.get(reverse("core:academic-year-assignments", args=[self.year.pk]))
        self.assertContains(page, "Login inactive or not a teacher")

    def test_overview_page_and_teacher_load(self):
        self.class_teacher(self.rao, self.six_a)
        self.assign(self.rao, self.maths, self.six_b)
        page = self.client.get(reverse("core:academic-year-assignments", args=[self.year.pk]))
        self.assertContains(page, reverse("core:teacher-load", args=[self.rao.pk]))
        load = self.client.get(reverse("core:teacher-load", args=[self.rao.pk]))
        (year, rows), = load.context["years"]
        self.assertEqual(year, self.year)
        self.assertEqual(len(rows["class"]), 1)
        self.assertEqual(len(rows["subject"]), 1)
        self.assertContains(load, "Active teacher")

    def test_teacher_cannot_open_admin_pages(self):
        teacher = self.client_class()
        teacher.login(username="rao", password="pass-12345")
        for url in (reverse("core:academic-year-assignments", args=[self.year.pk]),
                    reverse("core:assignment-copy", args=[self.next_year.pk]),
                    reverse("core:teacher-load", args=[self.rao.pk])):
            with self.subTest(url=url):
                self.assertEqual(teacher.get(url).status_code, 403)


class CopyPlanTests(AssignmentFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.class_teacher(self.rao, self.six_a)
        self.next_maths = self.offer(self.maths_subject)
        self.assign(self.rao, self.maths, self.six_a)
        self.assign(self.iyer, self.maths, self.six_b)

    def plan(self):
        return assignments.plan_copy(self.year, self.next_year)

    def test_exact_matches_are_planned(self):
        plan = self.plan()
        kinds = sorted((c.kind, c.section_id, c.offering_id) for c in plan["copies"])
        self.assertEqual(kinds, [("class", self.six_a.pk, None),
                                 ("subject", self.six_a.pk, self.next_maths.pk),
                                 ("subject", self.six_b.pk, self.next_maths.pk)])

    def test_missing_subject_is_skipped(self):
        self.assign(self.iyer, self.sanskrit, self.six_b)
        reasons = {s.reason for s in self.plan()["skips"]}
        self.assertIn("This Subject is not offered for this Class/Grade in the target year.",
                      reasons)

    def test_section_not_taking_subject_is_skipped(self):
        self.next_maths.set_sections([self.six_a])
        skips = self.plan()["skips"]
        self.assertEqual([s.reason for s in skips],
                         ["The Section does not take this Subject in the target year."])

    def test_subject_is_matched_by_identity_not_name(self):
        lookalike = Subject.objects.create(name="Maths")
        self.next_maths.delete()
        self.offer(lookalike)
        self.assertEqual([c.kind for c in self.plan()["copies"]], ["class"])

    def test_inactive_or_non_teacher_is_skipped(self):
        self.iyer.groups.remove(self.teachers)
        skips = self.plan()["skips"]
        self.assertEqual([s.reason for s in skips],
                         ["Login is inactive or not in the Teachers group."])

    def test_only_class_teacher_at_year_end_is_copied(self):
        self.class_teacher(self.iyer, self.six_a, start=date(2027, 1, 1))
        plan = self.plan()
        class_copies = [c for c in plan["copies"] if c.kind == "class"]
        self.assertEqual([c.teacher_id for c in class_copies], [self.iyer.pk])
        self.assertIn("Not the class teacher at the end of the source year.",
                      {s.reason for s in plan["skips"]})

    def test_already_assigned_targets_are_skipped(self):
        self.class_teacher(self.iyer, self.six_a, start=date(2027, 6, 1), year=self.next_year)
        AssessmentTeacherAssignment.objects.create(teacher=self.iyer, offering=self.next_maths,
                                                   section=self.six_a,
                                                   start_date=self.next_year.start_date)
        reasons = [s.reason for s in self.plan()["skips"]]
        self.assertIn("This Section already has a class teacher in the target year.", reasons)
        self.assertIn("This Subject and Section already have a teacher in the target year.",
                      reasons)

    def test_same_year_is_refused(self):
        with self.assertRaises(ValidationError):
            assignments.plan_copy(self.year, self.year)

    def test_new_grade_sections_are_not_guessed(self):
        grade7 = ClassGrade.objects.create(name="Grade 7")
        Section.objects.create(class_grade=grade7, name="A")
        self.offer(self.maths_subject, grade=grade7)
        plan = self.plan()
        self.assertFalse(any(c.section_id not in (self.six_a.pk, self.six_b.pk)
                             for c in plan["copies"]))


class CopyApplyTests(AssignmentFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.class_teacher(self.rao, self.six_a)
        self.next_maths = self.offer(self.maths_subject)
        self.assign(self.iyer, self.maths, self.six_b)
        self.url = reverse("core:assignment-copy", args=[self.next_year.pk])

    def test_preview_writes_nothing(self):
        page = self.client.get(self.url)
        self.assertEqual(page.context["source"], self.year)
        self.assertEqual(len(page.context["plan"]["copies"]), 2)
        self.assertFalse(SectionClassTeacher.objects.filter(academic_year=self.next_year).exists())

    def test_confirm_creates_exactly_the_preview_and_is_idempotent(self):
        token = self.client.get(self.url).context["plan"]["token"]
        response = self.client.post(self.url, {"source": self.year.pk, "token": token})
        self.assertRedirects(response, reverse("core:academic-year-assignments",
                                               args=[self.next_year.pk]))
        row = SectionClassTeacher.objects.get(academic_year=self.next_year)
        self.assertEqual((row.teacher, row.section, row.start_date, row.end_date),
                         (self.rao, self.six_a, self.next_year.start_date, None))
        self.assertTrue(AssessmentTeacherAssignment.objects.filter(
            teacher=self.iyer, offering=self.next_maths, section=self.six_b).exists())
        # Second confirm with the old token: plan changed (now empty) -> nothing written.
        self.client.post(self.url, {"source": self.year.pk, "token": token})
        self.assertEqual(SectionClassTeacher.objects.filter(academic_year=self.next_year).count(),
                         1)
        replan = assignments.plan_copy(self.year, self.next_year)
        self.assertEqual(replan["copies"], [])

    def test_stale_preview_is_refused(self):
        token = self.client.get(self.url).context["plan"]["token"]
        self.iyer.is_active = False
        self.iyer.save()
        response = self.client.post(self.url, {"source": self.year.pk, "token": token},
                                    follow=True)
        self.assertContains(response, "changed since the preview")
        self.assertFalse(SectionClassTeacher.objects.filter(academic_year=self.next_year).exists())

    def test_source_choice_and_bad_source(self):
        page = self.client.get(self.url, {"source": "nonsense"})
        self.assertIsNone(page.context["plan"])
        page = self.client.get(self.url, {"source": self.next_year.pk})
        self.assertIsNone(page.context["plan"])

    def test_requires_both_add_permissions(self):
        from django.contrib.auth.models import Permission
        clerk = self.make_user("clerk")
        clerk.user_permissions.add(Permission.objects.get(codename="add_sectionclassteacher"))
        client = self.client_class()
        client.login(username="clerk", password="pass-12345")
        self.assertEqual(client.get(self.url).status_code, 403)
