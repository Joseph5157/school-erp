"""Option B1: per-row marks-entry autosave (Option B spec §4, tests §10.1)."""

import re
import threading
import time
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from unittest import mock, skipUnless

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection
from django.test import Client, TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core import guardian_accounts as ga
from core.forms import ResultEntryForm
from core.models import (
    TEACHERS_GROUP_NAME,
    AcademicEnrollment,
    Assessment,
    Guardian,
    GuardianAccount,
    ResultCorrection,
    StudentResult,
)
from core.tests.test_ui_teacher_marks import MONDAY, MarksFixture

BASE_DIR = Path(settings.BASE_DIR)
ERP_JS = (BASE_DIR / "static" / "js" / "erp.js").read_text(encoding="utf-8")
MARKS_TEMPLATE = BASE_DIR / "core" / "templates" / "core" / "assessment_marks_entry.html"
ATTENDANCE_TABLE = BASE_DIR / "core" / "templates" / "core" / "_attendance_capture_table.html"

FINALIZED = "This assessment is finalized. Ask an administrator if a result needs correcting."
NOT_YET = "Marks cannot be entered before the assessment date."
NO_LONGER = "You can no longer enter marks for this assessment. Reload the page."
OFF_ROSTER = "Not on this assessment&#x27;s roster."


def marks_block():
    """The marks-entry part of erp.js, between its comment and the next block's."""
    start = ERP_JS.index("// Marks entry:")
    end = ERP_JS.index("// Announcement form:", start)
    return ERP_JS[start:end]


class AutosaveFixture(MarksFixture):
    def autosave_url(self, assessment=None):
        return reverse("core:assessment-marks-autosave", args=[(assessment or self.test1).pk])

    def post_row(self, enrollment, status="", score="", base_status="", base_score="", *,
                 assessment=None, client=None, hx=True, base=True):
        pk = enrollment.pk
        data = {"enrollment": pk, f"status_{pk}": status, f"score_{pk}": score}
        if base:
            data[f"base_status_{pk}"] = base_status
            data[f"base_score_{pk}"] = base_score
        extra = {"HTTP_HX_REQUEST": "true"} if hx else {}
        return (client or self.teacher).post(self.autosave_url(assessment), data, **extra)

    def saved(self, enrollment, assessment=None):
        result = (assessment or self.test1).results.filter(academic_enrollment=enrollment).first()
        return (result.status, result.score) if result else None

    def client_for(self, user):
        client = self.client_class()
        client.force_login(user)
        return client


class AutosaveAuthorizationTests(AutosaveFixture, TestCase):
    def test_a_post_without_htmx_is_refused(self):
        response = self.post_row(self.asha, "MARKED", "12", hx=False)
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(self.saved(self.asha))

    def test_a_post_without_the_base_fields_is_refused(self):
        response = self.post_row(self.asha, "MARKED", "12", base=False)
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(self.saved(self.asha))

    def test_get_is_not_allowed(self):
        self.assertEqual(self.teacher.get(self.autosave_url()).status_code, 405)

    def test_a_teacher_not_assigned_to_the_slot_is_refused(self):
        response = self.post_row(self.asha, "MARKED", "12", client=self.client_for(self.iyer))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, NO_LONGER, status_code=403)
        self.assertNotContains(response, "Retry", status_code=403)
        self.assertIsNone(self.saved(self.asha))

    def test_a_guardian_is_refused(self):
        guardian = Guardian.objects.create(full_name="Meena Rao")
        account, _ = ga.create_guardian_account(
            guardian=guardian, username="meena", note="known", actor=self.admin,
            method=GuardianAccount.VerificationMethod.EXISTING_RECORDS)
        account.user.must_change_password = False
        account.user.save(update_fields=["must_change_password"])
        response = self.post_row(self.asha, "MARKED", "12", client=self.client_for(account.user))
        self.assertEqual(response.status_code, 403)
        self.assertIsNone(self.saved(self.asha))

    def test_anonymous_is_redirected_or_told_it_is_signed_out(self):
        page = self.post_row(self.asha, "MARKED", "12", client=Client(), hx=False)
        self.assertEqual(page.status_code, 302)
        self.assertTrue(page["Location"].startswith(reverse("login")))
        background = self.post_row(self.asha, "MARKED", "12", client=Client())
        self.assertEqual(background.status_code, 401)
        self.assertEqual(background.json(), {"error": "signed-out", "expired": None})
        self.assertIsNone(self.saved(self.asha))

    def test_an_assignment_that_ended_yesterday_is_refused(self):
        self.duty.end_date = MONDAY - timedelta(days=1)
        self.duty.save(update_fields=["end_date"])
        response = self.post_row(self.asha, "MARKED", "12")
        self.assertEqual(response.status_code, 403)
        self.assertIsNone(self.saved(self.asha))

    def test_a_finalized_assessment_is_refused_with_no_write(self):
        self.force_finalize(self.test1)
        response = self.post_row(self.asha, "MARKED", "12")
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, FINALIZED, status_code=409)
        self.assertFalse(StudentResult.objects.exists())

    def test_an_assessment_dated_tomorrow_is_not_open_and_never_called_finalized(self):
        later = self.make_assessment(name="Unit Test 3", on=MONDAY + timedelta(days=1),
                                     term=self.term2)
        response = self.post_row(self.asha, "MARKED", "12", assessment=later)
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, NOT_YET, status_code=409)
        self.assertNotContains(response, "finalized", status_code=409)
        self.assertFalse(StudentResult.objects.exists())

    def test_an_enrollment_off_the_roster_is_refused(self):
        _, zed = self.make_student("Zed", section=self.six_b)
        response = self.post_row(zed, "MARKED", "12")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, OFF_ROSTER, status_code=404)
        self.assertFalse(StudentResult.objects.exists())

    def test_admin_permissions_without_an_assignment_are_refused(self):
        head = self.make_user("head", self.admins, self.teachers)
        response = self.post_row(self.asha, "MARKED", "12", client=self.client_for(head))
        self.assertEqual(response.status_code, 403)
        self.assertIsNone(self.saved(self.asha))


class AutosaveSavingTests(AutosaveFixture, TestCase):
    def test_marked_with_a_score_creates_one_result(self):
        response = self.post_row(self.asha, "MARKED", "12")
        self.assertContains(response, "Saved")
        result = StudentResult.objects.get()
        self.assertEqual((result.status, result.score), ("MARKED", Decimal("12")))
        self.assertEqual(result.entered_by, self.rao)

    def test_absent_clears_the_score(self):
        self.result(self.test1, self.asha, "MARKED", "18")
        response = self.post_row(self.asha, "ABSENT", "", "MARKED", "18")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.saved(self.asha), ("ABSENT", None))

    def test_a_score_with_no_status_saves_as_marked(self):
        self.post_row(self.asha, "", "7")
        self.assertEqual(self.saved(self.asha), ("MARKED", Decimal("7")))

    def test_a_score_above_the_maximum_is_refused(self):
        response = self.post_row(self.asha, "MARKED", "21")
        self.assertEqual(response.status_code, 422)
        self.assertIsNone(self.saved(self.asha))

    def test_too_many_decimal_places_are_refused(self):
        self.assertEqual(self.post_row(self.asha, "MARKED", "19.005").status_code, 422)
        self.assertIsNone(self.saved(self.asha))

    def test_zero_saves(self):
        self.assertEqual(self.post_row(self.asha, "MARKED", "0").status_code, 200)
        self.assertEqual(self.saved(self.asha), ("MARKED", Decimal("0")))

    def test_blank_and_blank_saves_nothing(self):
        response = self.post_row(self.asha, "", "")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(StudentResult.objects.exists())

    def test_clearing_a_saved_score_is_refused_and_deletes_nothing(self):
        self.result(self.test1, self.asha, "MARKED", "18")
        response = self.post_row(self.asha, "MARKED", "", "MARKED", "18")
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, "Enter a score or choose Absent.", status_code=422)
        self.assertEqual(self.saved(self.asha), ("MARKED", Decimal("18")))

    def test_the_same_value_again_writes_nothing(self):
        self.result(self.test1, self.asha, "MARKED", "18")
        before = StudentResult.objects.get()
        response = self.post_row(self.asha, "MARKED", "18.00", "MARKED", "18")
        self.assertContains(response, "Saved")
        after = StudentResult.objects.get()
        self.assertEqual(after.updated_at, before.updated_at)
        self.assertEqual(after.entered_by_id, before.entered_by_id)



class AutosaveConflictTests(AutosaveFixture, TestCase):
    def test_a_stale_base_is_refused_with_only_that_rows_server_value(self):
        self.result(self.test1, self.asha, "MARKED", "18")
        self.result(self.test1, self.bina, "MARKED", "13.75")
        response = self.post_row(self.asha, "MARKED", "12", "MARKED", "15")
        self.assertEqual(response.status_code, 409)
        html = response.content.decode()
        self.assertIn("data-erp-conflict", html)
        self.assertIn('data-server-status="MARKED"', html)
        self.assertIn('data-server-score="18"', html)
        self.assertIn("Keep 18", html)
        self.assertIn("Use 12", html)
        self.assertNotIn("Bina", html)
        self.assertNotIn("13.75", html)
        self.assertEqual(self.saved(self.asha), ("MARKED", Decimal("18")))

    def test_an_empty_base_never_overwrites_an_existing_row(self):
        self.result(self.test1, self.asha, "ABSENT")
        response = self.post_row(self.asha, "MARKED", "12")
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, 'data-server-status="ABSENT"', status_code=409)
        self.assertEqual(self.saved(self.asha), ("ABSENT", None))

    def test_two_first_saves_give_one_save_and_one_conflict(self):
        first = self.post_row(self.asha, "MARKED", "12")
        second = self.post_row(self.asha, "MARKED", "13", client=self.client_for(self.rao))
        self.assertEqual((first.status_code, second.status_code), (200, 409))
        self.assertEqual(self.saved(self.asha), ("MARKED", Decimal("12")))

    def test_the_fallback_request_shape_gets_the_same_conflict(self):
        # The fallback Save draft re-sends a failed row by triggering its change: the same fields.
        self.result(self.test1, self.asha, "MARKED", "18")
        response = self.post_row(self.asha, "MARKED", "9", "MARKED", "16")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.saved(self.asha), ("MARKED", Decimal("18")))

    def test_an_integrity_error_in_the_save_leaves_the_transaction_usable(self):
        with mock.patch.object(StudentResult, "save", side_effect=IntegrityError("forced")):
            response = self.post_row(self.asha, "MARKED", "12")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(StudentResult.objects.count(), 0)  # a query in the same transaction works

    def test_finalize_after_every_row_is_saved_then_autosave_is_refused(self):
        for enrollment in (self.asha, self.bina, self.ravi):
            self.assertEqual(self.post_row(enrollment, "MARKED", "10").status_code, 200)
        self.test1.finalize(actor=self.admin)
        response = self.post_row(self.asha, "MARKED", "11", "MARKED", "10")
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, FINALIZED, status_code=409)
        self.assertEqual(self.saved(self.asha), ("MARKED", Decimal("10")))

    def test_the_whole_form_post_ignores_the_base_inputs(self):
        self.result(self.test1, self.asha, "MARKED", "18")
        pk = self.asha.pk
        response = self.teacher.post(self.entry_url(self.test1), {
            f"status_{pk}": "MARKED", f"score_{pk}": "5",
            f"base_status_{pk}": "ABSENT", f"base_score_{pk}": "",
        }, follow=True)
        self.assertContains(response, "Marks saved as draft.")
        self.assertEqual(self.saved(self.asha), ("MARKED", Decimal("5")))


class AutosaveIdempotentRetryTests(AutosaveFixture, TestCase):
    """A save whose reply was lost, then Retry with the old base: Saved, never a self-conflict.

    Order under the lock: refusals (assignment, DRAFT, date, roster) first, then "stored value
    equals the request" (Saved, no write), then the base check (conflict), then the save.
    """

    def writes(self, queries):
        return [q["sql"] for q in queries.captured_queries
                if q["sql"].startswith(("INSERT", "UPDATE", "DELETE")) and "core_studentresult" in q["sql"]]

    def test_retry_with_the_old_base_after_a_lost_reply_is_saved(self):
        self.assertEqual(self.post_row(self.asha, "MARKED", "12").status_code, 200)  # reply "lost"
        retry = self.post_row(self.asha, "MARKED", "12")                            # same old base
        self.assertEqual(retry.status_code, 200)
        self.assertContains(retry, "Saved")
        self.assertNotContains(retry, "data-erp-conflict")
        self.assertIn(f'name="base_score_{self.asha.pk}" value="12"', retry.content.decode())
        self.assertEqual(self.saved(self.asha), ("MARKED", Decimal("12")))

    def test_the_same_score_written_differently_is_the_same_value(self):
        self.assertEqual(self.post_row(self.asha, "MARKED", "12.5").status_code, 200)
        retry = self.post_row(self.asha, "MARKED", "12.50")
        self.assertEqual(retry.status_code, 200)
        self.assertNotContains(retry, "data-erp-conflict")
        self.assertIn(f'name="base_score_{self.asha.pk}" value="12.5"', retry.content.decode())

    def test_absent_retried_is_saved_too(self):
        self.result(self.test1, self.asha, "MARKED", "18")
        self.assertEqual(self.post_row(self.asha, "ABSENT", "", "MARKED", "18").status_code, 200)
        retry = self.post_row(self.asha, "ABSENT", "", "MARKED", "18")
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(self.saved(self.asha), ("ABSENT", None))

    def test_the_idempotent_retry_writes_nothing(self):
        self.post_row(self.asha, "MARKED", "12")
        before = StudentResult.objects.get()
        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(self.post_row(self.asha, "MARKED", "12.00").status_code, 200)
        self.assertEqual(self.writes(queries), [])
        after = StudentResult.objects.get()
        self.assertEqual((after.updated_at, after.entered_by_id), (before.updated_at, before.entered_by_id))
        self.assertFalse(ResultCorrection.objects.exists())

    def test_a_genuinely_different_stored_value_is_still_a_conflict(self):
        self.result(self.test1, self.asha, "MARKED", "18")
        response = self.post_row(self.asha, "MARKED", "12")  # old empty base, different value
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, 'data-server-score="18"', status_code=409)
        self.assertEqual(self.saved(self.asha), ("MARKED", Decimal("18")))

    def test_a_finalized_assessment_is_refused_before_the_equality_check(self):
        self.post_row(self.asha, "MARKED", "12")
        self.force_finalize(self.test1)
        response = self.post_row(self.asha, "MARKED", "12")
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, FINALIZED, status_code=409)

    def test_an_unassigned_teacher_is_refused_before_the_equality_check(self):
        self.post_row(self.asha, "MARKED", "12")
        response = self.post_row(self.asha, "MARKED", "12", client=self.client_for(self.iyer))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, NO_LONGER, status_code=403)

    def test_a_reassigned_teacher_is_refused_before_the_equality_check(self):
        self.post_row(self.asha, "MARKED", "12")
        self.duty.end_date = MONDAY - timedelta(days=1)
        self.duty.save(update_fields=["end_date"])
        self.assertEqual(self.post_row(self.asha, "MARKED", "12").status_code, 403)

    def test_an_enrollment_off_the_roster_is_refused_before_the_equality_check(self):
        self.post_row(self.asha, "MARKED", "12")
        # Backdated: the enrollment now starts after the assessment date, so it is off the roster.
        AcademicEnrollment.objects.filter(pk=self.asha.pk).update(start_date=date(2026, 8, 1))
        response = self.post_row(self.asha, "MARKED", "12")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, OFF_ROSTER, status_code=404)


@skipUnless(connection.vendor == "postgresql", "SELECT ... FOR UPDATE only reaches PostgreSQL")
class AutosaveLockOrderSqlTests(AutosaveFixture, TestCase):
    def test_the_assessment_is_locked_before_the_result_row(self):
        self.result(self.test1, self.asha, "MARKED", "18")
        with CaptureQueriesContext(connection) as queries:
            response = self.post_row(self.asha, "MARKED", "12", "MARKED", "18")
        self.assertEqual(response.status_code, 200)
        locks = [q["sql"] for q in queries.captured_queries if "FOR UPDATE" in q["sql"]]
        first_assessment = next(i for i, sql in enumerate(locks)
                                if 'FROM "core_assessment"' in sql)
        first_result = next(i for i, sql in enumerate(locks)
                            if 'FROM "core_studentresult"' in sql)
        self.assertLess(first_assessment, first_result)


class AutosaveHistoryTests(AutosaveFixture, TestCase):
    def test_autosave_never_corrects_or_touches_publication(self):
        self.result(self.test1, self.asha, "MARKED", "18")
        with mock.patch("core.publication.mark_stale_for_result") as stale:
            self.post_row(self.asha, "MARKED", "12", "MARKED", "18")
            self.post_row(self.bina, "ABSENT", "")
        stale.assert_not_called()
        self.assertFalse(ResultCorrection.objects.exists())

    def test_correct_still_refuses_a_draft_assessment(self):
        self.post_row(self.asha, "MARKED", "12")
        with self.assertRaises(ValidationError):
            StudentResult.objects.get().correct(
                new_status="MARKED", new_score=Decimal("13"), actor=self.admin, reason="typo")


class AutosaveReplyTests(AutosaveFixture, TestCase):
    def counts_in(self, html):
        return {key: int(value) for key, value in
                re.findall(r'id="erp-count-(\w+)"[^>]*>(\d+)<', html)}

    def test_the_reply_carries_no_other_students_data(self):
        self.result(self.test1, self.bina, "MARKED", "13.75")
        html = self.post_row(self.asha, "MARKED", "12").content.decode()
        self.assertNotIn("Bina", html)
        self.assertNotIn("Ravi", html)
        self.assertNotIn("13.75", html)

    def test_out_of_band_counts_match_the_form_after_the_save(self):
        self.result(self.test1, self.bina, "ABSENT")
        html = self.post_row(self.asha, "MARKED", "12").content.decode()
        self.assertEqual(self.counts_in(html), ResultEntryForm(assessment=self.test1).counts())
        self.assertIn('hx-swap-oob="true"', html)
        self.assertIn("1 not entered", html)

    def test_the_saved_reply_swaps_the_new_base_values_out_of_band(self):
        html = self.post_row(self.asha, "MARKED", "12.50").content.decode()
        oob = re.search(rf'<span id="erp-base-{self.asha.pk}" hx-swap-oob="true">(.*?)</span>',
                        html, re.S)
        self.assertIsNotNone(oob)
        self.assertIn(f'name="base_status_{self.asha.pk}" value="MARKED"', oob.group(1))
        self.assertIn(f'name="base_score_{self.asha.pk}" value="12.5"', oob.group(1))

    def test_every_fragment_reply_is_marked_as_a_row_fragment(self):
        _, zed = self.make_student("Zed", section=self.six_b)
        replies = [
            self.post_row(self.asha, "MARKED", "12"),                        # 200
            self.post_row(self.bina, "MARKED", "99"),                        # 422
            self.post_row(self.asha, "MARKED", "13"),                        # 409 conflict
            self.post_row(zed, "MARKED", "1"),                               # 404
            self.post_row(self.ravi, "MARKED", "1", client=self.client_for(self.iyer)),  # 403
        ]
        self.assertEqual([r.status_code for r in replies], [200, 422, 409, 404, 403])
        for reply in replies:
            self.assertEqual(reply["X-ERP-Row-Fragment"], "1")

    def test_the_csrf_failure_page_is_not_a_row_fragment(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.rao)
        response = self.post_row(self.asha, "MARKED", "12", client=client)
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("X-ERP-Row-Fragment", response)

    def test_the_query_count_does_not_grow_with_the_roster(self):
        for n in range(2):
            self.make_student(f"Extra {n}")
        with CaptureQueriesContext(connection) as five:
            self.assertEqual(self.post_row(self.asha, "MARKED", "1").status_code, 200)
        for n in range(2, 37):
            self.make_student(f"Extra {n}")
        self.assertEqual(self.test1.roster().count(), 40)
        with CaptureQueriesContext(connection) as forty:
            self.assertEqual(self.post_row(self.bina, "MARKED", "1").status_code, 200)
        self.assertEqual(len(forty), len(five))


class MarksAutosavePageTests(AutosaveFixture, TestCase):
    def page(self, assessment=None):
        return self.teacher.get(self.entry_url(assessment or self.test1)).content.decode()

    def test_rows_post_to_autosave_with_their_own_timeout_and_queue(self):
        html = self.page()
        url = self.autosave_url()
        self.assertEqual(html.count(f'hx-post="{url}"'), 3)
        self.assertEqual(html.count("""hx-request='{"timeout": 15000}'"""), 3)
        self.assertEqual(html.count('hx-sync="this:queue last"'), 3)
        self.assertEqual(html.count('hx-include="this"'), 3)
        self.assertEqual(html.count('hx-trigger="change"'), 3)
        self.assertIn(f"""hx-vals='{{"enrollment": {self.asha.pk}}}'""", html)

    def test_rows_carry_base_inputs_with_the_saved_value(self):
        self.result(self.test1, self.asha, "MARKED", "18.50")
        html = self.page()
        self.assertIn(f'<input type="hidden" name="base_status_{self.asha.pk}" value="MARKED">', html)
        self.assertIn(f'<input type="hidden" name="base_score_{self.asha.pk}" value="18.5">', html)
        self.assertIn(f'<input type="hidden" name="base_status_{self.bina.pk}" value="">', html)
        self.assertIn(f'<input type="hidden" name="base_score_{self.bina.pk}" value="">', html)

    def test_only_marks_entry_gains_the_timeout_and_no_global_timeout_is_set(self):
        self.assertNotIn("hx-request", ATTENDANCE_TABLE.read_text(encoding="utf-8"))
        self.assertNotIn("htmx.config.timeout", ERP_JS)

    def test_htmx_loads_only_when_the_form_is_shown(self):
        script = "vendor/htmx/2.0.4/htmx.min.js"
        self.assertIn(script, self.page())
        later = self.make_assessment(name="Later", on=MONDAY + timedelta(days=3), term=self.term2)
        self.assertNotIn(script, self.page(later))
        self.force_finalize(self.test2)
        self.assertNotIn(script, self.page(self.test2))

    def test_save_draft_stays_as_the_fallback_with_status_and_live_regions(self):
        html = self.page()
        self.assertIn("data-erp-save-fallback", html)
        self.assertIn(">Save draft</button>", html)
        self.assertIn("data-erp-autosave-state", html)
        self.assertIn("data-erp-autosave-announce", html)
        self.assertIn('aria-live="polite"', html)
        self.assertEqual(html.count('<div class="erp-row-status" data-erp-row-status></div>'), 3)

    def test_the_csrf_token_travels_in_an_htmx_header(self):
        self.assertIn("hx-headers='{\"X-CSRFToken\": ", self.page())


class MarksAutosaveScriptTests(TestCase):
    def test_the_marks_sheet_keeps_htmx_globals_alone(self):
        self.assertNotIn("htmx.config", marks_block())

    def test_the_swap_handler_is_scoped_to_the_sheet(self):
        self.assertIn('sheet.addEventListener("htmx:beforeSwap"', marks_block())
        self.assertNotIn('document.addEventListener("htmx:beforeSwap"', ERP_JS)

    def test_last_row_enter_saves_and_keeps_focus_in_the_row(self):
        # Kept although browser test M8 covers the behaviour: in Chromium the sign-in "Next"
        # helper's focus move already fires `change`, so M8 still passes without this trigger
        # (spec F-JS4). Retire only when a browser test can tell the difference.
        block = marks_block()
        handler = block[block.index('sheet.addEventListener("keydown"'):]
        handler = handler[:handler.index("\n    });") + 8]
        self.assertIn("if (autosaveOn)", handler)
        self.assertIn('window.htmx.trigger(event.target, "change")', handler)
        self.assertIn("event.target.focus();", handler)

    def test_the_marks_block_never_submits_the_whole_form_itself(self):
        # Policy guard (an absence on every path). The behaviour, that Save draft resends only
        # failed rows and never posts the form, is browser test M6 (bt_marks_autosave.py).
        block = marks_block()
        self.assertNotIn(".submit()", block)
        self.assertNotIn("requestSubmit", block)

    def test_nothing_is_written_to_browser_storage_and_nothing_retries_by_itself(self):
        block = marks_block()
        for word in ("localStorage", "sessionStorage", "indexedDB", "setTimeout", "setInterval"):
            self.assertNotIn(word, block)

    def test_leaving_with_unsaved_rows_warns(self):
        self.assertIn('"beforeunload"', marks_block())

    def test_marks_template_keeps_the_whole_form_post_for_no_javascript(self):
        source = MARKS_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn('<form method="post"', source)
        self.assertIn('type="submit"', source)


# --- PostgreSQL concurrency (spec §4.3, §4.5, §10.1 lock order) ---------------------------------


@skipUnless(connection.vendor == "postgresql", "needs concurrent writers (PostgreSQL)")
class AutosaveConcurrencyTests(AutosaveFixture, TransactionTestCase):
    """Two connections at once. lock_timeout makes a deadlock or lock inversion fail fast."""

    def setUp(self):
        # A TransactionTestCase flushes the database, deleting the groups the migrations made.
        for name in ("School Administrators", TEACHERS_GROUP_NAME):
            Group.objects.get_or_create(name=name)
        super().setUp()
        self.admin.is_superuser = True  # the flushed admin group has no permissions left
        self.admin.save(update_fields=["is_superuser"])
        self.release = threading.Event()

    @staticmethod
    def _with_lock_timeout():
        from django.db import connection as conn

        with conn.cursor() as cursor:
            cursor.execute("SET lock_timeout = '5s'")

    def run_threads(self, holder, waiter, *, hold_point):
        """Run `holder` until it sets `hold_point` (holding the assessment lock), start `waiter`,
        check it is blocked, then let `holder` commit. An exception counts as an outcome."""
        outcomes = {}

        def run(name, work):
            from django.db import connection as conn

            try:
                self._with_lock_timeout()
                outcomes[name] = work()
            except Exception as error:  # noqa: BLE001 - the test inspects it
                outcomes[name] = error
            finally:
                conn.close()

        first = threading.Thread(target=run, args=("holder", holder), name="holder")
        first.start()
        self.assertTrue(hold_point.wait(10), "the holder never reached its lock")
        second = threading.Thread(target=run, args=("waiter", waiter), name="waiter")
        second.start()
        time.sleep(0.5)
        self.assertTrue(second.is_alive(), "the waiter did not wait for the assessment lock")
        self.release.set()
        first.join(15)
        second.join(15)
        return outcomes["holder"], outcomes["waiter"]

    def hold_inside_save_draft_result(self):
        """The thread named "holder" pauses right after its first save_draft_result."""
        held = threading.Event()
        original = Assessment.save_draft_result

        def paused(assessment, **kwargs):
            result = original(assessment, **kwargs)
            if threading.current_thread().name == "holder" and not held.is_set():
                held.set()
                self.release.wait(10)
            return result

        patch = mock.patch.object(Assessment, "save_draft_result", paused)
        patch.start()
        self.addCleanup(patch.stop)
        return held

    def save_all(self, value="10"):
        for enrollment in (self.asha, self.bina, self.ravi):
            self.result(self.test1, enrollment, "MARKED", value)

    def test_finalize_first_then_autosave_is_refused_as_finalized(self):
        self.save_all()
        held = threading.Event()
        assessment = Assessment.objects.get(pk=self.test1.pk)

        def finalize_and_hold():
            from django.db import transaction

            with transaction.atomic():
                assessment.finalize(actor=self.admin)
                held.set()
                self.release.wait(10)
            return "finalized"

        holder, waiter = self.run_threads(
            finalize_and_hold,
            lambda: self.post_row(self.asha, "MARKED", "11", "MARKED", "10").status_code,
            hold_point=held,
        )
        self.assertEqual((holder, waiter), ("finalized", 409))
        self.assertEqual(self.saved(self.asha), ("MARKED", Decimal("10")))

    def test_autosave_first_then_finalize_sees_the_saved_row(self):
        self.save_all()
        held = self.hold_inside_save_draft_result()

        def finalize():
            Assessment.objects.get(pk=self.test1.pk).finalize(actor=self.admin)
            return "finalized"

        holder, waiter = self.run_threads(
            lambda: self.post_row(self.asha, "MARKED", "11", "MARKED", "10").status_code,
            finalize, hold_point=held,
        )
        self.assertEqual((holder, waiter), (200, "finalized"))
        self.assertEqual(self.saved(self.asha), ("MARKED", Decimal("11")))

    def test_whole_form_first_then_autosave_on_its_row_gets_the_conflict(self):
        self.save_all()
        held = self.hold_inside_save_draft_result()
        pk = self.asha.pk
        holder, waiter = self.run_threads(
            lambda: self.teacher.post(self.entry_url(self.test1),
                                      {f"status_{pk}": "MARKED", f"score_{pk}": "15"}).status_code,
            lambda: self.post_row(self.asha, "MARKED", "12", "MARKED", "10",
                                  client=self.client_for(self.rao)).status_code,
            hold_point=held,
        )
        self.assertEqual((holder, waiter), (302, 409))
        self.assertEqual(self.saved(self.asha), ("MARKED", Decimal("15")))

    def test_whole_form_first_then_autosave_on_another_row_saves(self):
        held = self.hold_inside_save_draft_result()
        pk = self.asha.pk
        holder, waiter = self.run_threads(
            lambda: self.teacher.post(self.entry_url(self.test1),
                                      {f"status_{pk}": "MARKED", f"score_{pk}": "15"}).status_code,
            lambda: self.post_row(self.bina, "ABSENT", "",
                                  client=self.client_for(self.rao)).status_code,
            hold_point=held,
        )
        self.assertEqual((holder, waiter), (302, 200))
        self.assertEqual(self.saved(self.asha), ("MARKED", Decimal("15")))
        self.assertEqual(self.saved(self.bina), ("ABSENT", None))

    def test_autosave_first_then_whole_form_keeps_last_write_wins(self):
        self.save_all()
        held = self.hold_inside_save_draft_result()
        pk = self.asha.pk
        holder, waiter = self.run_threads(
            lambda: self.post_row(self.asha, "MARKED", "12", "MARKED", "10").status_code,
            lambda: self.client_for(self.rao).post(
                self.entry_url(self.test1),
                {f"status_{pk}": "MARKED", f"score_{pk}": "16"}).status_code,
            hold_point=held,
        )
        self.assertEqual((holder, waiter), (200, 302))
        self.assertEqual(self.saved(self.asha), ("MARKED", Decimal("16")))

    def test_two_autosaves_on_one_row_with_one_base_give_one_save_and_one_conflict(self):
        barrier = threading.Barrier(2)
        outcomes = []
        clients = [self.client_for(self.rao), self.client_for(self.rao)]

        def work(client, score):
            from django.db import connection as conn

            try:
                self._with_lock_timeout()
                barrier.wait()
                outcomes.append(self.post_row(self.asha, "MARKED", score, client=client).status_code)
            finally:
                conn.close()

        threads = [threading.Thread(target=work, args=(clients[0], "12")),
                   threading.Thread(target=work, args=(clients[1], "13"))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(15)
        self.assertEqual(sorted(outcomes), [200, 409])
        self.assertEqual(StudentResult.objects.count(), 1)
