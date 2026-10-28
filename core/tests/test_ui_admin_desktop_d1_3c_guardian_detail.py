"""UI-D1-3C (T1): Guardian detail adopts the shared header, panels and labelled table regions.

Behaviour parity is the point: permissions, links, POST+CSRF forms and conditional
sections are unchanged. All names are synthetic.
"""

import re

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import SecurityEvent
from core import guardian_accounts as ga
from core.models import (
    Applicant,
    ApplicantGuardian,
    Guardian,
    GuardianAccessReview,
    GuardianAccount,
    GuardianContactConsent,
    GuardianStudentAccess,
    Student,
    StudentGuardian,
)

User = get_user_model()
METHOD = GuardianAccount.VerificationMethod.IN_PERSON_DOCUMENTS
LONG_NAME = "Venkataraghavan Subramaniam Ramachandran-Krishnamurthy Iyengar"


def normalise(html):
    return re.sub(r"\s+", " ", html)


class GuardianDetailD13CBase:
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(username="admin", password="pass-12345")
        self.admin.groups.add(Group.objects.get(name="School Administrators"))
        self.client.login(username="admin", password="pass-12345")
        self.guardian = Guardian.objects.create(full_name="Meena Rao", phone="98450-12345", email="meena@example.test")
        self.asha = self.student("Asha Rao")
        self.ravi = self.student("Ravi Rao")
        self.asha_link = StudentGuardian.objects.create(
            student=self.asha, guardian=self.guardian, relationship_type="MOTHER"
        )
        self.ravi_link = StudentGuardian.objects.create(
            student=self.ravi, guardian=self.guardian, relationship_type="MOTHER"
        )

    @staticmethod
    def student(name):
        applicant = Applicant.objects.create(admission_status="ACCEPTED", full_name=name)
        return Student.objects.create(applicant=applicant, full_name=name)

    def create_account(self, username="meena.rao"):
        account, _password = ga.create_guardian_account(
            guardian=self.guardian, username=username, method=METHOD,
            note="Aadhaar card seen by office", actor=self.admin,
        )
        return account

    def grant(self, link):
        return ga.grant_student_access(student_guardian=link, actor=self.admin)

    def url(self, name, *args):
        return reverse(f"core:{name}", args=args)

    def get(self, client=None, guardian=None):
        guardian = guardian or self.guardian
        response = (client or self.client).get(self.url("guardian-detail", guardian.pk))
        self.assertEqual(response.status_code, 200)
        return normalise(response.content.decode())

    def get_response(self, client=None, guardian=None):
        guardian = guardian or self.guardian
        response = (client or self.client).get(self.url("guardian-detail", guardian.pk))
        self.assertEqual(response.status_code, 200)
        return response

    def main(self, content):
        return content[content.index("<main"):]

    def section(self, content, section_id):
        start = content.index(f'id="{section_id}"')
        end = content.index("</section>", start)
        return content[start:end]

    def client_with(self, *codenames):
        user = User.objects.create_user(username="limited", password="pass-12345")
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        client = self.client_class()
        client.login(username="limited", password="pass-12345")
        return client


class HeaderAndStructureTests(GuardianDetailD13CBase, TestCase):
    def test_single_h1_and_shared_header(self):
        content = self.get()
        self.assertEqual(content.count("<h1"), 1)
        self.assertIn('class="erp-page-header"', content)
        self.assertIn('<p class="erp-page-eyebrow">People</p>', content)
        self.assertRegex(content, r'<h1 class="erp-page-title">Meena Rao</h1>')
        self.assertNotIn('<h1 class="h3 mb-3">', content)

    def test_long_name_not_truncated(self):
        guardian = Guardian.objects.create(full_name=LONG_NAME)
        self.assertIn(LONG_NAME, self.get(guardian=guardian))

    def test_long_name_and_email_can_wrap(self):
        guardian = Guardian.objects.create(
            full_name=LONG_NAME, email="venkataraghavan.subramaniam.ramachandran@example.test"
        )
        content = self.get(guardian=guardian)
        # Title is wrapped at template level (the shared header partial is untouched).
        self.assertRegex(content, r'<div class="text-break"> ?<header class="erp-page-header">')
        self.assertRegex(content, r'<dd class="col-sm-9 text-break">venkataraghavan\.subramaniam')

    def test_contact_details_definition_list_and_defaults(self):
        content = self.get()
        self.assertIn('<dt class="col-sm-3">Phone</dt>', content)
        self.assertIn('<dd class="col-sm-9 text-break">98450-12345</dd>', content)
        self.assertIn('<dd class="col-sm-9 text-break">meena@example.test</dd>', content)
        bare = Guardian.objects.create(full_name="Bare Guardian")
        page = self.get(guardian=bare)
        self.assertEqual(page.count('<dd class="col-sm-9 text-break">-</dd>'), 2)

    def test_contact_details_in_labelled_panel(self):
        content = self.get()
        self.assertRegex(content, r'<section class="erp-panel[^"]*" aria-labelledby="guardian-contact-heading">')
        self.assertRegex(content, r'<h2 class="[^"]*" id="guardian-contact-heading">Contact details</h2>')

    def test_sections_keep_ids_and_labels_and_are_panels(self):
        self.create_account()
        self.grant(self.asha_link)
        content = self.get()
        for section_id, heading in (
            ("applicants", "Associated Applicants"),
            ("portal-account", "Guardian Portal account"),
            ("student-access", "Student access"),
            ("history", "Account and access history"),
        ):
            tag = re.search(rf'<section id="{section_id}"[^>]*>', content)
            self.assertIsNotNone(tag, section_id)
            self.assertIn(f'aria-labelledby="{section_id}-heading"', tag.group(0))
            self.assertIn("erp-panel", tag.group(0))
            self.assertRegex(content, rf'<h2 class="[^"]*" id="{section_id}-heading">{heading}</h2>')

    def test_section_nav_links_preserved(self):
        content = self.get()
        for section_id in ("applicants", "portal-account", "student-access", "history"):
            self.assertIn(f'<a href="#{section_id}">', content)

    def test_back_link_preserved(self):
        self.assertIn(f'href="{self.url("guardian-list")}">Back to Guardians</a>', self.get())

    def test_scroll_regions_labelled_and_focusable(self):
        self.grant(self.asha_link)
        content = self.get()
        self.assertIn('class="erp-table-scroll', content)
        for label in ("Associated Applicants", "Student access"):
            self.assertRegex(
                content,
                rf'<div class="erp-table-scroll[^"]*" role="region" aria-label="{label}" tabindex="0">',
            )

    def test_panel_heading_block_and_name_cells_use_scoped_classes(self):
        self.grant(self.asha_link)
        content = self.get()
        for target in ("applicants", "student-access"):
            section = self.section(content, target)
            self.assertRegex(section, r'<div class="[^"]*\bpb-md-0\b[^"]*\berp-panel-head\b')
            self.assertIn("erp-name-table", section)
        self.assertIn('<td class="text-break">Asha', self.section(content, "student-access"))

    def test_table_headers_have_scope_col(self):
        self.grant(self.asha_link)
        content = self.get()
        self.assertNotIn("<th>", content)
        self.assertNotIn("<th></th>", content)
        for heading in ("Applicant", "Relationship", "Student", "Portal access"):
            self.assertIn(f'<th scope="col">{heading}</th>', content)
        self.assertIn('<th scope="col"><span class="visually-hidden">Actions</span></th>', content)

    def test_relationship_explainer_text_is_visible(self):
        # explanatory sentence about relationships not granting access is kept as visible text
        self.assertIn(
            "Access is granted explicitly for each relationship. The relationship type never grants access by itself.",
            self.get(),
        )


class ApplicantsSectionTests(GuardianDetailD13CBase, TestCase):
    def test_empty_state(self):
        content = self.get()
        self.assertIn("Not associated with any Applicant.", content)

    def test_links_and_relationships_in_view_order(self):
        first = Applicant.objects.create(admission_status="PENDING", full_name="Zed Applicant")
        second = Applicant.objects.create(admission_status="PENDING", full_name="Amy Applicant")
        ApplicantGuardian.objects.create(applicant=first, guardian=self.guardian, relationship_type="FATHER")
        ApplicantGuardian.objects.create(applicant=second, guardian=self.guardian, relationship_type="MOTHER")
        content = self.get()
        self.assertNotIn("Not associated with any Applicant.", content)
        self.assertIn(f'<a class="text-break" href="{self.url("applicant-detail", first.pk)}">Zed Applicant</a>', content)
        self.assertIn(f'<a class="text-break" href="{self.url("applicant-detail", second.pk)}">Amy Applicant</a>', content)
        expected = [
            link.applicant.full_name
            for link in self.guardian.applicant_links.select_related("applicant")
        ]
        positions = [content.index(name) for name in expected]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("Father", content)
        self.assertIn("Mother", content)


class PortalAccountTests(GuardianDetailD13CBase, TestCase):
    def portal(self, content=None):
        return self.section(content or self.get(), "portal-account")

    def test_no_account_shows_warning_and_create_link_actions(self):
        section = self.portal()
        self.assertIn("No active portal account. Recording a Guardian grants no access.", section)
        create = self.url("guardian-account-create", self.guardian.pk)
        link = self.url("guardian-account-link", self.guardian.pk)
        self.assertIn(f'href="{create}">Create portal account</a>', section)
        self.assertIn(f'href="{link}">Link an existing login</a>', section)
        self.assertNotIn("Reset password", section)

    def test_add_guardianaccount_alone_shows_create_and_link_actions(self):
        client = self.client_with("view_guardian", "view_guardianaccount", "add_guardianaccount")
        section = self.portal(self.get(client))
        self.assertIn(f'href="{self.url("guardian-account-create", self.guardian.pk)}">Create portal account</a>', section)
        self.assertIn(f'href="{self.url("guardian-account-link", self.guardian.pk)}">Link an existing login</a>', section)
        self.assertNotIn("Reset password", section)
        self.assertNotIn("Revoke account link", section)

    def test_no_account_actions_need_add_guardianaccount(self):
        client = self.client_with("view_guardian", "view_guardianaccount")
        section = self.portal(self.get(client))
        self.assertIn("Recording a Guardian grants no access.", section)
        self.assertNotIn("Create portal account", section)
        self.assertNotIn("Link an existing login", section)

    def test_active_account_details_and_all_actions_for_admin(self):
        account = self.create_account()
        section = self.portal()
        self.assertIn("<strong>meena.rao</strong>", section)
        self.assertIn("verified by admin (In person, with identity documents)", section)
        self.assertIn(str(timezone.localtime(account.created_at).day) + timezone.localtime(account.created_at).strftime(" %b %Y"), section)
        self.assertIn(f'href="{self.url("guardian-account-reset-password", account.pk)}">Reset password</a>', section)
        self.assertIn(f'href="{self.url("guardian-account-username", account.pk)}">Change username</a>', section)
        self.assertIn(f'href="{self.url("guardian-account-revoke", account.pk)}">Revoke account link</a>', section)
        self.assertNotIn("No active portal account", section)
        self.assertNotIn("Create portal account", section)

    def test_each_account_action_has_its_own_predicate(self):
        account = self.create_account()
        cases = {
            "reset_guardian_password": ("guardian-account-reset-password", "Reset password"),
            "change_guardian_username": ("guardian-account-username", "Change username"),
            "change_guardianaccount": ("guardian-account-revoke", "Revoke account link"),
        }
        for codename, (route, label) in cases.items():
            with self.subTest(codename=codename):
                User.objects.filter(username="limited").delete()
                client = self.client_with("view_guardian", "view_guardianaccount", codename)
                section = self.portal(self.get(client))
                self.assertIn(f'href="{self.url(route, account.pk)}">{label}</a>', section)
                for other, (other_route, other_label) in cases.items():
                    if other != codename:
                        self.assertNotIn(self.url(other_route, account.pk), section)
                        self.assertNotIn(other_label, section)

    def test_view_only_user_sees_no_account_actions(self):
        account = self.create_account()
        client = self.client_with("view_guardian", "view_guardianaccount")
        section = self.portal(self.get(client))
        self.assertIn("<strong>meena.rao</strong>", section)
        for route in ("guardian-account-reset-password", "guardian-account-username", "guardian-account-revoke"):
            self.assertNotIn(self.url(route, account.pk), section)

    def test_must_change_password_badge(self):
        self.create_account()  # new accounts must change password
        section = self.portal()
        self.assertIn("must change password", section)
        account = GuardianAccount.objects.get()
        account.user.must_change_password = False
        account.user.save(update_fields=["must_change_password"])
        self.assertNotIn("must change password", self.portal())

    def test_login_inactive_badge(self):
        account = self.create_account()
        self.assertNotIn("login inactive", self.portal())
        account.user.is_active = False
        account.user.save(update_fields=["is_active"])
        self.assertIn("login inactive", self.portal())

    def test_revoked_earlier_account_text(self):
        old = self.create_account("old.login")
        ga.revoke_account_link(account=old, actor=self.admin, reason="Requested by school")
        section = self.portal()
        self.assertIn("Earlier link: old.login", section)
        self.assertIn("by admin (Requested by school)", section)
        self.assertIn("No active portal account", section)
        self.assertIn("Create portal account", section)

    def test_section_hidden_without_view_guardianaccount(self):
        self.create_account()
        content = self.get(self.client_with("view_guardian"))
        self.assertNotIn('id="portal-account"', content)
        self.assertNotIn("Guardian Portal account", content)
        self.assertNotIn('href="#portal-account"', content)


class StudentAccessTests(GuardianDetailD13CBase, TestCase):
    def access(self, content=None):
        return self.section(content or self.get(), "student-access")

    def test_not_granted_rows_post_form_with_csrf(self):
        section = self.access()
        self.assertEqual(section.count("Not granted"), 2)
        action = self.url("guardian-access-grant", self.asha_link.pk)
        self.assertRegex(
            section,
            rf'<form method="post" action="{action}"[^>]*>\s*<input type="hidden" name="csrfmiddlewaretoken"',
        )
        self.assertEqual(section.count('method="post"'), 2)
        self.assertEqual(section.count("csrfmiddlewaretoken"), 2)
        self.assertEqual(section.count('type="submit"'), 2)
        self.assertEqual(section.count(">Grant access</button>"), 2)
        for button in re.findall(r'<button type="submit"[^>]*>Grant access</button>', section):
            self.assertRegex(button, r'class="[^"]*\btext-nowrap\b')
        self.assertNotIn("Revoke", section)

    def test_grant_button_accessible_name_includes_student(self):
        section = self.access()
        self.assertIn('aria-label="Grant access for Asha Rao"', section)
        self.assertIn('aria-label="Grant access for Ravi Rao"', section)

    def test_get_to_grant_url_does_not_mutate(self):
        response = self.client.get(self.url("guardian-access-grant", self.asha_link.pk))
        self.assertRedirects(
            response, self.url("guardian-detail", self.asha_link.guardian_id), fetch_redirect_response=False
        )
        self.assertFalse(GuardianStudentAccess.objects.exists())

    def test_active_grant_shows_revoke_link_and_no_grant_form(self):
        grant = self.grant(self.asha_link)
        section = self.access()
        self.assertIn("Granted ", section)
        self.assertIn("by admin", section)
        revoke = self.url("guardian-access-revoke", grant.pk)
        self.assertRegex(section, rf'href="{revoke}"[^>]*>Revoke</a>')
        self.assertIn('aria-label="Revoke access for Asha Rao"', section)
        self.assertRegex(section, rf'<a class="[^"]*\btext-nowrap\b[^"]*" href="{revoke}"')
        self.assertIn('<td class="text-end text-nowrap">', section)
        grant_url = self.url("guardian-access-grant", self.asha_link.pk)
        self.assertNotIn(grant_url, section)
        self.assertIn(self.url("guardian-access-grant", self.ravi_link.pk), section)

    def test_under_review_text_and_link(self):
        self.grant(self.asha_link)  # no enrolment, so the review is pending
        section = self.access()
        self.assertIn("under review &mdash; no data shown", section.replace("—", "&mdash;"))
        self.assertIn(f'href="{self.url("guardian-access-reviews")}"', section)

    def test_reviewed_grant_is_not_under_review(self):
        grant = self.grant(self.asha_link)
        GuardianAccessReview.objects.create(
            grant=grant, trigger=GuardianAccessReview.Trigger.NO_CURRENT_ENROLLMENT, enrollment=None,
            decision=GuardianAccessReview.Decision.RETAINED, decided_by=self.admin,
        )
        section = self.access()
        self.assertIn("Granted ", section)
        self.assertNotIn("under review", section)

    def test_revoked_grants_listed_with_reason(self):
        grant = self.grant(self.asha_link)
        ga.revoke_student_access(grant=grant, actor=self.admin, reason="Court order on file")
        section = self.access()
        self.assertIn("Revoked ", section)
        self.assertIn("by admin (Court order on file)", section)
        self.assertIn("Not granted", section)
        self.assertIn(self.url("guardian-access-grant", self.asha_link.pk), section)

    def test_grant_and_revoke_predicates_are_independent(self):
        grant = self.grant(self.asha_link)
        revoke = self.url("guardian-access-revoke", grant.pk)
        grant_url = self.url("guardian-access-grant", self.ravi_link.pk)
        only_change = self.access(self.get(self.client_with("view_guardian", "view_guardianstudentaccess", "change_guardianstudentaccess")))
        self.assertIn(revoke, only_change)
        self.assertNotIn(grant_url, only_change)
        self.assertNotIn("<form", only_change)
        User.objects.filter(username="limited").delete()
        only_add = self.access(self.get(self.client_with("view_guardian", "view_guardianstudentaccess", "add_guardianstudentaccess")))
        self.assertNotIn(revoke, only_add)
        self.assertIn(grant_url, only_add)
        User.objects.filter(username="limited").delete()
        view_only = self.access(self.get(self.client_with("view_guardian", "view_guardianstudentaccess")))
        self.assertNotIn(revoke, view_only)
        self.assertNotIn("<form", view_only)
        self.assertNotIn("Grant access", view_only)

    def test_row_context_label_per_row_in_action_cell(self):
        grant = self.grant(self.asha_link)
        section = self.access()
        revoke = self.url("guardian-access-revoke", grant.pk)
        rows = re.findall(r"<tr>.*?</tr>", section)
        asha = next(r for r in rows if "Asha Rao</td>" in r)
        ravi = next(r for r in rows if "Ravi Rao</td>" in r)
        label = r'<span class="erp-row-context text-break">Student: %s</span>'
        self.assertRegex(asha, label % "Asha Rao" + r"<a [^>]*" + re.escape(revoke))
        self.assertNotIn("Ravi Rao</span>", asha)
        self.assertRegex(ravi, r"<td class=\"text-end text-nowrap\">\s*" + label % "Ravi Rao" + r"\s*<form ")
        self.assertEqual(section.count("erp-row-context"), 2)
        self.assertNotIn('aria-label="Student:', section)

    def test_row_context_label_only_when_a_control_renders(self):
        self.grant(self.asha_link)
        view_only = self.access(self.get(self.client_with("view_guardian", "view_guardianstudentaccess")))
        self.assertNotIn("erp-row-context", view_only)
        User.objects.filter(username="limited").delete()
        only_change = self.access(self.get(self.client_with("view_guardian", "view_guardianstudentaccess", "change_guardianstudentaccess")))
        self.assertEqual(only_change.count("erp-row-context"), 1)  # Asha (granted) only
        User.objects.filter(username="limited").delete()
        only_add = self.access(self.get(self.client_with("view_guardian", "view_guardianstudentaccess", "add_guardianstudentaccess")))
        self.assertEqual(only_add.count("erp-row-context"), 1)  # Ravi (not granted) only
        self.assertIn("Student: Ravi Rao", only_add)
        self.assertNotIn("Student: Asha Rao", only_add)

    def test_student_rows_render_in_view_order(self):
        self.grant(self.asha_link)
        response = self.get_response()
        names = [row["link"].student.full_name for row in response.context["relationships"]]
        self.assertEqual(sorted(names), ["Asha Rao", "Ravi Rao"])
        section = self.access(normalise(response.content.decode()))
        positions = [section.index(f"<td class=\"text-break\">{name}</td>") for name in names]
        self.assertEqual(positions, sorted(positions))

    def test_relationship_labels_and_empty_state(self):
        self.assertIn("Mother", self.access())
        lonely = Guardian.objects.create(full_name="Lonely Guardian")
        section = self.access(self.get(guardian=lonely))
        self.assertIn("Not associated with any Student.", section)

    def test_section_hidden_without_view_guardianstudentaccess(self):
        content = self.get(self.client_with("view_guardian"))
        self.assertNotIn('id="student-access"', content)
        self.assertNotIn("Student access", content)
        self.assertNotIn("csrfmiddlewaretoken", self.main(content))
        self.assertNotIn(self.url("guardian-access-grant", self.asha_link.pk), content)


class HistoryAndConsentTests(GuardianDetailD13CBase, TestCase):
    def test_history_empty_state(self):
        section = self.section(self.get(), "history")
        self.assertIn("None.", section)

    def test_history_events_in_view_order_with_actor(self):
        self.create_account()
        self.grant(self.asha_link)
        section = self.section(self.get(), "history")
        self.assertNotIn("None.", section)
        self.assertIn("Guardian account created", section)
        self.assertIn("Student access granted", section)
        self.assertIn("by admin", section)
        events = SecurityEvent.objects.filter(
            guardian_id_ref=self.guardian.pk, event_class=SecurityEvent.EventClass.HISTORY
        )
        self.assertEqual(section.count("<li"), events.count())
        # Rendered order follows the view's (context) event order.
        response = self.get_response()
        labels = [event.get_event_type_display() for event in response.context["events"]]
        self.assertGreaterEqual(len(labels), 2)
        cursor = 0
        for label in labels:
            at = section.index(label, cursor)
            cursor = at + len(label)

    def test_history_hidden_without_view_securityevent(self):
        content = self.get(self.client_with("view_guardian"))
        self.assertNotIn('id="history"', content)
        self.assertNotIn("Account and access history", content)

    def test_consent_include_still_conditional(self):
        plain = self.get(self.client_with("view_guardian"))
        self.assertNotIn("WhatsApp messages", plain)
        User.objects.filter(username="limited").delete()
        content = self.get(self.client_with("view_guardian", "view_guardiancontactconsent"))
        self.assertIn("WhatsApp messages", content)
        self.assertNotIn(self.url("guardian-consent-record", self.guardian.pk), content)
        self.assertIn("WhatsApp messages", self.get())
        self.assertIn(self.url("guardian-consent-record", self.guardian.pk), self.get())
        self.assertEqual(GuardianContactConsent.objects.count(), 0)

    def test_view_only_user_page_has_no_actions_or_forms(self):
        self.create_account()
        self.grant(self.asha_link)
        content = self.main(self.get(self.client_with("view_guardian", "view_guardianaccount", "view_guardianstudentaccess")))
        self.assertNotIn("Edit contact details", content)
        self.assertNotIn("<form", content)
        self.assertNotIn("<button", content)


class EditActionTests(GuardianDetailD13CBase, TestCase):
    def test_edit_link_for_change_guardian(self):
        edit = self.url("guardian-edit", self.guardian.pk)
        self.assertIn(f'href="{edit}">Edit contact details</a>', self.get())

    def test_edit_link_hidden_for_view_only(self):
        content = self.get(self.client_with("view_guardian"))
        self.assertNotIn(self.url("guardian-edit", self.guardian.pk), content)
        self.assertNotIn("Edit contact details", content)

    def test_edit_link_for_change_only_user(self):
        content = self.get(self.client_with("view_guardian", "change_guardian"))
        self.assertIn("Edit contact details", content)
