"""Phase 4 Gate 1: Subjects, Academic Terms and subject offerings (ADR 0009)."""

from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from core.models import (
    AcademicSubjectOffering,
    AcademicSubjectOfferingSection,
    AcademicTerm,
    AcademicYear,
    ClassGrade,
    Section,
    Subject,
)

User = get_user_model()


class StructureFixture:
    def build(self):
        self.year = AcademicYear.objects.create(
            name="2026-27", start_date=date(2026, 6, 1), end_date=date(2027, 3, 31)
        )
        self.other_year = AcademicYear.objects.create(
            name="2027-28", start_date=date(2027, 6, 1), end_date=date(2028, 3, 31)
        )
        self.grade6 = ClassGrade.objects.create(name="Grade 6")
        self.grade7 = ClassGrade.objects.create(name="Grade 7")
        self.six_a = Section.objects.create(class_grade=self.grade6, name="A")
        self.six_b = Section.objects.create(class_grade=self.grade6, name="B")
        self.seven_a = Section.objects.create(class_grade=self.grade7, name="A")
        self.maths = Subject.objects.create(name="Mathematics", code="MATH")
        self.english = Subject.objects.create(name="English")
        self.sanskrit = Subject.objects.create(name="Sanskrit")

    def offer(self, subject, grade=None, sections=(), year=None):
        offering = AcademicSubjectOffering(
            academic_year=year or self.year, class_grade=grade or self.grade6, subject=subject
        )
        offering.full_clean()
        offering.save()
        offering.set_sections(sections)
        return offering

    def term(self, name, start, end, order, year=None):
        term = AcademicTerm(
            academic_year=year or self.year,
            name=name,
            start_date=start,
            end_date=end,
            display_order=order,
        )
        term.full_clean()
        term.save()
        return term


class SubjectTests(StructureFixture, TestCase):
    def setUp(self):
        self.build()

    def test_name_unique(self):
        with self.assertRaises(ValidationError):
            Subject(name="Mathematics").full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Subject.objects.create(name="Mathematics")

    def test_code_unique_only_when_set(self):
        Subject.objects.create(name="Science")  # second blank code is fine
        with self.assertRaises(IntegrityError), transaction.atomic():
            Subject.objects.create(name="Maths 2", code="MATH")

    def test_clean_normalises_name_and_code(self):
        subject = Subject(name="  Science ", code=" sci ")
        subject.full_clean()
        self.assertEqual((subject.name, subject.code), ("Science", "SCI"))

    def test_rename_keeps_offerings_attached(self):
        offering = self.offer(self.maths)
        self.maths.name = "Maths"
        self.maths.save()
        offering.refresh_from_db()
        self.assertEqual(offering.subject.name, "Maths")

    def test_inactive_subject_cannot_be_newly_offered(self):
        self.sanskrit.is_active = False
        self.sanskrit.save()
        with self.assertRaises(ValidationError):
            self.offer(self.sanskrit)

    def test_deactivating_keeps_existing_offering_valid(self):
        offering = self.offer(self.sanskrit)
        self.sanskrit.is_active = False
        self.sanskrit.save()
        offering.full_clean()

    def test_subject_with_offering_cannot_be_deleted(self):
        self.offer(self.maths)
        with self.assertRaises(ProtectedError), transaction.atomic():
            self.maths.delete()


class AcademicTermTests(StructureFixture, TestCase):
    def setUp(self):
        self.build()

    def test_valid_terms_in_explicit_order(self):
        self.term("Term 2", date(2026, 10, 1), date(2026, 12, 31), 2)
        self.term("Term 1", date(2026, 6, 1), date(2026, 9, 30), 1)
        self.assertEqual([t.name for t in self.year.terms.all()], ["Term 1", "Term 2"])

    def test_end_must_be_after_start(self):
        for end in (date(2026, 6, 1), date(2026, 5, 31)):
            with self.subTest(end=end), self.assertRaises(ValidationError):
                self.term("Bad", date(2026, 6, 1), end, 1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            AcademicTerm.objects.create(
                academic_year=self.year,
                name="Bad",
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 1),
                display_order=1,
            )

    def test_term_must_be_inside_academic_year(self):
        for start, end in (
            (date(2026, 5, 1), date(2026, 9, 30)),
            (date(2027, 1, 1), date(2027, 4, 30)),
        ):
            with self.subTest(start=start), self.assertRaises(ValidationError):
                self.term("Out", start, end, 1)

    def test_year_boundaries_inclusive(self):
        self.term("Whole year", date(2026, 6, 1), date(2027, 3, 31), 1)

    def test_terms_may_not_overlap(self):
        self.term("Term 1", date(2026, 6, 1), date(2026, 9, 30), 1)
        for start, end in (
            (date(2026, 9, 30), date(2026, 12, 31)),  # touches last day
            (date(2026, 7, 1), date(2026, 8, 1)),  # inside
            (date(2026, 5, 31), date(2026, 6, 1)),  # out of year anyway
        ):
            with self.subTest(start=start), self.assertRaises(ValidationError):
                self.term("Term 2", start, end, 2)
        self.term("Term 2", date(2026, 10, 1), date(2026, 12, 31), 2)

    def test_editing_a_term_does_not_clash_with_itself(self):
        term = self.term("Term 1", date(2026, 6, 1), date(2026, 9, 30), 1)
        term.end_date = date(2026, 10, 15)
        term.full_clean()
        term.save()

    def test_name_and_order_unique_within_year_only(self):
        self.term("Term 1", date(2026, 6, 1), date(2026, 9, 30), 1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            AcademicTerm.objects.create(
                academic_year=self.year, name="Term 1", start_date=date(2026, 10, 1),
                end_date=date(2026, 12, 31), display_order=2,
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            AcademicTerm.objects.create(
                academic_year=self.year, name="Term 2", start_date=date(2026, 10, 1),
                end_date=date(2026, 12, 31), display_order=1,
            )
        self.term("Term 1", date(2027, 6, 1), date(2027, 9, 30), 1, year=self.other_year)

    def test_contains(self):
        term = self.term("Term 1", date(2026, 6, 1), date(2026, 9, 30), 1)
        self.assertTrue(term.contains(date(2026, 6, 1)))
        self.assertTrue(term.contains("2026-09-30"))
        self.assertFalse(term.contains(date(2026, 10, 1)))

    def test_year_with_terms_cannot_be_deleted(self):
        self.term("Term 1", date(2026, 6, 1), date(2026, 9, 30), 1)
        with self.assertRaises(ProtectedError), transaction.atomic():
            self.year.delete()


class SubjectOfferingTests(StructureFixture, TestCase):
    def setUp(self):
        self.build()

    def test_offering_unique_per_year_grade_subject(self):
        self.offer(self.maths)
        with self.assertRaises(ValidationError):
            self.offer(self.maths)
        with self.assertRaises(IntegrityError), transaction.atomic():
            AcademicSubjectOffering.objects.create(
                academic_year=self.year, class_grade=self.grade6, subject=self.maths
            )
        self.offer(self.maths, grade=self.grade7)
        self.offer(self.maths, year=self.other_year)

    def test_no_sections_means_all_sections(self):
        offering = self.offer(self.maths)
        self.assertTrue(offering.applies_to_all_sections)
        self.assertTrue(offering.applies_to(self.six_a))
        self.assertTrue(offering.applies_to(self.six_b))
        self.assertFalse(offering.applies_to(self.seven_a))

    def test_restricted_sections(self):
        offering = self.offer(self.sanskrit, sections=[self.six_b])
        self.assertFalse(offering.applies_to_all_sections)
        self.assertEqual(list(offering.sections), [self.six_b])
        self.assertFalse(offering.applies_to(self.six_a))
        self.assertTrue(offering.applies_to(self.six_b))

    def test_section_from_other_grade_rejected_without_change(self):
        offering = self.offer(self.sanskrit, sections=[self.six_b])
        with self.assertRaises(ValidationError):
            offering.set_sections([self.six_a, self.seven_a])
        self.assertEqual(list(offering.sections), [self.six_b])
        link = AcademicSubjectOfferingSection(offering=offering, section=self.seven_a)
        with self.assertRaises(ValidationError):
            link.full_clean()

    def test_set_sections_replaces_scope(self):
        offering = self.offer(self.sanskrit, sections=[self.six_b])
        offering.set_sections([self.six_a])
        self.assertEqual(list(offering.sections), [self.six_a])
        offering.set_sections([])
        self.assertTrue(offering.applies_to_all_sections)

    def test_duplicate_section_link_rejected_by_database(self):
        offering = self.offer(self.sanskrit, sections=[self.six_b])
        with self.assertRaises(IntegrityError), transaction.atomic():
            AcademicSubjectOfferingSection.objects.create(offering=offering, section=self.six_b)

    def test_which_subjects_for_section_and_term(self):
        self.offer(self.maths)  # all Grade 6 Sections
        self.offer(self.english, sections=[self.six_a, self.six_b])
        self.offer(self.sanskrit, sections=[self.six_b])
        self.offer(self.english, grade=self.grade7)
        self.offer(self.sanskrit, year=self.other_year)
        term = self.term("Term 1", date(2026, 6, 1), date(2026, 9, 30), 1)

        def subjects(qs):
            return sorted(o.subject.name for o in qs)

        self.assertEqual(
            subjects(AcademicSubjectOffering.objects.for_section(self.year, self.six_a)),
            ["English", "Mathematics"],
        )
        self.assertEqual(
            subjects(AcademicSubjectOffering.objects.for_term_section(term, self.six_b)),
            ["English", "Mathematics", "Sanskrit"],
        )
        self.assertEqual(
            subjects(AcademicSubjectOffering.objects.for_section(self.year, self.seven_a)),
            ["English"],
        )
        self.assertEqual(
            subjects(AcademicSubjectOffering.objects.for_section(self.other_year, self.six_b)),
            ["Sanskrit"],
        )

    def test_section_in_use_cannot_be_deleted(self):
        self.offer(self.sanskrit, sections=[self.six_b])
        with self.assertRaises(ProtectedError), transaction.atomic():
            self.six_b.delete()


class StructureViewTests(StructureFixture, TestCase):
    def setUp(self):
        self.build()
        admin = User.objects.create_user(username="administrator", password="pass-12345")
        admin.groups.add(Group.objects.get(name="School Administrators"))
        self.client.login(username="administrator", password="pass-12345")
        self.other = self.client_class()
        User.objects.create_user(username="teacher", password="pass-12345")
        self.other.login(username="teacher", password="pass-12345")

    def test_subject_create_and_edit(self):
        response = self.client.post(
            reverse("core:subject-create"), {"name": "Science", "code": "sci", "is_active": "on"}
        )
        self.assertRedirects(response, reverse("core:subject-list"))
        science = Subject.objects.get(name="Science")
        self.assertEqual(science.code, "SCI")
        self.client.post(
            reverse("core:subject-update", args=[science.pk]), {"name": "General Science"}
        )
        science.refresh_from_db()
        self.assertEqual(science.name, "General Science")
        self.assertFalse(science.is_active)
        self.assertContains(self.client.get(reverse("core:subject-list")), "Inactive")

    def test_term_create_validates_and_lists(self):
        url = reverse("core:term-create", args=[self.year.pk])
        ok = self.client.post(
            url,
            {"name": "Term 1", "start_date": "2026-06-01", "end_date": "2026-09-30",
             "display_order": 1},
        )
        self.assertRedirects(ok, reverse("core:academic-year-terms", args=[self.year.pk]))
        clash = self.client.post(
            url,
            {"name": "Term 1", "start_date": "2026-09-01", "end_date": "2026-12-31",
             "display_order": 1},
        )
        self.assertEqual(clash.status_code, 200)
        self.assertContains(clash, "already uses this")
        self.assertContains(clash, "overlap")
        self.assertEqual(self.year.terms.count(), 1)
        listing = self.client.get(reverse("core:academic-year-terms", args=[self.year.pk]))
        self.assertContains(listing, "Term 1")

    def test_term_update(self):
        term = self.term("Term 1", date(2026, 6, 1), date(2026, 9, 30), 1)
        response = self.client.post(
            reverse("core:term-update", args=[term.pk]),
            {"name": "First Term", "start_date": "2026-06-01", "end_date": "2026-10-15",
             "display_order": 1},
        )
        self.assertRedirects(response, reverse("core:academic-year-terms", args=[self.year.pk]))
        term.refresh_from_db()
        self.assertEqual((term.name, term.end_date), ("First Term", date(2026, 10, 15)))

    def test_offering_create_all_sections_and_restricted(self):
        url = reverse("core:offering-create", args=[self.year.pk])
        self.client.post(url, {"class_grade": self.grade6.pk, "subject": self.maths.pk})
        self.client.post(
            url,
            {"class_grade": self.grade6.pk, "subject": self.sanskrit.pk,
             "sections": [self.six_b.pk]},
        )
        maths = AcademicSubjectOffering.objects.get(subject=self.maths)
        sanskrit = AcademicSubjectOffering.objects.get(subject=self.sanskrit)
        self.assertTrue(maths.applies_to_all_sections)
        self.assertEqual(list(sanskrit.sections), [self.six_b])
        listing = self.client.get(reverse("core:academic-year-offerings", args=[self.year.pk]))
        self.assertContains(listing, "All Sections")

    def test_offering_create_rejects_wrong_grade_section_and_duplicate(self):
        url = reverse("core:offering-create", args=[self.year.pk])
        bad = self.client.post(
            url,
            {"class_grade": self.grade6.pk, "subject": self.maths.pk,
             "sections": [self.seven_a.pk]},
        )
        self.assertContains(bad, "Every Section must belong")
        self.assertFalse(AcademicSubjectOffering.objects.exists())
        self.client.post(url, {"class_grade": self.grade6.pk, "subject": self.maths.pk})
        duplicate = self.client.post(url, {"class_grade": self.grade6.pk, "subject": self.maths.pk})
        self.assertContains(duplicate, "already offered")
        self.assertEqual(AcademicSubjectOffering.objects.count(), 1)

    def test_offering_form_hides_inactive_subjects(self):
        self.sanskrit.is_active = False
        self.sanskrit.save()
        response = self.client.post(
            reverse("core:offering-create", args=[self.year.pk]),
            {"class_grade": self.grade6.pk, "subject": self.sanskrit.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(AcademicSubjectOffering.objects.exists())

    def test_offering_update_changes_scope_only(self):
        offering = self.offer(self.sanskrit, sections=[self.six_b])
        response = self.client.post(
            reverse("core:offering-update", args=[offering.pk]),
            {"sections": [self.six_a.pk], "subject": self.maths.pk},
        )
        self.assertRedirects(
            response, reverse("core:academic-year-offerings", args=[self.year.pk])
        )
        offering.refresh_from_db()
        self.assertEqual(offering.subject, self.sanskrit)
        self.assertEqual(list(offering.sections), [self.six_a])

    def test_offered_subjects_lookup(self):
        self.offer(self.maths)
        self.offer(self.sanskrit, sections=[self.six_b])
        term = self.term("Term 1", date(2026, 6, 1), date(2026, 9, 30), 1)
        url = reverse("core:academic-year-offerings", args=[self.year.pk])
        a = self.client.get(url, {"section": self.six_a.pk, "term": term.pk})
        b = self.client.get(url, {"section": self.six_b.pk})
        self.assertEqual([o.subject for o in a.context["offered"]], [self.maths])
        self.assertEqual([o.subject for o in b.context["offered"]], [self.maths, self.sanskrit])

    def test_non_admin_cannot_change_structures(self):
        offering = self.offer(self.maths)
        term = self.term("Term 1", date(2026, 6, 1), date(2026, 9, 30), 1)
        for url, data in (
            (reverse("core:subject-create"), {"name": "X"}),
            (reverse("core:subject-update", args=[self.maths.pk]), {"name": "X"}),
            (reverse("core:term-create", args=[self.year.pk]), {}),
            (reverse("core:term-update", args=[term.pk]), {}),
            (reverse("core:offering-create", args=[self.year.pk]), {}),
            (reverse("core:offering-update", args=[offering.pk]), {"sections": []}),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.other.post(url, data).status_code, 403)
        self.maths.refresh_from_db()
        self.assertEqual(self.maths.name, "Mathematics")
        self.assertEqual(Subject.objects.count(), 3)
