"""UI-D1-3C (T2): Guardian access reviews adopt the shared header, panels and labelled table region.

Behaviour parity is the point: the queue, the per-row POST+CSRF decision form, permissions
and the Recent decisions history are unchanged. All names are synthetic.
"""

import re
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from core import guardian_access
from core import guardian_accounts as ga
from core.models import (
    AcademicYear,
    Applicant,
    ClassGrade,
    Guardian,
    GuardianAccessReview,
    GuardianAccount,
    GuardianStudentAccess,
    Section,
    Student,
    StudentGuardian,
)

User = get_user_model()
METHOD = GuardianAccount.VerificationMethod.IN_PERSON_DOCUMENTS
RETAIN = GuardianAccessReview.Decision.RETAINED
REVOKE = GuardianAccessReview.Decision.REVOKED
INTRO = (
    "These Students have no current enrollment (for example after their Academic Year ended). "
    "Until you decide, their guardians see no information about them in the portal. "
    "Nothing is decided automatically."
)


def normalise(html):
    return re.sub(r"\s+", " ", html)


class AccessReviewsD13CBase:
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(username="admin", password="pass-12345")
        self.admin.groups.add(Group.objects.get(name="School Administrators"))
        self.client.login(username="admin", password="pass-12345")
        self.url = reverse("core:guardian-access-reviews")

    @staticmethod
    def student(name):
        applicant = Applicant.objects.create(admission_status="ACCEPTED", full_name=name)
        return Student.objects.create(applicant=applicant, full_name=name)

    def pending(self, student_name, guardian_name):
        """An active grant for a Student with no enrollment (review pending)."""
        guardian = Guardian.objects.create(full_name=guardian_name)
        student = self.student(student_name)
        link = StudentGuardian.objects.create(student=student, guardian=guardian, relationship_type="MOTHER")
        return ga.grant_student_access(student_guardian=link, actor=self.admin)

    def get(self, client=None):
        response = (client or self.client).get(self.url)
        self.assertEqual(response.status_code, 200)
        return response, normalise(response.content.decode())

    def client_with(self, *codenames):
        user = User.objects.create_user(username="limited", password="pass-12345")
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        client = self.client_class()
        client.login(username="limited", password="pass-12345")
        return client

    @staticmethod
    def panel(content, heading_id):
        start = content.index(f'aria-labelledby="{heading_id}"')
        return content[start:content.index("</section>", start)]


class HeaderAndTableTests(AccessReviewsD13CBase, TestCase):
    def test_single_h1_and_shared_header(self):
        _, content = self.get()
        self.assertEqual(content.count("<h1"), 1)
        self.assertIn('class="erp-page-header"', content)
        self.assertRegex(content, r'<h1 class="erp-page-title">Guardian access reviews</h1>')
        self.assertNotIn('<h1 class="h3 mb-1">', content)

    def test_full_instructional_paragraph(self):
        _, content = self.get()
        self.assertIn(INTRO, content)

    def test_panel_and_labelled_focusable_scroll_region(self):
        self.pending("Asha Rao", "Meena Rao")
        _, content = self.get()
        self.assertRegex(content, r'<section class="erp-panel[^"]*" aria-labelledby="pending-reviews-heading">')
        panel = self.panel(content, "pending-reviews-heading")
        region = re.search(r'<div class="erp-table-scroll[^"]*"[^>]*>', panel)
        self.assertIsNotNone(region)
        self.assertIn('role="region"', region.group(0))
        self.assertIn('tabindex="0"', region.group(0))
        self.assertRegex(region.group(0), r'aria-label="[^"]+"')

    def test_four_columns_with_scope(self):
        _, content = self.get()
        heads = re.findall(r'<th scope="col"[^>]*>(.*?)</th>', self.panel(content, "pending-reviews-heading"))
        self.assertEqual([h.strip() for h in heads], ["Student", "Guardian", "Last placement", "Decision"])

    def test_rows_links_and_fallback_in_order(self):
        zed = self.pending("Zed Rao", "Zara Rao")
        abe = self.pending("Abe Rao", "Abha Rao")
        response, content = self.get()
        self.assertEqual([r["grant"] for r in response.context["rows"]], [abe, zed])
        for grant in (abe, zed):
            guardian = grant.student_guardian.guardian
            self.assertIn(
                f'<a class="text-break" href="{reverse("core:guardian-detail", args=[guardian.pk])}">{guardian.full_name}</a>',
                content,
            )
        self.assertLess(content.index("Abe Rao"), content.index("Zed Rao"))
        self.assertEqual(content.count("No enrollment"), 2)

    def test_placement_year_name_does_not_break(self):
        grant = self.pending("Asha Rao", "Meena Rao")
        year = AcademicYear.objects.create(
            name="2025-26", start_date=date(2025, 6, 1), end_date=date(2026, 3, 31)
        )
        grade = ClassGrade.objects.create(name="Grade 5")
        section = Section.objects.create(class_grade=grade, name="A")
        grant.student_guardian.student.enroll(
            academic_year=year, class_grade=grade, section=section, start_date=date(2025, 6, 1)
        )
        _, content = self.get()
        self.assertIn('<span class="text-nowrap">2025-26</span>', content)

    def test_empty_queue_message(self):
        _, content = self.get()
        self.assertIn("No pending access reviews.", content)
        self.assertRegex(content, r'<td colspan="4">No pending access reviews\.</td>')


class DecisionFormTests(AccessReviewsD13CBase, TestCase):
    def test_admin_row_form_parity(self):
        grant = self.pending("Asha Rao", "Meena Rao")
        response, content = self.get()
        action = reverse("core:guardian-access-review-decide", args=[grant.pk])
        forms = [
            (attrs, inner)
            for attrs, inner in re.findall(r"<form\b([^>]*)>(.*?)</form>", content)
            if re.search(rf'\baction="{re.escape(action)}"', attrs)
        ]
        self.assertEqual(len(forms), 1)
        attrs, body = forms[0]
        self.assertRegex(attrs, r'\bmethod="post"')
        self.assertIn('name="csrfmiddlewaretoken"', body)
        select = re.search(r'<select[^>]*name="decision"[^>]*>(.*?)</select>', body)
        self.assertIsNotNone(select)
        self.assertIn(" required", re.search(r"<select[^>]*>", body).group(0))
        self.assertIn('<option value="">Choose', select.group(1))
        values = re.findall(r'<option value="([^"]+)">([^<]+)</option>', select.group(1))
        self.assertEqual(values, [(v, l) for v, l in response.context["decisions"]])
        note = re.search(r"<input[^>]*name=\"note\"[^>]*>", body).group(0)
        self.assertIn('type="text"', note)
        self.assertIn('maxlength="200"', note)
        self.assertIn('placeholder="Note (optional)"', note)
        self.assertNotIn(" required", note)
        self.assertRegex(body, r'<button type="submit"[^>]*>Record</button>')
        self.assertEqual(content.count("<form"), content.count("</form>"))

    def test_controls_use_scoped_class_not_inline_style(self):
        self.pending("Asha Rao", "Meena Rao")
        _, content = self.get()
        select = re.search(r'<select[^>]*name="decision"[^>]*>', content).group(0)
        note = re.search(r"<input[^>]*name=\"note\"[^>]*>", content).group(0)
        self.assertRegex(select, r'class="[^"]*\berp-review-control\b')
        self.assertRegex(note, r'class="[^"]*\berp-review-control\b')
        self.assertRegex(note, r'class="[^"]*\berp-review-note\b')
        self.assertNotIn("style=", select)
        self.assertNotIn("style=", note)

    def test_long_names_wrap_and_heading_block_is_tight(self):
        self.pending("Asha Rao", "Meena Rao")
        _, content = self.get()
        self.assertRegex(content, r'<div class="[^"]*\bpb-md-0\b[^"]*\berp-panel-head\b[^"]*"><h2 class="h5" id="pending-reviews-heading">')
        self.assertIn("erp-review-table", content)
        self.assertIn('<td class="text-break">Asha Rao</td>', content)
        self.assertRegex(content, r'<td class="text-break"><a class="text-break" href="[^"]+">Meena Rao</a></td>')

    def test_controls_have_row_context_accessible_names(self):
        self.pending("Asha Rao", "Meena Rao")
        _, content = self.get()
        select = re.search(r'<select[^>]*name="decision"[^>]*>', content).group(0)
        note = re.search(r"<input[^>]*name=\"note\"[^>]*>", content).group(0)
        for control in (select, note):
            label = re.search(r'aria-label="([^"]+)"', control)
            self.assertIsNotNone(label, control)
            self.assertIn("Asha Rao", label.group(1))
            self.assertIn("Meena Rao", label.group(1))
        self.assertNotEqual(
            re.search(r'aria-label="([^"]+)"', select).group(1),
            re.search(r'aria-label="([^"]+)"', note).group(1),
        )

    def test_record_button_has_row_context_accessible_name(self):
        self.pending("Asha Rao", "Meena Rao")
        _, content = self.get()
        button = re.search(r'<button type="submit"[^>]*>Record</button>', content).group(0)
        self.assertIn('aria-label="Record decision for Asha Rao and guardian Meena Rao"', button)

    def test_without_add_permission_no_form(self):
        self.pending("Asha Rao", "Meena Rao")
        client = self.client_with("view_guardianaccessreview")
        _, content = self.get(client)
        self.assertIn("Asha Rao", content)
        self.assertNotIn("<form", self.panel(content, "pending-reviews-heading"))
        self.assertNotIn('name="decision"', content)

    def test_row_context_labels_in_decision_cell_per_row(self):
        self.pending("Asha Rao", "Meena Rao")
        self.pending("Ravi Nair", "Sunil Nair")
        _, content = self.get()
        panel = self.panel(content, "pending-reviews-heading")
        cells = re.findall(r"<td>\s*<span class=\"erp-row-context[^>]*>.*?</td>", panel)
        self.assertEqual(len(cells), 2)
        for cell, (student, guardian) in zip(sorted(cells), sorted([("Asha Rao", "Meena Rao"), ("Ravi Nair", "Sunil Nair")])):
            self.assertRegex(cell, r'<span class="erp-row-context text-break">Student: %s</span>' % student)
            self.assertRegex(cell, r'<span class="erp-row-context text-break">Guardian: %s</span>' % guardian)
            # label sits above the form, outside it
            self.assertLess(cell.index("Guardian: "), cell.index("<form"))
        self.assertNotIn("aria-label=\"Student:", content)

    def test_row_context_label_absent_without_add_permission(self):
        self.pending("Asha Rao", "Meena Rao")
        _, content = self.get(self.client_with("view_guardianaccessreview"))
        self.assertNotIn("erp-row-context", self.panel(content, "pending-reviews-heading"))

    def test_form_post_csrf_unchanged_with_label(self):
        grant = self.pending("Asha Rao", "Meena Rao")
        _, content = self.get()
        action = reverse("core:guardian-access-review-decide", args=[grant.pk])
        self.assertRegex(content, rf'<form method="post" action="{action}"[^>]*>\s*<input type="hidden" name="csrfmiddlewaretoken"')
        self.assertEqual(self.panel(content, "pending-reviews-heading").count("csrfmiddlewaretoken"), 1)

    def test_get_does_not_decide(self):
        self.pending("Asha Rao", "Meena Rao")
        self.get()
        self.get()
        self.assertEqual(GuardianAccessReview.objects.filter(decision__in=[RETAIN, REVOKE]).count(), 0)
        self.assertTrue(GuardianStudentAccess.objects.get().is_active)

    def test_post_still_records_decision(self):
        grant = self.pending("Asha Rao", "Meena Rao")
        action = reverse("core:guardian-access-review-decide", args=[grant.pk])
        response = self.client.post(action, {"decision": RETAIN, "note": "Checked"})
        self.assertRedirects(response, self.url)
        review = GuardianAccessReview.objects.get(grant=grant, decision=RETAIN)
        self.assertEqual(review.note, "Checked")
        self.assertEqual(review.decided_by, self.admin)


class RecentDecisionsTests(AccessReviewsD13CBase, TestCase):
    def test_empty_history(self):
        _, content = self.get()
        self.assertRegex(content, r'<section class="erp-panel[^"]*" aria-labelledby="recent-decisions-heading">')
        self.assertRegex(content, r'<h2 class="[^"]*" id="recent-decisions-heading">Recent decisions</h2>')
        self.assertIn("None yet.", self.panel(content, "recent-decisions-heading"))

    def test_history_contents_and_order_preserved(self):
        first = self.pending("Asha Rao", "Meena Rao")
        second = self.pending("Ravi Rao", "Lata Rao")
        guardian_access.decide_date_review(grant=first, decision=RETAIN, actor=self.admin, note="Still enrolled elsewhere")
        guardian_access.decide_date_review(grant=second, decision=REVOKE, actor=self.admin)
        response, content = self.get()
        recent = list(response.context["recent"])
        self.assertEqual(len(recent), 2)
        panel = self.panel(content, "recent-decisions-heading")
        self.assertNotIn("None yet.", panel)
        positions = []
        for review in recent:
            pair = f"{review.grant.student_guardian.student.full_name} / {review.grant.student_guardian.guardian.full_name}"
            self.assertIn(pair, panel)
            self.assertIn(review.get_trigger_display(), panel)
            self.assertIn(f"<strong>{review.get_decision_display()}</strong>", panel)
            self.assertIn(f"by {review.decided_by}", panel)
            positions.append(panel.index(pair))
        self.assertEqual(positions, sorted(positions))
        self.assertIn("(Still enrolled elsewhere)", panel)
        self.assertEqual(panel.count("<li>"), 2)
        self.assertEqual(panel.count("(Still enrolled elsewhere)"), 1)
        self.assertEqual(panel.count("<strong>"), 2)
