"""Option A1: NOT_TAKEN and DRAFT rows on Missing attendance say who acts and offer the next step.

Spec: docs/competitive-research/OPTION_A_IMPLEMENTATION_SPEC.md, section 4. Rules are checked in
order: archived section, overlapping academic years, no class teacher, teacher cannot take
attendance, past day, otherwise the class teacher. No user gains a power: every link is gated by
the permission of the page it opens, and "Take register" never appears on archived or
overlapping-year rows.

All data here is synthetic and local.
"""

import re
from datetime import date
from unittest import mock

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core import attendance_actions, home_today, reports
from core.models import (
    AcademicYear,
    Applicant,
    AttendanceRegister,
    AttendanceStatus,
    ClassGrade,
    Section,
    SectionClassTeacher,
    Student,
)
from core.tests.phase4_fixtures import Phase4Fixture

TODAY = date(2026, 10, 12)  # a Monday inside the 2026-27 year
FRIDAY = date(2026, 10, 9)  # the previous school day

Problem = attendance_actions.Problem
Owner = attendance_actions.Owner


def _patch_today(test):
    for target in ("core.views.business_today", "core.models.business_today",
                   "core.reports.business_today"):
        patcher = mock.patch(target, new=lambda: TODAY)
        patcher.start()
        test.addCleanup(patcher.stop)


def _archive(model, obj, actor):
    model.objects.filter(pk=obj.pk).update(archived_at=timezone.now(), archived_by=actor)


class A1Fixture(Phase4Fixture):
    """Grade 6 A has class teacher Rao and one student; Grade 6 B has a student and no class
    teacher."""

    def setUp(self):
        self.build_phase4()
        _patch_today(self)
        self.student_a, self.enrollment_a = self.make_student("Asha")
        self.student_b, self.enrollment_b = self.make_student("Bala", section=self.six_b)
        self.duty_a = SectionClassTeacher.assign(
            teacher=self.rao, academic_year=self.year, section=self.six_a,
            start_date=date(2026, 6, 1),
        )

    def rows(self, start=TODAY, end=TODAY, section=None, academic_year=None):
        return attendance_actions.resolve_missing(
            reports.missing_attendance(start, end, section=section, academic_year=academic_year),
            TODAY,
        )

    def row(self, section, on=TODAY, year=None):
        matches = [
            r for r in self.rows(on, on, section=section)
            if year is None or r["academic_year_id"] == year.pk
        ]
        self.assertEqual(len(matches), 1, matches)
        return matches[0]

    def make_year2(self):
        """A second academic year overlapping 2026-27, with its own Grade 6 A cohort."""
        self.year2 = AcademicYear.objects.create(
            name="2026-27 overlapping session", start_date=date(2026, 8, 1),
            end_date=date(2027, 5, 31),
        )
        student = Student.objects.create(
            applicant=Applicant.objects.create(admission_status="ACCEPTED", full_name="Bina Y2"),
            full_name="Bina Y2",
        )
        student.enroll(
            academic_year=self.year2, class_grade=self.grade6, section=self.six_a,
            start_date=date(2026, 8, 1),
        )
        return self.year2

    def take(self, on, *, submit=True, year=None, section=None):
        register = AttendanceRegister(
            academic_year=year or self.year, class_grade=self.grade6,
            section=section or self.six_a, date=on,
        )
        register.full_clean()
        register.save()
        for enrollment in register.eligible_enrollments():
            register.capture(enrollment=enrollment, status=AttendanceStatus.PRESENT)
        if submit:
            register.submit(actor=self.admin)
        return register

    def perm_user(self, username, *perms):
        user = self.make_user(username)
        for perm in perms:
            app_label, codename = perm.split(".")
            user.user_permissions.add(
                Permission.objects.get(content_type__app_label=app_label, codename=codename)
            )
        return user


class ResolverRuleTests(A1Fixture, TestCase):
    def test_today_with_a_valid_class_teacher_is_the_teachers(self):
        row = self.row(self.six_a)
        self.assertEqual(row["owner"], Owner.TEACHER)
        self.assertEqual(row["teacher"], self.rao)
        self.assertIsNone(row["problem"])
        self.assertTrue(row["can_take"])

    def test_a_past_day_is_the_offices_and_keeps_the_teacher_as_context(self):
        row = self.row(self.six_a, on=FRIDAY)
        self.assertEqual(row["owner"], Owner.OFFICE)
        self.assertEqual(row["teacher"], self.rao)
        self.assertIsNone(row["problem"])
        self.assertTrue(row["can_take"])

    def test_no_assignment_is_a_problem_for_the_office(self):
        row = self.row(self.six_b)
        self.assertEqual(row["problem"], Problem.NO_CLASS_TEACHER)
        self.assertEqual(row["owner"], Owner.OFFICE)
        self.assertIsNone(row["teacher"])
        self.assertTrue(row["can_take"])

    def test_an_assignment_that_ended_leaves_today_without_a_class_teacher(self):
        self.duty_a.end(FRIDAY)
        self.assertEqual(self.row(self.six_a)["problem"], Problem.NO_CLASS_TEACHER)
        friday = self.row(self.six_a, on=FRIDAY)
        self.assertIsNone(friday["problem"])
        self.assertEqual(friday["teacher"], self.rao)

    def test_an_assignment_that_starts_tomorrow_does_not_count_today(self):
        SectionClassTeacher.assign(
            teacher=self.iyer, academic_year=self.year, section=self.six_b,
            start_date=date(2026, 10, 13),
        )
        self.assertEqual(self.row(self.six_b)["problem"], Problem.NO_CLASS_TEACHER)

    def test_an_inactive_teacher_cannot_take_attendance(self):
        self.rao.is_active = False
        self.rao.save(update_fields=["is_active"])
        row = self.row(self.six_a)
        self.assertEqual(row["problem"], Problem.TEACHER_CANNOT_TAKE)
        self.assertEqual(row["owner"], Owner.OFFICE)
        self.assertEqual(row["teacher"], self.rao)
        self.assertTrue(row["can_take"])

    def test_a_teacher_removed_from_the_teachers_group_cannot_take_attendance(self):
        self.rao.groups.remove(self.teachers)
        self.assertEqual(self.row(self.six_a)["problem"], Problem.TEACHER_CANNOT_TAKE)

    def test_an_archived_section_offers_no_register(self):
        _archive(Section, self.six_a, self.admin)
        row = self.row(self.six_a)
        self.assertEqual(row["problem"], Problem.ARCHIVED_SECTION)
        self.assertEqual(row["owner"], Owner.OFFICE)
        self.assertFalse(row["can_take"])
        self.assertEqual(row["review_years"], [])

    def test_an_archived_class_offers_no_register(self):
        _archive(ClassGrade, self.grade6, self.admin)
        row = self.row(self.six_b)
        self.assertEqual(row["problem"], Problem.ARCHIVED_SECTION)
        self.assertFalse(row["can_take"])

    def test_a_draft_register_gets_the_same_resolution(self):
        self.take(TODAY, submit=False)
        row = self.row(self.six_a)
        self.assertEqual(row["state"], AttendanceRegister.AttendanceState.DRAFT)
        self.assertEqual(row["owner"], Owner.TEACHER)
        self.assertEqual(row["teacher"], self.rao)

    def test_review_links_point_at_the_rows_own_year(self):
        row = self.row(self.six_b)
        self.assertEqual([year["id"] for year in row["review_years"]], [self.year.pk])

    def test_take_url_fills_in_year_class_section_and_date(self):
        url = self.row(self.six_a)["take_url"]
        self.assertTrue(url.startswith(reverse("core:attendance-register-create") + "?"))
        for part in (f"academic_year={self.year.pk}", f"class_grade={self.grade6.pk}",
                     f"section={self.six_a.pk}", "date=2026-10-12"):
            self.assertIn(part, url)


class OverlappingYearTests(A1Fixture, TestCase):
    def setUp(self):
        super().setUp()
        self.make_year2()

    def test_a_section_expected_in_two_years_today_offers_no_register(self):
        rows = self.rows(section=self.six_a)
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row["problem"], Problem.OVERLAPPING_YEARS)
            self.assertEqual(row["owner"], Owner.OFFICE)
            self.assertFalse(row["can_take"])
            self.assertEqual(row["expected_academic_year_ids"],
                             tuple(sorted([self.year.pk, self.year2.pk])))

    def test_the_overlap_is_a_problem_on_past_days_too(self):
        for row in self.rows(FRIDAY, FRIDAY, section=self.six_a):
            self.assertEqual(row["problem"], Problem.OVERLAPPING_YEARS)
            self.assertFalse(row["can_take"])

    def test_review_links_name_each_expected_year(self):
        row = self.rows(section=self.six_a)[0]
        self.assertEqual(
            sorted((year["id"], year["name"]) for year in row["review_years"]),
            sorted([(self.year.pk, self.year.name), (self.year2.pk, self.year2.name)]),
        )

    def test_a_submitted_register_of_one_year_does_not_satisfy_the_other(self):
        self.take(TODAY, year=self.year)
        rows = reports.missing_attendance(TODAY, TODAY, section=self.six_a)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["academic_year_id"], self.year2.pk)
        self.assertIsNone(rows[0]["register"])
        self.assertEqual(rows[0]["expected_academic_year_ids"],
                         tuple(sorted([self.year.pk, self.year2.pk])))
        resolved = attendance_actions.resolve_missing(rows, TODAY)
        self.assertEqual(resolved[0]["problem"], Problem.OVERLAPPING_YEARS)

    def test_the_year_filter_keeps_both_expected_years_on_the_row(self):
        rows = reports.missing_attendance(TODAY, TODAY, section=self.six_a,
                                          academic_year=self.year2)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["expected_academic_year_ids"],
                         tuple(sorted([self.year.pk, self.year2.pk])))

    def test_archived_and_overlapping_is_archived(self):
        _archive(Section, self.six_a, self.admin)
        for row in self.rows(section=self.six_a):
            self.assertEqual(row["problem"], Problem.ARCHIVED_SECTION)


class AssignmentOnlyOverlapTests(A1Fixture, TestCase):
    def test_two_assignments_across_years_with_one_cohort_is_overlapping(self):
        year2 = AcademicYear.objects.create(
            name="Second session", start_date=date(2026, 8, 1), end_date=date(2027, 5, 31),
        )
        SectionClassTeacher.assign(
            teacher=self.iyer, academic_year=year2, section=self.six_a,
            start_date=date(2026, 8, 1),
        )
        row = self.row(self.six_a)
        self.assertEqual(row["expected_academic_year_ids"], (self.year.pk,))
        self.assertEqual(row["problem"], Problem.OVERLAPPING_YEARS)
        self.assertFalse(row["can_take"])
        self.assertEqual(sorted(year["id"] for year in row["review_years"]),
                         sorted([self.year.pk, year2.pk]))


class NormalDataTests(A1Fixture, TestCase):
    def test_single_year_rows_and_counts_are_unchanged_by_year_matching(self):
        self.take(TODAY)
        rows = reports.missing_attendance(TODAY, TODAY)
        self.assertEqual([r["section"] for r in rows], [self.six_b])
        self.assertEqual(rows[0]["expected_academic_year_ids"], (self.year.pk,))

    def test_query_count_does_not_grow_with_rows(self):
        one = reports.missing_attendance(TODAY, TODAY)
        many = reports.missing_attendance(date(2026, 9, 14), TODAY)
        self.assertGreater(len(many), len(one) * 5)
        with self.assertNumQueries(2):
            attendance_actions.resolve_missing(one, TODAY)
        with self.assertNumQueries(2):
            attendance_actions.resolve_missing(many, TODAY)

    def test_the_year_lookup_runs_once_only_when_a_row_overlaps(self):
        self.make_year2()
        rows = reports.missing_attendance(date(2026, 9, 14), TODAY)
        with self.assertNumQueries(3):
            attendance_actions.resolve_missing(rows, TODAY)


class ReportPageLinkTests(A1Fixture, TestCase):
    URL = reverse("core:report-missing-attendance")

    def page(self, user, on=TODAY):
        self.client.force_login(user)
        response = self.client.get(self.URL, {"start": on.isoformat(), "end": on.isoformat()})
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_view_only_sees_owner_and_problem_but_no_actions(self):
        html = self.page(self.perm_user("viewer", "core.view_attendanceregister"))
        self.assertIn("Waiting for rao", html)
        self.assertIn("No class teacher assigned", html)
        self.assertNotIn("Take register", html)
        self.assertNotIn("Review class teacher", html)
        self.assertNotIn(reverse("core:teacher-detail", args=[self.rao.pk]), html)

    def test_take_register_needs_add_permission(self):
        html = self.page(self.perm_user(
            "opener", "core.view_attendanceregister", "core.add_attendanceregister"))
        self.assertIn("Take register", html)
        self.assertIn(f"section={self.six_a.pk}", html)

    def test_teacher_link_needs_manage_teacher_accounts(self):
        html = self.page(self.perm_user(
            "manager", "core.view_attendanceregister", "accounts.manage_teacher_accounts"))
        self.assertIn(reverse("core:teacher-detail", args=[self.rao.pk]), html)

    def test_review_class_teacher_needs_only_the_view_permission(self):
        html = self.page(self.perm_user(
            "reviewer", "core.view_attendanceregister", "core.view_sectionclassteacher"))
        self.assertIn("Review class teacher", html)
        self.assertIn(reverse("core:academic-year-class-teachers", args=[self.year.pk]), html)

    def test_review_destination_keeps_its_own_assign_permission(self):
        reviewer = self.perm_user(
            "reviewer2", "core.view_attendanceregister", "core.view_sectionclassteacher")
        self.client.force_login(reviewer)
        list_url = reverse("core:academic-year-class-teachers", args=[self.year.pk])
        self.assertEqual(self.client.get(list_url).status_code, 200)
        assign_url = reverse("core:class-teacher-assign", args=[self.year.pk])
        self.assertEqual(self.client.get(assign_url).status_code, 403)

    def test_overlapping_and_archived_rows_never_offer_take_register(self):
        superuser = self.make_user("root", is_superuser=True, is_staff=True)
        self.make_year2()
        _archive(Section, self.six_b, self.admin)
        html = self.page(superuser)
        self.assertIn("Two academic years overlap", html)
        self.assertIn("This section is archived", html)
        self.assertNotIn("Take register", html)
        self.assertIn(self.year2.name, html)

    def test_a_past_day_names_the_office(self):
        html = self.page(self.perm_user("viewer2", "core.view_attendanceregister"), on=FRIDAY)
        self.assertIn("Past day: office to take", html)


class RegisterPrefillTests(A1Fixture, TestCase):
    URL = reverse("core:attendance-register-create")

    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)

    def get(self, **params):
        response = self.client.get(self.URL, params)
        self.assertEqual(response.status_code, 200)
        return response

    def test_valid_parameters_fill_the_form(self):
        response = self.get(academic_year=self.year.pk, class_grade=self.grade6.pk,
                            section=self.six_a.pk, date="2026-10-12")
        initial = response.context["form"].initial
        self.assertEqual(initial["academic_year"], self.year.pk)
        self.assertEqual(initial["class_grade"], self.grade6.pk)
        self.assertEqual(initial["section"], self.six_a.pk)
        self.assertEqual(initial["date"], TODAY)
        self.assertFalse(response.context["form"].is_bound)

    def test_invalid_values_are_ignored_without_errors(self):
        response = self.get(academic_year="abc", class_grade=999999, section="", date="12/10/26")
        form = response.context["form"]
        self.assertEqual(form.initial, {})
        self.assertFalse(form.errors)

    def test_an_archived_section_is_not_preselected(self):
        _archive(Section, self.six_a, self.admin)
        initial = self.get(section=self.six_a.pk, class_grade=self.grade6.pk).context["form"].initial
        self.assertNotIn("section", initial)
        self.assertEqual(initial["class_grade"], self.grade6.pk)

    def test_get_never_creates_a_register(self):
        self.get(academic_year=self.year.pk, class_grade=self.grade6.pk,
                 section=self.six_a.pk, date="2026-10-12")
        self.assertFalse(AttendanceRegister.objects.exists())

    def test_post_still_redirects_to_an_existing_register(self):
        existing = self.take(TODAY, submit=False)
        response = self.client.post(self.URL, {
            "academic_year": self.year.pk, "class_grade": self.grade6.pk,
            "section": self.six_a.pk, "date": "2026-10-12",
        })
        self.assertRedirects(
            response, reverse("core:attendance-register-detail", args=[existing.pk]),
            fetch_redirect_response=False,
        )


class ReviewFollowUpTests(A1Fixture, TestCase):
    """PR #277 review: Unicode digits, rendered DRAFT rows, dashboard counts, teacher links on
    TEACHER_CANNOT_TAKE, and deterministic order of overlapping-year rows."""

    URL = reverse("core:report-missing-attendance")

    def page(self, user, on=TODAY):
        self.client.force_login(user)
        response = self.client.get(self.URL, {"start": on.isoformat(), "end": on.isoformat()})
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def row_html(self, html, section_label):
        rows = [row for row in re.findall(r"<tr>(.*?)</tr>", html, re.S) if section_label in row]
        self.assertEqual(len(rows), 1, rows)
        return rows[0]

    def attendance_card_count(self):
        """Rows in the admin home Today tab's "Not taken yet" list, which replaced the old
        dashboard "Attendance today" card when the admin home merged."""
        return len(home_today.attendance_today(
            TODAY, include_rows=True, can_view_registers=True)["not_taken"])

    # 1. Unicode digits are ignored, not a 500.
    def test_unicode_digits_in_prefill_are_ignored(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("core:attendance-register-create"), {
            "section": "²", "class_grade": "٣", "academic_year": "¹",
        })
        self.assertEqual(response.status_code, 200)
        initial = response.context["form"].initial
        for name in ("section", "class_grade", "academic_year"):
            self.assertNotIn(name, initial)

    # 2. A rendered DRAFT row.
    def test_a_draft_row_offers_open_register_and_names_the_owner_but_not_take(self):
        self.take(TODAY, submit=False)
        html = self.page(self.perm_user(
            "drafter", "core.view_attendanceregister", "core.add_attendanceregister"))
        draft = self.row_html(html, "Grade 6 - A")
        self.assertIn("Draft", draft)
        self.assertIn("Open register", draft)
        self.assertIn("Waiting for rao", draft)
        self.assertNotIn("Take register", draft)

    def test_a_past_draft_row_names_the_office(self):
        self.take(FRIDAY, submit=False)
        html = self.page(self.perm_user("drafter2", "core.view_attendanceregister",
                                        "core.add_attendanceregister"), on=FRIDAY)
        draft = self.row_html(html, "Grade 6 - A")
        self.assertIn("Open register", draft)
        self.assertIn("Past day: office to take", draft)
        self.assertNotIn("Take register", draft)

    # 3. The "Attendance today" count (now the Today tab's "Not taken yet" list).
    def test_dashboard_count_is_unchanged_for_single_year_data(self):
        self.assertEqual(self.attendance_card_count(), 2)  # 6A and 6B not submitted
        self.take(TODAY)
        self.assertEqual(self.attendance_card_count(), 1)  # 6B only, as before year matching

    def test_dashboard_counts_the_overlapping_section_whose_other_year_is_missing(self):
        self.make_year2()
        self.take(TODAY, year=self.year)  # 6A submitted for 2026-27 only
        # Before year-aware matching this register hid the overlapping year's row and the card
        # said 1 (6B). Now 6A still has a missing row for the other year, flagged
        # OVERLAPPING_YEARS, so the card counts it, as the approved spec intends.
        self.assertEqual(self.attendance_card_count(), 2)
        six_a = [r for r in self.rows() if r["section"] == self.six_a]
        self.assertEqual([r["problem"] for r in six_a], [Problem.OVERLAPPING_YEARS])

    # 4. TEACHER_CANNOT_TAKE links the teacher only with manage_teacher_accounts.
    def test_teacher_who_cannot_take_is_linked_for_a_teacher_manager(self):
        self.rao.is_active = False
        self.rao.save(update_fields=["is_active"])
        html = self.page(self.perm_user(
            "manager2", "core.view_attendanceregister", "accounts.manage_teacher_accounts"))
        row = self.row_html(html, "Grade 6 - A")
        detail = reverse("core:teacher-detail", args=[self.rao.pk])
        self.assertIn(f'<a href="{detail}">rao</a> can\'t sign in as a teacher', row)
        self.client.force_login(self.perm_user("manager3", "accounts.manage_teacher_accounts"))
        self.assertEqual(self.client.get(detail).status_code, 200)

    def test_teacher_who_cannot_take_is_plain_text_without_the_permission(self):
        self.rao.is_active = False
        self.rao.save(update_fields=["is_active"])
        row = self.row_html(self.page(self.perm_user("viewer3", "core.view_attendanceregister")),
                            "Grade 6 - A")
        self.assertIn("rao can't sign in as a teacher", row)
        self.assertNotIn(reverse("core:teacher-detail", args=[self.rao.pk]), row)

    def test_teacher_outside_the_group_is_never_linked_to_a_page_that_would_404(self):
        self.rao.groups.remove(self.teachers)
        row = self.row_html(self.page(self.perm_user(
            "manager4", "core.view_attendanceregister", "accounts.manage_teacher_accounts")),
            "Grade 6 - A")
        self.assertIn("rao can't sign in as a teacher", row)
        self.assertNotIn(reverse("core:teacher-detail", args=[self.rao.pk]), row)

    # 5. Deterministic order of overlapping-year rows.
    def test_overlapping_year_rows_are_ordered_by_academic_year(self):
        self.make_year2()
        rows = reports.missing_attendance(TODAY, TODAY, section=self.six_a)
        self.assertEqual([r["academic_year_id"] for r in rows],
                         sorted([self.year.pk, self.year2.pk]))
