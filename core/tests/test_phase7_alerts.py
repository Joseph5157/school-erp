"""Phase 7 Gates 2 and 4: absence alerts and report-card notices (ADR 0015)."""

from datetime import date
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from core import guardian_accounts as ga
from core import notification_producers, notifications
from core.forms import SchoolForm
from core.models import (
    Applicant,
    AttendanceRegister,
    AttendanceStatus,
    Guardian,
    GuardianContactConsent,
    Notification,
    NotificationTemplate,
    School,
    Student,
    StudentGuardian,
)
from core.tests.test_phase6_access_boundary import TODAY
from core.tests.test_phase6_publication import PublicationFixture
from core.tests.test_phase7_notifications import NotificationFixture

BASE = "https://erp.example"
ABSENCE_BODY = (
    "Dear parent, {first_name} was marked absent at school on {date}. "
    "Attendance details: {portal_url}"
)
NOTICE_BODY = (
    "Dear parent, {first_name}'s report card is now available on the school portal: "
    "{portal_url}"
)
ADDRESS_ERROR = "Set the portal address (PORTAL_BASE_URL) before sending WhatsApp messages."


class SeededTemplateTests(TestCase):
    def test_both_texts_are_seeded_approved_and_valid(self):
        for key, body in (("absence-alert", ABSENCE_BODY),
                          ("report-card-published", NOTICE_BODY)):
            with self.subTest(key=key):
                template = NotificationTemplate.objects.get(
                    key=key, channel="WHATSAPP", language="en", version=1)
                self.assertTrue(template.approved)
                self.assertEqual(template.body, body)
                template.full_clean()


class SchoolFormAddressTests(TestCase):
    def form(self, mode):
        return SchoolForm(data={"name": "Greenwood High", "notification_channel": mode})

    @override_settings(PORTAL_BASE_URL="")
    def test_assist_refused_without_portal_address(self):
        form = self.form("ASSIST")
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["notification_channel"], [ADDRESS_ERROR])

    @override_settings(PORTAL_BASE_URL="")
    def test_portal_only_allowed_without_portal_address(self):
        self.assertTrue(self.form("PORTAL_ONLY").is_valid())

    @override_settings(PORTAL_BASE_URL=BASE)
    def test_assist_allowed_with_portal_address(self):
        self.assertTrue(self.form("ASSIST").is_valid())


class ToSendWarningTests(NotificationFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username="admin", password="pass-12345")
        self.url = reverse("core:notifications-to-send")

    @override_settings(PORTAL_BASE_URL="")
    def test_warning_when_assist_without_portal_address(self):
        page = self.client.get(self.url)
        self.assertTrue(page.context["portal_address_missing"])
        self.assertContains(page, "PORTAL_BASE_URL")

    @override_settings(PORTAL_BASE_URL=BASE)
    def test_no_warning_with_portal_address(self):
        page = self.client.get(self.url)
        self.assertFalse(page.context["portal_address_missing"])
        self.assertNotContains(page, "PORTAL_BASE_URL")

    @override_settings(PORTAL_BASE_URL="")
    def test_no_address_warning_in_portal_only(self):
        School.objects.filter(pk=self.school.pk).update(notification_channel="PORTAL_ONLY")
        self.assertFalse(self.client.get(self.url).context["portal_address_missing"])


ABSENCE = Notification.Type.ABSENCE
NOTICE = Notification.Type.RESULT_PUBLISHED
PREPARED = Notification.Status.PREPARED


class AlertFixture(PublicationFixture):
    """Phase 6 publication fixture (Meena → Asha granted, Other → Bina granted,
    Meena → Ravi linked without access; today pinned to 2026-10-12 through
    `self.today`) plus an ASSIST school, consent for both portal guardians and
    a portal address."""

    def setUp(self):
        super().setUp()
        address = override_settings(PORTAL_BASE_URL=BASE)
        address.enable()
        self.addCleanup(address.disable)
        self.school = School.objects.create(
            name="Greenwood High", notification_channel=School.NotificationMode.ASSIST)
        self.consent(self.meena)
        self.consent(self.other)

    def consent(self, guardian, status=GuardianContactConsent.Status.OPTED_IN):
        GuardianContactConsent.objects.create(
            guardian=guardian, status=status,
            source=GuardianContactConsent.Source.PAPER_FORM, recorded_by=self.admin)

    def register(self, on_date=TODAY, *, asha=AttendanceStatus.ABSENT,
                 bina=AttendanceStatus.PRESENT, note="", submit=True):
        register = AttendanceRegister.objects.create(
            academic_year=self.year, class_grade=self.grade6, section=self.six_a, date=on_date)
        register.save_draft_entry(enrollment=self.asha_e, status=asha, absence_note=note)
        register.save_draft_entry(enrollment=self.bina_e, status=bina)
        if submit:
            register.submit(actor=self.admin)
        return register

    def messages(self, kind=ABSENCE):
        return list(Notification.objects.filter(type=kind).order_by("pk"))

    def attendance_link(self, grant):
        return BASE + reverse("portal:attendance", args=[grant.public_id])


class AbsenceAlertTests(AlertFixture, TestCase):
    def test_absent_student_gets_one_prepared_alert_per_portal_guardian(self):
        self.register()
        [alert] = self.messages()
        self.assertEqual((alert.guardian, alert.student, alert.status),
                         (self.meena, self.asha, PREPARED))
        self.assertEqual(alert.parameters, {
            "first_name": "Asha", "date": "12 Oct 2026",
            "portal_url": self.attendance_link(self.asha_grant),
        })
        self.assertEqual(alert.idempotency_key,
                         f"ABSENCE:{self.meena.pk}:{self.asha.pk}:2026-10-12")

    def test_text_is_exactly_the_approved_wording_without_the_note(self):
        self.register(note="Fever, called in")
        text = notifications.render(self.messages()[0])
        self.assertEqual(text, "Dear parent, Asha was marked absent at school on 12 Oct 2026. "
                               "Attendance details: " + self.attendance_link(self.asha_grant))
        self.assertNotIn("Fever", text)

    def test_present_students_get_nothing(self):
        self.register(asha=AttendanceStatus.PRESENT)
        self.assertEqual(self.messages(), [])

    def test_draft_register_prepares_nothing(self):
        self.register(submit=False)
        self.assertEqual(self.messages(), [])

    def test_guardian_without_consent_is_recorded_as_skipped(self):
        self.consent(self.meena, GuardianContactConsent.Status.OPTED_OUT)
        self.register()
        self.assertEqual([m.status for m in self.messages()],
                         [Notification.Status.SKIPPED_NO_CONSENT])

    def test_linked_guardian_without_portal_access_gets_nothing(self):
        father = Guardian.objects.create(full_name="Father Rao")
        StudentGuardian.objects.create(student=self.asha, guardian=father,
                                       relationship_type="FATHER")
        self.consent(father)
        self.register()
        self.assertEqual([m.guardian for m in self.messages()], [self.meena])

    def test_revoked_access_gets_nothing(self):
        ga.revoke_student_access(grant=self.asha_grant, actor=self.admin, reason="Court order")
        self.register()
        self.assertEqual(self.messages(), [])

    def test_inactive_login_gets_nothing(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.register()
        self.assertEqual(self.messages(), [])

    def test_pending_access_review_is_not_a_recipient(self):
        unplaced = Student.objects.create(
            applicant=Applicant.objects.create(full_name="Unplaced"), full_name="Unplaced")
        grant = ga.grant_student_access(student_guardian=self.relate(unplaced, self.meena),
                                        actor=self.admin)
        self.assertNotIn(grant, notification_producers.portal_grants(unplaced))
        self.assertEqual(notification_producers.portal_grants(self.asha), [self.asha_grant])

    def test_two_children_two_messages(self):
        bina_grant_for_meena = ga.grant_student_access(
            student_guardian=self.relate(self.bina, self.meena), actor=self.admin)
        self.register(bina=AttendanceStatus.ABSENT)
        mine = {m.student: m.parameters["portal_url"]
                for m in self.messages() if m.guardian == self.meena}
        self.assertEqual(mine, {
            self.asha: self.attendance_link(self.asha_grant),
            self.bina: self.attendance_link(bina_grant_for_meena),
        })

    def test_earlier_date_prepares_nothing(self):
        self.register(date(2026, 10, 9))
        self.assertEqual(self.messages(), [])

    def test_portal_only_prepares_nothing(self):
        School.objects.filter(pk=self.school.pk).update(notification_channel="PORTAL_ONLY")
        self.register()
        self.assertEqual(self.messages(), [])

    def test_missing_portal_address_is_logged_and_submit_succeeds(self):
        with override_settings(PORTAL_BASE_URL=""), \
                self.assertLogs("core.notification_producers", "WARNING") as logs:
            register = self.register()
        register.refresh_from_db()
        self.assertEqual(register.status, AttendanceRegister.Status.SUBMITTED)
        self.assertEqual(self.messages(), [])
        self.assertNotIn("Asha", "\n".join(logs.output))

    def test_missing_template_is_logged_and_submit_succeeds(self):
        with mock.patch.object(notification_producers, "ABSENCE_TEMPLATE", "no-such-text"), \
                self.assertLogs("core.notification_producers", "WARNING"):
            register = self.register()
        register.refresh_from_db()
        self.assertEqual(register.status, AttendanceRegister.Status.SUBMITTED)
        self.assertEqual(self.messages(), [])

    def test_running_the_producer_twice_creates_nothing_new(self):
        register = self.register()
        notification_producers.absence_alerts_for_register(register)
        self.assertEqual(len(self.messages()), 1)

    def test_first_name_is_first_word(self):
        for full_name, expected in (("Asha Rao", "Asha"), ("  Ravi   Kumar ", "Ravi"),
                                    ("Lakshmi", "Lakshmi"), ("", "")):
            with self.subTest(full_name=full_name):
                self.assertEqual(
                    notification_producers.first_name(Student(full_name=full_name)), expected)


class CorrectionTests(AlertFixture, TestCase):
    def entry(self, register):
        return register.entries.get(academic_enrollment=self.asha_e)

    def correct(self, register, status):
        self.entry(register).record_status_change(status, actor=self.admin,
                                                  reason="Register was wrong")

    def test_correction_to_present_dismisses_waiting_alert(self):
        register = self.register()
        self.correct(register, AttendanceStatus.PRESENT)
        [alert] = self.messages()
        self.assertEqual(alert.status, Notification.Status.DISMISSED)
        self.assertEqual(alert.dismissed_by, self.admin)
        self.assertEqual(alert.dismiss_reason, "Attendance corrected to Present")

    def test_sent_alert_is_not_retracted(self):
        register = self.register()
        notifications.mark_sent(self.messages()[0], user=self.admin)
        self.correct(register, AttendanceStatus.PRESENT)
        self.assertEqual([m.status for m in self.messages()], [Notification.Status.SENT])

    def test_dismissal_works_in_portal_only_mode(self):
        register = self.register()
        School.objects.filter(pk=self.school.pk).update(notification_channel="PORTAL_ONLY")
        self.correct(register, AttendanceStatus.PRESENT)
        self.assertEqual([m.status for m in self.messages()], [Notification.Status.DISMISSED])

    def test_correction_to_absent_same_day_prepares_alert(self):
        register = self.register(asha=AttendanceStatus.PRESENT)
        self.correct(register, AttendanceStatus.ABSENT)
        self.assertEqual([(m.student, m.status) for m in self.messages()],
                         [(self.asha, PREPARED)])

    def test_correction_to_absent_on_a_later_day_prepares_nothing(self):
        register = self.register(asha=AttendanceStatus.PRESENT)
        self.today = date(2026, 10, 13)
        self.correct(register, AttendanceStatus.ABSENT)
        self.assertEqual(self.messages(), [])

    def test_back_and_forth_does_not_reprepare_a_dismissed_alert(self):
        register = self.register()
        self.correct(register, AttendanceStatus.PRESENT)
        self.correct(register, AttendanceStatus.ABSENT)
        self.assertEqual([m.status for m in self.messages()], [Notification.Status.DISMISSED])

    def test_correcting_another_student_leaves_this_alert_alone(self):
        register = self.register(bina=AttendanceStatus.ABSENT)
        register.entries.get(academic_enrollment=self.bina_e).record_status_change(
            AttendanceStatus.PRESENT, actor=self.admin, reason="Register was wrong")
        statuses = {m.student: m.status for m in self.messages()}
        self.assertEqual(statuses[self.asha], PREPARED)
        self.assertEqual(statuses[self.bina], Notification.Status.DISMISSED)
