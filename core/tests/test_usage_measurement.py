"""Option B2: privacy-safe usage measurement store (ADR 0027).

Covers spec section 10.2: the store refuses anything outside its enums and column-use rules, it
records nothing unless switched on and never under Global Privacy Control, a write can never break
the caller's transaction, rows older than 180 days are purged, the beacon is closed to signed-out
browsers and does not keep a session alive, and the sign-in and session signals carry no person.
"""

import json
import logging
import time
from datetime import date, timedelta
from io import StringIO
from unittest import mock

from django.conf import settings
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db import DatabaseError, IntegrityError, connection, models, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.middleware import LOGOUT_PATH, SEEN_KEY, STARTED_KEY, USAGE_BEACON_PATH
from core import usage
from core.models import TEACHERS_GROUP_NAME, Guardian, UsageCounter

TODAY = date(2026, 11, 20)
BEACON = "/u/"
XHR = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}
ON = override_settings(USAGE_MEASUREMENT_ENABLED=True)


def rows(**filters):
    return list(UsageCounter.objects.filter(**filters).values_list("step", "count"))


def count_of(**filters):
    row = UsageCounter.objects.filter(**filters).first()
    return row.count if row else 0


class FakeRequest:
    """Only what record() reads: headers."""

    def __init__(self, headers=None):
        self.headers = headers or {}


SIGN_IN_OK = {"area": "admin", "workflow": "sign_in", "step": "completed"}


class Users:
    def make_users(self):
        User = get_user_model()
        self.password = "a-long-test-password-1"
        self.admin = User.objects.create_user("office1", password=self.password)
        self.admin.groups.add(Group.objects.get(name="School Administrators"))
        self.teacher = User.objects.create_user("teach1", password=self.password)
        self.teacher.groups.add(Group.objects.get(name=TEACHERS_GROUP_NAME))
        self.multi = User.objects.create_user("both1", password=self.password)
        self.multi.groups.add(Group.objects.get(name="School Administrators"),
                              Group.objects.get(name=TEACHERS_GROUP_NAME))


# --- the store -----------------------------------------------------------------------------------


class SettingTests(TestCase):
    def test_measurement_is_off_by_default(self):
        self.assertIs(settings.USAGE_MEASUREMENT_ENABLED, False)

    def test_record_is_a_no_op_when_off(self):
        self.assertFalse(usage.record(FakeRequest(), **SIGN_IN_OK))
        self.assertFalse(UsageCounter.objects.exists())

    @ON
    def test_record_is_a_no_op_under_global_privacy_control(self):
        self.assertFalse(usage.record(FakeRequest({"Sec-GPC": "1"}), **SIGN_IN_OK))
        self.assertFalse(UsageCounter.objects.exists())


@ON
class RecordTests(TestCase):
    def test_creates_then_increments_one_row(self):
        self.assertTrue(usage.record(FakeRequest(), **SIGN_IN_OK))
        self.assertTrue(usage.record(None, **SIGN_IN_OK))
        self.assertEqual(UsageCounter.objects.count(), 1)
        row = UsageCounter.objects.get()
        self.assertEqual(row.count, 2)
        self.assertEqual((row.page_route, row.device, row.display, row.platform), ("", "", "", ""))

    def test_day_is_the_business_date(self):
        with mock.patch("core.usage.business_today", return_value=TODAY):
            usage.record(None, **SIGN_IN_OK)
        self.assertEqual(UsageCounter.objects.get().day, TODAY)

    def test_creation_race_rolls_back_only_the_insert_and_retries_the_update(self):
        real_increment = usage._increment
        calls = []

        def other_request_creates_between(dims):
            calls.append(1)
            if len(calls) == 1:  # the first update finds nothing; then "another request" inserts
                UsageCounter.objects.create(**dims, count=1)
                return 0
            return real_increment(dims)

        with mock.patch("core.usage._increment", side_effect=other_request_creates_between):
            # The real insert now hits the unique constraint inside savepoint S2.
            self.assertTrue(usage.record(None, **SIGN_IN_OK))
        self.assertEqual(len(calls), 2)
        self.assertEqual(UsageCounter.objects.get().count, 2)

    def test_insert_integrity_error_does_not_escape(self):
        with mock.patch("core.usage._insert", side_effect=IntegrityError("dup")), \
                mock.patch("core.usage._increment", side_effect=[0, 0]):
            usage.record(None, **SIGN_IN_OK)  # no exception

    def test_database_error_leaves_the_outer_transaction_usable(self):
        def broken(dims):
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 / 0")  # a real error: PostgreSQL aborts the transaction

        logger = logging.getLogger("core.usage")
        with transaction.atomic():
            Guardian.objects.create(full_name="Kept By Outer Commit")
            with mock.patch("core.usage._increment", side_effect=broken), \
                    mock.patch.object(logger, "warning") as warn:
                self.assertFalse(usage.record(None, **SIGN_IN_OK))
            self.assertTrue(Guardian.objects.filter(full_name="Kept By Outer Commit").exists())
        self.assertTrue(Guardian.objects.filter(full_name="Kept By Outer Commit").exists())
        self.assertFalse(UsageCounter.objects.exists())
        warn.assert_called_once()
        self.assertNotIn("sign_in", repr(warn.call_args))

    def test_invalid_value_is_refused_before_the_database(self):
        with self.assertRaises(usage.InvalidEvent):
            usage.validate(area="admin", workflow="sign_in", step="deleted")
        with self.assertNumQueries(0):
            self.assertFalse(usage.record(None, area="admin", workflow="sign_in", step="deleted"))
        with self.assertNumQueries(0):
            self.assertFalse(usage.record(None, area="admin", workflow="sign_in",
                                          step="completed", device="iPhone 15"))

    def test_unknown_dimension_names_are_refused(self):
        with self.assertRaises(TypeError):
            usage.record(None, **SIGN_IN_OK, user_id=3)

    def test_code_level_rules_beyond_the_database(self):
        bad = [
            {"area": "teacher", "workflow": "sign_in", "step": "viewed"},       # step not in workflow
            {"area": "admin", "workflow": "marks_entry", "step": "started"},    # wrong surface
            {"area": "teacher", "workflow": "page", "step": "viewed",
             "page_route": "core:student-list"},                                # admin route
            {"area": "teacher", "workflow": "sign_in", "step": "completed",
             "duration_bucket": "<5s"},                                         # untimed workflow
            {"area": "public", "workflow": "page", "step": "viewed", "page_route": "other"},
        ]
        for dims in bad:
            with self.subTest(dims=dims), self.assertRaises(usage.InvalidEvent):
                usage.validate(**dims)

    def test_a_route_outside_the_allow_list_is_mapped_to_other(self):
        self.assertEqual(usage.page_route_for("core:student-list"), "core:student-list")
        self.assertEqual(usage.page_route_for("core:academic-year-create"), "other")
        self.assertEqual(usage.page_route_for("/students/123/"), "other")
        self.assertEqual(usage.page_route_for(None), "other")
        usage.record(None, area="admin", workflow="page", step="viewed",
                     page_route=usage.page_route_for("core:academic-year-create"))
        self.assertEqual(UsageCounter.objects.get().page_route, "other")


class ConstraintTests(TestCase):
    """The database itself refuses unknown values and wrong combinations."""

    def assert_refused(self, **fields):
        base = {"day": TODAY, "area": "teacher", "workflow": "marks_entry", "step": "attempt",
                "count": 1}
        base.update(fields)
        with self.assertRaises(IntegrityError), transaction.atomic():
            UsageCounter.objects.create(**base)

    def test_valid_row_is_accepted(self):
        UsageCounter.objects.create(day=TODAY, area="teacher", workflow="marks_entry",
                                    step="completed", duration_bucket="1-3m", size_bucket="21-40",
                                    device="phone", display="installed", platform="android")

    def test_enum_values(self):
        for field, value in [("area", "staff"), ("workflow", "fees"), ("step", "abandoned"),
                             ("device", "watch"), ("display", "kiosk"), ("platform", "linux"),
                             ("size_bucket", "35"), ("area", "")]:
            with self.subTest(field=field):
                self.assert_refused(**{field: value})

    def test_page_route_allow_list(self):
        self.assert_refused(workflow="page", step="viewed", page_route="core:academic-year-create")
        self.assert_refused(workflow="page", step="viewed", page_route="/students/123/")

    def test_column_use_rules(self):
        self.assert_refused(page_route="other")                                     # not page
        self.assert_refused(workflow="page", step="viewed")                         # page, no route
        self.assert_refused(area="guardian", workflow="notice_view", step="viewed",
                            age_bucket="same_day", size_bucket="1-20")              # size on notice
        self.assert_refused(area="guardian", workflow="notice_view", step="viewed")  # no age
        self.assert_refused(age_bucket="later")                                     # age elsewhere
        self.assert_refused(duration_bucket="<5s")                                  # not completed
        self.assert_refused(area="admin", workflow="sign_in", step="completed",
                            duration_bucket="<5s")                                  # untimed
        self.assert_refused(area="public")                                          # teacher flow
        self.assert_refused(area="public", workflow="page", step="viewed",
                            page_route="core:my-home")
        self.assert_refused(area="multi", workflow="sign_in", step="failed")
        self.assert_refused(area="multi")

    def test_count_is_at_least_one(self):
        self.assert_refused(count=0)

    def test_identical_dimensions_cannot_make_two_rows(self):
        UsageCounter.objects.create(day=TODAY, area="teacher", workflow="marks_entry",
                                    step="attempt")
        self.assert_refused()

    def test_no_field_can_hold_free_text(self):
        for field in UsageCounter._meta.concrete_fields:
            with self.subTest(field=field.name):
                if field.name in ("id", "day", "count"):
                    continue
                self.assertIsInstance(field, models.CharField)
                self.assertTrue(field.choices, f"{field.name} has no fixed choices")
                self.assertLessEqual(field.max_length, 40)
        names = {f.name for f in UsageCounter._meta.concrete_fields}
        self.assertEqual(names, {
            "id", "day", "area", "workflow", "step", "page_route", "duration_bucket",
            "size_bucket", "age_bucket", "device", "display", "platform", "count"})
        self.assertFalse([f for f in UsageCounter._meta.get_fields() if f.is_relation])

    def test_not_registered_in_django_admin(self):
        self.assertNotIn(UsageCounter, admin.site._registry)


class ClientHeaderTests(TestCase):
    def test_only_enum_values_are_accepted(self):
        self.assertEqual(
            usage.parse_client_header("device=phone;display=installed;platform=android"),
            {"device": "phone", "display": "installed", "platform": "android"})
        self.assertEqual(usage.parse_client_header("device=phone;display=kiosk;ua=Mozilla"),
                         {"device": "phone", "display": "", "platform": ""})
        self.assertEqual(usage.parse_client_header(None),
                         {"device": "", "display": "", "platform": ""})
        self.assertEqual(usage.parse_client_header("device=phone;" + "x" * 200),
                         {"device": "", "display": "", "platform": ""})

    @ON
    def test_record_takes_device_fields_from_the_header(self):
        usage.record(FakeRequest({"X-ERP-Client": "device=tablet;display=browser;platform=ios"}),
                     **SIGN_IN_OK)
        row = UsageCounter.objects.get()
        self.assertEqual((row.device, row.display, row.platform), ("tablet", "browser", "ios"))


# --- retention and reporting ---------------------------------------------------------------------


class PurgeTests(TestCase):
    def make(self, day, step="completed"):
        UsageCounter.objects.create(day=day, area="admin", workflow="sign_in", step=step)

    def run_purge(self):
        out = StringIO()
        with mock.patch("core.usage.business_today", return_value=TODAY):
            call_command("purge_usage_counters", stdout=out)
        return out.getvalue()

    def test_keeps_exactly_the_last_180_days(self):
        self.make(TODAY - timedelta(days=180))
        self.make(TODAY - timedelta(days=181), step="failed")
        self.make(TODAY - timedelta(days=179))
        self.make(TODAY)
        self.assertFalse(settings.USAGE_MEASUREMENT_ENABLED)  # runs with measurement off
        self.assertEqual(self.run_purge().strip(), "Deleted 2 usage counter rows.")
        self.assertEqual(sorted(UsageCounter.objects.values_list("day", flat=True)),
                         [TODAY - timedelta(days=179), TODAY])

    def test_second_run_deletes_nothing_and_prints_only_a_number(self):
        self.make(TODAY - timedelta(days=200))
        self.run_purge()
        self.assertEqual(self.run_purge().strip(), "Deleted 0 usage counter rows.")

    def test_cron_start_command_runs_purge_as_its_own_step(self):
        readme = (settings.BASE_DIR / "README.md").read_text(encoding="utf-8")
        self.assertIn('sh -c "python manage.py purge_usage_counters; python manage.py '
                      'expire_import_batches', readme)


class ReportTests(TestCase):
    def report(self, *args):
        out = StringIO()
        with mock.patch("core.usage.business_today", return_value=TODAY):
            call_command("usage_report", *args, stdout=out)
        return out.getvalue()

    def test_warns_when_a_row_is_older_than_the_cutoff(self):
        UsageCounter.objects.create(day=TODAY - timedelta(days=181), area="admin",
                                    workflow="sign_in", step="completed")
        self.assertIn("older than the 180-day retention", self.report())

    def test_no_warning_when_rows_are_in_range(self):
        UsageCounter.objects.create(day=TODAY, area="admin", workflow="sign_in", step="completed")
        self.assertNotIn("older than", self.report())

    def test_small_cells_are_hidden_after_filtering_and_weekly_grouping(self):
        monday = TODAY - timedelta(days=TODAY.weekday())
        UsageCounter.objects.create(day=monday, area="admin", workflow="sign_in", step="failed",
                                    count=3)
        UsageCounter.objects.create(day=monday + timedelta(days=1), area="admin",
                                    workflow="sign_in", step="failed", count=3)
        UsageCounter.objects.create(day=monday, area="teacher", workflow="sign_in",
                                    step="completed", count=4)
        UsageCounter.objects.create(day=monday, area="admin", workflow="sign_in",
                                    step="completed", count=2)
        out = self.report("--weeks", "1")
        self.assertRegex(out, r"sign_in\s+failed\s+6")        # two daily 3s merge into one week
        self.assertRegex(out, r"sign_in\s+completed\s+6")     # 4 + 2 across areas
        out = self.report("--weeks", "1", "--area", "teacher")
        self.assertRegex(out, r"sign_in\s+completed\s+<5")    # 4 alone is hidden after filtering
        self.assertNotRegex(out, r"\s4\s")


# --- the beacon ----------------------------------------------------------------------------------


def beacon_body(events=None, **shared):
    body = {"d": "phone", "x": "browser", "p": "android", "r": "core:my-home", "a": "teacher"}
    body.update(shared)
    body["e"] = events if events is not None else [{"w": "page", "s": "viewed"}]
    return json.dumps(body)


class BeaconTests(Users, TestCase):
    def setUp(self):
        self.make_users()
        self.client.force_login(self.teacher)

    def post(self, body, client=None, **extra):
        client = client or self.client
        return client.post(BEACON, body, content_type="application/json", **XHR, **extra)

    def test_path_matches_the_url_name(self):
        self.assertEqual(reverse("usage-beacon"), BEACON)
        self.assertEqual(USAGE_BEACON_PATH, BEACON)
        self.assertEqual(LOGOUT_PATH, reverse("logout"))

    def test_anonymous_gets_401_not_a_redirect(self):
        response = self.post(beacon_body(), client=Client())
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.content, b"")
        self.assertIn("no-store", response["Cache-Control"])

    def test_anonymous_without_xhr_header_also_gets_401(self):
        response = Client().post(BEACON, beacon_body(), content_type="application/json")
        self.assertEqual(response.status_code, 401)

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(BEACON).status_code, 405)

    def test_missing_csrf_token_is_refused(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.teacher)
        self.assertEqual(self.post(beacon_body(), client=client).status_code, 403)

    def test_off_answers_204_and_records_nothing(self):
        response = self.post(beacon_body())
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertFalse(UsageCounter.objects.exists())

    @ON
    def test_records_an_allowed_page_view(self):
        response = self.post(beacon_body())
        self.assertEqual(response.status_code, 204)
        row = UsageCounter.objects.get()
        self.assertEqual((row.area, row.workflow, row.step, row.page_route, row.device),
                         ("teacher", "page", "viewed", "core:my-home", "phone"))

    @ON
    def test_route_is_used_only_for_page_events(self):
        self.post(beacon_body([{"w": "teacher_home", "s": "completed", "b": "<5s"}]))
        row = UsageCounter.objects.get()
        self.assertEqual((row.workflow, row.page_route, row.duration_bucket),
                         ("teacher_home", "", "<5s"))

    @ON
    def test_global_privacy_control_records_nothing(self):
        response = self.post(beacon_body(), HTTP_SEC_GPC="1")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(UsageCounter.objects.exists())

    @ON
    def test_oversized_or_too_many_events_are_dropped_whole(self):
        too_many = [{"w": "page", "s": "viewed"}] * 21
        self.assertEqual(self.post(beacon_body(too_many)).status_code, 400)
        big = beacon_body([{"w": "page", "s": "viewed", "pad": "x" * 2100}])
        self.assertEqual(self.post(big).status_code, 400)
        self.assertFalse(UsageCounter.objects.exists())

    @ON
    def test_one_bad_field_drops_the_whole_batch(self):
        cases = [
            beacon_body([{"w": "page", "s": "viewed"}, {"w": "page", "s": "clicked"}]),
            beacon_body([{"w": "page", "s": "viewed", "score": 85}]),
            beacon_body(d="iPhone"),
            beacon_body(a="admin"),                       # not one of this teacher's areas
            beacon_body(a="multi"),
            beacon_body(r="/students/123/"),              # a path, never a route name
            beacon_body(r="core:student-list"),           # an admin route on the teacher surface
            beacon_body([{"w": "marks_entry", "s": "saved"}]),   # server-recorded only
            beacon_body([{"w": "sign_in", "s": "completed"}]),   # server-recorded only
            beacon_body([{"w": "page", "s": "viewed", "b": "<5s"}]),
            beacon_body([{"w": "page", "s": "viewed"}], d=["phone"]),
            beacon_body([]),
            "not json",
            json.dumps([1, 2]),
            beacon_body(extra="x"),
        ]
        for body in cases:
            with self.subTest(body=body[:80]):
                self.assertEqual(self.post(body).status_code, 400)
        self.assertFalse(UsageCounter.objects.exists())

    @ON
    def test_other_route_is_accepted(self):
        self.post(beacon_body(r="other"))
        self.assertEqual(UsageCounter.objects.get().page_route, "other")

    @ON
    def test_rate_limit_drops_above_200_events_per_hour(self):
        twenty = [{"w": "page", "s": "viewed"}] * 20
        for _ in range(11):
            self.assertEqual(self.post(beacon_body(twenty)).status_code, 204)
        self.assertEqual(count_of(workflow="page"), 200)

    @ON
    def test_the_rate_window_restarts_after_an_hour(self):
        twenty = [{"w": "page", "s": "viewed"}] * 20
        for _ in range(10):
            self.post(beacon_body(twenty))
        session = self.client.session
        session[usage.RATE_KEY] = [int(time.time()) - 3601, 200]
        session.save()
        self.post(beacon_body(twenty))
        self.assertEqual(count_of(workflow="page"), 220)

    @ON
    def test_nothing_from_the_body_or_header_is_logged(self):
        with mock.patch.object(logging.Logger, "_log") as log:
            self.post(beacon_body(), HTTP_X_ERP_CLIENT="device=phone;display=browser;platform=ios")
            self.post(beacon_body(d="iPhone-secret"))
        for call in log.call_args_list:
            text = repr(call)
            self.assertNotIn("iPhone-secret", text)
            self.assertNotIn("core:my-home", text)
            self.assertNotIn("platform=ios", text)

    def test_beacon_does_not_move_the_idle_clock(self):
        session = self.client.session
        session[SEEN_KEY] = time.time() - 20 * 60
        session[STARTED_KEY] = time.time() - 20 * 60
        session.save()
        before = self.client.session[SEEN_KEY]
        self.post(beacon_body())
        self.assertEqual(self.client.session[SEEN_KEY], before)

    def test_an_expired_beacon_without_script_headers_still_gets_401(self):
        session = self.client.session
        session[SEEN_KEY] = time.time() - 31 * 60
        session[STARTED_KEY] = time.time() - 31 * 60
        session.save()
        response = self.client.post(BEACON, beacon_body(), content_type="application/json")
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("Clear-Site-Data", response)

    def test_an_expired_session_is_still_signed_out_with_401(self):
        session = self.client.session
        session[SEEN_KEY] = time.time() - 31 * 60
        session[STARTED_KEY] = time.time() - 31 * 60
        session.save()
        self.assertEqual(self.post(beacon_body()).status_code, 401)
        self.assertNotIn("_auth_user_id", self.client.session)


# --- server-side sign-in and session signals ----------------------------------------------------


@ON
class SignInSignalTests(Users, TestCase):
    def setUp(self):
        self.make_users()
        self.login_url = reverse("login")

    def sign_in(self, username, password=None, client=None):
        client = client or self.client
        return client.post(self.login_url, {"username": username,
                                            "password": password or self.password})

    def test_success_records_the_users_area_and_no_person(self):
        self.sign_in("teach1")
        self.assertEqual(rows(area="teacher", workflow="sign_in"), [("completed", 1)])
        self.sign_in("both1", client=Client())
        self.assertEqual(rows(area="multi", workflow="sign_in"), [("completed", 1)])

    def test_failed_sign_in_of_a_real_guardian_is_public(self):
        from core import guardian_accounts as ga
        from core.tests.test_phase6_access_boundary import METHOD

        guardian = Guardian.objects.create(full_name="Meena Rao")
        ga.create_guardian_account(guardian=guardian, username="meena", method=METHOD,
                                   note="known", actor=self.admin)
        self.sign_in("meena", "wrong-password")
        self.assertEqual(list(UsageCounter.objects.values_list("area", "workflow", "step")),
                         [("public", "sign_in", "failed")])

    def test_throttled_attempt_is_counted_as_throttled_not_failed(self):
        with mock.patch("accounts.security.is_throttled", return_value=True):
            self.sign_in("teach1")
        self.assertEqual(rows(workflow="sign_in"), [("throttled", 1)])

    def test_login_page_get_records_nothing_in_b2(self):
        self.client.get(self.login_url)
        self.assertFalse(UsageCounter.objects.exists())

    def test_gpc_sign_in_records_nothing(self):
        self.client.post(self.login_url, {"username": "teach1", "password": self.password},
                         HTTP_SEC_GPC="1")
        self.assertFalse(UsageCounter.objects.exists())

    def test_forced_password_change_records_first_change(self):
        self.teacher.must_change_password = True
        self.teacher.save()
        self.client.force_login(self.teacher)
        new = "another-long-password-2"
        self.client.post(reverse("password_change"), {
            "old_password": self.password, "new_password1": new, "new_password2": new})
        self.assertEqual(rows(workflow="sign_in", area="teacher"),
                         [("password_changed_first", 1)])

    def test_an_ordinary_password_change_records_nothing(self):
        self.client.force_login(self.teacher)
        new = "another-long-password-2"
        self.client.post(reverse("password_change"), {
            "old_password": self.password, "new_password1": new, "new_password2": new})
        self.assertFalse(UsageCounter.objects.exists())


@ON
class SessionSignalTests(Users, TestCase):
    def setUp(self):
        self.make_users()
        self.client.force_login(self.admin)

    def expire(self, seconds_idle=31 * 60, started=None):
        session = self.client.session
        session[SEEN_KEY] = time.time() - seconds_idle
        session[STARTED_KEY] = time.time() - (started or seconds_idle)
        session.save()

    def test_idle_and_unsaved_expiry_are_counted_by_route_area(self):
        self.expire()
        self.client.post(reverse("core:student-list"))
        self.assertEqual(sorted(rows(workflow="session", area="admin")),
                         [("expired_idle", 1), ("expired_unsaved", 1)])

    def test_signing_out_after_expiry_is_not_counted_as_unsaved(self):
        self.expire()
        self.client.post(reverse("logout"))
        self.assertEqual(rows(workflow="session"), [("expired_idle", 1)])

    def test_absolute_limit_expiry(self):
        self.expire(seconds_idle=60, started=9 * 3600)
        self.client.get(reverse("core:student-list"))
        self.assertEqual(rows(workflow="session"), [("expired_limit", 1)])

    def test_expiry_on_a_page_outside_any_area_uses_the_users_area(self):
        self.client.logout()
        self.client.force_login(self.teacher)
        self.expire()
        self.client.get(reverse("home"))
        self.assertEqual(rows(workflow="session", area="teacher"), [("expired_idle", 1)])

    def test_relogin_within_ten_minutes_of_a_real_expiry(self):
        self.expire()
        self.client.get(reverse("core:student-list"))
        marker = self.client.session.get(usage.EXPIRED_MARKER)
        self.assertIsInstance(marker, int)
        self.client.post(reverse("login"), {"username": "office1", "password": self.password})
        self.assertEqual(rows(workflow="session", step="relogin_after_expiry"),
                         [("relogin_after_expiry", 1)])
        self.assertNotIn(usage.EXPIRED_MARKER, self.client.session)

    def test_forged_expired_query_without_a_marker_records_nothing(self):
        client = Client()
        client.post(reverse("login") + "?expired=idle",
                    {"username": "office1", "password": self.password})
        self.assertFalse(UsageCounter.objects.filter(workflow="session").exists())

    def test_old_marker_records_nothing_and_is_still_deleted(self):
        client = Client()
        client.get(reverse("login"))
        session = client.session
        session[usage.EXPIRED_MARKER] = int(time.time()) - 11 * 60
        session.save()
        client.post(reverse("login"), {"username": "office1", "password": self.password})
        self.assertFalse(UsageCounter.objects.filter(step="relogin_after_expiry").exists())
        self.assertNotIn(usage.EXPIRED_MARKER, client.session)

    def test_non_integer_marker_is_ignored(self):
        client = Client()
        client.get(reverse("login"))
        session = client.session
        session[usage.EXPIRED_MARKER] = "recent"
        session.save()
        client.post(reverse("login"), {"username": "office1", "password": self.password})
        self.assertFalse(UsageCounter.objects.filter(step="relogin_after_expiry").exists())

    @override_settings(USAGE_MEASUREMENT_ENABLED=False)
    def test_off_leaves_no_marker_and_no_rows(self):
        self.expire()
        self.client.get(reverse("core:student-list"))
        self.assertNotIn(usage.EXPIRED_MARKER, self.client.session)
        self.assertFalse(UsageCounter.objects.exists())

    def test_a_failing_store_never_breaks_sign_in(self):
        client = Client()
        with mock.patch("core.usage._increment", side_effect=DatabaseError("down")):
            response = client.post(reverse("login"),
                                   {"username": "office1", "password": self.password})
        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", client.session)
