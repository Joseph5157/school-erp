"""UI-D1-2B: class teacher mapping and assignment overview adopt the shared panel; data and access unchanged."""

import re
from datetime import date
from unittest import mock

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from core.models import (
    AcademicSubjectOffering,
    AcademicSubjectOfferingSection,
    AssessmentTeacherAssignment,
    Section,
    SectionClassTeacher,
)
from core.tests.phase4_fixtures import Phase4Fixture

TODAY = date(2026, 10, 10)
today_patch = mock.patch("core.models.business_today", new=lambda: TODAY)
view_today_patch = mock.patch("core.views.business_today", new=lambda: TODAY)

LONG_NAME = ("Venkataraghavan Subramaniam", "Ramachandran-Krishnamurthy Iyengar")


class D12BFixture(Phase4Fixture):
    def setUp(self):
        self.build_phase4()
        self.client.login(username="admin", password="pass-12345")
        self.long = self.make_user(
            "longname", self.teachers, first_name=LONG_NAME[0], last_name=LONG_NAME[1])
        assign = SectionClassTeacher.assign
        self.past = assign(teacher=self.rao, academic_year=self.year, section=self.six_a, start_date=date(2026, 6, 1))
        self.current = assign(teacher=self.iyer, academic_year=self.year, section=self.six_a, start_date=date(2026, 9, 1))
        self.planned = assign(teacher=self.long, academic_year=self.year, section=self.six_a, start_date=date(2026, 11, 1))
        self.ct_url = reverse("core:academic-year-class-teachers", args=[self.year.pk])
        self.ov_url = reverse("core:academic-year-assignments", args=[self.year.pk])

    def login_with(self, username, *codenames):
        user = self.make_user(username)
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        client = self.client_class()
        client.login(username=username, password="pass-12345")
        return client

    def wipe_sections(self):
        # Raw deletes: the models rightly refuse to delete assignments that have taken effect.
        AssessmentTeacherAssignment.objects.all()._raw_delete("default")
        SectionClassTeacher.objects.all()._raw_delete("default")
        AcademicSubjectOfferingSection.objects.all()._raw_delete("default")
        AcademicSubjectOffering.objects.all()._raw_delete("default")
        Section.objects.all().delete()

    def history_cell(self, content, index=0):
        return content.split('class="erp-assignment-history-cell"')[index + 1].split("</td>")[0]


@today_patch
@view_today_patch
class ClassTeacherMappingTests(D12BFixture, TestCase):
    def test_page_uses_header_panel_and_labelled_scroll_region(self):
        content = self.client.get(self.ct_url).content.decode()
        self.assertIn('class="erp-page-header"', content)
        self.assertEqual(content.count("<h1"), 1)
        self.assertIn("School setup", content)
        self.assertIn('class="erp-panel"', content)
        self.assertIn('role="region" aria-label="Class teachers" tabindex="0"', content)
        self.assertEqual(content.count('<th scope="col">'), 5)
        self.assertIn('<span class="visually-hidden">Actions</span>', content)

    def test_every_history_entry_is_kept_in_order_with_dates(self):
        cell = self.history_cell(self.client.get(self.ct_url).content.decode())
        self.assertEqual(cell.count('<li class="erp-assignment-entry">'), 3)
        names = re.findall(r'class="erp-assignment-teacher">([^<]+)<', cell)
        self.assertEqual(names, ["rao", "iyer", " ".join(LONG_NAME)])
        self.assertLess(cell.index("1 Jun 2026"), cell.index("1 Sep 2026"))
        self.assertLess(cell.index("1 Sep 2026"), cell.index("1 Nov 2026"))
        self.assertIn('<span class="text-nowrap">open</span>', cell)
        self.assertIn('<span class="text-nowrap">31 Aug 2026</span>', cell)
        self.assertNotIn("badge", cell)  # no invented statuses

    def test_administrator_actions_follow_existing_conditions(self):
        content = self.client.get(self.ct_url).content.decode()
        cell = self.history_cell(content)
        for row in (self.past, self.current, self.planned):
            self.assertIn(reverse("core:class-teacher-end", args=[row.pk]), cell)
        delete = lambda row: reverse("core:class-teacher-delete", args=[row.pk])
        self.assertNotIn(delete(self.past), cell)
        self.assertNotIn(delete(self.current), cell)
        self.assertIn(f'<form method="post" action="{delete(self.planned)}"', cell)
        self.assertEqual(cell.count("csrfmiddlewaretoken"), 1)
        assign_url = reverse("core:class-teacher-assign", args=[self.year.pk])
        self.assertIn(f"{assign_url}?section={self.six_a.pk}", content)
        self.assertIn("Replace", content)
        self.assertIn("Assign", content)

    def test_view_only_user_sees_history_but_no_actions(self):
        client = self.login_with("viewer", "view_sectionclassteacher", "view_academicyear", "view_section")
        content = client.get(self.ct_url).content.decode()
        self.assertEqual(self.history_cell(content).count('<li class="erp-assignment-entry">'), 3)
        for text in ("erp-assignment-actions", "Replace", "Delete planned", "btn-outline-primary",
                     reverse("core:class-teacher-end", args=[self.past.pk])):
            self.assertNotIn(text, content)

    def test_change_only_user_gets_end_but_not_delete_or_assign(self):
        client = self.login_with("changer", "view_sectionclassteacher", "change_sectionclassteacher")
        content = client.get(self.ct_url).content.decode()
        self.assertIn(reverse("core:class-teacher-end", args=[self.planned.pk]), content)
        self.assertNotIn("Delete planned", content)
        self.assertNotIn("btn-outline-primary", content)

    def test_current_year_note_and_empty_state(self):
        self.assertIn('"Current" means effective today', self.client.get(self.ct_url).content.decode())
        self.wipe_sections()
        self.assertIn("No Sections yet.", self.client.get(self.ct_url).content.decode())


@today_patch
@view_today_patch
class AssignmentOverviewTests(D12BFixture, TestCase):
    def setUp(self):
        super().setUp()
        AssessmentTeacherAssignment.assign(
            teacher=self.rao, offering=self.maths, section=self.six_a, start_date=date(2026, 6, 1))
        self.rao.is_active = False
        self.rao.save()

    def test_header_two_labelled_tables_and_one_h1(self):
        content = self.client.get(self.ov_url).content.decode()
        self.assertEqual(content.count("<h1"), 1)
        self.assertIn('class="erp-page-header"', content)
        self.assertEqual(content.count('class="erp-panel"'), 2)
        self.assertIn('aria-labelledby="overview-class-teachers"', content)
        self.assertIn('aria-labelledby="overview-subject-teachers"', content)
        self.assertEqual(content.count("<h2"), 2)

    def test_counts_date_and_warning_messages_come_from_the_view(self):
        response = self.client.get(self.ov_url)
        content = response.content.decode()
        self.assertIn("10 Oct 2026", content)
        self.assertIn(f"Gaps: {response.context['class_gaps']} Section(s)", content)
        self.assertIn(f"{response.context['subject_gaps']} Subject/Section(s)", content)
        self.assertIn(f"inactive or non-teacher logins: {response.context['inactive']}.", content)
        self.assertIn("No class teacher", content)
        self.assertIn("No teacher", content)
        self.assertIn("Login inactive or not a teacher &mdash; reassign", content)
        self.assertGreaterEqual(content.count('class="table-warning"'), 2)

    def test_administrator_links_and_targets(self):
        content = self.client.get(self.ov_url).content.decode()
        self.assertIn(reverse("core:assignment-copy", args=[self.year.pk]), content)
        self.assertIn(reverse("core:academic-year-class-teachers", args=[self.year.pk]), content)
        self.assertIn(reverse("core:academic-year-teacher-assignments", args=[self.year.pk]), content)
        self.assertIn(reverse("core:teacher-load", args=[self.iyer.pk]), content)

    def test_copy_needs_both_add_permissions_and_subject_link_needs_view(self):
        copy_url = reverse("core:assignment-copy", args=[self.year.pk])
        subject_url = reverse("core:academic-year-teacher-assignments", args=[self.year.pk])
        only_class = self.login_with("only-class", "view_sectionclassteacher", "add_sectionclassteacher")
        content = only_class.get(self.ov_url).content.decode()
        self.assertNotIn(copy_url, content)
        self.assertNotIn(subject_url, content)
        both = self.login_with("both-add", "view_sectionclassteacher", "add_sectionclassteacher",
                               "add_assessmentteacherassignment")
        content = both.get(self.ov_url).content.decode()
        self.assertIn(copy_url, content)
        self.assertNotIn(subject_url, content)

    def test_empty_class_rows_state(self):
        self.wipe_sections()
        self.assertIn("No Sections yet.", self.client.get(self.ov_url).content.decode())
