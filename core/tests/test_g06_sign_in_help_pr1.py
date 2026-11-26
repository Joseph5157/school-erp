"""G-06 sign-in help spec PR 1 (§3, §5, §6, §10): models, office queue, permissions, cleanup.

Synthetic data only. There is no public page in PR 1, so every request row here is made directly.
"""

import contextlib
import importlib
import io
import logging
from datetime import timedelta
from unittest import mock

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management import CommandError, call_command
from django.db import DatabaseError, connection, connections
from django.db.migrations.executor import MigrationExecutor
from django.http import Http404
from django.test import Client, TestCase, TransactionTestCase, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone

from accounts import request_cache, sign_in_help
from accounts.models import SecurityEvent, SignInHelpDay, SignInHelpRequest, SignInHelpSourceHour
from core import dashboard, nav_badges, reset_staff
from core.models import Guardian, GuardianAccount

User = get_user_model()
Event = SecurityEvent.EventType
LIST = reverse("core:sign-in-help-requests")
VIEW = "view_signinhelprequest"
CHANGE = "change_signinhelprequest"
TRICKY = "<script>alert('x')</script> & ‮evil"


def handle_url(row):
    return reverse("core:sign-in-help-request-handle", args=[row.pk])


def make_request(name="Asha Test", child="Ravi Test", klass="Class 5 B", age=timedelta(hours=1),
                 **extra):
    return SignInHelpRequest.objects.create(
        guardian_name=name, child_name=child, child_class=klass, repeat_key="k" * 64,
        received_at=timezone.now() - age, **extra,
    )


def queue_permissions():
    return Permission.objects.filter(content_type__app_label="accounts", codename__in=[VIEW, CHANGE])


def handled_events():
    return SecurityEvent.objects.filter(event_type=Event.SIGN_IN_HELP_HANDLED)


class Fixture:
    def setUp(self):
        super().setUp()
        self.admins = Group.objects.get(name="School Administrators")
        self.reset_group = Group.objects.get(name=reset_staff.RESET_GROUP)
        self.root = User.objects.create_superuser("root", password="pass-12345")
        self.member = self.user("member", "Mira", "Member", groups=[self.admins, self.reset_group])
        self.office = self.user("office", groups=[self.admins])

    def user(self, username, first="", last="", groups=()):
        user = User.objects.create_user(username=username, password="pass-12345",
                                        first_name=first, last_name=last)
        for group in groups:
            user.groups.add(group)
        return user

    def client_for(self, user, **kwargs):
        client = Client(**kwargs)
        client.login(username=user.username, password="pass-12345")
        return client


class PermissionTests(Fixture, TestCase):
    def test_migration_gave_the_reset_group_both_queue_permissions(self):
        codenames = set(self.reset_group.permissions.values_list("codename", flat=True))
        self.assertTrue({VIEW, CHANGE} <= codenames)

    def test_only_view_and_change_permissions_exist(self):
        codenames = set(Permission.objects.filter(
            content_type__app_label="accounts", codename__contains="signinhelp"
        ).values_list("codename", flat=True))
        self.assertEqual(codenames, {VIEW, CHANGE})

    def test_group_member_sees_the_queue(self):
        make_request()
        response = self.client_for(self.member).get(LIST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Asha Test")
        self.assertContains(response, "Sign-in help requests")  # sidebar link
        self.assertContains(response, 'aria-label="Breadcrumbs"')

    def test_reset_permission_alone_is_not_enough(self):
        holder = self.user("resetter")
        holder.user_permissions.add(Permission.objects.get(codename="reset_guardian_password"))
        self.assertEqual(self.client_for(holder).get(LIST).status_code, 403)

    def test_administrator_teacher_and_guardian_refused(self):
        row = make_request()
        teacher = self.user("teach", groups=[Group.objects.get(name="Teachers")])
        guardian = self.user("parent")
        GuardianAccount.objects.create(
            user=guardian, guardian=Guardian.objects.create(full_name="Parent Test"),
            identity_verified_by=self.root, identity_verification_method="OTHER",
            identity_verification_note="x", created_by=self.root)
        for user in (self.office, teacher, guardian):
            client = self.client_for(user)
            self.assertEqual(client.get(LIST).status_code, 403, user.username)
            self.assertEqual(client.post(handle_url(row), {"outcome": "NO_MATCH"}).status_code, 403)
        row.refresh_from_db()
        self.assertEqual(row.outcome, "")

    def test_anonymous_goes_to_sign_in(self):
        for response in (Client().get(LIST), Client().post(handle_url(make_request()), {})):
            self.assertEqual(response.status_code, 302)
            self.assertIn(reverse("login"), response["Location"])

    def test_view_only_holder_sees_no_form_and_cannot_handle(self):
        viewer = self.user("viewer")
        viewer.user_permissions.add(queue_permissions().get(codename=VIEW))
        row = make_request()
        client = self.client_for(viewer)
        response = client.get(LIST)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, handle_url(row))
        self.assertEqual(client.post(handle_url(row), {"outcome": "NO_MATCH"}).status_code, 403)

    def test_handle_route_refuses_get_and_pages_deny_framing(self):
        client = self.client_for(self.member)
        self.assertEqual(client.get(handle_url(make_request())).status_code, 405)
        self.assertEqual(client.get(LIST)["X-Frame-Options"], "DENY")

    def test_handle_without_csrf_token_is_refused(self):
        row = make_request()
        client = self.client_for(self.member, enforce_csrf_checks=True)
        self.assertEqual(client.post(handle_url(row), {"outcome": "NO_MATCH"}).status_code, 403)
        row.refresh_from_db()
        self.assertEqual(row.outcome, "")

    def test_models_are_not_in_the_django_admin(self):
        for model in (SignInHelpRequest, SignInHelpDay, SignInHelpSourceHour):
            self.assertNotIn(model, admin.site._registry)


class HandleTests(Fixture, TestCase):
    def test_handle_records_outcome_and_one_routine_event(self):
        row = make_request()
        response = self.client_for(self.member).post(handle_url(row), {"outcome": "VISIT_BOOKED"})
        self.assertRedirects(response, LIST)
        row.refresh_from_db()
        self.assertEqual((row.outcome, row.handled_by), ("VISIT_BOOKED", self.member))
        self.assertIsNotNone(row.handled_at)
        event = handled_events().get()
        self.assertEqual(event.event_class, SecurityEvent.EventClass.ROUTINE)
        self.assertEqual(event.detail, {"outcome": "VISIT_BOOKED"})
        self.assertEqual(event.actor, self.member)
        self.assertIsNone(event.guardian_id_ref)
        self.assertIsNone(event.subject_user)

    def test_event_type_is_routine(self):
        self.assertEqual(SecurityEvent.class_for(Event.SIGN_IN_HELP_HANDLED),
                         SecurityEvent.EventClass.ROUTINE)

    def test_outcome_is_required_and_limited_to_the_five_values(self):
        row = make_request()
        client = self.client_for(self.member)
        for data in ({}, {"outcome": ""}, {"outcome": "SOMETHING"}):
            response = client.post(handle_url(row), data, follow=True)
            self.assertContains(response, "Choose an outcome.")
        row.refresh_from_db()
        self.assertEqual(row.outcome, "")
        self.assertFalse(handled_events().exists())
        self.assertEqual(len(SignInHelpRequest.Outcome.values), 5)

    def test_second_handle_changes_nothing_and_names_who_handled(self):
        row = make_request()
        sign_in_help.handle(row.pk, actor=self.member, outcome="NOT_REACHED")
        other = self.user("other", groups=[self.admins, self.reset_group])
        response = self.client_for(other).post(handle_url(row), {"outcome": "NO_MATCH"}, follow=True)
        self.assertContains(response, "Already handled by Mira Member.")
        row.refresh_from_db()
        self.assertEqual((row.outcome, row.handled_by), ("NOT_REACHED", self.member))
        self.assertEqual(handled_events().count(), 1)

    def test_missing_or_expired_request_is_404(self):
        client = self.client_for(self.member)
        expired = make_request(age=timedelta(days=31))
        self.assertEqual(client.post(handle_url(expired), {"outcome": "NO_MATCH"}).status_code, 404)
        missing = reverse("core:sign-in-help-request-handle", args=[expired.pk + 999])
        self.assertEqual(client.post(missing, {"outcome": "NO_MATCH"}).status_code, 404)
        expired.refresh_from_db()
        self.assertEqual(expired.outcome, "")
        self.assertFalse(handled_events().exists())

    def test_service_refuses_an_unknown_outcome(self):
        with self.assertRaises(ValueError):
            sign_in_help.handle(make_request().pk, actor=self.member, outcome="free text")


class PageTests(Fixture, TestCase):
    def test_typed_values_are_escaped_inside_bdi_on_both_tabs(self):
        make_request(name=TRICKY, child=TRICKY, klass="5 <b>")
        handled = make_request(name=TRICKY, child="Other", klass="6")
        sign_in_help.handle(handled.pk, actor=self.member, outcome="NO_MATCH")
        client = self.client_for(self.member)
        escaped = "<bdi>&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt; &amp; ‮evil</bdi>"
        for tab in ("open", "handled"):
            body = client.get(LIST, {"tab": tab}).content.decode()
            self.assertIn(escaped, body)
            self.assertNotIn("<script>alert", body)
            self.assertNotIn('evil"', body)  # never inside an attribute

    def test_open_tab_oldest_first_handled_tab_newest_first(self):
        make_request(name="Older", age=timedelta(hours=5))
        make_request(name="Newer", age=timedelta(hours=1))
        body = self.client_for(self.member).get(LIST).content.decode()
        self.assertLess(body.index("Older"), body.index("Newer"))
        first = make_request(name="HandledFirst")
        second = make_request(name="HandledSecond")
        sign_in_help.handle(first.pk, actor=self.member, outcome="NO_MATCH",
                            now=timezone.now() - timedelta(minutes=5))
        sign_in_help.handle(second.pk, actor=self.member, outcome="NO_MATCH")
        body = self.client_for(self.member).get(LIST, {"tab": "handled"}).content.decode()
        self.assertLess(body.index("HandledSecond"), body.index("HandledFirst"))

    def test_expired_rows_hidden_and_the_cleanup_warning_shown(self):
        make_request(name="Expired Person", age=timedelta(days=31))
        response = self.client_for(self.member).get(LIST)
        self.assertNotContains(response, "Expired Person")
        self.assertContains(response, "Old requests are waiting to be deleted. Check the cron job.")

    def test_drop_notice_shows_today_and_last_seven_days(self):
        today = timezone.localdate()
        SignInHelpDay.objects.create(day=today, dropped=2)
        SignInHelpDay.objects.create(day=today - timedelta(days=3), dropped=5)
        SignInHelpDay.objects.create(day=today - timedelta(days=9), dropped=40)
        response = self.client_for(self.member).get(LIST)
        self.assertContains(response, "Not saved because of limits or repeats: today 2, last 7 days 7.")

    def test_page_has_no_search_box_and_no_guardian_link(self):
        make_request()
        body = self.client_for(self.member).get(LIST).content.decode()
        self.assertNotIn('type="search"', body)
        self.assertNotIn(reverse("core:guardian-list") + "?", body)


class IndicatorTests(Fixture, TestCase):
    def test_badge_counts_only_open_rows_inside_retention(self):
        make_request()
        make_request(age=timedelta(days=30, minutes=1))
        make_request(outcome="NO_MATCH")
        self.assertEqual(sign_in_help.open_count(), 1)
        self.assertEqual(nav_badges.queue_counts(self.member)["core:sign-in-help-requests"], 1)

    def test_hour_rows_older_than_a_day_raise_the_cleanup_warning(self):
        now = timezone.now()
        SignInHelpSourceHour.objects.create(source_key="d" * 64,
                                            hour_start=sign_in_help.hour_start(now) - timedelta(hours=6))
        self.assertFalse(sign_in_help.expired_rows_exist(now))  # normal wait for the 6-hour cron
        SignInHelpSourceHour.objects.create(source_key="e" * 64,
                                            hour_start=now - timedelta(days=1, minutes=1))
        self.assertTrue(sign_in_help.expired_rows_exist(now))
        card = {c["key"]: c for c in dashboard.overview_cards(self.member)}["sign-in-help"]
        self.assertIn("Old requests are waiting to be deleted. Check the cron job.", card["detail"])
        response = self.client_for(self.member).get(LIST)
        self.assertContains(response, "Old requests are waiting to be deleted. Check the cron job.")

    def test_non_holder_runs_no_badge_query(self):
        with mock.patch.object(sign_in_help, "open_count", side_effect=AssertionError):
            counts = nav_badges.queue_counts(self.office)
        self.assertNotIn("core:sign-in-help-requests", counts)

    def test_badge_counted_once_per_request(self):
        request_cache.enable(self.member)  # as AccountSecurityMiddleware does for request.user
        with mock.patch.object(sign_in_help, "open_count", return_value=3) as counted:
            nav_badges.queue_counts(self.member)
            nav_badges.cached_count(self.member, "core:sign-in-help-requests")
        self.assertEqual(counted.call_count, 1)

    def test_overview_card_only_for_holders_with_drop_and_cleanup_notes(self):
        make_request()
        make_request(age=timedelta(days=31))
        SignInHelpDay.objects.create(day=timezone.localdate(), dropped=4)
        cards = {card["key"]: card for card in dashboard.overview_cards(self.member)}
        card = cards["sign-in-help"]
        self.assertEqual(card["count"], 1)
        self.assertIn("4 not saved today because of limits or repeats.", card["detail"])
        self.assertIn("Old requests are waiting to be deleted. Check the cron job.", card["detail"])
        self.assertNotIn("sign-in-help", {c["key"] for c in dashboard.overview_cards(self.office)})


class RetentionBoundaryTests(Fixture, TestCase):
    """Exactly 30 days old is expired everywhere: hidden, not counted, not handled, purged
    (review PR1-SR-01). One microsecond younger is still live."""

    def test_exact_30_day_boundary(self):
        now = timezone.now()
        boundary = SignInHelpRequest.objects.create(
            guardian_name="Boundary Exact", child_name="C", child_class="1", repeat_key="k" * 64,
            received_at=now - timedelta(days=30))
        inside = SignInHelpRequest.objects.create(
            guardian_name="Boundary Inside", child_name="C", child_class="1", repeat_key="k" * 64,
            received_at=now - timedelta(days=30) + timedelta(microseconds=1))
        with mock.patch("django.utils.timezone.now", return_value=now):
            self.assertEqual(list(sign_in_help.open_requests()), [inside])
            self.assertEqual(sign_in_help.open_count(), 1)
            self.assertEqual(nav_badges.queue_counts(self.member)["core:sign-in-help-requests"], 1)
            body = self.client_for(self.member).get(LIST).content.decode()
            self.assertNotIn("Boundary Exact", body)
            self.assertIn("Boundary Inside", body)
            with self.assertRaises(Http404):
                sign_in_help.handle(boundary.pk, actor=self.member, outcome="NO_MATCH")
            self.assertEqual(sign_in_help.purge()["requests"], 1)
        self.assertEqual(list(SignInHelpRequest.objects.all()), [inside])


class ResetStaffTests(Fixture, TestCase):
    def test_reset_staff_page_mentions_the_queue_and_lists_other_holders(self):
        direct = self.user("direct", groups=[self.admins])
        direct.user_permissions.add(queue_permissions().get(codename=VIEW))
        other = Group.objects.create(name="Front desk")
        other.permissions.add(queue_permissions().get(codename=CHANGE))
        response = self.client_for(self.root).get(reverse("core:reset-staff"))
        self.assertContains(response, "Members also see sign-in help requests.")
        self.assertContains(response, "Can also see sign-in help requests")
        self.assertContains(response, "(direct) &middot; granted outside this page")
        self.assertContains(response, 'Group "Front desk"')

    def test_add_confirmation_mentions_the_queue(self):
        candidate = self.user("candidate", groups=[self.admins])
        response = self.client_for(self.root).post(reverse("core:reset-staff-add"),
                                                   {"user": candidate.pk}, follow=True)
        self.assertContains(response, "This also lets them see sign-in help requests.")

    def test_role_permission_gaps_lists_queue_holders(self):
        out = io.StringIO()
        call_command("role_permission_gaps", stdout=out)
        text = out.getvalue()
        self.assertIn("Who can see sign-in help requests", text)
        self.assertIn("  member (group permission)", text)
        self.assertNotIn("  root", text)

    def test_queue_holders_count_superusers(self):
        holders = reset_staff.queue_holders()
        self.assertIn(self.root, holders)
        self.assertIn(self.member, holders)
        self.assertNotIn(self.office, holders)


class PurgeTests(Fixture, TestCase):
    def run_command(self, *args):
        out = io.StringIO()
        call_command("purge_sign_in_help_requests", *args, stdout=out)
        return out.getvalue()

    def test_each_table_is_purged_at_its_own_age(self):
        now = timezone.now()
        today = timezone.localdate(now)
        keep = make_request(age=timedelta(days=29))
        make_request(age=timedelta(days=31))
        make_request(age=timedelta(days=31), outcome="NO_MATCH")
        SignInHelpDay.objects.create(day=today - timedelta(days=31))
        kept_day = SignInHelpDay.objects.create(day=today - timedelta(days=29))
        this_hour = sign_in_help.hour_start(now)
        SignInHelpSourceHour.objects.create(source_key="a" * 64,
                                            hour_start=this_hour - timedelta(hours=1))
        kept_hour = SignInHelpSourceHour.objects.create(source_key="b" * 64, hour_start=this_hour)
        SecurityEvent.record(Event.SIGN_IN_HELP_HANDLED, detail={"outcome": "NO_MATCH"})

        output = self.run_command()

        self.assertEqual(output.strip(), "Deleted 1 day rows, 2 requests, 1 hour rows.")
        self.assertEqual(list(SignInHelpRequest.objects.all()), [keep])
        self.assertEqual(list(SignInHelpDay.objects.all()), [kept_day])
        self.assertEqual(list(SignInHelpSourceHour.objects.all()), [kept_hour])
        self.assertEqual(handled_events().count(), 1)

    def test_purge_works_in_batches(self):
        for _ in range(5):
            make_request(age=timedelta(days=40))
        with mock.patch.object(sign_in_help, "_delete_batch",
                               wraps=sign_in_help._delete_batch) as batches:
            deleted = sign_in_help.purge(batch=2)
        self.assertEqual(deleted["requests"], 5)
        self.assertFalse(SignInHelpRequest.objects.exists())
        self.assertEqual(batches.call_count, 1 + 3 + 1)  # day rows, requests (2+2+1), hour rows

    def test_all_without_yes_deletes_nothing(self):
        make_request()
        SignInHelpDay.objects.create(day=timezone.localdate())
        output = self.run_command("--all")
        self.assertIn("Would delete 1 day rows, 1 requests, 0 hour rows.", output)
        self.assertEqual(SignInHelpRequest.objects.count(), 1)
        self.assertEqual(SignInHelpDay.objects.count(), 1)

    def test_all_yes_deletes_every_row_but_no_event(self):
        make_request()
        make_request(outcome="NO_MATCH")
        SignInHelpDay.objects.create(day=timezone.localdate(), stored=2)
        SignInHelpSourceHour.objects.create(source_key="c" * 64,
                                            hour_start=sign_in_help.hour_start())
        SecurityEvent.record(Event.SIGN_IN_HELP_HANDLED, detail={"outcome": "NO_MATCH"})
        output = self.run_command("--all", "--yes")
        self.assertIn("No sign-in help rows remain.", output)
        self.assertEqual(sign_in_help.row_counts(), {"day rows": 0, "requests": 0, "hour rows": 0})
        self.assertTrue(handled_events().exists())

    def test_yes_alone_is_refused(self):
        make_request()
        with self.assertRaises(CommandError):
            self.run_command("--yes")
        self.assertEqual(SignInHelpRequest.objects.count(), 1)

    def test_database_error_fails_the_command_without_the_message(self):
        with mock.patch.object(sign_in_help, "purge", side_effect=DatabaseError("Asha Test")):
            with self.assertRaises(CommandError) as raised:
                self.run_command()
        self.assertIn("DatabaseError", str(raised.exception))
        self.assertNotIn("Asha Test", str(raised.exception))

    def test_rows_left_after_a_wipe_fail_the_command(self):
        make_request()
        nothing = {"day rows": 0, "requests": 0, "hour rows": 0}
        with mock.patch.object(sign_in_help, "purge", return_value=nothing):
            with self.assertRaises(CommandError) as raised:
                self.run_command("--all", "--yes")
        self.assertIn("Rows remain: 0 day rows, 1 requests, 0 hour rows.", str(raised.exception))


class LoggingTests(Fixture, TestCase):
    def test_no_typed_value_reaches_the_logs(self):
        values = {"name": "Zebulon Secretname", "child": "Quintus Childname", "klass": "Class 9 Z"}
        expired = make_request(age=timedelta(days=31), **values)
        live = make_request(**values)
        client = self.client_for(self.member)
        with self.assertLogs(level=logging.DEBUG) as captured:
            logging.getLogger("g06.test").debug("start")
            client.get(LIST)
            client.post(handle_url(live), {"outcome": "VISIT_BOOKED"})
            client.post(handle_url(live), {"outcome": "NO_MATCH"})
            client.post(handle_url(expired), {"outcome": "NO_MATCH"})  # 404
            call_command("purge_sign_in_help_requests", stdout=io.StringIO())
        text = "\n".join(captured.output)
        for value in ("Zebulon", "Quintus", "Class 9 Z"):
            self.assertNotIn(value, text)


class DataMigrationTests(TestCase):
    """The permission grant in core 0097, run against the migration state's apps."""

    def setUp(self):
        self.module = importlib.import_module("core.migrations.0097_sign_in_help_permissions")
        executor = MigrationExecutor(connection)
        self.apps = executor.loader.project_state(("core", "0097_sign_in_help_permissions")).apps
        self.editor = mock.Mock(connection=connection)
        self.group = Group.objects.get(name=reset_staff.RESET_GROUP)

    def queue_codenames(self, group):
        return set(group.permissions.filter(codename__in=[VIEW, CHANGE])
                   .values_list("codename", flat=True))

    def test_forward_is_idempotent_and_keeps_other_permissions(self):
        others = set(self.group.permissions.exclude(codename__in=[VIEW, CHANGE])
                     .values_list("pk", flat=True))
        self.assertTrue(others)  # the group already holds reset_guardian_password
        self.module.grant_to_reset_group(self.apps, self.editor)
        self.module.grant_to_reset_group(self.apps, self.editor)
        self.assertEqual(self.queue_codenames(self.group), {VIEW, CHANGE})
        self.assertEqual(queue_permissions().count(), 2)
        self.assertEqual(set(self.group.permissions.exclude(codename__in=[VIEW, CHANGE])
                             .values_list("pk", flat=True)), others)

    def test_reverse_removes_only_the_queue_permissions(self):
        self.module.remove_from_reset_group(self.apps, self.editor)
        self.assertEqual(self.queue_codenames(self.group), set())
        self.assertTrue(self.group.permissions.filter(codename="reset_guardian_password").exists())
        self.module.grant_to_reset_group(self.apps, self.editor)
        self.assertEqual(self.queue_codenames(self.group), {VIEW, CHANGE})

    def test_creates_missing_permissions(self):
        queue_permissions().delete()
        self.module.grant_to_reset_group(self.apps, self.editor)
        self.assertEqual(self.queue_codenames(self.group), {VIEW, CHANGE})

    def test_without_the_group_it_does_nothing(self):
        self.group.delete()
        self.module.grant_to_reset_group(self.apps, self.editor)
        self.module.remove_from_reset_group(self.apps, self.editor)
        self.assertEqual(queue_permissions().count(), 2)
        self.assertFalse(Group.objects.filter(permissions__in=queue_permissions()).exists())


class ModelMigrationRoundTripTests(TransactionTestCase):
    """accounts 0013 and core 0097 migrate backward (printing counts only) and forward again."""

    BEFORE = [("accounts", "0012_temporary_password_expiry"),
              ("core", "0096_portal_password_resets_group")]

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def _fixture_teardown(self):
        # The SQLite flush deletes row by row, so lift the append-only guards for it and put them
        # back (PostgreSQL truncates, which fires no row trigger). The migrations record a
        # CONTACT_AUDIT_STARTED event that the security-event guard would refuse to delete.
        if connection.vendor != "sqlite":
            return super()._fixture_teardown()
        guards = importlib.import_module("accounts.migrations.0003_securityevent_guards")
        with connection.cursor() as cursor:
            cursor.execute("DROP TRIGGER IF EXISTS core_nt_no_delete")
            cursor.execute("DROP TRIGGER IF EXISTS acc_se_retention")
        try:
            super()._fixture_teardown()
        finally:
            with connection.cursor() as cursor:
                cursor.execute(
                    "CREATE TRIGGER core_nt_no_delete BEFORE DELETE ON core_notificationtemplate "
                    "BEGIN SELECT RAISE(ABORT, 'Notification templates are never deleted.'); END;"
                )
                cursor.execute(guards.SQLITE[1])

    def test_backward_prints_counts_only_and_drops_the_tables(self):
        make_request(name="Zebulon Secretname")
        SignInHelpDay.objects.create(day=timezone.localdate(), stored=1)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            executor = MigrationExecutor(connection)
            executor.loader.build_graph()
            executor.migrate(self.BEFORE)
        text = out.getvalue()
        self.assertIn("Dropping sign-in help tables: 1 requests, 1 day rows, 0 hour rows.", text)
        self.assertNotIn("Zebulon", text)
        self.assertNotIn(SignInHelpRequest._meta.db_table, connection.introspection.table_names())
        group = Group.objects.get(name=reset_staff.RESET_GROUP)
        self.assertFalse(group.permissions.filter(codename__in=[VIEW, CHANGE]).exists())
        self.assertTrue(group.permissions.filter(codename="reset_guardian_password").exists())

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        self.assertIn(SignInHelpRequest._meta.db_table, connection.introspection.table_names())
        self.assertEqual(group.permissions.filter(codename__in=[VIEW, CHANGE]).count(), 2)


@skipUnlessDBFeature("has_select_for_update_skip_locked")
class PurgeLockTimeoutTests(TransactionTestCase):
    """A real PostgreSQL lock timeout fails the command (review PR1-SR-02).

    Another connection holds today's gate row, so the batch waits for its 2-second lock_timeout and
    gets a real OperationalError. The command must exit unsuccessfully, print no "Deleted" line,
    roll the batch back and leave unrelated data alone.
    """

    def test_lock_timeout_fails_the_command_and_changes_nothing(self):
        if connection.vendor != "postgresql":
            self.skipTest("SET LOCAL lock_timeout is PostgreSQL only")
        today = timezone.localdate()
        gate = SignInHelpDay.objects.create(day=today, stored=1)
        old_day = SignInHelpDay.objects.create(day=today - timedelta(days=40))
        expired = make_request(name="Expired Row", age=timedelta(days=40))
        live = make_request(name="Live Row")
        bystander = User.objects.create_user("bystander", password="pass-12345")

        other = connections.create_connection("default")
        try:
            other.set_autocommit(False)
            with other.cursor() as cursor:
                cursor.execute(
                    f"SELECT id FROM {SignInHelpDay._meta.db_table} WHERE id = %s FOR UPDATE",
                    [gate.pk],
                )
            out = io.StringIO()
            with self.assertRaises(CommandError) as raised:
                call_command("purge_sign_in_help_requests", stdout=out)
        finally:
            other.rollback()
            other.close()

        self.assertIn("OperationalError", str(raised.exception))
        self.assertNotIn("Deleted", out.getvalue())
        self.assertTrue(SignInHelpDay.objects.filter(pk=old_day.pk).exists())  # rolled back
        self.assertTrue(SignInHelpRequest.objects.filter(pk=expired.pk).exists())
        self.assertTrue(SignInHelpRequest.objects.filter(pk=live.pk).exists())
        self.assertTrue(User.objects.filter(pk=bystander.pk).exists())
        # Once the lock is gone, the same command succeeds.
        self.assertIn("Deleted 1 day rows, 1 requests, 0 hour rows.",
                      self._run_ok())

    def _run_ok(self):
        out = io.StringIO()
        call_command("purge_sign_in_help_requests", stdout=out)
        return out.getvalue()
