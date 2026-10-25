"""TDB-4D: office Section weekly timetable grid and slot workflow (ADR 0021 D3, D4, D6, D9)."""

import re
from datetime import date
from unittest import mock

from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import get_resolver, reverse

from core.models import (
    AcademicSubjectOffering,
    AcademicYear,
    AssessmentTeacherAssignment,
    ClassGrade,
    Section,
    Subject,
    TimetablePeriod,
    TimetableSlot,
)
from core.tests.phase4_fixtures import Phase4Fixture

TODAY = date(2026, 10, 19)  # a Monday inside the 2026-27 year


def pinned(on=TODAY):
    return mock.patch("core.models.business_today", new=lambda: on)


class GridFixture(Phase4Fixture):
    def build_grid(self):
        self.build_phase4()
        self.p1 = TimetablePeriod.objects.create(academic_year=self.year, sequence=1, label="P1")
        self.p2 = TimetablePeriod.objects.create(academic_year=self.year, sequence=2, label="P2")
        self.science = AcademicSubjectOffering.objects.create(
            academic_year=self.year, class_grade=self.grade6,
            subject=Subject.objects.create(name="Science"),
        )
        self.client.force_login(self.admin)

    def grid_url(self, section=None, on=None, year=None):
        url = reverse(
            "core:timetable-grid", args=[(year or self.year).pk, (section or self.six_a).pk]
        )
        return f"{url}?date={on.isoformat()}" if on else url

    def add_url(self, period=None, weekday=0, section=None, on=None):
        url = reverse(
            "core:timetable-slot-create",
            args=[self.year.pk, (section or self.six_a).pk, (period or self.p1).pk, weekday],
        )
        return f"{url}?date={on.isoformat()}" if on else url

    def make_slot(self, **overrides):
        values = {
            "period": self.p1, "weekday": 0, "section": self.six_a, "offering": self.maths,
            "start_date": date(2026, 6, 1),
        }
        values.update(overrides)
        return TimetableSlot.create(**values)

    def assign_from(self, teacher, offering, section, start, end=None):
        return AssessmentTeacherAssignment.objects.create(
            teacher=teacher, offering=offering, section=section, start_date=start, end_date=end,
        )

    def cell(self, response, period, weekday):
        for row in response.context["rows"]:
            if row["period"] == period:
                return row["cells"][weekday]
        raise AssertionError("period not in grid")


@pinned()
class SectionSelectionTests(GridFixture, TestCase):
    def setUp(self):
        self.build_grid()

    def test_index_offers_section_timetables_for_each_year(self):
        response = self.client.get(reverse("core:timetable-index"))
        self.assertContains(response, reverse("core:timetable-sections", args=[self.year.pk]))

    def test_sections_page_lists_sections_with_offerings_that_year(self):
        other_grade = ClassGrade.objects.create(name="Grade 9")
        Section.objects.create(class_grade=other_grade, name="A")  # no offerings this year
        response = self.client.get(reverse("core:timetable-sections", args=[self.year.pk]))
        self.assertContains(response, self.grid_url(self.six_a))
        self.assertContains(response, self.grid_url(self.six_b))
        self.assertNotContains(response, "Grade 9")

    def test_sections_table_sits_in_the_shared_panel(self):
        html = self.client.get(
            reverse("core:timetable-sections", args=[self.year.pk])
        ).content.decode()
        self.assertRegex(
            html, r'<div class="erp-panel">\s*<div class="erp-table-scroll" role="region"'
        )
        self.assertIn('<table class="table erp-keep">', html)

    def test_sections_page_empty_state(self):
        AcademicSubjectOffering.objects.all().delete()
        response = self.client.get(reverse("core:timetable-sections", args=[self.year.pk]))
        self.assertContains(response, "No Sections have subject offerings")

    def test_grid_belongs_to_the_chosen_year_and_section(self):
        response = self.client.get(self.grid_url(self.six_b))
        self.assertEqual(response.context["section"], self.six_b)
        self.assertEqual(response.context["academic_year"], self.year)

    def test_unknown_section_or_year_is_404(self):
        self.assertEqual(self.client.get(self.grid_url(year=self.year).replace(
            f"/{self.six_a.pk}/", "/9999/")).status_code, 404)
        self.assertEqual(self.client.get(reverse("core:timetable-sections", args=[9999])
                                         ).status_code, 404)


class ScheduleDateTests(GridFixture, TestCase):
    def setUp(self):
        self.build_grid()

    @pinned(date(2026, 10, 19))
    def test_defaults_to_today_inside_the_year(self):
        response = self.client.get(self.grid_url())
        self.assertEqual(response.context["schedule_date"], date(2026, 10, 19))
        self.assertContains(response, 'value="2026-10-19"')

    @pinned(date(2027, 5, 1))
    def test_defaults_to_year_start_when_today_is_after_the_year(self):
        self.assertEqual(self.client.get(self.grid_url()).context["schedule_date"],
                         self.year.start_date)

    @pinned(date(2026, 1, 1))
    def test_defaults_to_year_start_when_today_is_before_the_year(self):
        self.assertEqual(self.client.get(self.grid_url()).context["schedule_date"],
                         self.year.start_date)

    @pinned()
    def test_a_chosen_date_inside_the_year_is_used(self):
        response = self.client.get(self.grid_url(on=date(2026, 8, 3)))
        self.assertEqual(response.context["schedule_date"], date(2026, 8, 3))
        self.assertContains(response, 'value="2026-08-03"')

    @pinned()
    def test_a_date_outside_the_year_is_rejected_and_the_default_is_shown(self):
        response = self.client.get(self.grid_url(on=date(2028, 1, 1)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["schedule_date"], date(2026, 10, 19))
        self.assertContains(response, "Choose a date between")
        self.assertIn('aria-invalid="true"', self._tag(response, "id_date"))

    @pinned()
    def test_unparseable_date_is_rejected(self):
        response = self.client.get(self.grid_url() + "?date=not-a-date")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["schedule_date"], date(2026, 10, 19))
        self.assertIn('aria-invalid="true"', self._tag(response, "id_date"))

    @pinned()
    def test_date_field_is_labelled_schedule_date(self):
        response = self.client.get(self.grid_url())
        self.assertContains(response, 'for="id_date"')
        self.assertContains(response, "Schedule date")

    def _tag(self, response, field_id):
        found = re.search(rf'<input\b[^>]*\bid="{field_id}"[^>]*>', response.content.decode())
        self.assertIsNotNone(found)
        return found.group(0)


@pinned()
class GridContentTests(GridFixture, TestCase):
    def setUp(self):
        self.build_grid()

    def test_columns_are_monday_to_saturday_only(self):
        response = self.client.get(self.grid_url())
        html = response.content.decode()
        for day in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"):
            self.assertIn(f">{day}<", html)
        self.assertNotIn("Sunday", html)

    def test_rows_are_periods_in_sequence_order_without_clock_times(self):
        p0 = TimetablePeriod.objects.create(academic_year=self.year, sequence=3, label="P3")
        TimetablePeriod.objects.filter(pk=self.p1.pk).update(sequence=5)
        response = self.client.get(self.grid_url())
        self.assertEqual([r["period"] for r in response.context["rows"]], [self.p2, p0, self.p1])
        for word in ("Start time", "End time", "Room", "Free period"):
            self.assertNotContains(response, word)

    def test_populated_cell_shows_the_real_subject_name(self):
        self.make_slot(weekday=1, offering=self.science)
        response = self.client.get(self.grid_url())
        self.assertEqual(self.cell(response, self.p1, 1)["slot"].offering, self.science)
        self.assertContains(response, "Science")

    def test_empty_cells_say_no_slot_scheduled_and_invent_nothing(self):
        response = self.client.get(self.grid_url())
        self.assertIsNone(self.cell(response, self.p1, 0)["slot"])
        self.assertContains(response, "No slot scheduled")
        self.assertNotContains(response, "Mathematics")

    def test_only_this_sections_slots_are_shown(self):
        self.make_slot(section=self.six_b)
        self.assertIsNone(self.cell(self.client.get(self.grid_url(self.six_a)), self.p1, 0)["slot"])

    def test_period_less_year_points_to_period_setup(self):
        TimetablePeriod.objects.all().delete()
        response = self.client.get(self.grid_url())
        self.assertContains(response, "No periods yet")
        self.assertContains(response, reverse("core:timetable-periods", args=[self.year.pk]))

    def test_saturday_cells_explain_when_the_year_has_no_instructional_saturdays(self):
        response = self.client.get(self.grid_url())
        self.assertContains(response, "Saturday is not a school day")
        self.assertNotContains(response, self.add_url(weekday=5))

    def test_saturday_cells_can_be_scheduled_when_the_year_runs_saturdays(self):
        self.year.saturdays_instructional = True
        self.year.save()
        response = self.client.get(self.grid_url())
        self.assertContains(response, self.add_url(weekday=5, on=TODAY))

    def test_teacher_is_derived_from_the_assignment_on_the_schedule_date(self):
        self.make_slot()
        self.assign_from(self.rao, self.maths, self.six_a, date(2026, 6, 1), date(2026, 10, 31))
        self.assign_from(self.iyer, self.maths, self.six_a, date(2026, 11, 1))
        october = self.client.get(self.grid_url(on=date(2026, 10, 19)))
        november = self.client.get(self.grid_url(on=date(2026, 11, 2)))
        self.assertEqual(self.cell(october, self.p1, 0)["teacher"], "rao")
        self.assertEqual(self.cell(november, self.p1, 0)["teacher"], "iyer")

    def test_unassigned_slot_is_valid_and_marked(self):
        self.make_slot()
        response = self.client.get(self.grid_url())
        self.assertIsNone(self.cell(response, self.p1, 0)["teacher"])
        self.assertContains(response, "No teacher assigned")

    def test_no_teacher_field_exists_on_any_slot_form(self):
        slot = self.make_slot()
        urls = [
            self.add_url(),
            reverse("core:timetable-slot-change", args=[slot.pk]),
            reverse("core:timetable-slot-end", args=[slot.pk]),
        ]
        for url in urls:
            fields = set(self.client.get(url).context["form"].fields)
            self.assertFalse([f for f in fields if "teacher" in f], url)


@pinned()
class EffectiveVersionTests(GridFixture, TestCase):
    """The grid is one explicit schedule date: versions never mix in a cell."""

    def setUp(self):
        self.build_grid()
        self.history = self.make_slot(offering=self.maths, start_date=date(2026, 6, 1),
                                      end_date=date(2026, 9, 30))
        self.current = self.make_slot(offering=self.science, start_date=date(2026, 10, 1),
                                      end_date=date(2026, 12, 31))
        self.future = self.make_slot(offering=self.maths, start_date=date(2027, 1, 1))

    def subject_on(self, on):
        response = self.client.get(self.grid_url(on=on))
        slot = self.cell(response, self.p1, 0)["slot"]
        return slot.offering.subject.name if slot else None, response

    def test_each_date_shows_exactly_one_version(self):
        self.assertEqual(self.subject_on(date(2026, 9, 30))[0], "Mathematics")
        self.assertEqual(self.subject_on(date(2026, 10, 1))[0], "Science")
        self.assertEqual(self.subject_on(date(2026, 12, 31))[0], "Science")
        self.assertEqual(self.subject_on(date(2027, 1, 1))[0], "Mathematics")

    def test_other_versions_are_not_rendered_in_the_cell(self):
        _, response = self.subject_on(date(2026, 10, 19))
        self.assertContains(response, "Science")
        self.assertNotContains(response, "Mathematics")

    def test_a_cell_between_versions_is_empty(self):
        TimetableSlot.objects.filter(pk=self.current.pk).update(end_date=date(2026, 11, 30))
        TimetableSlot.objects.filter(pk=self.future.pk).update(start_date=date(2027, 1, 1))
        self.assertIsNone(self.subject_on(date(2026, 12, 15))[0])

    def test_historical_slot_offers_no_actions(self):
        cell = self.cell(self.client.get(self.grid_url(on=date(2026, 9, 15))), self.p1, 0)
        self.assertFalse(cell["can_change"] or cell["can_end"] or cell["can_delete"])
        self.assertTrue(cell["historical"])

    def test_historical_view_has_no_action_links(self):
        response = self.client.get(self.grid_url(on=date(2026, 9, 15)))
        for name in ("timetable-slot-change", "timetable-slot-end", "timetable-slot-delete"):
            self.assertNotContains(response, reverse(f"core:{name}", args=[self.history.pk]))
        self.assertContains(response, "Ended")

    def test_started_current_slot_offers_change_and_end_but_never_delete(self):
        cell = self.cell(self.client.get(self.grid_url(on=date(2026, 10, 19))), self.p1, 0)
        self.assertTrue(cell["can_change"] and cell["can_end"])
        self.assertFalse(cell["can_delete"])

    def test_future_slot_offers_change_end_and_delete(self):
        response = self.client.get(self.grid_url(on=date(2027, 1, 5)))
        cell = self.cell(response, self.p1, 0)
        self.assertTrue(cell["can_change"] and cell["can_delete"])
        self.assertContains(response, reverse("core:timetable-slot-delete", args=[self.future.pk]))


@pinned()
class AddSlotTests(GridFixture, TestCase):
    def setUp(self):
        self.build_grid()

    def post(self, **data):
        payload = {"offering": self.maths.pk, "start_date": "2026-10-19", "end_date": ""}
        payload.update(data)
        return self.client.post(self.add_url(on=TODAY), payload)

    def test_form_offers_only_offerings_valid_for_the_section_and_year(self):
        other = AcademicYear.objects.create(
            name="2027-28", start_date=date(2027, 6, 1), end_date=date(2028, 3, 31)
        )
        foreign = AcademicSubjectOffering.objects.create(
            academic_year=other, class_grade=self.grade6, subject=Subject.objects.create(name="Art")
        )
        form = self.client.get(self.add_url()).context["form"]
        choices = set(form.fields["offering"].queryset)
        self.assertEqual(choices, {self.maths, self.science})  # not Sanskrit (6B only)
        self.assertNotIn(foreign, choices)
        six_b = self.client.get(self.add_url(section=self.six_b)).context["form"]
        self.assertIn(self.sanskrit, set(six_b.fields["offering"].queryset))

    def test_cell_and_defaults_come_from_the_url_and_schedule_date(self):
        response = self.client.get(self.add_url(period=self.p2, weekday=2, on=date(2026, 11, 3)))
        self.assertContains(response, "P2")
        self.assertContains(response, "Wednesday")
        self.assertEqual(response.context["form"].initial["start_date"], date(2026, 11, 3))

    def test_default_start_is_today_when_the_schedule_date_is_in_the_past(self):
        response = self.client.get(self.add_url(on=date(2026, 8, 3)))
        self.assertEqual(response.context["form"].initial["start_date"], TODAY)

    def test_successful_add_goes_through_the_lifecycle_and_returns_to_the_grid(self):
        response = self.post()
        self.assertRedirects(response, self.grid_url(on=TODAY))
        slot = TimetableSlot.objects.get()
        self.assertEqual((slot.period, slot.weekday, slot.section, slot.offering),
                         (self.p1, 0, self.six_a, self.maths))
        self.assertEqual((slot.start_date, slot.end_date), (TODAY, None))

    def test_add_uses_timetableslot_create(self):
        with mock.patch.object(TimetableSlot, "create", wraps=TimetableSlot.create) as create:
            self.post()
        create.assert_called_once()

    def test_unassigned_slot_is_accepted(self):
        self.post()
        self.assertEqual(TimetableSlot.objects.count(), 1)

    def test_optional_end_date_is_saved(self):
        self.post(end_date="2026-12-31")
        self.assertEqual(TimetableSlot.objects.get().end_date, date(2026, 12, 31))

    def test_overlap_is_a_form_error_not_a_server_error(self):
        self.make_slot(start_date=date(2026, 6, 1))
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "overlap another slot")
        self.assertEqual(TimetableSlot.objects.count(), 1)

    def test_teacher_clash_is_a_form_error_and_moves_focus_to_the_summary(self):
        self.assign_from(self.rao, self.maths, self.six_a, date(2026, 6, 1))
        self.assign_from(self.rao, self.sanskrit, self.six_b, date(2026, 6, 1))
        self.make_slot(section=self.six_b, offering=self.sanskrit)
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already teaches")
        self.assertContains(response, 'role="alert"')
        self.assertTrue(response.context["form"].focus_summary)
        self.assertEqual(TimetableSlot.objects.count(), 1)

    def test_r2_wrong_offering_cannot_be_forged_into_the_form(self):
        response = self.post(offering=self.sanskrit.pk)
        self.assertEqual(response.status_code, 200)
        self.assertIn("offering", response.context["form"].errors)
        self.assertFalse(TimetableSlot.objects.exists())

    def test_r3_dates_outside_the_year_are_field_errors(self):
        response = self.post(end_date="2027-04-01")
        self.assertIn("end_date", response.context["form"].errors)
        self.assertIn('aria-invalid="true"',
                      re.search(r'<input\b[^>]*\bid="id_end_date"[^>]*>',
                                response.content.decode()).group(0))

    def test_r5_saturday_in_a_year_without_saturdays_is_an_error(self):
        response = self.client.post(
            self.add_url(weekday=5, on=TODAY),
            {"offering": self.maths.pk, "start_date": "2026-10-19", "end_date": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "no instructional Saturdays")
        self.assertFalse(TimetableSlot.objects.exists())

    def test_ui_rule_start_date_cannot_be_in_the_past(self):
        response = self.post(start_date="2026-10-18")
        self.assertIn("start_date", response.context["form"].errors)
        self.assertContains(response, "in the past")
        self.assertFalse(TimetableSlot.objects.exists())

    def test_end_before_start_is_an_error(self):
        response = self.post(start_date="2026-11-10", end_date="2026-11-09")
        self.assertIn("end_date", response.context["form"].errors)

    def test_bad_cell_urls_are_404(self):
        self.assertEqual(self.client.get(self.add_url(weekday=6)).status_code, 404)
        other = AcademicYear.objects.create(
            name="2027-28", start_date=date(2027, 6, 1), end_date=date(2028, 3, 31)
        )
        foreign_period = TimetablePeriod.objects.create(
            academic_year=other, sequence=1, label="P1"
        )
        self.assertEqual(self.client.get(self.add_url(period=foreign_period)).status_code, 404)

    def test_form_is_accessible(self):
        html = self.client.get(self.add_url()).content.decode()
        for field in ("offering", "start_date", "end_date"):
            self.assertIn(f'for="id_{field}"', html)
        self.assertIn("(required)", html)
        self.assertIn('id="id_end_date_helptext"', html)
        self.assertNotIn("aria-invalid", html)


@pinned()
class ChangeSlotTests(GridFixture, TestCase):
    def setUp(self):
        self.build_grid()

    def url(self, slot, on=None):
        url = reverse("core:timetable-slot-change", args=[slot.pk])
        return f"{url}?date={on.isoformat()}" if on else url

    def post(self, slot, **data):
        payload = {"offering": self.science.pk, "effective_from": "2026-11-02", "end_date": ""}
        payload.update(data)
        return self.client.post(self.url(slot, TODAY), payload)

    def test_change_of_a_started_slot_preserves_the_historical_row(self):
        slot = self.make_slot(start_date=date(2026, 6, 1))
        response = self.post(slot)
        self.assertRedirects(response, self.grid_url(on=TODAY))
        slot.refresh_from_db()
        self.assertEqual(slot.end_date, date(2026, 11, 1))
        new = TimetableSlot.objects.exclude(pk=slot.pk).get()
        self.assertEqual((new.offering, new.start_date, new.end_date),
                         (self.science, date(2026, 11, 2), None))
        self.assertEqual((new.period, new.weekday, new.section), (slot.period, 0, self.six_a))

    def test_change_uses_the_lifecycle_api(self):
        slot = self.make_slot(start_date=date(2026, 6, 1))
        with mock.patch.object(TimetableSlot, "change", autospec=True,
                               side_effect=TimetableSlot.change) as change:
            self.post(slot)
        change.assert_called_once()

    def test_form_defaults_to_the_current_offering_and_the_earliest_allowed_date(self):
        slot = self.make_slot(start_date=date(2026, 6, 1))
        form = self.client.get(self.url(slot)).context["form"]
        self.assertEqual(form.initial["offering"], self.maths.pk)
        self.assertEqual(form.initial["effective_from"], TODAY)

    def test_effective_from_before_today_is_refused_by_the_ui(self):
        slot = self.make_slot(start_date=date(2026, 6, 1))
        response = self.post(slot, effective_from="2026-10-18")
        self.assertIn("effective_from", response.context["form"].errors)
        self.assertContains(response, "in the past")
        slot.refresh_from_db()
        self.assertIsNone(slot.end_date)
        self.assertEqual(TimetableSlot.objects.count(), 1)

    def test_a_slot_that_started_today_can_only_change_from_a_later_date(self):
        slot = self.make_slot(start_date=TODAY)
        response = self.post(slot, effective_from="2026-10-19")
        self.assertIn("effective_from", response.context["form"].errors)
        self.assertEqual(
            self.client.get(self.url(slot)).context["form"].initial["effective_from"],
            date(2026, 10, 20),
        )

    def test_change_of_a_future_slot_replaces_it(self):
        slot = self.make_slot(start_date=date(2026, 12, 1))
        response = self.post(slot, effective_from="2026-12-08")
        self.assertEqual(response.status_code, 302)
        row = TimetableSlot.objects.get()
        self.assertEqual((row.offering, row.start_date), (self.science, date(2026, 12, 8)))

    def test_a_domain_failure_renders_as_a_form_error_and_changes_nothing(self):
        self.assign_from(self.rao, self.maths, self.six_a, date(2026, 6, 1))
        self.assign_from(self.rao, self.science, self.six_a, date(2026, 6, 1))
        slot = self.make_slot(start_date=date(2026, 6, 1))
        self.make_slot(section=self.six_b, offering=self.science, start_date=date(2026, 11, 2))
        # Rao would teach 6A Science and 6B Science in P1 on Monday from 2 Nov: a clash
        self.assign_from(self.rao, self.science, self.six_b, date(2026, 6, 1))
        response = self.post(slot)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already teaches")
        slot.refresh_from_db()
        self.assertIsNone(slot.end_date)

    def test_a_forged_change_of_an_ended_slot_fails_safely(self):
        slot = self.make_slot(start_date=date(2026, 6, 1), end_date=date(2026, 9, 30))
        response = self.post(slot)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already ended")
        slot.refresh_from_db()
        self.assertEqual(slot.end_date, date(2026, 9, 30))
        self.assertEqual(TimetableSlot.objects.count(), 1)

    def test_only_offering_dates_and_end_are_editable(self):
        slot = self.make_slot()
        names = set(self.client.get(self.url(slot)).context["form"].fields)
        self.assertEqual(names, {"offering", "effective_from", "end_date"})

    def test_offering_choices_are_limited_to_the_section(self):
        slot = self.make_slot()
        form = self.client.get(self.url(slot)).context["form"]
        self.assertNotIn(self.sanskrit, set(form.fields["offering"].queryset))


@pinned()
class EndSlotTests(GridFixture, TestCase):
    def setUp(self):
        self.build_grid()

    def url(self, slot, on=None):
        url = reverse("core:timetable-slot-end", args=[slot.pk])
        return f"{url}?date={on.isoformat()}" if on else url

    def test_end_sets_an_inclusive_end_date(self):
        slot = self.make_slot(start_date=date(2026, 6, 1))
        response = self.client.post(self.url(slot, TODAY), {"end_date": "2026-11-30"})
        self.assertRedirects(response, self.grid_url(on=TODAY))
        slot.refresh_from_db()
        self.assertEqual(slot.end_date, date(2026, 11, 30))
        effective = TimetableSlot.objects.effective_on
        self.assertIn(slot, effective(date(2026, 11, 30)))
        self.assertNotIn(slot, effective(date(2026, 12, 1)))

    def test_end_uses_the_lifecycle_api_and_the_form_explains_inclusivity(self):
        slot = self.make_slot(start_date=date(2026, 6, 1))
        self.assertContains(self.client.get(self.url(slot)), "last day")
        with mock.patch.object(TimetableSlot, "end", autospec=True,
                               side_effect=TimetableSlot.end) as end:
            self.client.post(self.url(slot), {"end_date": "2026-11-30"})
        end.assert_called_once()

    def test_end_date_before_today_is_refused_by_the_ui(self):
        slot = self.make_slot(start_date=date(2026, 6, 1))
        response = self.client.post(self.url(slot), {"end_date": "2026-10-18"})
        self.assertIn("end_date", response.context["form"].errors)
        slot.refresh_from_db()
        self.assertIsNone(slot.end_date)

    def test_ending_cannot_extend_an_ended_slot(self):
        slot = self.make_slot(start_date=date(2026, 6, 1), end_date=date(2026, 12, 31))
        response = self.client.post(self.url(slot), {"end_date": "2027-02-28"})
        self.assertIn("end_date", response.context["form"].errors)
        slot.refresh_from_db()
        self.assertEqual(slot.end_date, date(2026, 12, 31))

    def test_default_end_date_is_today_for_a_started_slot(self):
        slot = self.make_slot(start_date=date(2026, 6, 1))
        self.assertEqual(self.client.get(self.url(slot)).context["form"].initial["end_date"],
                         TODAY)

    def test_ending_a_historical_slot_is_refused(self):
        slot = self.make_slot(start_date=date(2026, 6, 1), end_date=date(2026, 9, 30))
        response = self.client.post(self.url(slot), {"end_date": "2026-10-19"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("end_date", response.context["form"].errors)
        slot.refresh_from_db()
        self.assertEqual(slot.end_date, date(2026, 9, 30))


@pinned()
class DeleteSlotTests(GridFixture, TestCase):
    def setUp(self):
        self.build_grid()

    def url(self, slot, on=None):
        url = reverse("core:timetable-slot-delete", args=[slot.pk])
        return f"{url}?date={on.isoformat()}" if on else url

    def test_future_slot_is_deleted_after_confirmation(self):
        slot = self.make_slot(start_date=date(2026, 12, 1))
        page = self.client.get(self.url(slot))
        self.assertContains(page, "Delete slot")
        self.assertTrue(TimetableSlot.objects.exists())  # GET never deletes
        self.assertRedirects(self.client.post(self.url(slot, TODAY)), self.grid_url(on=TODAY))
        self.assertFalse(TimetableSlot.objects.exists())

    def test_started_slot_offers_end_instead_of_delete(self):
        slot = self.make_slot(start_date=date(2026, 6, 1))
        page = self.client.get(self.url(slot))
        self.assertNotContains(page, "Delete slot</button>")
        self.assertContains(page, reverse("core:timetable-slot-end", args=[slot.pk]))
        grid = self.client.get(self.grid_url())
        self.assertNotContains(grid, reverse("core:timetable-slot-delete", args=[slot.pk]))

    def test_forged_delete_of_a_started_slot_fails_safely(self):
        slot = self.make_slot(start_date=date(2026, 6, 1))
        response = self.client.post(self.url(slot, TODAY), follow=True)
        self.assertContains(response, "taken effect")
        self.assertTrue(TimetableSlot.objects.filter(pk=slot.pk).exists())

    def test_a_slot_starting_today_counts_as_started(self):
        slot = self.make_slot(start_date=TODAY)
        self.client.post(self.url(slot))
        self.assertTrue(TimetableSlot.objects.filter(pk=slot.pk).exists())


@pinned()
class PermissionTests(GridFixture, TestCase):
    def setUp(self):
        self.build_grid()
        self.started = self.make_slot(start_date=date(2026, 6, 1))
        self.future = self.make_slot(weekday=1, start_date=date(2026, 12, 1))
        self.count = 0

    def user_with(self, *codenames):
        self.count += 1
        user = self.make_user(f"perm{self.count}")
        user.user_permissions.add(
            *Permission.objects.filter(content_type__app_label="core", codename__in=codenames)
        )
        return user

    def operations(self):
        return {
            "add_get": ("get", self.add_url(period=self.p2), "add_timetableslot"),
            "add_post": ("post", self.add_url(period=self.p2), "add_timetableslot"),
            "change_get": ("get", reverse("core:timetable-slot-change", args=[self.started.pk]),
                           "change_timetableslot"),
            "change_post": ("post", reverse("core:timetable-slot-change", args=[self.started.pk]),
                            "change_timetableslot"),
            "end_get": ("get", reverse("core:timetable-slot-end", args=[self.started.pk]),
                        "change_timetableslot"),
            "end_post": ("post", reverse("core:timetable-slot-end", args=[self.started.pk]),
                         "change_timetableslot"),
            "delete_get": ("get", reverse("core:timetable-slot-delete", args=[self.future.pk]),
                           "delete_timetableslot"),
            "delete_post": ("post", reverse("core:timetable-slot-delete", args=[self.future.pk]),
                            "delete_timetableslot"),
        }

    def test_each_mutation_needs_its_own_slot_permission(self):
        every = ["view_timetableslot", "add_timetableslot", "change_timetableslot",
                 "delete_timetableslot"]
        for name, (method, url, needed) in self.operations().items():
            for held in every:
                client = self.client_class()
                client.force_login(self.user_with(held))
                before = TimetableSlot.objects.count()
                response = getattr(client, method)(url, {})
                if held == needed:
                    self.assertNotEqual(response.status_code, 403, f"{name} with {held}")
                else:
                    self.assertEqual(response.status_code, 403, f"{name} with only {held}")
                    self.assertEqual(TimetableSlot.objects.count(), before, f"{name}/{held}")

    def test_grid_needs_slot_and_period_view_permissions(self):
        for held, expected in (
            (["view_timetableslot"], 403),
            (["view_timetableperiod"], 403),
            (["view_timetableslot", "view_timetableperiod"], 200),
        ):
            client = self.client_class()
            client.force_login(self.user_with(*held))
            self.assertEqual(client.get(self.grid_url()).status_code, expected, held)

    def test_sections_page_needs_slot_and_period_view_permissions(self):
        url = reverse("core:timetable-sections", args=[self.year.pk])
        for held, expected in (
            (["view_timetableperiod"], 403),
            (["view_timetableslot", "view_timetableperiod"], 200),
        ):
            client = self.client_class()
            client.force_login(self.user_with(*held))
            self.assertEqual(client.get(url).status_code, expected, held)

    def test_view_only_user_sees_no_actions(self):
        client = self.client_class()
        client.force_login(self.user_with("view_timetableslot", "view_timetableperiod"))
        html = client.get(self.grid_url(on=date(2026, 12, 7))).content.decode()
        for fragment in ("/slots/add/", "/timetable/slots/"):
            self.assertNotIn(fragment, html)

    def test_actions_follow_the_users_permissions(self):
        client = self.client_class()
        client.force_login(self.user_with(
            "view_timetableslot", "view_timetableperiod", "change_timetableslot"))
        html = client.get(self.grid_url(on=date(2026, 12, 7))).content.decode()
        self.assertIn(f"/timetable/slots/{self.started.pk}/change/", html)
        self.assertIn(f"/timetable/slots/{self.started.pk}/end/", html)
        self.assertNotIn(f"/timetable/slots/{self.future.pk}/delete/", html)
        self.assertNotIn("/slots/add/", html)

    def test_teacher_is_denied_everywhere(self):
        client = self.client_class()
        client.force_login(self.rao)
        urls = [self.grid_url(), reverse("core:timetable-sections", args=[self.year.pk])]
        urls += [u for _, u, _ in self.operations().values()]
        for url in urls:
            self.assertEqual(client.get(url).status_code, 403, url)

    def test_anonymous_is_redirected_to_sign_in(self):
        client = self.client_class()
        urls = [self.grid_url(), reverse("core:timetable-sections", args=[self.year.pk])]
        urls += [u for _, u, _ in self.operations().values()]
        for url in urls:
            response = client.get(url)
            self.assertEqual(response.status_code, 302, url)
            self.assertIn("login", response["Location"])


@pinned()
class ScopeAndQueryTests(GridFixture, TestCase):
    def setUp(self):
        self.build_grid()

    def test_the_grid_gate_added_no_report_urls(self):
        # (the Teacher dashboard timetable arrived in TDB-5 and has its own tests)
        names = {k for k in get_resolver().namespace_dict["core"][1].reverse_dict
                 if isinstance(k, str)}
        self.assertFalse([n for n in names if "timetable" in n and
                          ("conflict" in n or "missing" in n or "report" in n)])

    def test_grid_query_count_does_not_grow_with_populated_cells(self):
        self.assign_from(self.rao, self.maths, self.six_a, date(2026, 6, 1))

        def count():
            with CaptureQueriesContext(connection) as ctx:
                self.assertEqual(self.client.get(self.grid_url(on=TODAY)).status_code, 200)
            return len(ctx)

        self.make_slot(weekday=0)
        one = count()
        for weekday in range(1, 5):
            for period in (self.p1, self.p2):
                self.make_slot(weekday=weekday, period=period, offering=self.science)
        self.make_slot(weekday=0, period=self.p2)
        self.assertEqual(count(), one)


@pinned()
class SlotFormAccessibilityTests(GridFixture, TestCase):
    def setUp(self):
        self.build_grid()

    def test_error_state_is_wired_on_the_slot_form(self):
        response = self.client.post(
            self.add_url(on=TODAY),
            {"offering": self.maths.pk, "start_date": "2026-10-10", "end_date": ""},
        )
        html = response.content.decode()
        tag = re.search(r'<input\b[^>]*\bid="id_start_date"[^>]*>', html).group(0)
        self.assertIn('aria-invalid="true"', tag)
        self.assertIn("autofocus", tag)
        self.assertIn("id_start_date_helptext id_start_date_error", tag)
        self.assertIn('class="erp-form-errors" role="alert"', html)
        self.assertIn('href="#id_start_date"', html)
        self.assertIn('value="2026-10-10"', tag)  # typed input kept


@pinned()
class SlotFormHelpTextTests(GridFixture, TestCase):
    """Every field's helper text is rendered and associated, including dynamic help."""

    def setUp(self):
        self.build_grid()
        self.started = self.make_slot(start_date=date(2026, 6, 1))
        self.future = self.make_slot(weekday=1, start_date=date(2026, 12, 1))

    def assertHelpAssociated(self, url, fields):
        html = self.client.get(url).content.decode()
        for field in fields:
            self.assertIn(f'id="id_{field}_helptext"', html, f"{url} {field}")
            tag = re.search(rf'<input[^>]*id="id_{field}"[^>]*>|<select[^>]*id="id_{field}"[^>]*>',
                            html).group(0)
            self.assertIn(f"id_{field}_helptext", tag, f"{url} {field}")

    def test_change_form_renders_dynamic_help_for_started_and_future_slots(self):
        for slot, expected in ((self.started, "history is kept"), (self.future, "not started")):
            url = reverse("core:timetable-slot-change", args=[slot.pk])
            self.assertHelpAssociated(url, ["offering", "effective_from", "end_date"])
            self.assertContains(self.client.get(url), expected)

    def test_end_and_add_forms_render_their_help(self):
        self.assertHelpAssociated(
            reverse("core:timetable-slot-end", args=[self.started.pk]), ["end_date"])
        self.assertHelpAssociated(self.add_url(), ["offering", "start_date", "end_date"])
