"""TDB-4F: the whole office timetable flow end to end, plus hardening probes (ADR 0021)."""

import re
from datetime import date
from unittest import mock

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core import authorization
from core.models import (
    AcademicSubjectOffering,
    AssessmentTeacherAssignment,
    Subject,
    TimetablePeriod,
    TimetableSlot,
)
from core.tests.test_timetable_grid_ui import TODAY, GridFixture, pinned


def hrefs(response):
    return re.findall(r'href="([^"]+)"', response.content.decode())


@pinned()
class OfficeTimetableFlowTests(GridFixture, TestCase):
    """One administrator sets up periods, schedules, changes, ends, deletes and reviews."""

    def setUp(self):
        self.build_phase4()
        self.client.force_login(self.admin)
        self.science = AcademicSubjectOffering.objects.create(
            academic_year=self.year, class_grade=self.grade6,
            subject=Subject.objects.create(name="Science"),
        )

    def test_the_complete_workflow(self):
        c = self.client
        # Academic Year -> Periods
        index = c.get(reverse("core:timetable-index"))
        self.assertContains(index, reverse("core:timetable-periods", args=[self.year.pk]))
        periods_url = reverse("core:timetable-periods", args=[self.year.pk])
        for sequence, label in ((1, "P1"), (2, "P2")):
            c.post(reverse("core:timetable-period-create", args=[self.year.pk]),
                   {"sequence": sequence, "label": label})
        p1, p2 = TimetablePeriod.objects.order_by("sequence")
        self.assertEqual([p.label for p in c.get(periods_url).context["periods"]], ["P1", "P2"])

        # Section timetable: add Maths to 6A P1 Monday from today (assigned to Rao)
        self.assign_from(self.rao, self.maths, self.six_a, date(2026, 6, 1))
        grid = self.grid_url(self.six_a, on=TODAY)
        add = reverse("core:timetable-slot-create",
                      args=[self.year.pk, self.six_a.pk, p1.pk, 0]) + f"?date={TODAY}"
        self.assertRedirects(
            c.post(add, {"offering": self.maths.pk, "start_date": "2026-10-19", "end_date": ""}),
            grid)
        slot = TimetableSlot.objects.get()
        self.assertEqual(self.cell(c.get(grid), p1, 0)["teacher"], "rao")

        # Issues report: no clash, and nothing missing because Rao is assigned
        issues = reverse("core:timetable-issues", args=[self.year.pk]) + f"?date={TODAY}"
        report = c.get(issues)
        self.assertEqual(report.context["clashes"], [])
        self.assertEqual(report.context["missing"], [])

        # Change from 2 Nov to Science (unassigned): history kept, report shows the gap
        change = reverse("core:timetable-slot-change", args=[slot.pk]) + f"?date={TODAY}"
        self.assertRedirects(
            c.post(change, {"offering": self.science.pk, "effective_from": "2026-11-02",
                            "end_date": ""}), grid)
        slot.refresh_from_db()
        self.assertEqual((slot.offering, slot.end_date), (self.maths, date(2026, 11, 1)))
        replacement = TimetableSlot.objects.exclude(pk=slot.pk).get()
        self.assertEqual(c.get(self.grid_url(on=date(2026, 10, 30))).context["rows"][0]
                         ["cells"][0]["slot"].pk, slot.pk)
        self.assertEqual(c.get(self.grid_url(on=date(2026, 11, 2))).context["rows"][0]
                         ["cells"][0]["slot"].pk, replacement.pk)
        gap = c.get(reverse("core:timetable-issues", args=[self.year.pk]) + "?date=2026-11-03")
        self.assertEqual([r["subject"] for r in gap.context["missing"]], ["Science"])

        # End the replacement on 20 Nov (inclusive)
        end = reverse("core:timetable-slot-end", args=[replacement.pk]) + f"?date={TODAY}"
        self.assertRedirects(c.post(end, {"end_date": "2026-11-20"}), grid)
        replacement.refresh_from_db()
        self.assertEqual(replacement.end_date, date(2026, 11, 20))

        # A future slot can be deleted; the started ones cannot
        future = TimetableSlot.create(period=p2, weekday=1, section=self.six_a,
                                      offering=self.maths, start_date=date(2026, 12, 1))
        delete = reverse("core:timetable-slot-delete", args=[future.pk]) + f"?date={TODAY}"
        self.assertRedirects(c.post(delete, {}), grid)
        self.assertFalse(TimetableSlot.objects.filter(pk=future.pk).exists())
        c.post(reverse("core:timetable-slot-delete", args=[slot.pk]), {})
        self.assertTrue(TimetableSlot.objects.filter(pk=slot.pk).exists())  # started: end only

        # Period delete is refused while slots use it
        response = c.post(reverse("core:timetable-period-delete", args=[p1.pk]), follow=True)
        self.assertContains(response, "already used by timetable slots")
        self.assertTrue(TimetablePeriod.objects.filter(pk=p1.pk).exists())

    def test_started_history_is_never_rewritten_by_any_office_action(self):
        slot = self.make_slot_in_period()
        before = {f.name: getattr(slot, f.name) for f in TimetableSlot._meta.fields
                  if f.name not in ("end_date", "updated_at")}
        c = self.client
        c.post(reverse("core:timetable-slot-change", args=[slot.pk]),
               {"offering": self.science.pk, "effective_from": "2026-11-02", "end_date": ""})
        c.post(reverse("core:timetable-slot-change", args=[slot.pk]),
               {"offering": self.science.pk, "effective_from": "2026-10-01", "end_date": ""})
        c.post(reverse("core:timetable-slot-end", args=[slot.pk]), {"end_date": "2026-10-01"})
        c.post(reverse("core:timetable-slot-delete", args=[slot.pk]), {})
        slot.refresh_from_db()
        self.assertEqual({k: getattr(slot, k) for k in before}, before)
        self.assertEqual(slot.end_date, date(2026, 11, 1))  # only the allowed end

    def make_slot_in_period(self):
        p1 = TimetablePeriod.objects.create(academic_year=self.year, sequence=1, label="P1")
        self.p1 = p1
        return TimetableSlot.create(period=p1, weekday=0, section=self.six_a,
                                    offering=self.maths, start_date=date(2026, 6, 1))


@pinned()
class IntegrationHardeningTests(GridFixture, TestCase):
    def setUp(self):
        self.build_grid()
        self.assign_from(self.rao, self.maths, self.six_a, date(2026, 6, 1))
        self.started = self.make_slot(start_date=date(2026, 6, 1))
        self.future = self.make_slot(weekday=1, start_date=date(2026, 12, 1))
        self.ended = self.make_slot(period=self.p2, end_date=date(2026, 9, 30))

    # --- no raw 500s from expected validation failures --------------------------

    def test_forged_and_malformed_posts_never_cause_a_server_error(self):
        c = self.client
        bad_bodies = [
            {}, {"offering": "x"}, {"offering": "99999"}, {"offering": str(self.sanskrit.pk)},
            {"offering": str(self.maths.pk), "start_date": "garbage"},
            {"offering": str(self.maths.pk), "start_date": "2026-02-30"},
            {"offering": str(self.maths.pk), "start_date": "2026-10-19", "end_date": "nope"},
            {"offering": str(self.maths.pk), "start_date": "2999-01-01"},
            {"effective_from": "garbage"}, {"end_date": "garbage"},
            {"offering": str(self.maths.pk), "effective_from": "0001-01-01"},
            {"offering": str(self.maths.pk), "effective_from": "2026-11-02",
             "end_date": "2026-11-01"},
            {"end_date": "9999-12-31"}, {"end_date": "2026-10-19\x00"},
        ]
        urls = [
            reverse("core:timetable-slot-create",
                    args=[self.year.pk, self.six_a.pk, self.p1.pk, 3]),
            reverse("core:timetable-slot-change", args=[self.started.pk]),
            reverse("core:timetable-slot-change", args=[self.future.pk]),
            reverse("core:timetable-slot-change", args=[self.ended.pk]),
            reverse("core:timetable-slot-end", args=[self.started.pk]),
            reverse("core:timetable-slot-end", args=[self.ended.pk]),
            reverse("core:timetable-slot-end", args=[self.future.pk]),
        ]
        before = list(TimetableSlot.objects.order_by("pk").values())
        for url in urls:
            for body in bad_bodies:
                for suffix in ("", "?date=garbage", "?date=2026-10-19&date=junk"):
                    status = c.post(url + suffix, body).status_code
                    self.assertLess(status, 500, f"{url}{suffix} {body}")
        # only valid-looking bodies may have changed anything; nothing started was rewritten
        started = TimetableSlot.objects.get(pk=self.started.pk)
        self.assertEqual((started.offering, started.start_date, started.weekday),
                         (self.maths, date(2026, 6, 1), 0))
        self.assertEqual(TimetableSlot.objects.get(pk=self.ended.pk).end_date,
                         date(2026, 9, 30))
        self.assertGreaterEqual(len(before), 3)

    def test_odd_date_parameters_never_cause_a_server_error(self):
        for param in ("", "?date=", "?date=2026-02-30", "?date=%00", "?date=" + "9" * 300,
                      "?date=2026-10-19&date=junk", "?date=0001-01-01", "?date=2999-12-31"):
            for url in (self.grid_url(), reverse("core:timetable-issues", args=[self.year.pk])):
                self.assertEqual(self.client.get(url.split("?")[0] + param).status_code, 200,
                                 f"{url}{param}")

    def test_unknown_ids_are_404_not_500(self):
        for name, args in (
            ("timetable-slot-change", [999999]), ("timetable-slot-end", [999999]),
            ("timetable-slot-delete", [999999]),
            ("timetable-grid", [self.year.pk, 999999]),
            ("timetable-grid", [999999, self.six_a.pk]),
            ("timetable-sections", [999999]), ("timetable-issues", [999999]),
            ("timetable-slot-create", [self.year.pk, self.six_a.pk, 999999, 0]),
        ):
            self.assertEqual(self.client.get(reverse(f"core:{name}", args=args)).status_code,
                             404, name)

    def test_removing_a_section_that_has_slots_from_an_offering_is_a_form_error(self):
        self.sanskrit.set_sections([self.six_a, self.six_b])
        TimetableSlot.create(period=self.p1, weekday=3, section=self.six_a,
                             offering=self.sanskrit, start_date=date(2026, 6, 1))
        response = self.client.post(
            reverse("core:offering-update", args=[self.sanskrit.pk]),
            {"sections": [self.six_b.pk]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "timetable slot")
        self.assertTrue(self.sanskrit.applies_to(self.six_a))

    # --- breadcrumbs, navigation and date preservation ---------------------------

    def timetable_pages(self):
        year = self.year.pk
        return {
            "timetable-index": reverse("core:timetable-index"),
            "timetable-periods": reverse("core:timetable-periods", args=[year]),
            "timetable-period-create": reverse("core:timetable-period-create", args=[year]),
            "timetable-period-update": reverse("core:timetable-period-update",
                                               args=[self.p1.pk]),
            "timetable-period-delete": reverse("core:timetable-period-delete",
                                               args=[self.p1.pk]),
            "timetable-sections": reverse("core:timetable-sections", args=[year]),
            "timetable-grid": self.grid_url(),
            "timetable-slot-create": self.add_url(period=self.p2, weekday=4),
            "timetable-slot-change": reverse("core:timetable-slot-change",
                                             args=[self.started.pk]),
            "timetable-slot-end": reverse("core:timetable-slot-end", args=[self.started.pk]),
            "timetable-slot-delete": reverse("core:timetable-slot-delete",
                                             args=[self.future.pk]),
            "timetable-issues": reverse("core:timetable-issues", args=[year]),
        }

    def test_every_timetable_page_has_breadcrumbs_and_keeps_the_timetable_nav_active(self):
        for name, url in self.timetable_pages().items():
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, name)
            crumbs = response.context["breadcrumbs"]
            if name != "timetable-index":
                self.assertTrue(crumbs, name)
                self.assertEqual(crumbs[-1]["url"], None, name)
                for crumb in crumbs[:-1]:
                    self.assertEqual(self.client.get(crumb["url"]).status_code, 200,
                                     f"{name} crumb {crumb['label']}")
            if name != "timetable-index":  # the index itself is matched exactly by the sidebar
                self.assertEqual(response.context["nav_section"], "timetable-index", name)

    def test_grid_action_links_and_forms_preserve_the_schedule_date(self):
        on = date(2026, 12, 8)
        response = self.client.get(self.grid_url(on=on))
        actions = [h for h in hrefs(response) if "/timetable/slots/" in h or "/slots/add/" in h]
        self.assertTrue(actions)
        for href in actions:
            self.assertIn("date=2026-12-08", href)
            page = self.client.get(href.replace("&amp;", "&"))
            self.assertEqual(page.status_code, 200, href)
            cancel = [h for h in hrefs(page) if "/sections/" in h and "date=" in h]
            self.assertIn(self.grid_url(on=on), [h.replace("&amp;", "&") for h in cancel], href)

    def test_issue_report_links_land_on_the_section_at_the_report_date(self):
        self.raw_issue_slot()
        url = reverse("core:timetable-issues", args=[self.year.pk]) + "?date=2026-10-20"
        links = [h for h in hrefs(self.client.get(url)) if "/sections/" in h and "date=" in h]
        self.assertTrue(links)
        for href in links:
            self.assertIn("date=2026-10-20", href)
            self.assertEqual(self.client.get(href).context["schedule_date"], date(2026, 10, 20))

    def raw_issue_slot(self):
        TimetableSlot.objects.create(period=self.p1, weekday=2, section=self.six_a,
                                     offering=self.science, start_date=date(2026, 6, 1))

    # --- permissions and independence --------------------------------------------

    def test_teacher_and_anonymous_get_nothing_from_any_timetable_page(self):
        teacher = self.client_class()
        teacher.force_login(self.rao)
        anonymous = self.client_class()
        for name, url in self.timetable_pages().items():
            self.assertEqual(teacher.get(url).status_code, 403, name)
            response = anonymous.get(url)
            self.assertEqual(response.status_code, 302, name)
            self.assertIn("login", response["Location"], name)
        for body_url in (self.timetable_pages()["timetable-slot-delete"],
                         self.timetable_pages()["timetable-slot-end"]):
            self.assertEqual(teacher.post(body_url, {"end_date": "2026-11-01"}).status_code, 403)
        self.assertTrue(TimetableSlot.objects.filter(pk=self.future.pk).exists())

    def test_the_office_timetable_changes_no_teacher_authorization(self):
        def access():
            return (
                authorization.can_enter_results(self.rao, self.maths, self.six_a),
                authorization.can_enter_results(self.iyer, self.maths, self.six_a),
                sorted(authorization.current_teacher_assignments(self.rao).values_list("pk")),
            )

        before = access()
        c = self.client
        c.post(reverse("core:timetable-slot-end", args=[self.started.pk]),
               {"end_date": "2026-11-30"})
        c.post(reverse("core:timetable-slot-change", args=[self.started.pk]),
               {"offering": self.maths.pk, "effective_from": "2026-11-02", "end_date": ""})
        c.post(reverse("core:timetable-slot-delete", args=[self.future.pk]), {})
        self.assertEqual(access(), before)
        self.assertEqual(AssessmentTeacherAssignment.objects.count(), 1)

    def test_teacher_dashboard_has_no_timetable_yet(self):
        client = self.client_class()
        client.force_login(self.rao)
        page = client.get(reverse("core:my-home")).content.decode().lower()
        self.assertNotIn("timetable", page)

    # --- query regressions -------------------------------------------------------

    def count(self, url):
        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual(self.client.get(url).status_code, 200)
        return len(ctx)

    def test_pages_do_not_issue_queries_per_row(self):
        urls = {
            "sections": reverse("core:timetable-sections", args=[self.year.pk]),
            "index": reverse("core:timetable-index"),
            "periods": reverse("core:timetable-periods", args=[self.year.pk]),
            "grid": self.grid_url(on=TODAY),
            "issues": reverse("core:timetable-issues", args=[self.year.pk]) + f"?date={TODAY}",
        }
        small = {name: self.count(url) for name, url in urls.items()}
        # grow every table: more sections, periods, years, slots, assignments
        from core.models import AcademicYear, Section

        for i in range(6):
            section = Section.objects.create(class_grade=self.grade6, name=f"X{i}")
            TimetablePeriod.objects.create(academic_year=self.year, sequence=10 + i,
                                           label=f"Q{i}")
            AcademicYear.objects.create(name=f"Y{i}", start_date=date(2030 + i, 6, 1),
                                        end_date=date(2031 + i, 3, 31))
            TimetableSlot.objects.create(
                period=self.p1, weekday=0, section=section, offering=self.maths,
                start_date=date(2026, 6, 1))
        large = {name: self.count(url) for name, url in urls.items()}
        self.assertEqual(large, small)


class MockedBusinessDateTests(GridFixture, TestCase):
    """The UI rule 'nothing in the past' follows business_today, not the system clock."""

    def setUp(self):
        self.build_grid()

    def test_the_same_request_is_refused_or_accepted_as_the_business_date_moves(self):
        url = self.add_url()
        body = {"offering": self.maths.pk, "start_date": "2026-10-19", "end_date": ""}
        with mock.patch("core.models.business_today", new=lambda: date(2026, 10, 20)):
            self.assertEqual(self.client.post(url, body).status_code, 200)
            self.assertFalse(TimetableSlot.objects.exists())
        with mock.patch("core.models.business_today", new=lambda: date(2026, 10, 19)):
            self.assertEqual(self.client.post(url, body).status_code, 302)
            self.assertEqual(TimetableSlot.objects.count(), 1)
