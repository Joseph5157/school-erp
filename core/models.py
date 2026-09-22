from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class School(models.Model):
    """The single-school configuration record (docs/REQUIREMENTS.md - School configuration).

    Singleton enforcement: `singleton_id` is a non-editable field pinned to a
    constant value. Two database rules together make a second row
    impossible even through direct ORM writes that bypass
    ModelForm/`clean()`:
    - a `CheckConstraint` requires `singleton_id == SINGLETON_ID` on every
      row, so no row may be inserted with a different sentinel value;
    - `unique=True` on that same field means at most one row may hold that
      one permitted value.
    Together, every row must equal the constant, and only one row may hold
    it -- so at most one row can ever exist, regardless of what value
    application code tries to set. `clean()` performs the same "does a row
    already exist" check proactively so that forms surface a friendly
    validation error before either database rule is ever hit.
    """

    SINGLETON_ID = 1

    name = models.CharField(max_length=255)
    singleton_id = models.PositiveSmallIntegerField(
        default=SINGLETON_ID, unique=True, editable=False
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(singleton_id=1),
                name="school_singleton_id_must_be_constant",
            ),
        ]

    def clean(self):
        super().clean()
        if self.pk is None and School.objects.exists():
            raise ValidationError("A School configuration already exists. Only one is permitted.")

    def __str__(self):
        return self.name


class AcademicYear(models.Model):
    """An explicit academic year/session record (docs/DOMAIN_MODEL.md - Academic Year)."""

    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_date"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gt=models.F("start_date")),
                name="academicyear_end_date_after_start_date",
            )
        ]

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            raise ValidationError({"end_date": "End date must be after the start date."})

    def __str__(self):
        return self.name


class ClassGrade(models.Model):
    """A reusable, year-agnostic Class/Grade reference record.

    Per docs/adr/0001-academic-structure-and-enrollment-history.md, Class/Grade
    is not recreated per Academic Year and carries no year relationship. It is
    referenced by Section, and later by Academic Enrollment.
    """

    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Class/Grade"
        verbose_name_plural = "Classes/Grades"

    def __str__(self):
        return self.name


class Section(models.Model):
    """A year-agnostic Section belonging to exactly one Class/Grade.

    Per docs/adr/0001-academic-structure-and-enrollment-history.md, Academic
    Year is not placed on Section in Phase 1; year scope lives only on
    Academic Enrollment. Section names are unique within their Class/Grade.
    """

    class_grade = models.ForeignKey(ClassGrade, on_delete=models.PROTECT, related_name="sections")
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["class_grade", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["class_grade", "name"],
                name="section_unique_name_per_class_grade",
            )
        ]

    def __str__(self):
        return f"{self.class_grade} - {self.name}"


class RelationshipType(models.TextChoices):
    """How a Guardian relates to an Applicant or Student.

    Defined once and shared by the ApplicantGuardian and (later)
    StudentGuardian relationships, per
    docs/adr/0002-applicant-student-and-guardian-lifecycle.md.
    """

    FATHER = "FATHER", "Father"
    MOTHER = "MOTHER", "Mother"
    GUARDIAN = "GUARDIAN", "Guardian"
    GRANDPARENT = "GRANDPARENT", "Grandparent"
    OTHER = "OTHER", "Other"


class Guardian(models.Model):
    """A first-class, reusable Guardian record (docs/DOMAIN_MODEL.md - Guardians).

    A Guardian is independent of any single Applicant or Student and may be
    associated with several of either through explicit relationships, so that
    siblings can share one Guardian record rather than duplicating it.
    """

    full_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name


class Applicant(models.Model):
    """An application record, distinct from Student (docs/DOMAIN_MODEL.md - Applicant).

    Creating an Applicant never creates a Student; the admission state is
    explicit and only changes through the dedicated admission-decision
    workflow (docs/adr/0003-phase-1-status-and-transition-rules.md). The
    status vocabulary is fixed to PENDING/ACCEPTED/REJECTED for Phase 1.
    """

    class AdmissionStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ACCEPTED = "ACCEPTED", "Accepted"
        REJECTED = "REJECTED", "Rejected"

    full_name = models.CharField(max_length=255)
    date_of_birth = models.DateField(null=True, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    admission_status = models.CharField(
        max_length=10,
        choices=AdmissionStatus.choices,
        default=AdmissionStatus.PENDING,
    )
    admission_decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name"]

    def record_admission_decision(self, decision):
        """Record a final admission decision for a pending Applicant.

        Per docs/adr/0003-phase-1-status-and-transition-rules.md the only
        permitted Phase 1 transitions are PENDING -> ACCEPTED and
        PENDING -> REJECTED, and ACCEPTED/REJECTED are final. Any other
        request -- an unknown decision, a repeat, or a reversal -- is rejected
        without changing the record, so the original application history is
        never silently rewritten.
        """
        allowed = {self.AdmissionStatus.ACCEPTED, self.AdmissionStatus.REJECTED}
        if decision not in allowed:
            raise ValidationError("Invalid admission decision.")
        if self.admission_status != self.AdmissionStatus.PENDING:
            raise ValidationError(
                "An admission decision has already been recorded for this Applicant."
            )
        self.admission_status = decision
        self.admission_decided_at = timezone.now()
        self.save(update_fields=["admission_status", "admission_decided_at", "updated_at"])

    def __str__(self):
        return self.full_name


class ApplicantGuardian(models.Model):
    """An explicit Applicant-Guardian association carrying a relationship type.

    Per docs/adr/0002-applicant-student-and-guardian-lifecycle.md, an
    Applicant may have one or more Guardians before a Student exists. This
    history is preserved intact after progression; it is not replaced by the
    resulting StudentGuardian relationships. A given Guardian appears at most
    once per Applicant.
    """

    applicant = models.ForeignKey(
        Applicant, on_delete=models.PROTECT, related_name="guardian_links"
    )
    guardian = models.ForeignKey(
        Guardian, on_delete=models.PROTECT, related_name="applicant_links"
    )
    relationship_type = models.CharField(max_length=20, choices=RelationshipType.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["applicant", "guardian"]
        constraints = [
            models.UniqueConstraint(
                fields=["applicant", "guardian"],
                name="applicantguardian_unique_applicant_guardian",
            )
        ]

    def __str__(self):
        return f"{self.applicant} - {self.guardian} ({self.get_relationship_type_display()})"
