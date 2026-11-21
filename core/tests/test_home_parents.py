import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from core import announcements, home_parents, notification_producers
from core.models import (
    AcademicEnrollment,
    Announcement,
    ClassGrade,
    Guardian,
    GuardianAccount,
    GuardianStudentAccess,
    Section,
    StudentGuardian,
)
from core.tests.test_admin_overview_analytics import TODAY, MarksFixture

User = get_user_model()


def local(*args):
    """A wall-clock time in settings.TIME_ZONE."""
    return timezone.make_aware(datetime.datetime(*args))


def set_last_login(user, when):
    User.objects.filter(pk=user.pk).update(last_login=when)


class HomeParentsDataTests(MarksFixture, TestCase):
    def portal_parent(self, enrollment, *, active=True, name=None):
        """A guardian linked to the enrollment's student, with a login and a grant. Returns the user."""
        n = Guardian.objects.count() + 1
        guardian = Guardian.objects.create(full_name=name or f"Parent {n}")
        link = StudentGuardian.objects.create(
            student=enrollment.student, guardian=guardian, relationship_type="FATHER"
        )
        user = User.objects.create_user(username=f"parent{n}", is_active=active)
        GuardianAccount.objects.create(
            user=user, guardian=guardian, identity_verified_by=self.admin_user,
            identity_verification_method="OTHER", identity_verification_note="x",
            created_by=self.admin_user,
        )
        self.last_grant = GuardianStudentAccess.objects.create(
            student_guardian=link, granted_by=self.admin_user
        )
        return user

    def end_placement(self, enrollment):
        AcademicEnrollment.objects.filter(pk=enrollment.pk).update(
            status="COMPLETED", end_date=datetime.date(2026, 7, 1)
        )

    def grade_two(self, count=2):
        grade = ClassGrade.objects.create(name="Grade 2")
        section = Section.objects.create(class_grade=grade, name="A")
        students = [self.enroll_student(f"G2 Student {i}", grade, section) for i in range(count)]
        return grade, section, students

    def test_engagement_counts_students_with_a_portal_parent(self):
        self.portal_parent(self.s1)
        e = home_parents.engagement(TODAY)
        self.assertEqual((e["students"], e["students_on_portal"], e["students_pct"]), (2, 1, 50))

    def test_pending_grant_does_not_count(self):
        self.portal_parent(self.s1)
        self.end_placement(self.s1)
        self.assertEqual(home_parents.portal_student_ids([self.s1.student_id], TODAY), set())

    def test_inactive_login_counts_nowhere(self):
        self.portal_parent(self.s1, active=False)
        e = home_parents.engagement(TODAY)
        self.assertEqual((e["students_on_portal"], e["parents"]), (0, 0))

    def test_parents_active_this_month(self):
        a = self.portal_parent(self.s1)
        b = self.portal_parent(self.s2)
        set_last_login(a, local(2026, 7, 3, 9, 0))
        set_last_login(b, local(2026, 6, 20, 9, 0))
        e = home_parents.engagement(TODAY)
        self.assertEqual((e["parents"], e["parents_active"], e["parents_pct"]), (2, 1, 50))

    def test_logged_in_this_month_uses_local_midnight(self):
        a = self.portal_parent(self.s1)
        set_last_login(a, local(2026, 6, 30, 23, 59))
        self.assertEqual(home_parents.engagement(TODAY)["parents_active"], 0)
        set_last_login(a, local(2026, 7, 1, 0, 0))
        self.assertEqual(home_parents.engagement(TODAY)["parents_active"], 1)

    def test_empty_school_percentages_are_none(self):
        e = home_parents.engagement(datetime.date(2030, 1, 1))
        self.assertEqual((e["students_pct"], e["parents_pct"]), (None, None))

    def test_missing_accounts_rows_and_order(self):
        self.grade_two()
        self.portal_parent(self.s1)
        rows = home_parents.missing_accounts(TODAY, invite_links=True)
        self.assertEqual(
            [(r["class_name"], r["section_name"], r["missing"], r["students"]) for r in rows],
            [("Grade 2", "A", 2, 2), ("Grade 1", "A", 1, 2)],
        )
        self.assertEqual(
            rows[1]["url"],
            reverse("core:student-list") + f"?section={self.section.pk}&chip=no_portal",
        )

    def test_missing_accounts_skip_full_sections_and_hide_links(self):
        self.portal_parent(self.s1)
        self.assertEqual(home_parents.missing_accounts(TODAY, invite_links=True)[0]["missing"], 1)
        self.assertIsNone(home_parents.missing_accounts(TODAY, invite_links=False)[0]["url"])
        self.portal_parent(self.s2)
        self.assertEqual(home_parents.missing_accounts(TODAY, invite_links=False), [])

    def test_missing_accounts_tie_break_by_class_order_then_section(self):
        grade, _, _ = self.grade_two(count=1)
        section_b = Section.objects.create(class_grade=self.class_grade, name="B")
        self.enroll_student("B Student", self.class_grade, section_b)
        # Grade 1 A has 2 missing; Grade 2 A and Grade 1 B have 1 each.
        rows = home_parents.missing_accounts(TODAY, invite_links=False)
        self.assertEqual(rows[0]["missing"], 2)
        tied = [(r["class_name"], r["section_name"]) for r in rows[1:]]
        expected = sorted(
            [(self.class_grade, "B"), (grade, "A")],
            key=lambda cs: (cs[0].display_order, cs[0].name, cs[1]),
        )
        self.assertEqual(tied, [(cg.name, sec) for cg, sec in expected])

    def test_student_counted_once_under_latest_placement(self):
        _, section_two, _ = self.grade_two(count=0)
        # s2 moves to Grade 2 A from 1 July; the old placement ends today, so both are effective.
        AcademicEnrollment.objects.filter(pk=self.s2.pk).update(status="COMPLETED", end_date=TODAY)
        AcademicEnrollment.objects.create(
            student=self.s2.student, academic_year=self.year,
            class_grade=section_two.class_grade, section=section_two,
            start_date=datetime.date(2026, 7, 1),
        )
        self.assertEqual(home_parents.engagement(TODAY)["students"], 2)
        rows = {
            (r["class_name"], r["section_name"]): r["students"]
            for r in home_parents.missing_accounts(TODAY, invite_links=False)
        }
        self.assertEqual(rows, {("Grade 1", "A"): 1, ("Grade 2", "A"): 1})

    def test_access_reviews_rows_and_links(self):
        self.portal_parent(self.s1, name="Rajesh Rao")
        grant = self.last_grant
        self.end_placement(self.s1)
        r = home_parents.access_reviews(TODAY, with_names=True, decide_links=True)
        self.assertEqual(r["count"], 1)
        self.assertEqual(r["rows"][0]["guardian_name"], "Rajesh Rao")
        self.assertEqual(r["rows"][0]["student_name"], self.s1.student.full_name)
        self.assertEqual(
            r["rows"][0]["url"], reverse("core:guardian-access-review-decide", args=[grant.pk])
        )
        self.assertEqual(r["url"], reverse("core:guardian-access-reviews"))
        r = home_parents.access_reviews(TODAY, with_names=True, decide_links=False)
        self.assertEqual(r["rows"][0]["url"], reverse("core:guardian-access-reviews"))
        r = home_parents.access_reviews(TODAY, with_names=False, decide_links=True)
        self.assertIsNone(r["rows"])
        self.assertEqual(r["count"], 1)

    def test_sent_notices_newest_first_with_withdrawn_flag(self):
        def send(title, day):
            return announcements.publish(
                title=title, body="Body", audience=Announcement.Audience.ALL,
                actor=self.admin_user, published_at=local(2026, 7, day, 10, 0),
            )

        send("First", 1)
        second = send("Second", 2)
        third = send("Third", 3)
        announcements.withdraw(second, actor=self.admin_user, reason="Wrong date")
        rows = home_parents.sent_notices(limit=2)
        self.assertEqual([r["title"] for r in rows], ["Third", "Second"])
        self.assertEqual([r["withdrawn"] for r in rows], [False, True])
        self.assertEqual(rows[0]["audience"], "Whole school")
        self.assertEqual(rows[0]["published_on"], datetime.date(2026, 7, 3))
        self.assertEqual(rows[0]["url"], reverse("core:announcement-detail", args=[third.pk]))
        self.assertEqual(len(home_parents.sent_notices()), 3)

    def test_portal_grants_for_students_honours_on_date(self):
        self.portal_parent(self.s1)
        self.end_placement(self.s1)
        ids = [self.s1.student_id]
        self.assertEqual(notification_producers.portal_grants_for_students(ids, on_date=TODAY), [])
        usable = notification_producers.portal_grants_for_students(
            ids, on_date=datetime.date(2026, 6, 15)
        )
        self.assertEqual([g.pk for g in usable], [self.last_grant.pk])

    def test_query_count_does_not_grow_with_sections(self):
        self.portal_parent(self.s1)

        def count():
            with CaptureQueriesContext(connection) as ctx:
                home_parents.missing_accounts(TODAY, invite_links=True)
                home_parents.engagement(TODAY)
            return len(ctx)

        before = count()
        for i in range(3):
            grade = ClassGrade.objects.create(name=f"Extra {i}")
            section = Section.objects.create(class_grade=grade, name="A")
            self.enroll_student(f"Extra Student {i}", grade, section)
        self.assertEqual(count(), before)

    def test_context_without_show_missing_has_no_missing_rows(self):
        self.portal_parent(self.s1)
        kwargs = dict(
            notice_form=False, show_sent=False, invite_links=False, include_reviews=False,
            review_names=False, decide_links=False, guardians_link=False,
        )
        self.assertIsNone(home_parents.parents_tab_context(TODAY, show_missing=False, **kwargs)["missing"])
        self.assertTrue(home_parents.parents_tab_context(TODAY, **kwargs)["missing"])

    def test_context_computes_portal_state_once(self):
        self.portal_parent(self.s1)
        kwargs = dict(
            notice_form=False, show_sent=False, invite_links=True, include_reviews=False,
            review_names=False, decide_links=False, guardians_link=False,
        )
        with mock.patch.object(home_parents, "_placements", wraps=home_parents._placements) as spy:
            home_parents.parents_tab_context(TODAY, **kwargs)
        self.assertEqual(spy.call_count, 1)
