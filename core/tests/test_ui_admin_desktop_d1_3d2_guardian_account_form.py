"""UI-D1-3D2: the Guardian portal account create/link form adopts the shared form layout.

Views, forms, services, URLs and permissions are unchanged. All data is synthetic.
No credential-slip password is ever stored or printed by these tests.
"""

import re

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from accounts.models import SecurityEvent
from core import guardian_accounts as ga
from core.models import Guardian, GuardianAccount, GuardianStudentAccess

User = get_user_model()
METHOD = GuardianAccount.VerificationMethod.IN_PERSON_DOCUMENTS
XSS_NAME = '<script>alert("x")</script> Meena'

COMMON_WARNING = (
    "<strong>Identity verification required.</strong> Confirm that you have already verified "
    "this person's identity as the Guardian shown above. Select the method actually used and "
    "record a brief note. Do not enter document numbers. The system records your verification; "
    "it does not verify identity automatically."
)
CREATE_INSTRUCTION = (
    "Creating this account generates a temporary password shown only once on the next page "
    "for offline delivery. The Guardian must change it at first sign-in. Creating an account "
    "does not automatically grant access to any Student."
)
LINK_INSTRUCTION = (
    "Enter the existing login's username. Matching is case-insensitive after normalization; "
    "it does not search by name, phone or email. The existing password will not change. "
    "Linking this login does not automatically grant access to any Student."
)
METHOD_LABELS = [
    "In person, with identity documents",
    "Against existing school records",
    "Other (described in the note)",
]
FIELD_ORDER = ["username", "identity_verification_method", "identity_verification_note"]
NOT_FOUND = "No active login has exactly that username."


class GuardianAccountFormD13D2Tests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", password="pass-12345")
        self.admin.groups.add(Group.objects.get(name="School Administrators"))
        self.client.login(username="admin", password="pass-12345")
        self.guardian = Guardian.objects.create(full_name=XSS_NAME, phone="555-0100")
        self.create_url = reverse("core:guardian-account-create", args=[self.guardian.pk])
        self.link_url = reverse("core:guardian-account-link", args=[self.guardian.pk])
        self.detail_url = reverse("core:guardian-detail", args=[self.guardian.pk])

    # helpers
    def data(self, username="new.parent", method=METHOD, note="Seen at the office"):
        return {
            "username": username,
            "identity_verification_method": method,
            "identity_verification_note": note,
        }

    def form_html(self, content):
        match = re.search(r'<form method="post" class="erp-form">.*?</form>', content, re.S)
        self.assertIsNotNone(match, "erp-form not found")
        return match.group(0)

    def get(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def counts(self):
        return (GuardianAccount.objects.count(), SecurityEvent.objects.count(),
                User.objects.count(), GuardianStudentAccess.objects.count())

    def assert_page(self, content, mode):
        title = "Create portal account" if mode == "create" else "Link an existing login"
        submit = "Create account" if mode == "create" else "Link login"
        instruction = CREATE_INSTRUCTION if mode == "create" else LINK_INSTRUCTION
        other = LINK_INSTRUCTION if mode == "create" else CREATE_INSTRUCTION
        self.assertIn('class="erp-guardian-form-page"', content)
        self.assertEqual(content.count("<h1"), 1)
        self.assertIn(f'<h1 class="erp-page-title">{title}</h1>', content)
        self.assertIn('<p class="erp-page-eyebrow">People</p>', content)
        # Guardian name is escaped, never raw.
        self.assertNotIn("<script>alert", content)
        self.assertIn("Guardian: &lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; Meena", content)
        # Frozen copy, verbatim, once, above the form, as a non-live-region warning.
        self.assertEqual(content.count(COMMON_WARNING), 1)
        self.assertEqual(content.count(instruction), 1)
        self.assertNotIn(other, content)
        self.assertIn('<div class="alert alert-warning">' + COMMON_WARNING + "</div>", content)
        form_start = content.index('<form method="post" class="erp-form">')
        self.assertLess(content.index(COMMON_WARNING), form_start)
        self.assertLess(content.index(instruction), form_start)
        form = self.form_html(content)
        self.assertIn("csrfmiddlewaretoken", form)
        self.assertIn("erp-required-legend", form)
        self.assertIn('class="erp-form-actions"', form)
        self.assertNotIn("<p>", form)
        self.assertNotIn(" action=", form)
        self.assertEqual(form.count(f">{submit}</button>"), 1)
        self.assertEqual(form.count('type="submit"'), 1)
        self.assertEqual(form.count(">Cancel</a>"), 1)
        self.assertIn(f'<a class="btn btn-link" href="{self.detail_url}">Cancel</a>', form)
        self.assertNotIn('type="password"', form)
        names = [n for n in re.findall(r'<(?:input|select|textarea)[^>]*\bname="([^"]+)"', form)
                 if n != "csrfmiddlewaretoken"]
        self.assertEqual(names, FIELD_ORDER)
        options = re.findall(r"<option[^>]*>([^<]+)</option>", form)
        self.assertEqual([o for o in options if o != "---------"], METHOD_LABELS)
        self.assertRegex(
            form, r'<input type="text" name="identity_verification_note"[^>]*maxlength="200"'
        )
        self.assertNotIn("<textarea", form)
        return form

    # GET
    def test_create_get(self):
        form = self.assert_page(self.get(self.create_url), "create")
        self.assertRegex(form, r'name="username"[^>]*maxlength="30"')
        self.assertNotIn("Existing login username", form)

    def test_link_get(self):
        form = self.assert_page(self.get(self.link_url), "link")
        self.assertRegex(form, r'name="username"[^>]*maxlength="150"')
        self.assertIn("Existing login username", form)

    def test_note_help_text_forbids_document_numbers_in_both_modes(self):
        for url, mode in ((self.create_url, "create"), (self.link_url, "link")):
            with self.subTest(mode=mode):
                form = self.form_html(self.get(url))
                self.assertEqual(form.count("No document numbers."), 1)
                note_block = form[form.index('name="identity_verification_note"'):]
                self.assertIn("No document numbers.", note_block)

    # invalid POST
    def test_missing_fields_show_errors_once_in_both_modes(self):
        before = self.counts()
        for url, mode in ((self.create_url, "create"), (self.link_url, "link")):
            with self.subTest(mode=mode):
                content = self.client.post(
                    url, {"username": "", "identity_verification_method": "",
                          "identity_verification_note": ""}
                ).content.decode()
                self.assert_page(content, mode)
                self.assertEqual(content.count("This field is required."), 3)
                self.assertEqual(content.count('class="erp-field-errors"'), 3)
        self.assertEqual(self.counts(), before)

    def test_create_bad_username_keeps_values_and_warning(self):
        before = self.counts()
        content = self.client.post(
            self.create_url, self.data("a b", note="Kept note")
        ).content.decode()
        self.assert_page(content, "create")
        self.assertEqual(content.count('class="erp-form-errors" role="alert"'), 1)
        self.assertEqual(content.count("errorlist nonfield"), 1)
        self.assertIn('value="a b"', content)
        self.assertIn('value="Kept note"', content)
        self.assertIn(f'<option value="{METHOD}" selected>', content)
        self.assertEqual(self.counts(), before)

    def test_create_unavailable_username_error_once(self):
        User.objects.create_user(username="taken.name", password="pass-12345")
        before = self.counts()
        content = self.client.post(
            self.create_url, self.data("Taken.Name", note="Kept note")
        ).content.decode()
        self.assert_page(content, "create")
        self.assertEqual(content.count('class="erp-form-errors" role="alert"'), 1)
        self.assertEqual(content.count("errorlist nonfield"), 1)
        self.assertIn('value="Taken.Name"', content)
        self.assertIn('value="Kept note"', content)
        self.assertEqual(self.counts(), before)

    def test_link_nonexistent_login(self):
        before = self.counts()
        content = self.client.post(
            self.link_url, self.data("nobody.here", note="Kept note")
        ).content.decode()
        self.assert_page(content, "link")
        self.assertEqual(content.count(NOT_FOUND), 1)
        self.assertEqual(content.count('class="erp-form-errors" role="alert"'), 1)
        self.assertIn('value="nobody.here"', content)
        self.assertIn('value="Kept note"', content)
        self.assertEqual(self.counts(), before)

    def test_link_inactive_login(self):
        User.objects.create_user(username="gone.user", password="pass-12345", is_active=False)
        before = self.counts()
        content = self.client.post(self.link_url, self.data("gone.user")).content.decode()
        self.assert_page(content, "link")
        self.assertEqual(content.count(NOT_FOUND), 1)
        self.assertEqual(self.counts(), before)

    def test_link_login_already_linked_to_another_guardian(self):
        other = Guardian.objects.create(full_name="Other Parent")
        ga.create_guardian_account(
            guardian=other, username="other.parent", method=METHOD, note="n", actor=self.admin
        )
        before = self.counts()
        message = "That login is already linked to another guardian."
        content = self.client.post(self.link_url, self.data("other.parent")).content.decode()
        self.assert_page(content, "link")
        self.assertEqual(content.count(message), 1)
        self.assertEqual(self.counts(), before)

    def test_guardian_already_has_active_account(self):
        ga.create_guardian_account(
            guardian=self.guardian, username="meena.one", method=METHOD, note="n",
            actor=self.admin,
        )
        User.objects.create_user(username="spare.login", password="pass-12345")
        before = self.counts()
        message = "This guardian already has an active portal account."
        for url, username, mode in (
            (self.create_url, "meena.two", "create"),
            (self.link_url, "spare.login", "link"),
        ):
            with self.subTest(mode=mode):
                content = self.client.post(url, self.data(username)).content.decode()
                self.assert_page(content, mode)
                self.assertEqual(content.count(message), 1)
        self.assertEqual(self.counts(), before)

    # valid POST regression
    def test_valid_create_returns_slip_with_no_store(self):
        response = self.client.post(self.create_url, self.data("Fresh.Parent"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        account = GuardianAccount.objects.get()
        self.assertEqual(account.user.username, "fresh.parent")
        self.assertTrue(account.user.must_change_password)
        self.assertEqual(account.identity_verified_by, self.admin)
        password = response.context["password"]
        self.assertTrue(account.user.check_password(password))
        self.assertFalse(GuardianStudentAccess.objects.exists())
        # The temporary password exists only in that one response.
        self.assertNotContains(self.client.get(self.detail_url), password)
        self.assertNotContains(self.client.get(self.create_url), password)
        self.assertEqual(
            SecurityEvent.objects.filter(event_type=SecurityEvent.EventType.ACCOUNT_CREATED).count(),
            1,
        )

    def test_valid_link_redirects_and_keeps_password(self):
        user = User.objects.create_user(username="teacher.parent", password="pass-12345")
        before_hash = user.password
        response = self.client.post(self.link_url, self.data("Teacher.Parent"))
        self.assertRedirects(response, self.detail_url, fetch_redirect_response=False)
        self.assertEqual(GuardianAccount.objects.get().user, user)
        user.refresh_from_db()
        self.assertEqual(user.password, before_hash)
        self.assertFalse(GuardianStudentAccess.objects.exists())
        self.assertEqual(
            SecurityEvent.objects.filter(event_type=SecurityEvent.EventType.ACCOUNT_LINKED).count(),
            1,
        )

    # authorization
    def test_denied_roles_get_and_post_without_writes(self):
        teacher = User.objects.create_user(username="teach", password="pass-12345")
        teacher.groups.add(Group.objects.get(name="Teachers"))
        viewer = User.objects.create_user(username="viewer", password="pass-12345")
        viewer.user_permissions.add(Permission.objects.get(codename="view_guardian"))
        parent = User.objects.create_user(username="parent.user", password="pass-12345")
        other = Guardian.objects.create(full_name="Portal Parent")
        GuardianAccount.objects.create(
            user=parent, guardian=other, identity_verified_by=self.admin,
            identity_verification_method=METHOD, identity_verification_note="n",
            created_by=self.admin,
        )
        User.objects.create_user(username="target.login", password="pass-12345")
        before = self.counts()
        for name in ("teach", "viewer", "parent.user"):
            client = self.client_class()
            self.assertTrue(client.login(username=name, password="pass-12345"))
            for url, username in (
                (self.create_url, "denied.new"),
                (self.link_url, "target.login"),
            ):
                with self.subTest(user=name, url=url):
                    self.assertEqual(client.get(url).status_code, 403)
                    self.assertEqual(client.post(url, self.data(username)).status_code, 403)
        anonymous = self.client_class()
        for url in (self.create_url, self.link_url):
            with self.subTest(user="anonymous", url=url):
                response = anonymous.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn("login", response["Location"])
                self.assertEqual(anonymous.post(url, self.data("anon.new")).status_code, 302)
        self.assertEqual(self.counts(), before)
