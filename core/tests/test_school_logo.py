"""ADR 0020 Gate 1: school logo versions, validation, serving and management."""

import hashlib
from datetime import timedelta
from io import BytesIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone
from PIL import Image, ImageFile, PngImagePlugin

from accounts.models import SecurityEvent
from core import school_logo
from core.models import TEACHERS_GROUP_NAME, School, SchoolLogo

User = get_user_model()


def image_bytes(fmt="PNG", size=(40, 20), mode="RGB", color=(200, 30, 30), **save_kwargs):
    out = BytesIO()
    Image.new(mode, size, color).save(out, format=fmt, **save_kwargs)
    return out.getvalue()


def decode(data):
    image = Image.open(BytesIO(data))
    image.load()
    return image


class NormalizeTests(SimpleTestCase):
    def test_png_and_jpeg_become_png(self):
        for fmt in ("PNG", "JPEG"):
            with self.subTest(fmt=fmt):
                result = school_logo.normalize(image_bytes(fmt))
                self.assertEqual(decode(result).format, "PNG")

    def test_other_formats_are_refused(self):
        for fmt in ("GIF", "BMP", "WEBP"):
            with self.subTest(fmt=fmt):
                with self.assertRaisesMessage(ValidationError, "Only PNG and JPEG"):
                    school_logo.normalize(image_bytes(fmt))

    def test_svg_is_refused(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>'
        with self.assertRaises(ValidationError):
            school_logo.normalize(svg)

    def test_unreadable_and_truncated_files_are_refused(self):
        with self.assertRaisesMessage(ValidationError, "not a readable"):
            school_logo.normalize(b"not an image at all")
        with self.assertRaisesMessage(ValidationError, "not a readable"):
            school_logo.normalize(image_bytes("PNG", size=(300, 300))[:-40])

    def test_truncated_file_is_refused_even_when_pillow_tolerates_truncation(self):
        # WeasyPrint turns this flag on process-wide when it is imported.
        data = image_bytes("PNG", size=(300, 300))[:-40]
        ImageFile.LOAD_TRUNCATED_IMAGES = True
        self.addCleanup(setattr, ImageFile, "LOAD_TRUNCATED_IMAGES", False)
        with self.assertRaisesMessage(ValidationError, "not a readable"):
            school_logo.normalize(data)
        self.assertTrue(ImageFile.LOAD_TRUNCATED_IMAGES)  # restored for other users

    def test_over_512_kb_is_refused_not_shrunk(self):
        with self.assertRaisesMessage(ValidationError, "larger than 512 KB"):
            school_logo.normalize(b"x" * (512 * 1024 + 1))

    def test_exactly_512_kb_passes_the_size_check(self):
        # Not an image, so it fails later for being unreadable - never for size.
        with self.assertRaisesMessage(ValidationError, "not a readable"):
            school_logo.normalize(b"x" * (512 * 1024))

    def test_dimension_limit_is_refused_not_shrunk(self):
        for size in ((2001, 10), (10, 2001)):
            with self.subTest(size=size):
                with self.assertRaisesMessage(ValidationError, "limit is 2000 x 2000"):
                    school_logo.normalize(image_bytes("PNG", size=size))

    def test_2000_by_2000_is_accepted_and_stored_600_wide(self):
        image = decode(school_logo.normalize(image_bytes("PNG", size=(2000, 2000))))
        self.assertEqual(image.size, (600, 600))

    def test_wide_image_is_downscaled_keeping_proportions(self):
        image = decode(school_logo.normalize(image_bytes("PNG", size=(1200, 300))))
        self.assertEqual(image.size, (600, 150))

    def test_small_image_is_not_enlarged(self):
        image = decode(school_logo.normalize(image_bytes("PNG", size=(40, 20))))
        self.assertEqual(image.size, (40, 20))

    def test_metadata_is_stripped(self):
        exif = Image.Exif()
        exif[0x010E] = "secret camera note"
        jpeg = image_bytes("JPEG", exif=exif.tobytes())
        self.assertIn(b"secret camera note", jpeg)
        text = PngImagePlugin.PngInfo()
        text.add_text("Comment", "secret png note")
        png = image_bytes("PNG", pnginfo=text)
        self.assertIn(b"secret png note", png)
        for source in (jpeg, png):
            result = school_logo.normalize(source)
            self.assertNotIn(b"secret", result)
            info = decode(result).info
            self.assertFalse({"exif", "icc_profile", "Comment"} & set(info))

    def test_exif_orientation_is_applied_before_stripping(self):
        exif = Image.Exif()
        exif[0x0112] = 6  # rotate 90 degrees: a landscape file displays as portrait
        data = image_bytes("JPEG", size=(40, 20), exif=exif.tobytes())
        self.assertEqual(decode(school_logo.normalize(data)).size, (20, 40))

    def test_transparency_is_kept(self):
        data = image_bytes("PNG", mode="RGBA", color=(10, 20, 30, 0))
        image = decode(school_logo.normalize(data))
        self.assertEqual(image.mode, "RGBA")
        self.assertEqual(image.getpixel((0, 0))[3], 0)

    def test_palette_png_with_transparency_becomes_rgba(self):
        source = Image.new("P", (10, 10), 0)
        out = BytesIO()
        source.save(out, format="PNG", transparency=0)
        self.assertEqual(decode(school_logo.normalize(out.getvalue())).mode, "RGBA")

    def test_type_comes_from_content(self):
        with self.assertRaises(ValidationError):
            school_logo.normalize(b"GIF89a" + b"\x00" * 20)


class LogoFixture:
    def build_logo_fixture(self):
        self.school = School.objects.create(name="Sri Vidya School")
        self.admin = User.objects.create_user(username="admin", password="pass-12345")
        self.admin.groups.add(Group.objects.get(name="School Administrators"))
        self.plain = User.objects.create_user(username="plain", password="pass-12345")
        self.teacher = User.objects.create_user(username="rao", password="pass-12345")
        self.teacher.groups.add(Group.objects.get(name=TEACHERS_GROUP_NAME))
        self.viewer = User.objects.create_user(username="viewer", password="pass-12345")
        self.viewer.user_permissions.add(Permission.objects.get(codename="view_school"))

    def client_for(self, user):
        client = self.client_class()
        client.force_login(user)
        return client

    def upload(self, client, data=None, name="logo.png", content_type="image/png"):
        data = image_bytes("PNG") if data is None else data
        return client.post(
            reverse("core:school-logo-upload"),
            {"image": SimpleUploadedFile(name, data, content_type=content_type)},
        )


class LogoVersionTests(LogoFixture, TestCase):
    def setUp(self):
        self.build_logo_fixture()

    def test_replace_stores_normalized_png_with_matching_sha(self):
        version = school_logo.replace_logo(self.school, image_bytes("JPEG"), actor=self.admin)
        version.refresh_from_db()
        stored = bytes(version.image)
        self.assertEqual(decode(stored).format, "PNG")
        self.assertEqual(version.sha256, hashlib.sha256(stored).hexdigest())
        self.assertEqual((version.school, version.uploaded_by), (self.school, self.admin))
        self.assertFalse(version.is_removal)
        self.assertEqual(SchoolLogo.current_for(self.school), version)

    def test_each_change_records_a_permanent_security_event(self):
        first = school_logo.replace_logo(self.school, image_bytes("PNG"), actor=self.admin)
        school_logo.remove_logo(self.school, actor=self.admin)
        changed = SecurityEvent.objects.get(event_type="SCHOOL_LOGO_CHANGED")
        removed = SecurityEvent.objects.get(event_type="SCHOOL_LOGO_REMOVED")
        self.assertEqual(changed.actor, self.admin)
        self.assertEqual(changed.event_class, SecurityEvent.EventClass.HISTORY)
        self.assertEqual(changed.detail["logo_version_id"], first.pk)
        self.assertEqual(changed.detail["sha256"], first.sha256)
        self.assertNotIn("image", changed.detail)
        self.assertEqual(removed.event_class, SecurityEvent.EventClass.HISTORY)

    def test_replacing_with_the_current_image_is_refused(self):
        data = image_bytes("PNG")
        school_logo.replace_logo(self.school, data, actor=self.admin)
        with self.assertRaisesMessage(ValidationError, "already the current logo"):
            school_logo.replace_logo(self.school, data, actor=self.admin)
        self.assertEqual(SchoolLogo.objects.count(), 1)

    def test_replace_keeps_every_earlier_version(self):
        first = school_logo.replace_logo(
            self.school, image_bytes(color=(1, 2, 3)), actor=self.admin)
        second = school_logo.replace_logo(
            self.school, image_bytes(color=(9, 8, 7)), actor=self.admin)
        self.assertEqual(SchoolLogo.current_for(self.school), second)
        self.assertEqual(list(SchoolLogo.objects.order_by("pk")), [first, second])

    def test_remove_adds_a_tombstone_and_keeps_history(self):
        first = school_logo.replace_logo(self.school, image_bytes(), actor=self.admin)
        tombstone = school_logo.remove_logo(self.school, actor=self.admin)
        self.assertTrue(tombstone.is_removal)
        self.assertIsNone(tombstone.image)
        self.assertIsNone(tombstone.sha256)
        self.assertIsNone(SchoolLogo.current_for(self.school))
        self.assertTrue(SchoolLogo.objects.filter(pk=first.pk, is_removal=False).exists())

    def test_remove_without_a_logo_is_refused(self):
        with self.assertRaisesMessage(ValidationError, "no logo to remove"):
            school_logo.remove_logo(self.school, actor=self.admin)
        school_logo.replace_logo(self.school, image_bytes(), actor=self.admin)
        school_logo.remove_logo(self.school, actor=self.admin)
        with self.assertRaises(ValidationError):
            school_logo.remove_logo(self.school, actor=self.admin)

    def test_a_new_upload_after_removal_becomes_current(self):
        data = image_bytes(color=(1, 2, 3))
        school_logo.replace_logo(self.school, data, actor=self.admin)
        school_logo.remove_logo(self.school, actor=self.admin)
        again = school_logo.replace_logo(self.school, data, actor=self.admin)
        self.assertEqual(SchoolLogo.current_for(self.school), again)

    def test_latest_is_ordered_by_uploaded_at_then_pk(self):
        now = timezone.now()
        png = school_logo.normalize(image_bytes())
        digest = hashlib.sha256(png).hexdigest()
        # Created first but stamped later: it is the newest despite the lower pk.
        later_stamp = SchoolLogo.objects.create(
            school=self.school, image=png, sha256=digest, uploaded_by=self.admin,
            uploaded_at=now + timedelta(minutes=5))
        SchoolLogo.objects.create(
            school=self.school, image=png, sha256=digest, uploaded_by=self.admin,
            uploaded_at=now)
        self.assertEqual(SchoolLogo.current_for(self.school), later_stamp)
        # Equal timestamps: the higher pk wins, here a tombstone.
        stamp = now + timedelta(minutes=9)
        first = SchoolLogo.objects.create(
            school=self.school, image=png, sha256=digest, uploaded_by=self.admin,
            uploaded_at=stamp)
        second = SchoolLogo.objects.create(
            school=self.school, is_removal=True, uploaded_by=self.admin, uploaded_at=stamp)
        self.assertLess(first.pk, second.pk)
        self.assertIsNone(SchoolLogo.current_for(self.school))


class LogoDatabaseRuleTests(LogoFixture, TestCase):
    def setUp(self):
        self.build_logo_fixture()
        self.version = school_logo.replace_logo(self.school, image_bytes(), actor=self.admin)

    def create_row(self, **fields):
        values = {"school": self.school, "uploaded_by": self.admin}
        values.update(fields)
        with transaction.atomic():
            return SchoolLogo.objects.create(**values)

    def test_active_version_needs_image_and_sha(self):
        for fields in ({"image": None, "sha256": "a" * 64},
                       {"image": b"png", "sha256": None},
                       {}):
            with self.subTest(fields=fields), self.assertRaises(IntegrityError):
                self.create_row(**fields)

    def test_tombstone_must_have_no_image_and_no_sha(self):
        for fields in ({"image": b"png"}, {"sha256": "a" * 64}):
            with self.subTest(fields=fields), self.assertRaises(IntegrityError):
                self.create_row(is_removal=True, **fields)

    def test_school_is_required(self):
        with self.assertRaises(IntegrityError):
            self.create_row(school=None, is_removal=True)

    def test_update_is_refused(self):
        with self.assertRaises(DatabaseError), transaction.atomic():
            SchoolLogo.objects.filter(pk=self.version.pk).update(sha256="f" * 64)
        self.version.sha256 = "e" * 64
        with self.assertRaises(DatabaseError), transaction.atomic():
            self.version.save()

    def test_delete_is_refused(self):
        with self.assertRaises(DatabaseError), transaction.atomic():
            SchoolLogo.objects.filter(pk=self.version.pk).delete()
        self.assertTrue(SchoolLogo.objects.filter(pk=self.version.pk).exists())

    def test_the_school_cannot_be_deleted_while_it_has_logo_history(self):
        with self.assertRaises(ProtectedError), transaction.atomic():
            self.school.delete()

    def test_uploader_cannot_be_deleted(self):
        with self.assertRaises(ProtectedError), transaction.atomic():
            self.admin.delete()


class LogoViewTests(LogoFixture, TestCase):
    def setUp(self):
        self.build_logo_fixture()
        self.admin_client = self.client_for(self.admin)

    # --- management -----------------------------------------------------

    def test_administrator_uploads_a_logo(self):
        response = self.upload(self.admin_client, image_bytes("JPEG"), "logo.jpg", "image/jpeg")
        self.assertRedirects(response, reverse("core:school-detail"))
        version = SchoolLogo.current_for(self.school)
        self.assertEqual(decode(bytes(version.image)).format, "PNG")
        self.assertEqual(version.uploaded_by, self.admin)
        events = SecurityEvent.objects.filter(event_type="SCHOOL_LOGO_CHANGED")
        self.assertEqual(events.count(), 1)

    def test_a_real_image_is_accepted_whatever_content_type_the_browser_sends(self):
        self.upload(self.admin_client, content_type="application/octet-stream")
        self.assertIsNotNone(SchoolLogo.current_for(self.school))

    def test_invalid_uploads_show_an_error_and_store_nothing(self):
        cases = {
            "svg": (b"<svg xmlns='http://www.w3.org/2000/svg'/>", "logo.svg",
                    "not a readable"),
            "gif": (image_bytes("GIF"), "logo.gif", "Only PNG and JPEG"),
            "junk": (b"junk", "logo.png", "not a readable"),
            "big": (b"x" * (512 * 1024 + 1), "logo.png", "larger than 512 KB"),
            "dims": (image_bytes("PNG", size=(2001, 5)), "logo.png", "limit is 2000"),
        }
        for label, (data, name, message) in cases.items():
            with self.subTest(label=label):
                response = self.upload(self.admin_client, data, name)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, message)
        self.assertEqual(SchoolLogo.objects.count(), 0)
        self.assertFalse(SecurityEvent.objects.filter(event_type="SCHOOL_LOGO_CHANGED").exists())

    def test_missing_file_is_a_field_error(self):
        response = self.admin_client.post(reverse("core:school-logo-upload"), {})
        self.assertContains(response, "This field is required")

    def test_duplicate_upload_is_a_field_error(self):
        self.upload(self.admin_client)
        response = self.upload(self.admin_client)
        self.assertContains(response, "already the current logo")
        self.assertEqual(SchoolLogo.objects.count(), 1)

    def test_administrator_removes_the_logo(self):
        self.upload(self.admin_client)
        response = self.admin_client.post(reverse("core:school-logo-remove"))
        self.assertRedirects(response, reverse("core:school-detail"))
        self.assertIsNone(SchoolLogo.current_for(self.school))
        self.assertEqual(SchoolLogo.objects.count(), 2)

    def test_removing_when_there_is_no_logo_changes_nothing(self):
        response = self.admin_client.post(reverse("core:school-logo-remove"), follow=True)
        self.assertContains(response, "no logo to remove")
        self.assertEqual(SchoolLogo.objects.count(), 0)

    def test_management_requires_change_school(self):
        self.upload(self.admin_client)
        before = SchoolLogo.objects.count()
        for user in (self.plain, self.viewer):
            client = self.client_for(user)
            for name in ("core:school-logo-upload", "core:school-logo-remove"):
                with self.subTest(user=user.username, view=name):
                    self.assertEqual(client.post(reverse(name)).status_code, 403)
        self.assertEqual(SchoolLogo.objects.count(), before)

    def test_anonymous_users_are_sent_to_sign_in(self):
        for name in ("core:school-logo-upload", "core:school-logo-remove", "core:school-logo"):
            with self.subTest(view=name):
                response = self.client.post(reverse(name))
                self.assertEqual(response.status_code, 302)
                self.assertIn("/accounts/login/", response["Location"])

    def test_management_views_accept_post_only(self):
        for name in ("core:school-logo-upload", "core:school-logo-remove"):
            with self.subTest(view=name):
                self.assertEqual(self.admin_client.get(reverse(name)).status_code, 405)

    def test_school_page_offers_management_only_to_those_who_may_change(self):
        url = reverse("core:school-detail")
        page = self.admin_client.get(url)
        self.assertContains(page, "Upload logo")
        self.assertContains(page, reverse("core:school-logo-upload"))
        self.assertContains(page, "No logo.")
        self.upload(self.admin_client)
        page = self.admin_client.get(url)
        self.assertContains(page, "Replace logo")
        self.assertContains(page, "Remove logo")
        read_only = self.client_for(self.viewer).get(url)
        self.assertEqual(read_only.status_code, 200)
        self.assertNotContains(read_only, "Replace logo")
        self.assertNotContains(read_only, "Remove logo")

    # --- serving --------------------------------------------------------

    def test_any_signed_in_user_can_fetch_the_current_logo(self):
        self.upload(self.admin_client)
        stored = bytes(SchoolLogo.current_for(self.school).image)
        for user in (self.admin, self.plain, self.viewer):
            with self.subTest(user=user.username):
                response = self.client_for(user).get(reverse("core:school-logo"))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Content-Type"], "image/png")
                self.assertEqual(response["X-Content-Type-Options"], "nosniff")
                self.assertIn("private", response["Cache-Control"])
                self.assertEqual(response.content, stored)

    def test_unchanged_etag_gets_304_and_a_replacement_gets_new_bytes(self):
        self.upload(self.admin_client, image_bytes(color=(1, 2, 3)))
        url = reverse("core:school-logo")
        client = self.client_for(self.plain)
        etag = client.get(url)["ETag"]
        self.assertEqual(client.get(url, HTTP_IF_NONE_MATCH=etag).status_code, 304)
        self.upload(self.admin_client, image_bytes(color=(9, 9, 9)))
        refreshed = client.get(url, HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(refreshed.status_code, 200)
        self.assertNotEqual(refreshed["ETag"], etag)

    def test_no_logo_or_removed_logo_is_404(self):
        url = reverse("core:school-logo")
        self.assertEqual(self.client_for(self.plain).get(url).status_code, 404)
        self.upload(self.admin_client)
        self.admin_client.post(reverse("core:school-logo-remove"))
        self.assertEqual(self.client_for(self.plain).get(url).status_code, 404)

    def test_logo_fetch_works_while_a_password_change_is_required(self):
        self.upload(self.admin_client)
        self.plain.must_change_password = True
        self.plain.save()
        client = self.client_for(self.plain)
        self.assertEqual(client.get(reverse("core:school-logo")).status_code, 200)
        self.assertEqual(client.get(reverse("core:school-detail")).status_code, 302)

    # --- header ---------------------------------------------------------

    def test_header_shows_the_logo_with_the_text_brand_for_signed_in_users(self):
        self.upload(self.admin_client)
        version = SchoolLogo.current_for(self.school)
        for user in (self.admin, self.teacher):
            with self.subTest(user=user.username):
                landing = "core:my-home" if user == self.teacher else "core:school-detail"
                page = self.client_for(user).get(reverse(landing))
                self.assertContains(page, 'class="erp-brand-logo"')
                self.assertContains(page, f'{reverse("core:school-logo")}?v={version.pk}')
                self.assertContains(page, 'alt="Sri Vidya School logo"')
                self.assertContains(page, "School ERP</a>")

    def test_header_falls_back_to_text_without_a_logo(self):
        page = self.client_for(self.teacher).get(reverse("core:my-home"))
        self.assertNotContains(page, "erp-brand-logo")
        self.assertContains(page, "School ERP</a>")

    def test_header_falls_back_to_text_after_removal(self):
        self.upload(self.admin_client)
        self.admin_client.post(reverse("core:school-logo-remove"))
        page = self.client_for(self.teacher).get(reverse("core:my-home"))
        self.assertNotContains(page, "erp-brand-logo")

    def test_header_without_a_school_row_is_plain_text(self):
        School.objects.all().delete()
        page = self.client_for(self.teacher).get(reverse("core:my-home"))
        self.assertNotContains(page, "erp-brand-logo")

    def test_login_page_never_shows_the_logo(self):
        self.upload(self.admin_client)
        page = self.client_class().get(reverse("login"))
        self.assertNotContains(page, "erp-brand-logo")
