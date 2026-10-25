"""TDB-4C: office Period setup screens (ADR 0021 D2, D9)."""

import re
from datetime import date

from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from core.models import AcademicYear, TimetablePeriod, TimetableSlot
from core.navigation import office_nav
from core.tests.phase4_fixtures import Phase4Fixture

ALL_FOUR = ["view", "add", "change", "delete"]


class PeriodScreenTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        self.client.force_login(self.admin)
        self.list_url = reverse("core:timetable-periods", args=[self.year.pk])

    def post_period(self, url, **data):
        return self.client.post(url, data)

    def make_period(self, sequence, label, year=None):
        return TimetablePeriod.objects.create(
            academic_year=year or self.year, sequence=sequence, label=label
        )

    # --- navigation and year selection -------------------------------------

    def test_office_nav_has_a_timetable_entry_for_administrators_only(self):
        labels = [link["label"] for g in office_nav(self.admin, "") for link in g["links"]]
        self.assertIn("Timetable", labels)
        teacher_labels = [link["label"] for g in office_nav(self.rao, "") for link in g["links"]]
        self.assertNotIn("Timetable", teacher_labels)

    def test_timetable_entry_lets_the_user_choose_an_academic_year(self):
        later = AcademicYear.objects.create(
            name="2027-28", start_date=date(2027, 6, 1), end_date=date(2028, 3, 31)
        )
        response = self.client.get(reverse("core:timetable-index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2026-27")
        self.assertContains(response, "2027-28")
        self.assertContains(response, reverse("core:timetable-periods", args=[self.year.pk]))
        self.assertContains(response, reverse("core:timetable-periods", args=[later.pk]))

    # --- list ----------------------------------------------------------------

    def test_list_shows_periods_ordered_by_sequence_without_clock_times(self):
        self.make_period(3, "P3")
        self.make_period(1, "P1")
        self.make_period(2, "P2")
        response = self.client.get(self.list_url)
        self.assertEqual(
            [p.label for p in response.context["periods"]], ["P1", "P2", "P3"]
        )
        self.assertNotContains(response, "Start time")
        self.assertNotContains(response, "End time")

    def test_list_only_shows_the_chosen_years_periods(self):
        other = AcademicYear.objects.create(
            name="2027-28", start_date=date(2027, 6, 1), end_date=date(2028, 3, 31)
        )
        self.make_period(1, "P1")
        self.make_period(1, "Other", year=other)
        response = self.client.get(self.list_url)
        self.assertEqual([p.label for p in response.context["periods"]], ["P1"])

    def test_list_empty_state(self):
        response = self.client.get(self.list_url)
        self.assertContains(response, "No periods yet")
        self.assertContains(response, reverse("core:timetable-period-create", args=[self.year.pk]))

    def test_empty_state_has_a_single_add_action(self):
        page = self.client.get(self.list_url).content.decode()
        create = reverse("core:timetable-period-create", args=[self.year.pk])
        self.assertEqual(page.count(f'href="{create}"'), 1)
        self.assertIn("Add the first period", page)
        self.assertNotIn(">Add period<", page)

    def test_header_add_action_returns_once_periods_exist(self):
        self.make_period(1, "P1")
        page = self.client.get(self.list_url).content.decode()
        self.assertEqual(page.count(">Add period<"), 1)
        self.assertNotIn("Add the first period", page)

    def test_unknown_year_is_404(self):
        self.assertEqual(
            self.client.get(reverse("core:timetable-periods", args=[9999])).status_code, 404
        )

    # --- add -------------------------------------------------------------------

    def test_add_valid_period(self):
        url = reverse("core:timetable-period-create", args=[self.year.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.post_period(url, sequence="1", label="P1")
        self.assertRedirects(response, self.list_url)
        period = TimetablePeriod.objects.get()
        self.assertEqual((period.academic_year, period.sequence, period.label),
                         (self.year, 1, "P1"))

    def test_duplicate_sequence_is_rejected_on_the_form(self):
        self.make_period(1, "P1")
        url = reverse("core:timetable-period-create", args=[self.year.pk])
        response = self.post_period(url, sequence="1", label="Other")
        self.assertEqual(response.status_code, 200)
        self.assertIn("sequence", response.context["form"].errors)
        self.assertContains(response, "already uses this")
        self.assertEqual(TimetablePeriod.objects.count(), 1)

    def test_duplicate_label_is_rejected_on_the_form(self):
        self.make_period(1, "P1")
        url = reverse("core:timetable-period-create", args=[self.year.pk])
        response = self.post_period(url, sequence="2", label="P1")
        self.assertEqual(response.status_code, 200)
        self.assertIn("label", response.context["form"].errors)
        self.assertEqual(TimetablePeriod.objects.count(), 1)

    def test_same_sequence_and_label_are_fine_in_another_year(self):
        other = AcademicYear.objects.create(
            name="2027-28", start_date=date(2027, 6, 1), end_date=date(2028, 3, 31)
        )
        self.make_period(1, "P1", year=other)
        url = reverse("core:timetable-period-create", args=[self.year.pk])
        self.assertRedirects(self.post_period(url, sequence="1", label="P1"), self.list_url)

    def test_sequence_zero_is_rejected(self):
        url = reverse("core:timetable-period-create", args=[self.year.pk])
        response = self.post_period(url, sequence="0", label="P0")
        self.assertEqual(response.status_code, 200)
        self.assertIn("sequence", response.context["form"].errors)
        self.assertFalse(TimetablePeriod.objects.exists())

    def test_invalid_input_keeps_what_the_user_typed(self):
        url = reverse("core:timetable-period-create", args=[self.year.pk])
        response = self.post_period(url, sequence="0", label="Assembly")
        self.assertContains(response, 'value="Assembly"')

    def test_label_is_trimmed_and_required(self):
        url = reverse("core:timetable-period-create", args=[self.year.pk])
        self.post_period(url, sequence="1", label="  P1  ")
        self.assertEqual(TimetablePeriod.objects.get().label, "P1")
        response = self.post_period(url, sequence="2", label="   ")
        self.assertIn("label", response.context["form"].errors)

    # --- edit ------------------------------------------------------------------

    def test_edit_sequence_and_label(self):
        period = self.make_period(1, "P1")
        url = reverse("core:timetable-period-update", args=[period.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertRedirects(self.post_period(url, sequence="5", label="Assembly"), self.list_url)
        period.refresh_from_db()
        self.assertEqual((period.sequence, period.label), (5, "Assembly"))

    def test_edit_may_keep_its_own_sequence_and_label(self):
        period = self.make_period(1, "P1")
        url = reverse("core:timetable-period-update", args=[period.pk])
        self.assertRedirects(self.post_period(url, sequence="1", label="P1"), self.list_url)

    def test_edit_cannot_take_another_periods_sequence_or_label(self):
        self.make_period(1, "P1")
        period = self.make_period(2, "P2")
        url = reverse("core:timetable-period-update", args=[period.pk])
        response = self.post_period(url, sequence="1", label="P1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.context["form"].errors), {"sequence", "label"})

    def test_edit_cannot_change_the_academic_year(self):
        other = AcademicYear.objects.create(
            name="2027-28", start_date=date(2027, 6, 1), end_date=date(2028, 3, 31)
        )
        period = self.make_period(1, "P1")
        url = reverse("core:timetable-period-update", args=[period.pk])
        self.assertNotIn("academic_year", self.client.get(url).context["form"].fields)
        self.post_period(url, sequence="1", label="P1", academic_year=str(other.pk))
        period.refresh_from_db()
        self.assertEqual(period.academic_year, self.year)

    # --- delete ----------------------------------------------------------------

    def test_unused_period_is_deleted_after_confirmation(self):
        period = self.make_period(1, "P1")
        url = reverse("core:timetable-period-delete", args=[period.pk])
        self.assertContains(self.client.get(url), "Delete period")
        self.assertTrue(TimetablePeriod.objects.exists())  # GET never deletes
        self.assertRedirects(self.client.post(url), self.list_url)
        self.assertFalse(TimetablePeriod.objects.exists())

    def _used_period(self):
        period = self.make_period(1, "P1")
        slot = TimetableSlot.create(
            period=period, weekday=0, section=self.six_a, offering=self.maths,
            start_date=date(2026, 6, 1),
        )
        return period, slot

    def test_used_period_cannot_be_deleted_and_the_message_is_clear(self):
        period, slot = self._used_period()
        url = reverse("core:timetable-period-delete", args=[period.pk])
        message = "This period is already used by timetable slots and cannot be deleted."
        confirm = self.client.get(url)
        self.assertContains(confirm, message)
        self.assertNotContains(confirm, "Delete period</button>")
        response = self.client.post(url, follow=True)
        self.assertContains(response, message)
        self.assertTrue(TimetablePeriod.objects.filter(pk=period.pk).exists())
        slot.refresh_from_db()
        self.assertIsNone(slot.end_date)
        self.assertEqual(TimetableSlot.objects.count(), 1)

    # --- permissions -----------------------------------------------------------

    def user_with(self, *actions):
        self.user_count = getattr(self, "user_count", 0) + 1
        user = self.make_user(f"u{self.user_count}_{'_'.join(actions) or 'none'}")
        user.user_permissions.add(
            *Permission.objects.filter(
                content_type__app_label="core",
                codename__in=[f"{a}_timetableperiod" for a in actions],
            )
        )
        return user

    def urls(self, period):
        return {
            "index": ("get", reverse("core:timetable-index"), "view"),
            "list": ("get", self.list_url, "view"),
            "add_get": ("get", reverse("core:timetable-period-create", args=[self.year.pk]), "add"),
            "add_post": ("post", reverse("core:timetable-period-create", args=[self.year.pk]),
                         "add"),
            "edit_get": ("get", reverse("core:timetable-period-update", args=[period.pk]),
                         "change"),
            "edit_post": ("post", reverse("core:timetable-period-update", args=[period.pk]),
                          "change"),
            "delete_get": ("get", reverse("core:timetable-period-delete", args=[period.pk]),
                           "delete"),
            "delete_post": ("post", reverse("core:timetable-period-delete", args=[period.pk]),
                            "delete"),
        }

    def test_each_operation_needs_its_own_permission(self):
        data = {"sequence": "9", "label": "X"}
        for name in self.urls(self.make_period(1, "seed")):
            for held in ALL_FOUR:
                TimetablePeriod.objects.all().delete()
                period = self.make_period(1, "P1")
                method, url, needed = self.urls(period)[name]
                client = self.client_class()
                client.force_login(self.user_with(held))
                response = getattr(client, method)(url, data if method == "post" else None)
                if held == needed:
                    self.assertNotEqual(response.status_code, 403, f"{name} with {held}")
                else:
                    self.assertEqual(response.status_code, 403, f"{name} with only {held}")
                    self.assertTrue(
                        TimetablePeriod.objects.filter(pk=period.pk, label="P1").exists(),
                        f"{name} with only {held} changed the period",
                    )

    def test_a_user_with_no_permissions_is_denied_everywhere(self):
        period = self.make_period(1, "P1")
        client = self.client_class()
        client.force_login(self.user_with())
        for name, (method, url, _) in self.urls(period).items():
            self.assertEqual(getattr(client, method)(url).status_code, 403, name)

    def test_row_actions_follow_the_users_permissions(self):
        self.make_period(1, "P1")
        client = self.client_class()
        client.force_login(self.user_with("view"))
        page = client.get(self.list_url)
        self.assertNotContains(page, "Add period")
        self.assertNotContains(page, ">Edit<")
        self.assertNotContains(page, ">Delete<")

    def test_teacher_is_denied(self):
        period = self.make_period(1, "P1")
        client = self.client_class()
        client.force_login(self.rao)
        for name, (method, url, _) in self.urls(period).items():
            self.assertEqual(getattr(client, method)(url).status_code, 403, name)
        self.assertTrue(TimetablePeriod.objects.exists())

    def test_anonymous_is_redirected_to_sign_in(self):
        period = self.make_period(1, "P1")
        client = self.client_class()
        for name, (method, url, _) in self.urls(period).items():
            response = getattr(client, method)(url)
            self.assertEqual(response.status_code, 302, name)
            self.assertIn("login", response["Location"], name)

    # --- scope -------------------------------------------------------------------

    def test_period_pages_carry_no_slot_workflow(self):
        self.make_period(1, "P1")
        page = self.client.get(self.list_url)
        self.assertNotContains(page, "slot", html=False, msg_prefix="periods page has no slots")


class NoAcademicYearTests(Phase4Fixture, TestCase):
    def test_index_has_an_empty_state_without_academic_years(self):
        admin = self.make_user("admin", Group.objects.get(name="School Administrators"))
        self.client.force_login(admin)
        response = self.client.get(reverse("core:timetable-index"))
        self.assertContains(response, "No Academic Years yet")


class PeriodFormAccessibilityTests(Phase4Fixture, TestCase):
    """UI_DESIGN_RULES section 6: labels, help, errors, announcement, focus."""

    def setUp(self):
        self.build_phase4()
        self.client.force_login(self.admin)
        self.url = reverse("core:timetable-period-create", args=[self.year.pk])

    def tag(self, response, field_id, name="input"):
        html = response.content.decode()
        found = re.search(rf"<{name}\b[^>]*\bid=\"{field_id}\"[^>]*>", html)
        self.assertIsNotNone(found, f"no <{name}> with id {field_id}")
        return found.group(0)

    def test_fields_have_labels_help_and_required_text(self):
        response = self.client.get(self.url)
        html = response.content.decode()
        for field in ("sequence", "label"):
            self.assertIn(f'for="id_{field}"', html)
            self.assertIn(f'id="id_{field}_helptext"', html)
            self.assertIn(
                f'aria-describedby="id_{field}_helptext"', self.tag(response, f"id_{field}")
            )
        self.assertIn("(required)", html)  # text, not only the asterisk
        self.assertIn("Fields marked with an asterisk are required", html)
        self.assertIn("erp-field-help", html)  # muted helper style

    def test_sequence_keeps_numeric_input_behaviour(self):
        tag = self.tag(self.client.get(self.url), "id_sequence")
        self.assertIn('type="number"', tag)
        self.assertIn('min="1"', tag)
        self.assertIn('inputmode="numeric"', tag)

    def test_clean_form_has_no_error_state_or_autofocus(self):
        response = self.client.get(self.url)
        html = response.content.decode()
        self.assertNotIn("aria-invalid", html)
        self.assertNotIn("autofocus", html)
        self.assertNotIn("erp-form-errors", html)

    def test_failed_post_marks_the_invalid_field_and_associates_its_error(self):
        response = self.client.post(self.url, {"sequence": "0", "label": "Assembly"})
        sequence = self.tag(response, "id_sequence")
        self.assertIn('aria-invalid="true"', sequence)
        self.assertIn("id_sequence_helptext id_sequence_error", sequence)
        self.assertContains(response, 'id="id_sequence_error"')
        self.assertContains(response, "Enter a position of 1 or more.")
        # the valid field is not flagged and its typed value is kept
        label = self.tag(response, "id_label")
        self.assertNotIn("aria-invalid", label)
        self.assertIn('value="Assembly"', label)
        self.assertIn('value="0"', sequence)

    def test_failed_post_announces_a_summary_and_starts_focus_on_the_first_invalid_field(self):
        response = self.client.post(self.url, {"sequence": "0", "label": ""})
        html = response.content.decode()
        self.assertRegex(html, r'<div class="erp-form-errors" role="alert"')
        self.assertIn('href="#id_sequence"', html)
        self.assertIn('href="#id_label"', html)
        self.assertIn("autofocus", self.tag(response, "id_sequence"))
        self.assertNotIn("autofocus", self.tag(response, "id_label"))
        self.assertEqual(html.count("autofocus"), 1)

    def test_duplicate_errors_are_field_local_and_actionable(self):
        TimetablePeriod.objects.create(academic_year=self.year, sequence=1, label="P1")
        response = self.client.post(self.url, {"sequence": "1", "label": "P1"})
        self.assertContains(response, "already uses this order number")
        self.assertContains(response, "already uses this label")
        for field in ("sequence", "label"):
            self.assertIn('aria-invalid="true"', self.tag(response, f"id_{field}"))

    def test_missing_values_say_what_to_enter(self):
        response = self.client.post(self.url, {"sequence": "", "label": ""})
        self.assertContains(response, "Enter a position, for example 1.")
        self.assertContains(response, "Enter a label, for example P1.")

    def test_edit_form_has_the_same_error_wiring(self):
        period = TimetablePeriod.objects.create(academic_year=self.year, sequence=1, label="P1")
        url = reverse("core:timetable-period-update", args=[period.pk])
        response = self.client.post(url, {"sequence": "-3", "label": "P1"})
        self.assertIn('aria-invalid="true"', self.tag(response, "id_sequence"))
        self.assertContains(response, 'href="#id_sequence"')


class PeriodTableMobileTests(Phase4Fixture, TestCase):
    """The project's dense-table rule and 44px tap targets (UI_DESIGN_RULES 5, 15)."""

    def setUp(self):
        self.build_phase4()
        self.client.force_login(self.admin)
        TimetablePeriod.objects.create(academic_year=self.year, sequence=1, label="P1")

    def test_tables_scroll_inside_their_own_labelled_region(self):
        for url, label in (
            (reverse("core:timetable-index"), "Academic Years"),
            (reverse("core:timetable-periods", args=[self.year.pk]), "Periods"),
        ):
            html = self.client.get(url).content.decode()
            self.assertIn(f'class="erp-table-scroll" role="region" aria-label="{label}"', html)
            self.assertIn('tabindex="0"', html)

    def test_index_and_periods_tables_sit_in_the_shared_panel(self):
        for url in (
            reverse("core:timetable-index"),
            reverse("core:timetable-periods", args=[self.year.pk]),
        ):
            html = self.client.get(url).content.decode()
            self.assertRegex(
                html, r'<div class="erp-panel">\s*<div class="erp-table-scroll" role="region"'
            )
            # erp-keep must be absent so the table scrolls on phones instead of squeezing.
            self.assertNotIn("erp-keep", html)

    def test_row_actions_are_buttons_so_they_get_the_touch_target_size(self):
        html = self.client.get(
            reverse("core:timetable-periods", args=[self.year.pk])
        ).content.decode()
        self.assertRegex(html, r'<a class="btn [^"]*" href="/timetable/periods/\d+/edit/"')
        self.assertRegex(
            html, r'<a class="btn btn-outline-danger[^"]*" href="/timetable/periods/\d+/delete/"'
        )
