"""Option B3: workflow measurement and the evidence report (ADR 0027; spec sections 6, 6.1, 9).

Covers spec section 10.3: each workflow records only its listed steps at the stated moments, with
the right duration and size buckets; nothing is recorded for leaving a page; session timers hold
only numbers and vanish on completion and sign-out; the page carries the measurement attributes
only when switched on and without Global Privacy Control; route names never paths; notice views by
age only; the browser code is guarded by navigator.globalPrivacyControl and keeps events in page
memory only; and usage_report hides small cells after every filter and grouping, protects totals
with complementary suppression and prints n/a below every minimum denominator.
"""

import csv
import io
import json
import re
import time
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.management import call_command
from django.db import DatabaseError, IntegrityError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.middleware import SEEN_KEY, STARTED_KEY
from core import usage
from core.models import (
    AttendanceRegister,
    AttendanceStatus,
    SectionClassTeacher,
    TermPublication,
    UsageCounter,
)
from core.tests.phase4_fixtures import Phase4Fixture
from core.tests.test_marks_autosave import AutosaveFixture
from core.tests.test_phase5_teacher_attendance import MONDAY, on
from core.tests.test_phase6_publication import PublicationFixture
from core.tests.test_phase7_announcements import AnnouncementFixture

ON = override_settings(USAGE_MEASUREMENT_ENABLED=True)
HX = {"HTTP_HX_REQUEST": "true"}
XHR = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}
CLIENT = {"HTTP_X_ERP_CLIENT": "device=phone;display=installed;platform=android"}
BASE_DIR = Path(settings.BASE_DIR)
ERP_JS = (BASE_DIR / "static" / "js" / "erp.js").read_text(encoding="utf-8")
T0 = 1_800_000_000  # a fixed epoch second for patched clocks


def rows(**filters):
    return sorted(UsageCounter.objects.filter(**filters).values_list("workflow", "step", "count"))


def one(**filters):
    return UsageCounter.objects.get(**filters)


def clock(seconds):
    """Patch the usage clock to T0 + seconds."""
    return mock.patch("core.usage._now", return_value=T0 + seconds)


def usage_block():
    start = ERP_JS.index("// Usage measurement (ADR 0027")
    return ERP_JS[start:ERP_JS.index("// End of usage measurement.", start)]


# --- buckets -------------------------------------------------------------------------------------


class BucketTests(TestCase):
    def test_duration_buckets(self):
        cases = [(0, "<5s"), (4.9, "<5s"), (5, "5-15s"), (14.9, "5-15s"), (15, "15-60s"),
                 (60, "1-3m"), (180, "3-10m"), (600, "10-30m"), (1800, ">30m"), (99999, ">30m")]
        for seconds, bucket in cases:
            self.assertEqual(usage.duration_bucket(seconds), bucket, seconds)
        self.assertEqual(usage.duration_bucket(-3), "<5s")  # a clock step back never fails

    def test_size_buckets(self):
        self.assertEqual(usage.size_bucket(0), "")
        for n, bucket in ((1, "1-20"), (20, "1-20"), (21, "21-40"), (40, "21-40"), (41, "41+")):
            self.assertEqual(usage.size_bucket(n), bucket)

    def test_age_buckets(self):
        for days, bucket in ((-1, "same_day"), (0, "same_day"), (1, "1-2d"), (2, "1-2d"),
                             (3, "3-7d"), (7, "3-7d"), (8, "later")):
            self.assertEqual(usage.age_bucket(days), bucket)

    def test_no_abandoned_step_exists_anywhere(self):
        self.assertNotIn("abandoned", usage.STEPS)
        self.assertNotIn("abandon", ERP_JS.lower())


# --- page attributes and the sign-in page --------------------------------------------------------


class PageAttributeTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        self.student, _ = self.make_student("Asha")
        self.teacher = Client()
        self.teacher.force_login(self.rao)
        self.office = Client()
        self.office.force_login(self.admin)

    def body(self, response):
        return re.search(r"<body[^>]*>", response.content.decode()).group(0)

    def test_off_by_default_no_attributes(self):
        body = self.body(self.teacher.get(reverse("core:my-home")))
        self.assertNotIn("data-erp-usage", body)
        self.assertNotIn("data-erp-route", body)

    @ON
    def test_on_carries_route_name_and_area(self):
        body = self.body(self.teacher.get(reverse("core:my-home")))
        self.assertIn('data-erp-usage="1"', body)
        self.assertIn('data-erp-route="core:my-home"', body)
        self.assertIn('data-erp-area="teacher"', body)
        self.assertIn(f'data-erp-usage-url="{reverse("usage-beacon")}"', body)

    @ON
    def test_global_privacy_control_header_leaves_them_out(self):
        body = self.body(self.teacher.get(reverse("core:my-home"), HTTP_SEC_GPC="1"))
        self.assertNotIn("data-erp-usage", body)
        self.assertNotIn("data-erp-route", body)
        self.assertNotIn("data-erp-area", body)

    @ON
    def test_route_name_never_the_path(self):
        url = reverse("core:student-detail", args=[self.student.pk])
        body = self.body(self.office.get(url))
        self.assertIn('data-erp-route="core:student-detail"', body)
        self.assertIn('data-erp-area="admin"', body)
        self.assertNotIn(url, body)

    @ON
    def test_a_route_outside_the_allow_list_is_other(self):
        body = self.body(self.teacher.get(reverse("core:my-subjects")))
        self.assertIn('data-erp-route="other"', body)

    @ON
    def test_a_route_of_another_area_is_other(self):
        # A teacher refused an office page stays in the teacher area; the route is not theirs.
        body = self.body(self.teacher.get(reverse("core:student-list")))
        self.assertIn('data-erp-area="teacher"', body)
        self.assertIn('data-erp-route="other"', body)

    @ON
    def test_signed_out_pages_never_carry_them(self):
        body = self.body(Client().get(reverse("login")))
        self.assertNotIn("data-erp-usage", body)


@ON
class SignInPageTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()

    def test_sign_in_page_views_are_not_counted(self):
        """Deferred by decision: public GETs can come from bots and would make a hot counter;
        the sign-in attempt signals already feed the login triggers."""
        for _ in range(3):
            Client().get(reverse("login"), **CLIENT)
        self.assertFalse(UsageCounter.objects.exists())

    def test_sign_in_attempts_are_still_counted(self):
        Client().post(reverse("login"), {"username": "rao", "password": "wrong"})
        Client().post(reverse("login"), {"username": "rao", "password": "pass-12345"})
        self.assertEqual(rows(workflow="sign_in"), [("sign_in", "completed", 1),
                                                    ("sign_in", "failed", 1)])
        self.assertEqual(rows(workflow="page"), [])


# --- attendance capture --------------------------------------------------------------------------


class AttendanceFixture(Phase4Fixture):
    def setUp(self):
        self.build_phase4()
        for patch in on(MONDAY):
            patch.start()
            self.addCleanup(patch.stop)
        SectionClassTeacher.assign(teacher=self.rao, academic_year=self.year,
                                   section=self.six_a, start_date=date(2026, 6, 1))
        _, self.asha = self.make_student("Asha")
        _, self.ravi = self.make_student("Ravi")
        self.teacher = Client()
        self.teacher.login(username="rao", password="pass-12345")
        self.url = reverse("core:my-attendance", args=[self.six_a.pk])
        self.autosave = reverse("core:my-attendance-autosave", args=[self.six_a.pk])
        self.bulk = reverse("core:my-attendance-autosave-present", args=[self.six_a.pk])
        self.submit = reverse("core:my-attendance-submit", args=[self.six_a.pk])

    def open_register(self):
        self.teacher.post(self.url, {"action": "open"})
        return AttendanceRegister.objects.get(section=self.six_a, date=MONDAY)

    def fill(self, register):
        for enrollment in (self.asha, self.ravi):
            register.save_draft_entry(enrollment=enrollment, status=AttendanceStatus.PRESENT)

    def row(self, enrollment, status="PRESENT", client=None, **extra):
        data = {"enrollment": enrollment.pk, f"status_{enrollment.pk}": status,
                f"note_{enrollment.pk}": ""}
        return (client or self.teacher).post(self.autosave, data, **HX, **extra)


@ON
class AttendanceWorkflowTests(AttendanceFixture, TestCase):
    def test_first_view_of_todays_register_starts_once_per_session(self):
        with clock(0):
            self.teacher.get(self.url)
            self.teacher.get(self.url)
        row = one(workflow="attendance_capture", step="started")
        self.assertEqual((row.area, row.count, row.size_bucket), ("teacher", 1, "1-20"))
        self.assertEqual(self.teacher.session[usage.ATTENDANCE_TIMER], T0)
        self.assertIs(type(self.teacher.session[usage.ATTENDANCE_TIMER]), int)

    def test_an_opened_draft_register_also_starts(self):
        self.open_register()
        self.teacher.get(self.url)
        self.assertEqual(one(workflow="attendance_capture", step="started").size_bucket, "1-20")

    def test_a_submitted_register_does_not_start(self):
        register = self.open_register()
        self.fill(register)
        register.submit(actor=self.rao)
        self.teacher.get(self.url)
        self.assertEqual(rows(workflow="attendance_capture"), [])

    def test_successful_submit_completes_with_duration_and_size_and_clears_the_timer(self):
        register = self.open_register()
        with clock(0):
            self.teacher.get(self.url)
        self.fill(register)
        with clock(200):
            self.teacher.post(self.submit)
        row = one(workflow="attendance_capture", step="completed")
        self.assertEqual((row.duration_bucket, row.size_bucket, row.area),
                         ("3-10m", "1-20", "teacher"))
        self.assertNotIn(usage.ATTENDANCE_TIMER, self.teacher.session)

    def test_submit_without_a_timer_completes_without_a_duration(self):
        register = self.open_register()
        self.fill(register)
        self.teacher.post(self.submit)
        self.assertEqual(one(workflow="attendance_capture", step="completed").duration_bucket, "")

    def test_a_refused_submit_does_not_complete(self):
        self.open_register()
        self.teacher.get(self.url)
        self.teacher.post(self.submit)  # nobody marked yet: refused
        self.assertEqual(rows(workflow="attendance_capture", step="completed"), [])
        self.assertIn(usage.ATTENDANCE_TIMER, self.teacher.session)

    def test_autosave_outcomes_are_recorded_by_the_server_with_the_client_header(self):
        register = self.open_register()
        self.row(self.asha, **CLIENT)
        self.row(self.asha, "BOGUS")
        saved = one(workflow="attendance_capture", step="saved")
        self.assertEqual(
            (saved.area, saved.device, saved.display, saved.platform, saved.size_bucket),
            ("teacher", "phone", "installed", "android", ""))
        self.assertEqual(one(workflow="attendance_capture", step="invalid").count, 1)
        self.fill(register)
        register.submit(actor=self.rao)
        self.row(self.asha)
        self.assertEqual(one(workflow="attendance_capture", step="closed").count, 1)

    def test_a_refused_teacher_is_forbidden(self):
        self.open_register()
        other = Client()
        other.login(username="iyer", password="pass-12345")
        self.assertEqual(self.row(self.asha, client=other).status_code, 403)
        self.assertEqual(one(workflow="attendance_capture", step="forbidden").count, 1)

    def test_bulk_present_is_one_saved_event_per_request(self):
        self.open_register()
        self.teacher.post(self.bulk, {"enrollment": [self.asha.pk, self.ravi.pk]}, **XHR)
        self.assertEqual(rows(workflow="attendance_capture", step="saved"),
                         [("attendance_capture", "saved", 1)])

    def test_a_non_htmx_refusal_records_nothing(self):
        self.open_register()
        UsageCounter.objects.all().delete()
        self.teacher.post(self.autosave, {"enrollment": self.asha.pk})
        self.assertEqual(rows(workflow="attendance_capture"), [])

    def test_signed_out_autosave_reply_is_counted_for_the_route(self):
        self.open_register()
        response = self.row(self.asha, client=Client())
        self.assertEqual(response.status_code, 401)
        row = one(step="signed_out")
        self.assertEqual((row.area, row.workflow), ("teacher", "attendance_capture"))
        Client().post(self.bulk, {"enrollment": [self.asha.pk]}, **XHR)
        self.assertEqual(one(step="signed_out").count, 2)

    def test_expired_session_on_autosave_is_counted_as_signed_out(self):
        self.open_register()
        session = self.teacher.session
        session[SEEN_KEY] = time.time() - 31 * 60
        session[STARTED_KEY] = time.time() - 31 * 60
        session.save()
        self.assertEqual(self.row(self.asha).status_code, 401)
        self.assertEqual(one(step="signed_out").workflow, "attendance_capture")
        self.assertEqual(one(step="expired_idle").area, "teacher")

    def test_a_signed_out_page_request_is_not_counted(self):
        Client().get(self.url)
        self.assertEqual(rows(step="signed_out"), [])

    def test_gpc_records_nothing_and_writes_no_timer(self):
        self.teacher.get(self.url, HTTP_SEC_GPC="1")
        self.assertNotIn(usage.ATTENDANCE_TIMER, self.teacher.session)
        self.assertFalse(UsageCounter.objects.exists())


class AttendanceOffTests(AttendanceFixture, TestCase):
    def test_off_records_nothing_and_writes_no_timer(self):
        register = self.open_register()
        self.teacher.get(self.url)
        self.row(self.asha)
        self.fill(register)
        self.teacher.post(self.submit)
        Client().post(self.autosave, {"enrollment": self.asha.pk}, **HX)
        self.assertNotIn(usage.ATTENDANCE_TIMER, self.teacher.session)
        self.assertFalse(UsageCounter.objects.exists())


# --- marks entry ---------------------------------------------------------------------------------


@ON
class MarksWorkflowTests(AutosaveFixture, TestCase):
    def test_saved_and_each_refusal_is_recorded_once(self):
        self.post_row(self.asha, "MARKED", "12")
        self.post_row(self.bina, "MARKED", "999")
        self.post_row(self.asha, "MARKED", "14", "MARKED", "10")  # stale base
        self.assertEqual(rows(workflow="marks_entry"), [
            ("marks_entry", "conflict", 1), ("marks_entry", "invalid", 1),
            ("marks_entry", "saved", 1)])
        self.assertTrue(all(r.area == "teacher" and r.size_bucket == ""
                            for r in UsageCounter.objects.all()))

    def test_finalized_is_closed_and_unassigned_is_forbidden(self):
        self.post_row(self.asha, "MARKED", "12", client=self.client_for(self.iyer))
        self.force_finalize(self.test1)
        self.post_row(self.asha, "MARKED", "12")
        self.assertEqual(rows(workflow="marks_entry"), [
            ("marks_entry", "closed", 1), ("marks_entry", "forbidden", 1)])

    def test_blank_row_and_bad_requests_record_nothing(self):
        self.post_row(self.asha)  # 204
        self.post_row(self.asha, "MARKED", "12", hx=False)  # 400
        self.assertFalse(UsageCounter.objects.exists())

    def test_a_concurrent_first_save_is_a_conflict(self):
        with mock.patch.object(type(self.test1), "save_draft_result",
                               side_effect=IntegrityError("dup")):
            self.assertEqual(self.post_row(self.asha, "MARKED", "12").status_code, 409)
        self.assertEqual(rows(workflow="marks_entry"), [("marks_entry", "conflict", 1)])

    def test_a_failing_store_never_breaks_a_save(self):
        with mock.patch("core.usage._increment", side_effect=DatabaseError("down")):
            self.assertEqual(self.post_row(self.asha, "MARKED", "12").status_code, 200)
        self.assertEqual(self.saved(self.asha)[0], "MARKED")

    def test_the_sheet_carries_only_the_size_bucket(self):
        page = self.teacher.get(self.entry_url(self.test1)).content.decode()
        self.assertIn('data-erp-usage-size="1-20"', page)
        with override_settings(USAGE_MEASUREMENT_ENABLED=False):
            page = self.teacher.get(self.entry_url(self.test1)).content.decode()
        self.assertNotIn("data-erp-usage-size", page)

    def test_a_complete_sheet_does_not_start_marks_entry(self):
        """Opening a sheet with nothing left to enter is a page view, not a new workflow: the
        server renders no size bucket, and the page starts only with a bucket and an unmarked
        row (static check below)."""
        self.result(self.test1, self.asha, "MARKED", "12")
        self.result(self.test1, self.bina, "ABSENT")
        page = self.teacher.get(self.entry_url(self.test1)).content.decode()
        self.assertIn('data-erp-usage-size="1-20"', page)  # Ravi is still not entered
        self.result(self.test1, self.ravi, "MARKED", "9")
        page = self.teacher.get(self.entry_url(self.test1)).content.decode()
        self.assertIn("data-erp-marks", page)
        self.assertNotIn("data-erp-usage-size", page)

    def test_the_page_starts_only_with_work_left_and_completes_only_after_a_start(self):
        block = ERP_JS[ERP_JS.index("var markSize"):ERP_JS.index("var form = sheet.closest")]
        self.assertIn('if (markSize && rows.some(function (row) { return statusOf(row) === '
                      '"unmarked"; }))', block)
        self.assertIn("var marksStarted = null;", block)
        self.assertIn('!marksDone && marksStarted !== null', ERP_JS)

    def test_signed_out_marks_autosave_is_counted(self):
        self.post_row(self.asha, "MARKED", "12", client=Client())
        row = one(step="signed_out")
        self.assertEqual((row.area, row.workflow), ("teacher", "marks_entry"))


# --- find student --------------------------------------------------------------------------------


@ON
class FindStudentTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        self.student, _ = self.make_student("Asha Varma")
        self.office = Client()
        self.office.force_login(self.admin)
        self.list_url = reverse("core:student-list")
        self.detail_url = reverse("core:student-detail", args=[self.student.pk])

    def test_a_search_starts_and_opening_a_student_completes(self):
        with clock(0):
            self.office.get(self.list_url, {"q": "Asha"})
        self.assertEqual(self.office.session[usage.FIND_TIMER], T0)
        with clock(40):
            self.office.get(self.detail_url)
        self.assertEqual(rows(workflow="find_student"), [
            ("find_student", "completed", 1), ("find_student", "started", 1)])
        self.assertEqual(one(step="completed").duration_bucket, "15-60s")
        self.assertEqual(one(step="completed").area, "admin")
        self.assertNotIn(usage.FIND_TIMER, self.office.session)

    def test_the_search_term_is_never_stored(self):
        self.office.get(self.list_url, {"q": "Asha Varma"})
        for row in UsageCounter.objects.values():
            self.assertNotIn("asha", json.dumps(row, default=str).lower())
        self.assertIs(type(self.office.session[usage.FIND_TIMER]), int)

    def test_list_without_a_search_or_detail_without_one_records_nothing(self):
        self.office.get(self.list_url)
        self.office.get(self.list_url, {"q": "   "})
        self.office.get(self.detail_url)
        self.assertEqual(rows(workflow="find_student"), [])

    def test_refining_a_running_search_keeps_one_start(self):
        with clock(0):
            self.office.get(self.list_url, {"q": "As"})
        with clock(30):
            self.office.get(self.list_url, {"q": "Asha"})
        self.assertEqual(one(step="started").count, 1)
        self.assertEqual(self.office.session[usage.FIND_TIMER], T0)

    def test_after_ten_minutes_opening_a_student_is_not_a_completion(self):
        with clock(0):
            self.office.get(self.list_url, {"q": "Asha"})
        with clock(601):
            self.office.get(self.detail_url)
        self.assertEqual(rows(step="completed"), [])
        self.assertNotIn(usage.FIND_TIMER, self.office.session)

    def test_a_new_search_after_ten_minutes_starts_again(self):
        with clock(0):
            self.office.get(self.list_url, {"q": "Asha"})
        with clock(700):
            self.office.get(self.list_url, {"q": "Asha"})
        self.assertEqual(one(step="started").count, 2)


# --- guardian workflows --------------------------------------------------------------------------


@ON
class GuardianWorkflowTests(PublicationFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.publish()
        self.pub = TermPublication.objects.get(student=self.asha, term=self.term1)
        self.card_url = reverse("portal:report-card",
                                args=[self.asha_grant.public_id, self.pub.public_id])
        self.pdf_url = reverse("portal:report-card-pdf",
                               args=[self.asha_grant.public_id, self.pub.public_id])
        UsageCounter.objects.all().delete()

    def sign_in(self):
        self.user.must_change_password = False
        self.user.save(update_fields=["must_change_password"])
        client = Client()
        client.post(reverse("login"), {"username": "meena", "password": self.password})
        return client

    def test_sign_in_starts_and_the_first_child_page_completes(self):
        with clock(0):
            client = self.sign_in()
        self.assertEqual(client.session[usage.GUARDIAN_TIMER], T0)
        with clock(3):
            client.get(reverse("portal:home"))
        self.assertEqual(rows(workflow="guardian_first_view"),
                         [("guardian_first_view", "started", 1)])
        with clock(20):
            client.get(reverse("portal:child", args=[self.asha_grant.public_id]))
            client.get(reverse("portal:attendance", args=[self.asha_grant.public_id]))
        completed = one(workflow="guardian_first_view", step="completed")
        self.assertEqual((completed.count, completed.duration_bucket, completed.area),
                         (1, "15-60s", "guardian"))
        self.assertNotIn(usage.GUARDIAN_TIMER, client.session)

    def test_attendance_and_report_pages_also_complete(self):
        for name in ("portal:attendance", "portal:report-cards"):
            client = self.sign_in()
            client.get(reverse(name, args=[self.asha_grant.public_id]))
        self.assertEqual(one(workflow="guardian_first_view", step="completed").count, 2)

    def test_a_teacher_sign_in_starts_no_guardian_timer(self):
        client = Client()
        client.post(reverse("login"), {"username": "rao", "password": "pass-12345"})
        self.assertNotIn(usage.GUARDIAN_TIMER, client.session)
        self.assertEqual(rows(workflow="guardian_first_view"), [])

    def test_report_card_view_starts_and_pdf_completes(self):
        with mock.patch("core.documents.service.render_pdf", return_value=b"%PDF-1.4 fake"):
            self.portal.get(self.card_url)
            self.portal.get(self.card_url)
            self.assertEqual(self.portal.get(self.pdf_url).status_code, 200)
        self.assertEqual(rows(workflow="guardian_report_pdf"), [
            ("guardian_report_pdf", "completed", 1), ("guardian_report_pdf", "started", 2)])
        self.assertTrue(all(r.duration_bucket == "" for r in UsageCounter.objects.all()))

    def test_a_missing_report_card_records_nothing(self):
        other = reverse("portal:report-card-pdf",
                        args=[self.asha_grant.public_id, self.asha_grant.public_id])
        self.assertEqual(self.portal.get(other).status_code, 404)
        self.assertEqual(rows(workflow="guardian_report_pdf"), [])

    def test_sign_out_leaves_no_timer(self):
        client = self.sign_in()
        client.post(reverse("logout"))
        self.assertFalse([key for key in client.session.keys()
                          if key.startswith("_u_") and key != usage.EXPIRED_MARKER])


@ON
class NoticeViewTests(AnnouncementFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.portal = self.guardian_client()

    def view(self, days_old):
        # Announcements cannot be rewritten, so "today" moves instead of the publication time.
        notice = self.notice()
        published_on = timezone.localtime(notice.published_at).date()
        self.today = published_on + timedelta(days=days_old)
        self.portal.get(reverse("portal:notice", args=[notice.public_id]))
        return notice

    def test_age_buckets_and_no_notice_reference(self):
        for days in (0, 2, 5, 30):
            self.view(days)
        notice_rows = UsageCounter.objects.filter(workflow="notice_view")
        self.assertEqual(sorted(notice_rows.values_list("age_bucket", flat=True)),
                         sorted(["same_day", "1-2d", "3-7d", "later"]))
        self.assertTrue(all(r.area == "guardian" and r.step == "viewed" for r in notice_rows))

    def test_repeated_views_are_events(self):
        notice = self.view(0)
        self.portal.get(reverse("portal:notice", args=[notice.public_id]))
        self.assertEqual(one(workflow="notice_view").count, 2)

    def test_a_hidden_notice_records_nothing(self):
        self.portal.get(reverse("portal:notice", args=["00000000-0000-0000-0000-000000000000"]))
        self.assertEqual(rows(workflow="notice_view"), [])


# --- the beacon in B3 ----------------------------------------------------------------------------


@ON
class BeaconB3Tests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        self.teacher = Client()
        self.teacher.force_login(self.rao)
        self.office = Client()
        self.office.force_login(self.admin)

    def post(self, events, client=None, **shared):
        body = {"d": "phone", "x": "browser", "p": "ios", "r": "core:my-home", "a": "teacher",
                **shared, "e": events}
        return (client or self.teacher).post(reverse("usage-beacon"), json.dumps(body),
                                             content_type="application/json", **XHR)

    def test_teacher_home_and_marks_events_with_buckets(self):
        response = self.post([
            {"w": "teacher_home", "s": "started"},
            {"w": "teacher_home", "s": "completed", "b": "<5s"},
            {"w": "marks_entry", "s": "started", "z": "21-40"},
            {"w": "marks_entry", "s": "completed", "b": "3-10m", "z": "21-40"},
            {"w": "marks_entry", "s": "attempt"},
            {"w": "marks_entry", "s": "network"},
            {"w": "marks_entry", "s": "retry_succeeded"},
            {"w": "attendance_capture", "s": "csrf"},
            {"w": "install", "s": "dismissed"},
        ])
        self.assertEqual(response.status_code, 204)
        self.assertEqual(one(workflow="marks_entry", step="completed").size_bucket, "21-40")
        self.assertEqual(one(workflow="teacher_home", step="completed").duration_bucket, "<5s")
        self.assertEqual(UsageCounter.objects.count(), 9)

    def test_size_is_refused_outside_marks_start_and_completion(self):
        for event in ({"w": "marks_entry", "s": "attempt", "z": "1-20"},
                      {"w": "teacher_home", "s": "started", "z": "1-20"},
                      {"w": "marks_entry", "s": "started", "z": "12"}):
            self.assertEqual(self.post([event]).status_code, 400, event)
        self.assertFalse(UsageCounter.objects.exists())

    def test_server_recorded_outcomes_cannot_be_claimed_by_the_browser(self):
        for step in ("saved", "invalid", "conflict", "closed", "forbidden", "signed_out",
                     "started", "completed"):
            self.assertEqual(self.post([{"w": "attendance_capture", "s": step}]).status_code,
                             400, step)
        self.assertFalse(UsageCounter.objects.exists())

    def test_missing_attendance_act_is_admin_only(self):
        events = [{"w": "missing_attendance_act", "s": "started"},
                  {"w": "missing_attendance_act", "s": "completed", "b": "15-60s"}]
        self.assertEqual(self.post(events).status_code, 400)  # area teacher
        response = self.post(events, client=self.office, a="admin",
                             r="core:report-missing-attendance")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(rows(workflow="missing_attendance_act"), [
            ("missing_attendance_act", "completed", 1), ("missing_attendance_act", "started", 1)])

    def test_install_outcomes_are_separate(self):
        self.post([{"w": "install", "s": "shown"}, {"w": "install", "s": "installed"}])
        self.assertEqual(rows(workflow="install"), [("install", "installed", 1),
                                                    ("install", "shown", 1)])

    def test_a_beacon_never_refreshes_the_idle_clock(self):
        session = self.teacher.session
        session[SEEN_KEY] = seen = time.time() - 600
        session.save()
        self.post([{"w": "page", "s": "viewed"}])
        self.assertEqual(self.teacher.session[SEEN_KEY], seen)

    def test_stored_rows_hold_only_allowed_values(self):
        self.post([{"w": "page", "s": "viewed"}, {"w": "install", "s": "shown"}])
        for row in UsageCounter.objects.values():
            for name, value in row.items():
                if name in ("id", "day", "count"):
                    continue
                self.assertTrue(value == "" or value in usage._ENUMS[name], (name, value))


# --- browser code (static checks) ----------------------------------------------------------------


class BrowserCodeTests(TestCase):
    def test_flush_is_guarded_by_global_privacy_control_and_identifies_itself(self):
        block = usage_block()
        self.assertIn("navigator.globalPrivacyControl === true", block)
        flush = block[block.index("function flush"):]
        flush = flush[:flush.index("\n  }\n")]
        self.assertIn("gpc()", flush)
        self.assertIn('"X-Requested-With": "XMLHttpRequest"', flush)
        self.assertIn('"X-CSRFToken"', flush)
        self.assertIn("keepalive: true", flush)

    def test_events_stay_in_page_memory_only(self):
        block = usage_block()
        for word in ("localStorage", "sessionStorage", "indexedDB", "sendBeacon",
                     "document.cookie", "serviceWorker", "SyncManager"):
            self.assertNotIn(word, block)
        self.assertIn("MAX_EVENTS = 20", block)
        self.assertIn("queue.shift()", block)  # the oldest is dropped first

    def test_flush_moments(self):
        block = usage_block()
        self.assertIn('document.visibilityState === "hidden"', block)
        self.assertIn("setInterval(flush, 30000)", block)
        # A failed flush puts its events back in memory for the next moment.
        self.assertIn("queue = batch.concat(queue)", block)

    def test_nothing_is_sent_without_the_page_attribute(self):
        self.assertIn('getAttribute("data-erp-usage") === "1"', usage_block())

    def test_client_header_only_when_measurement_is_on(self):
        self.assertIn('if (erpUsage.on()) event.detail.headers["X-ERP-Client"]', ERP_JS)

    def test_events_are_built_only_from_enum_constants(self):
        calls = re.findall(r"erpUsage\.add\(([^)]*)\)", ERP_JS)
        self.assertGreater(len(calls), 15)
        # Buckets are computed first (erpUsage.since) and the size comes from the server's bucket.
        allowed_extra = {"took", "markSize", "null"}
        for call in calls:
            args = [arg.strip() for arg in call.split(", ")]
            self.assertTrue(args[0].startswith('"') and args[1].startswith('"'), call)
            workflow, step = args[0].strip('"'), args[1].strip('"')
            self.assertIn((workflow, step), usage.CLIENT_EVENTS, call)
            for extra in args[2:]:
                self.assertIn(extra, allowed_extra, call)

    def test_device_dimensions_are_taken_when_the_event_happens(self):
        """A resize or rotation between an event and its send must not relabel it: each event
        keeps its own device, display and platform, and one send carries one set of them."""
        block = usage_block()
        self.assertIn("queue.push({ e: event, d: device(), x: display(), p: platform() });", block)
        self.assertIn("d: first.d, x: first.x, p: first.p", block)
        self.assertNotIn("d: device(), x: display(), p: platform(), r:", block)

    def test_payload_carries_only_shared_dimensions_and_events(self):
        body = re.search(r"JSON\.stringify\(\{([^}]*)\}\)", usage_block()).group(1)
        self.assertEqual(sorted(re.findall(r"(\w+):", body)), ["a", "d", "e", "p", "r", "x"])

    def test_install_dismiss_and_installed_are_separate(self):
        self.assertIn('erpUsage.add("install", "dismissed")', ERP_JS)
        self.assertIn('erpUsage.add("install", "installed")', ERP_JS)
        self.assertIn('erpUsage.add("install", "shown")', ERP_JS)
        dismiss = ERP_JS[ERP_JS.index("dismiss.addEventListener"):]
        dismiss = dismiss[:dismiss.index("});")]
        self.assertNotIn("installed", dismiss)

    def test_route_bound_workflows(self):
        self.assertIn('erpUsage.route() === "core:my-home"', ERP_JS)
        self.assertIn('erpUsage.route() === "core:report-missing-attendance"', ERP_JS)

    def test_missing_attendance_links_are_marked(self):
        template = (BASE_DIR / "core" / "templates" / "core"
                    / "report_missing_attendance.html").read_text(encoding="utf-8")
        self.assertEqual(template.count("data-erp-usage-act"), 2)

    def test_save_handling_is_counted_by_the_client(self):
        for event in ('"marks_entry", "retry_tapped"', '"marks_entry", "retry_succeeded"',
                      '"marks_entry", "fallback_save_used"', '"marks_entry", "attempt"',
                      '"marks_entry", "network"', '"marks_entry", "server"',
                      '"marks_entry", "csrf"', '"attendance_capture", "attempt"',
                      '"attendance_capture", "network"', '"attendance_capture", "server"',
                      '"attendance_capture", "retry_tapped"',
                      '"attendance_capture", "retry_succeeded"'):
            self.assertIn(f"erpUsage.add({event}", ERP_JS)

    def test_a_successful_save_flushes_so_offline_failures_are_sent_later(self):
        self.assertGreaterEqual(ERP_JS.count("erpUsage.flush()"), 3)


# --- the report ----------------------------------------------------------------------------------


TODAY = date(2026, 11, 20)  # a Friday in ISO week 47
MONDAY_W47 = TODAY - timedelta(days=TODAY.weekday())


def add(day=MONDAY_W47, count=1, **dims):
    return UsageCounter.objects.create(day=day, count=count, **dims)


class ReportFixture:
    def report(self, *args):
        out = StringIO()
        with mock.patch("core.usage.business_today", return_value=TODAY):
            call_command("usage_report", *args, stdout=out)
        return out.getvalue()

    def csv_rows(self, *args):
        return list(csv.reader(io.StringIO(self.report("--format", "csv", *args))))


class ReportWorkflowTests(ReportFixture, TestCase):
    def test_started_completed_rate_and_left_incomplete_with_its_limitation(self):
        add(area="admin", workflow="find_student", step="started", count=30)
        add(area="admin", workflow="find_student", step="completed", count=21,
            duration_bucket="15-60s")
        out = self.report("--weeks", "1")
        self.assertRegex(out, r"find_student\s+started 30\s+completed 21\s+rate 70\.0%\s+"
                              r"left incomplete 9")
        self.assertIn("upper bound", out)
        self.assertIn("not a count of people", out)

    def test_left_incomplete_is_not_printed_when_a_cell_is_hidden(self):
        add(area="admin", workflow="find_student", step="started", count=30)
        add(area="admin", workflow="find_student", step="completed", count=3)
        out = self.report("--weeks", "1")
        self.assertRegex(out, r"find_student\s+started 30\s+completed <5\s+rate <16\.7%\s+"
                              r"left incomplete n/a")
        self.assertNotIn(" 27", out)

    def test_rate_is_na_below_its_minimum(self):
        add(area="admin", workflow="find_student", step="started", count=12)
        add(area="admin", workflow="find_student", step="completed", count=10)
        self.assertRegex(self.report("--weeks", "1"), r"rate n/a")

    def test_rate_minimum_is_exactly_20_starts(self):
        started = add(area="admin", workflow="find_student", step="started", count=19)
        add(area="admin", workflow="find_student", step="completed", count=10)
        self.assertRegex(self.report("--weeks", "1"), r"started 19\s+completed 10\s+rate n/a")
        UsageCounter.objects.filter(pk=started.pk).update(count=20)
        self.assertRegex(self.report("--weeks", "1"), r"started 20\s+completed 10\s+rate 50\.0%")

    def test_duration_distribution_hides_a_second_cell_when_one_is_small(self):
        add(area="admin", workflow="find_student", step="started", count=40)
        add(area="admin", workflow="find_student", step="completed", count=3,
            duration_bucket="<5s")
        add(area="admin", workflow="find_student", step="completed", count=9,
            duration_bucket="15-60s")
        out = self.report("--weeks", "1")
        self.assertRegex(out, r"completed 12")
        self.assertRegex(out, r"<5s\s+<5")
        self.assertRegex(out, r"15-60s\s+\*")  # 12 - 3 would reveal it
        self.assertNotRegex(out, r"15-60s\s+9")

    def test_size_split_for_marks_and_attendance(self):
        for size, started, completed in (("1-20", 20, 8), ("21-40", 15, 6)):
            add(area="teacher", workflow="marks_entry", step="started", count=started,
                size_bucket=size)
            add(area="teacher", workflow="marks_entry", step="completed", count=completed,
                size_bucket=size, duration_bucket="3-10m")
        out = self.report("--weeks", "1")
        self.assertRegex(out, r"size 1-20\s+started 20\s+completed 8")
        self.assertRegex(out, r"size 21-40\s+started 15\s+completed 6")

    def test_cells_are_hidden_after_filters_and_weekly_grouping(self):
        add(area="teacher", workflow="install", step="shown", count=3, device="phone")
        add(day=MONDAY_W47 + timedelta(days=1), area="teacher", workflow="install",
            step="shown", count=3, device="phone")
        add(area="admin", workflow="install", step="shown", count=4, device="tablet")
        self.assertRegex(self.report("--weeks", "1"), r"install\s+shown\s+10")
        self.assertRegex(self.report("--weeks", "1", "--device", "phone"),
                         r"install\s+shown\s+6")
        out = self.report("--weeks", "1", "--area", "admin")
        self.assertRegex(out, r"install\s+shown\s+<5")
        self.assertNotRegex(out, r"shown\s+4")

    def test_install_outcomes_print_as_separate_lines(self):
        for step, count in (("shown", 30), ("installed", 6), ("dismissed", 12)):
            add(area="guardian", workflow="install", step=step, count=count)
        out = self.report("--weeks", "1")
        for step, count in (("shown", 30), ("installed", 6), ("dismissed", 12)):
            self.assertRegex(out, rf"install\s+{step}\s+{count}")

    def test_notice_views_are_events_among_notices_that_were_viewed(self):
        add(area="guardian", workflow="notice_view", step="viewed", age_bucket="same_day",
            count=7)
        add(area="guardian", workflow="notice_view", step="viewed", age_bucket="later", count=2)
        out = self.report("--weeks", "1")
        self.assertIn("among notices that were viewed", out)
        self.assertIn("events, not people", out)
        self.assertRegex(out, r"same_day\s+7")
        self.assertRegex(out, r"later\s+<5")

    def test_pages_by_route_and_device_are_events(self):
        add(area="admin", workflow="page", step="viewed", page_route="core:student-list",
            device="phone", count=12)
        add(area="admin", workflow="page", step="viewed", page_route="other", device="phone",
            count=6)
        add(area="public", workflow="page", step="viewed", page_route="root:login", count=40)
        out = self.report("--weeks", "1")
        self.assertIn("Page views (events, not people)", out)
        self.assertRegex(out, r"core:student-list\s+phone 12")
        self.assertRegex(out, r"other\s+phone 6")
        self.assertRegex(out, r"root:login\s+unknown 40")

    def test_display_and_platform_splits_protect_each_other(self):
        """Both splits add up to the same weekly page total, so one small cell in either split
        could be recovered from the other split: a second cell is hidden."""
        for display, platform, count in (("installed", "android", 3), ("browser", "android", 20),
                                         ("browser", "ios", 10)):
            add(area="guardian", workflow="page", step="viewed", page_route="portal:home",
                device="phone", display=display, platform=platform, count=count)
        out = self.report("--weeks", "1")
        self.assertRegex(out, r"installed\s+<5")
        self.assertNotRegex(out, r"browser\s+30\b")  # 33 - 3 would reveal it

    def test_save_failures_are_labelled_as_observed(self):
        add(area="teacher", workflow="marks_entry", step="network", count=6)
        out = self.report("--weeks", "1")
        self.assertIn("observed network failures", out)
        self.assertIn("complete disconnects", out)


class ReportEvidenceTests(ReportFixture, TestCase):
    def fill_four_weeks(self, *, attempts, network, taps, succeeded):
        for week in range(4):
            day = MONDAY_W47 - timedelta(weeks=week)
            add(day=day, area="teacher", workflow="marks_entry", step="attempt", count=attempts,
                device="phone")
            add(day=day, area="teacher", workflow="marks_entry", step="network", count=network,
                device="phone")
            add(day=day, area="teacher", workflow="marks_entry", step="retry_tapped",
                count=taps, device="phone")
            add(day=day, area="teacher", workflow="marks_entry", step="retry_succeeded",
                count=succeeded, device="phone")

    def test_offline_trigger_met(self):
        self.fill_four_weeks(attempts=150, network=6, taps=10, succeeded=5)
        out = self.report()
        self.assertRegex(out, r"N, observed network failure rate .*: 4\.0%")
        self.assertRegex(out, r"R, retry success rate .*: 50\.0%")
        self.assertRegex(out, r"9\.1 offline write and sync: met")
        self.assertIn("open a design gate only", out)
        self.assertIn("never approve", out)

    def test_below_minimum_is_na_never_met_or_missed(self):
        self.fill_four_weeks(attempts=100, network=6, taps=2, succeeded=1)  # 400 attempts
        out = self.report()
        self.assertRegex(out, r"N, observed network failure rate .*: n/a")
        self.assertRegex(out, r"9\.1 offline write and sync: n/a")
        self.assertIn("not met or missed", out)

    def test_retry_minimum_alone_makes_the_trigger_na(self):
        self.fill_four_weeks(attempts=150, network=6, taps=4, succeeded=1)  # 16 taps
        self.assertRegex(self.report(), r"9\.1 offline write and sync: n/a")

    def test_stays_online_only_when_network_is_low(self):
        self.fill_four_weeks(attempts=150, network=1, taps=10, succeeded=5)
        # One small weekly cell only: four lines of 1 under a <5 total would pin each one, and
        # the report then widens the total to * (test_a_small_window_total_..._is_widened).
        UsageCounter.objects.filter(step="network").exclude(day=MONDAY_W47).delete()
        UsageCounter.objects.filter(step="network").update(count=4)
        out = self.report()
        # 4 of 600 is hidden; the bound 5/600 is rounded up, so it never understates.
        self.assertRegex(out, r"N, observed network failure rate .*: <0\.9%")
        self.assertRegex(out, r"9\.1 offline write and sync: not met")

    def test_window_total_hides_a_second_weekly_cell(self):
        """Weekly network cells 6, 6, 6 and 3 with a printed window total would reveal the 3."""
        self.fill_four_weeks(attempts=150, network=6, taps=10, succeeded=5)
        UsageCounter.objects.filter(step="network", day=MONDAY_W47).update(count=3)
        out = self.report()
        weekly = re.findall(r"marks_entry\s+network\s+(\S+)", out)
        self.assertEqual(len(weekly), 4)
        self.assertEqual(weekly.count("<5"), 1)
        self.assertEqual(weekly.count("*"), 1)

    def test_evidence_is_printed_only_for_an_unfiltered_report_of_four_weeks(self):
        self.fill_four_weeks(attempts=150, network=6, taps=10, succeeded=5)
        filtered = self.report("--area", "teacher")
        self.assertIn("printed only for an unfiltered report", filtered)
        self.assertNotIn("9.1 offline write and sync: met", filtered)
        self.assertIn("needs at least 4 weeks", self.report("--weeks", "2"))

    def test_login_and_push_triggers_compute_from_counters(self):
        for week in range(4):
            day = MONDAY_W47 - timedelta(weeks=week)
            add(day=day, area="teacher", workflow="sign_in", step="completed", count=60)
            add(day=day, area="teacher", workflow="session", step="expired_unsaved", count=5)
            add(day=day, area="public", workflow="sign_in", step="failed", count=20)
            add(day=day, area="multi", workflow="sign_in", step="completed", count=6)
            add(day=day, area="guardian", workflow="notice_view", step="viewed",
                age_bucket="same_day", count=10)
            add(day=day, area="guardian", workflow="notice_view", step="viewed",
                age_bucket="later", count=20)
            add(day=day, area="guardian", workflow="page", step="viewed",
                page_route="portal:home", device="phone", platform="ios", display="browser",
                count=60)
            add(day=day, area="guardian", workflow="page", step="viewed",
                page_route="portal:home", device="desktop", platform="other",
                display="browser", count=10)
        out = self.report()
        self.assertRegex(out, r"E, expired-unsaved rate .*: 8\.3%")
        self.assertRegex(out, r"multi-area sign-ins .*: 24")
        self.assertRegex(out, r"9\.3 login convenience: met")
        self.assertRegex(out, r"S, share of recorded notice-view events .*: 33\.3%")
        self.assertRegex(out, r"P, share of guardian page-view events .*: 85\.7%")
        self.assertRegex(out, r"9\.2 push notifications: met")
        self.assertRegex(out, r"I, share of iOS guardian page-view events .*: 0\.0%")
        self.assertIn("events, not people", out)
        self.assertIn("documented PWA capability testing", out)

    def test_csv_follows_the_same_rules(self):
        add(area="admin", workflow="find_student", step="started", count=40)
        add(area="admin", workflow="find_student", step="completed", count=3,
            duration_bucket="<5s")
        add(area="admin", workflow="find_student", step="completed", count=9,
            duration_bucket="15-60s")
        data = self.csv_rows("--weeks", "1")
        self.assertEqual(data[0], ["section", "period", "item", "value"])
        values = {(r[0], r[2]): r[3] for r in data[1:]}
        self.assertEqual(values[("workflows", "find_student completed <5s")], "<5")
        self.assertEqual(values[("workflows", "find_student completed 15-60s")], "*")
        self.assertNotIn("9", [r[3] for r in data[1:]])

    def test_two_small_cells_under_a_visible_total_cannot_be_pinned(self):
        """Started 8 split into two size cells of 4: both print <5, but 8 = 4 + 4 would pin them.
        The engine must hide the total too (or otherwise keep each cell anywhere in 1 to 4)."""
        for size in ("1-20", "21-40"):
            add(area="teacher", workflow="marks_entry", step="started", count=4, size_bucket=size)
        out = self.report("--weeks", "1")
        self.assertNotRegex(out, r"marks_entry\s+started 8")
        self.assertRegex(out, r"marks_entry\s+started \*")

    def test_a_small_window_total_over_small_weekly_lines_is_widened(self):
        """Four weekly lines of 1 under a <5 window total would make each exactly 1."""
        self.fill_four_weeks(attempts=150, network=6, taps=10, succeeded=1)
        out = self.report()
        self.assertEqual(re.findall(r"marks_entry\s+retry_succeeded\s+(\S+)", out),
                         ["<5"] * 4)
        self.assertRegex(out, r"R, retry success rate .*: n/a \(hidden\)\s+\(\* of 40")

    def admin_phone_views(self, per_week_list, other_per_week):
        for week in range(4):
            day = MONDAY_W47 - timedelta(weeks=week)
            add(day=day, area="admin", workflow="page", step="viewed",
                page_route="core:student-list", device="phone", count=per_week_list)
            add(day=day, area="admin", workflow="page", step="viewed", page_route="other",
                device="phone", count=other_per_week)

    def test_other_share_needs_100_admin_phone_views(self):
        self.admin_phone_views(19, 6)  # 4 x 25 = 100 views
        out = self.report()
        self.assertRegex(out, r"Share of other among admin phone views .*: 24\.0%")
        UsageCounter.objects.filter(page_route="other", day=MONDAY_W47).update(count=5)
        out = self.report()  # 99 views
        self.assertRegex(out, r"Share of other among admin phone views .*: n/a\s+\(\S+ of 99; "
                              r"below the minimum of 100")

    def test_five_phone_views_a_week_route_rule_is_unchanged_below_100(self):
        """The 100-view minimum applies to the other share only; a route averaging at least
        five phone views a week is still flagged when the admin total is under 100."""
        self.admin_phone_views(5, 6)  # 20 student-list views + 24 other = 44 total
        out = self.report()
        self.assertRegex(out, r"core:student-list\s+20\s+\(at least 5 a week")
        self.assertRegex(out, r"Share of other among admin phone views .*: n/a")
        UsageCounter.objects.filter(page_route="core:student-list", day=MONDAY_W47).update(count=6)
        UsageCounter.objects.filter(page_route="core:student-list").exclude(
            day=MONDAY_W47).update(count=4)  # 18 over 4 weeks: under 5 a week
        self.assertNotRegex(self.report(), r"core:student-list\s+18\s+\(at least 5 a week")

    def test_unknown_platform_is_printed_so_no_residual_reveals_it(self):
        self.fill_four_weeks(attempts=150, network=6, taps=10, succeeded=5)  # platform unknown
        out = self.report()
        self.assertRegex(out, r"N on unknown \(network / attempt\): 4\.0%")

    def test_brute_force_attacker_cannot_narrow_any_hidden_duration_cell(self):
        """Independent of the engine: from the printed text alone, enumerate every value the
        hidden duration cells could take (<5 is 1..4, * is any value from 1) given the printed
        completed total, and require each <5 cell to stay free across the whole range 1..4."""
        import itertools
        import random

        rng = random.Random(20261121)
        buckets = ["<5s", "5-15s", "15-60s", "1-3m"]
        for _ in range(60):
            UsageCounter.objects.all().delete()
            counts = [rng.choice([0, 1, 2, 3, 4, 4, 5, 6, 9]) for _ in buckets]
            if not any(counts):
                continue
            add(area="admin", workflow="find_student", step="started", count=40)
            for bucket, count in zip(buckets, counts, strict=True):
                if count:
                    add(area="admin", workflow="find_student", step="completed", count=count,
                        duration_bucket=bucket)
            out = self.report("--weeks", "1")
            total = re.search(r"find_student\s+started 40\s+completed (\S+)", out).group(1)
            printed = dict(re.findall(r"took (\S+)\s+(\S+)", out))
            hidden = [b for b, v in printed.items() if not v.isdigit()]
            ranges = {b: range(1, 5) if printed[b] == "<5" else range(1, 41) for b in hidden}
            known = sum(int(v) for v in printed.values() if v.isdigit())
            seen = {b: set() for b in hidden if printed[b] == "<5"}
            for values in itertools.product(*(ranges[b] for b in hidden)):
                if total.isdigit() and known + sum(values) != int(total):
                    continue
                if total == "<5" and not 1 <= known + sum(values) <= 4:
                    continue
                for bucket, value in zip(hidden, values, strict=True):
                    if bucket in seen:
                        seen[bucket].add(value)
            for possible in seen.values():
                self.assertEqual(possible, {1, 2, 3, 4}, (counts, out))

    def test_two_visible_buckets_and_one_small_one_hide_exactly_one_more(self):
        add(area="admin", workflow="find_student", step="started", count=40)
        for bucket, count in (("<5s", 3), ("15-60s", 9), ("1-3m", 8)):
            add(area="admin", workflow="find_student", step="completed", count=count,
                duration_bucket=bucket)
        out = self.report("--weeks", "1")
        self.assertRegex(out, r"completed 20")
        self.assertEqual(len(re.findall(r"(15-60s|1-3m)\s+\*", out)), 1)
        self.assertRegex(out, r"15-60s\s+9")  # the smallest visible cell (8) is hidden instead
