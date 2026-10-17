import datetime
import string
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator, MinValueValidator, RegexValidator
from django.db import IntegrityError, models, transaction
from django.db.models.functions import Upper
from django.utils import timezone


def _as_date(value):
    """Normalise a date-like value (date or ISO string) to a `datetime.date`.

    Unsaved or freshly created model instances may still hold the string that
    was passed in, so date comparisons go through this helper.
    """
    if value is None or value == "":
        return None
    return models.DateField().to_python(value)


def business_today():
    """Today's local business date (per settings.TIME_ZONE).

    Kept as one function so operational "no future date" rules share a single
    definition of today, and tests can pin it deterministically.
    """
    return timezone.localdate()


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

    class NotificationMode(models.TextChoices):
        PORTAL_ONLY = "PORTAL_ONLY", "Portal only (no WhatsApp messages)"
        ASSIST = "ASSIST", "WhatsApp, sent by office staff (ASSIST)"
        API = "API", "WhatsApp Business API"
        SMS = "SMS", "SMS"

    name = models.CharField(max_length=255)
    address = models.TextField(blank=True)
    affiliation_number = models.CharField(max_length=50, blank=True)
    principal_name = models.CharField(max_length=120, blank=True)
    notification_channel = models.CharField(
        "Messages to guardians",
        max_length=12,
        choices=NotificationMode.choices,
        default=NotificationMode.PORTAL_ONLY,
    )
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
    """An explicit academic year/session record (docs/DOMAIN_MODEL.md - Academic Year).

    Also carries the year's weekly instructional pattern for the minimal school
    calendar (docs/adr/0008-phase-2-school-calendar-rules.md): Monday-Friday
    are instructional, Sunday is not, and Saturday follows
    `saturdays_instructional`. Individual dates that differ from the pattern
    are recorded as SchoolCalendarDay exceptions.
    """

    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    saturdays_instructional = models.BooleanField(
        default=False,
        help_text="Whether Saturdays are normally instructional days in this Academic Year.",
    )
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

    def contains(self, on_date):
        on_date = _as_date(on_date)
        return _as_date(self.start_date) <= on_date <= _as_date(self.end_date)

    def default_is_instructional(self, on_date):
        """The weekly pattern alone, ignoring calendar exceptions."""
        weekday = _as_date(on_date).weekday()
        if weekday == 6:  # Sunday
            return False
        if weekday == 5:  # Saturday
            return self.saturdays_instructional
        return True

    def is_instructional_day(self, on_date):
        """Is attendance expected on `on_date` in this Academic Year?

        Dates outside the year are never instructional. A SchoolCalendarDay
        exception for the date wins; otherwise the weekly pattern applies.
        """
        on_date = _as_date(on_date)
        if not self.contains(on_date):
            return False
        override = (
            self.calendar_days.filter(date=on_date)
            .values_list("is_instructional", flat=True)
            .first()
        )
        if override is not None:
            return override
        return self.default_is_instructional(on_date)

    def set_saturdays_instructional(self, value):
        """Change the year's Saturday rule, if it is still safe to do so.

        Rejected when it would not change anything, when the year already has
        attendance registers (changing the pattern would silently reclassify
        dates that already carry attendance), or when Saturday exceptions
        exist (they would contradict the new pattern; remove them first).
        """
        value = bool(value)
        if value == self.saturdays_instructional:
            raise ValidationError("Saturdays already have this setting for this Academic Year.")
        if self.attendance_registers.exists():
            raise ValidationError(
                "The Saturday rule cannot change once attendance has been recorded "
                "in this Academic Year."
            )
        if self.calendar_days.filter(date__week_day=7).exists():
            raise ValidationError(
                "Remove this year's Saturday calendar exceptions before changing the "
                "Saturday rule."
            )
        self.saturdays_instructional = value
        self.save(update_fields=["saturdays_instructional", "updated_at"])

    def __str__(self):
        return self.name


class SchoolCalendarDay(models.Model):
    """One date that differs from its Academic Year's weekly pattern.

    Minimal Phase 2 calendar (docs/adr/0007-phase-2-attendance-model.md,
    docs/adr/0008-phase-2-school-calendar-rules.md). Only exceptions are
    stored: a holiday/closure on a normally instructional date
    (`is_instructional=False`), or an extra instructional date such as a
    working Saturday (`is_instructional=True`). An entry that merely repeats
    the weekly pattern is rejected.

    Attendance protection: an exception that makes a date non-instructional
    cannot be added, and no exception can be deleted, while an attendance
    register exists for that Academic Year and date. Date and type are fixed
    once recorded; only the label may change.
    """

    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.PROTECT, related_name="calendar_days"
    )
    date = models.DateField()
    is_instructional = models.BooleanField(
        help_text="True for an extra instructional day, False for a holiday or closure."
    )
    label = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date"]
        verbose_name = "School calendar day"
        constraints = [
            models.UniqueConstraint(
                fields=["academic_year", "date"],
                name="schoolcalendarday_unique_academic_year_date",
            )
        ]

    def clean(self):
        super().clean()
        if not (self.academic_year_id and self.date) or self.is_instructional is None:
            return
        year = self.academic_year
        if not year.contains(self.date):
            raise ValidationError({"date": "Date must fall within the selected Academic Year."})

        if self.pk is not None:
            original = SchoolCalendarDay.objects.get(pk=self.pk)
            if (
                original.academic_year_id != self.academic_year_id
                or original.date != _as_date(self.date)
                or original.is_instructional != self.is_instructional
            ):
                raise ValidationError(
                    "A calendar exception's date and type cannot be changed; "
                    "delete it and record a new one."
                )
            return

        if self.is_instructional == year.default_is_instructional(self.date):
            state = "instructional" if self.is_instructional else "non-instructional"
            raise ValidationError(
                {"date": f"This date is already {state} under the weekly pattern."}
            )
        if not self.is_instructional and self.attendance_registers().exists():
            raise ValidationError(
                {"date": "Attendance already exists on this date; it cannot become a holiday."}
            )

    def attendance_registers(self):
        return AttendanceRegister.objects.filter(
            academic_year_id=self.academic_year_id, date=self.date
        )

    def delete(self, *args, **kwargs):
        if self.attendance_registers().exists():
            raise ValidationError(
                "Attendance already exists on this date; this calendar exception cannot be removed."
            )
        return super().delete(*args, **kwargs)

    def __str__(self):
        kind = "Instructional" if self.is_instructional else "Non-instructional"
        suffix = f" - {self.label}" if self.label else ""
        return f"{self.academic_year} {self.date} ({kind}){suffix}"


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
    admission_decision_reason = models.TextField(blank=True, default="")
    import_batch = models.ForeignKey(
        "ImportBatch",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        editable=False,
        related_name="applicants",
        help_text="Set only for Applicants created by a bulk import (ADR 0017).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name"]

    def record_admission_decision(self, decision, reason=""):
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
        with transaction.atomic():
            applicant = Applicant.objects.select_for_update().get(pk=self.pk)
            if applicant.admission_status != self.AdmissionStatus.PENDING:
                raise ValidationError(
                    "An admission decision has already been recorded for this Applicant."
                )
            if decision == self.AdmissionStatus.REJECTED and not reason.strip():
                raise ValidationError("A reason is required to reject an applicant.")
            if (
                decision == self.AdmissionStatus.REJECTED
                and Student.objects.filter(applicant=applicant).exists()
            ):
                raise ValidationError(
                    "This Applicant already has a Student record, so it cannot be rejected."
                )
            applicant.admission_status = decision
            applicant.admission_decided_at = timezone.now()
            applicant.admission_decision_reason = reason.strip()
            applicant.save(
                update_fields=[
                    "admission_status",
                    "admission_decided_at",
                    "admission_decision_reason",
                    "updated_at",
                ]
            )
        self.admission_status = applicant.admission_status
        self.admission_decided_at = applicant.admission_decided_at
        self.admission_decision_reason = applicant.admission_decision_reason

    def progress_to_student(self):
        """Explicitly create the one Student for an accepted Applicant.

        Per docs/adr/0002-applicant-student-and-guardian-lifecycle.md and the
        Requirements progression rules: only an ACCEPTED Applicant may
        progress, one Applicant yields at most one Student, and the approved
        ApplicantGuardian relationships are carried into the new
        StudentGuardian relationships while the ApplicantGuardian history is
        preserved intact. An invalid or repeated attempt raises
        ValidationError without creating or changing anything.
        """
        if self.admission_status != self.AdmissionStatus.ACCEPTED:
            raise ValidationError("Only an accepted Applicant can progress to a Student.")
        if Student.objects.filter(applicant=self).exists():
            raise ValidationError("This Applicant has already progressed to a Student.")

        try:
            with transaction.atomic():
                student = Student.objects.create(
                    applicant=self,
                    full_name=self.full_name,
                    date_of_birth=self.date_of_birth,
                    email=self.email,
                    phone=self.phone,
                )
                StudentGuardian.objects.bulk_create(
                    StudentGuardian(
                        student=student,
                        guardian=link.guardian,
                        relationship_type=link.relationship_type,
                    )
                    for link in self.guardian_links.all()
                )
        except IntegrityError:
            # A concurrent progression won the race on the OneToOne link.
            raise ValidationError(
                "This Applicant has already progressed to a Student."
            ) from None
        return student

    def __str__(self):
        return self.full_name


def reconcile_applicant(applicant, *, include_rejected=False):
    """Mark an Applicant ACCEPTED because a Student record already exists for it.

    Repairs old data where a Student was created next to a PENDING (or
    REJECTED) Applicant. This deliberately bypasses `record_admission_decision`,
    which treats decisions as final. A REJECTED Applicant is only changed when
    `include_rejected` is true, and its old reason is kept in the new text.
    Returns True when the row was changed; an Applicant that is already
    ACCEPTED, has no Student, or is an unflagged REJECTED one is left alone.
    """
    accepted = Applicant.AdmissionStatus.ACCEPTED
    with transaction.atomic():
        locked = Applicant.objects.select_for_update().get(pk=applicant.pk)
        student = Student.objects.filter(applicant=locked).first()
        if student is None or locked.admission_status == accepted:
            return False
        reason = "Reconciled: Student record already existed."
        if locked.admission_status == Applicant.AdmissionStatus.REJECTED:
            if not include_rejected:
                return False
            old = locked.admission_decision_reason.strip()
            reason = (
                f"Reconciled: Student record already existed (was rejected: {old[:2000]})."
                if old
                else "Reconciled: Student record already existed (was rejected)."
            )
        locked.admission_status = accepted
        locked.admission_decided_at = student.created_at
        locked.admission_decision_reason = reason
        locked.save(
            update_fields=[
                "admission_status",
                "admission_decided_at",
                "admission_decision_reason",
                "updated_at",
            ]
        )
    applicant.admission_status = locked.admission_status
    applicant.admission_decided_at = locked.admission_decided_at
    applicant.admission_decision_reason = locked.admission_decision_reason
    return True


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


ADMISSION_NUMBER_VALIDATOR = RegexValidator(
    r"^[A-Za-z0-9][A-Za-z0-9/._-]{0,29}\Z",
    "Use letters, digits, slash, dot, underscore or hyphen (up to 30).",
)


def normalize_admission_number(value):
    """Trim; empty means not recorded (None). Case is kept as entered."""
    value = (value or "").strip()
    return value or None


class Student(models.Model):
    """The long-lived school identity created by explicit progression.

    Distinct from Applicant (docs/DOMAIN_MODEL.md - Applicant and Student are
    different concepts). The OneToOne link to the source Applicant enforces at
    most one Student per Applicant and keeps the Student traceable back to its
    application (docs/adr/0002-applicant-student-and-guardian-lifecycle.md).
    Academic placement is deliberately absent here; it lives on Academic
    Enrollment, which is out of scope for this milestone.
    """

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"

    applicant = models.OneToOneField(
        Applicant, on_delete=models.PROTECT, related_name="student"
    )
    full_name = models.CharField(max_length=255)
    date_of_birth = models.DateField(null=True, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    status_changed_at = models.DateTimeField(null=True, blank=True)
    admission_number = models.CharField(
        max_length=30,
        null=True,
        blank=True,
        validators=[ADMISSION_NUMBER_VALIDATOR],
        help_text="Optional, entered by the school; never generated (ADR 0014).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name"]
        constraints = [
            models.UniqueConstraint(
                Upper("admission_number"),
                condition=models.Q(admission_number__isnull=False),
                name="student_admission_number_ci_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(admission_number__isnull=True)
                | ~models.Q(admission_number=""),
                name="student_admission_number_not_blank",
            ),
        ]

    def save(self, *args, **kwargs):
        # Insert-only guard (audit F08): existing rows must always stay savable.
        if (
            self._state.adding
            and self.applicant_id is not None
            and self.applicant.admission_status != Applicant.AdmissionStatus.ACCEPTED
        ):
            raise ValidationError("A Student can only be created for an accepted Applicant.")
        super().save(*args, **kwargs)

    def set_admission_number(self, value):
        """Record (or clear) the admission number entered by an administrator."""
        value = normalize_admission_number(value)
        if value is not None:
            ADMISSION_NUMBER_VALIDATOR(value)
            clash = Student.objects.annotate(_key=Upper("admission_number")).filter(
                _key=value.upper()
            ).exclude(pk=self.pk)
            if clash.exists():
                raise ValidationError("Another Student already has this admission number.")
        self.admission_number = value
        try:
            with transaction.atomic():
                self.save(update_fields=["admission_number", "updated_at"])
        except IntegrityError as error:
            raise ValidationError(
                "Another Student already has this admission number."
            ) from error

    def record_status_change(self, new_status, *, actor=None, access_decisions=None,
                             access_note="", reason=""):
        """Change the Student's lifecycle status between ACTIVE and INACTIVE.

        Per docs/adr/0003-phase-1-status-and-transition-rules.md the frozen
        Phase 1 Student status set is ACTIVE/INACTIVE. Phase 1 keeps the
        lifecycle deliberately small: an administrator may deactivate an
        active Student or reactivate an inactive one. An unknown status or a
        no-op change is rejected without changing the record, and this only
        touches the Student row so historical enrollment and application data
        are never silently rewritten.
        """
        allowed = {self.Status.ACTIVE, self.Status.INACTIVE}
        if new_status not in allowed:
            raise ValidationError("Invalid Student status.")
        if new_status == self.status:
            raise ValidationError("Student already has this status.")
        if new_status == self.Status.INACTIVE and not reason.strip():
            raise ValidationError("A reason is required to deactivate a Student.")
        previous_status = self.status
        with transaction.atomic():
            list(Student.objects.select_for_update().filter(pk=self.pk).values_list("pk"))
            if new_status == self.Status.INACTIVE:
                # Phase 6 (ADR 0013): every active guardian grant needs an
                # explicit retain/revoke decision; nothing is inferred.
                from core.guardian_access import apply_review_decisions

                apply_review_decisions(
                    student=self,
                    trigger=GuardianAccessReview.Trigger.STUDENT_INACTIVE,
                    enrollment=self.enrollments.filter(
                        status=AcademicEnrollment.Status.ACTIVE
                    ).first(),
                    decisions=access_decisions,
                    actor=actor,
                    note=access_note,
                )
            self.status = new_status
            self.status_changed_at = timezone.now()
            self.save(update_fields=["status", "status_changed_at", "updated_at"])
            StudentStatusChange.objects.create(
                student=self,
                previous_status=previous_status,
                new_status=new_status,
                reason=reason.strip(),
                changed_by=actor,
            )

    def enroll(self, *, academic_year, class_grade, section, start_date, actor=None,
               access_decisions=None, access_note=""):
        """Place the Student into a new academic placement effective `start_date`.

        Per docs/adr/0003-phase-1-status-and-transition-rules.md, a Student has
        at most one ACTIVE Academic Enrollment, and per
        docs/adr/0006-academic-enrollment-effective-dating.md every placement
        carries a business-effective date range. Recording a new placement:

        - requires the caller to state the effective `start_date` explicitly
          (it is never inferred from the clock or audit timestamps);
        - rejects a `start_date` later than today's local business date, so an
          ACTIVE enrollment is always the placement effective now (scheduled
          future placements are not a Phase 2 concept);
        - closes the previous ACTIVE enrollment with `end_date` set to the day
          before `start_date` and marks it COMPLETED, preserving it;
        - creates the new ACTIVE enrollment from `start_date`.

        Effective ranges are inclusive on both ends, so a transfer effective
        on date D leaves the Student in the old placement through D - 1 and in
        the new placement from D. The Section must belong to the enrollment's
        Class/Grade. An incompatible placement, an exact repeat of the current
        one, or a date that would produce an invalid or overlapping history is
        rejected without changing anything.
        """
        start_date = _as_date(start_date)
        if start_date is None:
            raise ValidationError("An effective start date is required.")
        if start_date > business_today():
            raise ValidationError("The effective start date cannot be in the future.")
        if section.class_grade_id != class_grade.pk:
            raise ValidationError("Selected Section does not belong to the selected Class/Grade.")

        try:
            with transaction.atomic():
                # Serialise placement changes for this Student so concurrent
                # requests cannot both close/create around the same history.
                list(
                    Student.objects.select_for_update()
                    .filter(pk=self.pk)
                    .values_list("pk", flat=True)
                )
                current = AcademicEnrollment.objects.filter(
                    student=self, status=AcademicEnrollment.Status.ACTIVE
                ).first()
                if current is not None:
                    if (
                        current.academic_year_id == academic_year.pk
                        and current.class_grade_id == class_grade.pk
                        and current.section_id == section.pk
                    ):
                        raise ValidationError(
                            "This Student already has an active enrollment for this placement."
                        )
                    if start_date <= current.start_date:
                        raise ValidationError(
                            "The new placement must start after the current placement's "
                            f"start date ({current.start_date.isoformat()})."
                        )
                    # Phase 6 (ADR 0013): ending a placement needs an explicit
                    # retain/revoke decision for every active guardian grant.
                    from core.guardian_access import apply_review_decisions

                    apply_review_decisions(
                        student=self,
                        trigger=GuardianAccessReview.Trigger.PLACEMENT_ENDED,
                        enrollment=current,
                        decisions=access_decisions,
                        actor=actor,
                        note=access_note,
                    )
                    AcademicEnrollment.objects.filter(pk=current.pk).update(
                        status=AcademicEnrollment.Status.COMPLETED,
                        end_date=start_date - datetime.timedelta(days=1),
                        updated_at=timezone.now(),
                    )
                enrollment = AcademicEnrollment(
                    student=self,
                    academic_year=academic_year,
                    class_grade=class_grade,
                    section=section,
                    start_date=start_date,
                )
                enrollment.full_clean()
                enrollment.save()
                return enrollment
        except IntegrityError:
            raise ValidationError(
                "This Student already has an active enrollment for this placement."
            ) from None

    def enrollment_on(self, on_date):
        """The AcademicEnrollment effective for this Student on `on_date`, or None.

        This is the single date-lookup path required by ADR 0006: date-sensitive
        records (such as attendance) use the placement effective on their
        business date, not the current one.
        """
        return AcademicEnrollment.objects.filter(student=self).effective_on(on_date).first()

    @property
    def current_enrollment(self):
        return self.enrollments.filter(status=AcademicEnrollment.Status.ACTIVE).first()

    def __str__(self):
        return self.full_name


class AcademicEnrollmentQuerySet(models.QuerySet):
    def effective_on(self, on_date):
        """Enrollments whose inclusive effective range contains `on_date`."""
        on_date = _as_date(on_date)
        return self.filter(start_date__lte=on_date).filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gte=on_date)
        )


class AcademicEnrollment(models.Model):
    """A Student's academic placement for a specific Academic Year.

    Connects Student, Academic Year, Class/Grade, Section, and a status
    (docs/DOMAIN_MODEL.md - Academic Enrollment). Placement is historical:
    changing placement completes the previous ACTIVE enrollment rather than
    overwriting it, and a Student may accumulate many COMPLETED enrollments
    (docs/adr/0001-academic-structure-and-enrollment-history.md,
    docs/adr/0003-phase-1-status-and-transition-rules.md). The database
    enforces at most one ACTIVE enrollment per Student.

    Effective dating (docs/adr/0006-academic-enrollment-effective-dating.md):
    `start_date` and `end_date` are business-effective dates, inclusive on
    both ends; `created_at`/`updated_at` are audit metadata only. An ACTIVE
    enrollment has no `end_date`; a COMPLETED enrollment has one, and it may
    not precede `start_date` (both enforced by database check constraints).
    Effective periods for one Student must not overlap; this is enforced in
    `clean()` and in the `Student.enroll` workflow, which locks the Student
    row while it changes placement.
    """

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        COMPLETED = "COMPLETED", "Completed"

    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="enrollments")
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.PROTECT, related_name="enrollments"
    )
    class_grade = models.ForeignKey(
        ClassGrade, on_delete=models.PROTECT, related_name="enrollments"
    )
    section = models.ForeignKey(Section, on_delete=models.PROTECT, related_name="enrollments")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    start_date = models.DateField(
        help_text="First date this placement is effective (inclusive)."
    )
    end_date = models.DateField(
        null=True,
        blank=True,
        help_text="Last date this placement is effective (inclusive). Empty while ACTIVE.",
    )
    roll_number = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text="Optional, entered by the school; never generated. Unique within the "
        "Academic Year and Section (ADR 0014).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = AcademicEnrollmentQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["student"],
                condition=models.Q(status="ACTIVE"),
                name="academicenrollment_one_active_per_student",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status="ACTIVE", end_date__isnull=True)
                    | models.Q(status="COMPLETED", end_date__isnull=False)
                ),
                name="academicenrollment_end_date_matches_status",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(end_date__isnull=True)
                    | models.Q(end_date__gte=models.F("start_date"))
                ),
                name="academicenrollment_end_date_not_before_start_date",
            ),
            models.UniqueConstraint(
                fields=["academic_year", "section", "roll_number"],
                condition=models.Q(roll_number__isnull=False),
                name="academicenrollment_roll_number_unique_in_year_section",
            ),
            models.CheckConstraint(
                condition=models.Q(roll_number__isnull=True) | models.Q(roll_number__gte=1),
                name="academicenrollment_roll_number_positive",
            ),
        ]

    def clean(self):
        super().clean()
        if (
            self.section_id
            and self.class_grade_id
            and self.section.class_grade_id != self.class_grade_id
        ):
            raise ValidationError(
                {"section": "Selected Section does not belong to the selected Class/Grade."}
            )

        start_date = _as_date(self.start_date)
        end_date = _as_date(self.end_date)
        if self.status == self.Status.ACTIVE and end_date is not None:
            raise ValidationError({"end_date": "An active enrollment cannot have an end date."})
        if self.status == self.Status.COMPLETED and end_date is None:
            raise ValidationError({"end_date": "A completed enrollment requires an end date."})
        if start_date is None:
            return
        if end_date is not None and end_date < start_date:
            raise ValidationError({"end_date": "End date cannot be before the start date."})
        if self.academic_year_id:
            year = self.academic_year
            if not (_as_date(year.start_date) <= start_date <= _as_date(year.end_date)):
                raise ValidationError(
                    {"start_date": "Start date must fall within the selected Academic Year."}
                )
        if self.student_id and self.overlapping_enrollments().exists():
            raise ValidationError(
                "This placement's effective dates overlap another enrollment for this Student."
            )

    def set_roll_number(self, value):
        """Record (or clear) the roll number entered by an administrator."""
        if value in ("", None):
            value = None
        else:
            value = int(value)
            if value < 1:
                raise ValidationError("A roll number must be a positive whole number.")
            if AcademicEnrollment.objects.filter(
                academic_year_id=self.academic_year_id, section_id=self.section_id,
                roll_number=value,
            ).exclude(pk=self.pk).exists():
                raise ValidationError(
                    "This roll number is already used in this Section for this Academic Year."
                )
        self.roll_number = value
        try:
            with transaction.atomic():
                AcademicEnrollment.objects.filter(pk=self.pk).update(
                    roll_number=value, updated_at=timezone.now()
                )
        except IntegrityError as error:
            raise ValidationError(
                "This roll number is already used in this Section for this Academic Year."
            ) from error

    def overlapping_enrollments(self):
        """Other enrollments of this Student whose effective range meets this one."""
        start_date = _as_date(self.start_date)
        end_date = _as_date(self.end_date)
        others = AcademicEnrollment.objects.filter(student_id=self.student_id).filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gte=start_date)
        )
        if end_date is not None:
            others = others.filter(start_date__lte=end_date)
        if self.pk is not None:
            others = others.exclude(pk=self.pk)
        return others

    def is_effective_on(self, on_date):
        on_date = _as_date(on_date)
        start_date = _as_date(self.start_date)
        end_date = _as_date(self.end_date)
        return start_date <= on_date and (end_date is None or on_date <= end_date)

    def __str__(self):
        return f"{self.student} - {self.academic_year} ({self.get_status_display()})"


class StudentStatusChange(models.Model):
    student = models.ForeignKey(
        Student, on_delete=models.PROTECT, related_name="status_changes"
    )
    previous_status = models.CharField(max_length=10, choices=Student.Status.choices)
    new_status = models.CharField(max_length=10, choices=Student.Status.choices)
    reason = models.TextField(blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]


class StudentGuardian(models.Model):
    """An explicit Student-Guardian association carrying a relationship type.

    Separate from ApplicantGuardian (docs/adr/0002-applicant-student-and-
    guardian-lifecycle.md). During progression the ApplicantGuardian
    relationships are copied here; the ApplicantGuardian history is left
    intact. A given Guardian appears at most once per Student.
    """

    student = models.ForeignKey(
        Student, on_delete=models.PROTECT, related_name="guardian_links"
    )
    guardian = models.ForeignKey(
        Guardian, on_delete=models.PROTECT, related_name="student_links"
    )
    relationship_type = models.CharField(max_length=20, choices=RelationshipType.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["student", "guardian"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "guardian"],
                name="studentguardian_unique_student_guardian",
            )
        ]

    def __str__(self):
        return f"{self.student} - {self.guardian} ({self.get_relationship_type_display()})"


class AttendanceStatus(models.TextChoices):
    """The Phase 2 attendance status vocabulary: exactly PRESENT and ABSENT.

    Frozen by docs/adr/0007-phase-2-attendance-model.md, which supersedes the
    four-value set of ADR 0005. LATE, EXCUSED, HALF_DAY and similar statuses
    require a new decision; the set is also enforced by database check
    constraints, so it cannot grow by silently adding enum members.
    """

    PRESENT = "PRESENT", "Present"
    ABSENT = "ABSENT", "Absent"


ATTENDANCE_STATUS_VALUES = ["PRESENT", "ABSENT"]


class AttendanceRegister(models.Model):
    """One attendance register for a Section on a single date.

    Per docs/adr/0007-phase-2-attendance-model.md, attendance is daily,
    year-aware and enrollment-scoped. A Section may have at most one register
    per date. Registers are historical records and are not hard deleted
    through normal operation.

    Lifecycle (ADR 0007): a register is created DRAFT and becomes SUBMITTED
    only through `submit()`, which requires a complete date-effective roster
    and records `submitted_by`/`submitted_at`. Database constraints require a
    DRAFT register to have no submission data and a SUBMITTED one to have
    both. Attendance semantics: no register = NOT TAKEN; DRAFT = started but
    not official; SUBMITTED = officially taken. A missing entry is never
    ABSENT.

    A register can only be opened for a past-or-today, instructional date in
    its Academic Year (school calendar, ADR 0008); submission re-checks both.

    `academic_year` and `class_grade` are stored alongside `section` and
    `date`; `clean()` rejects any combination in which they contradict each
    other, and the context cannot change once entries exist.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"

    CONTEXT_FIELDS = ("academic_year_id", "class_grade_id", "section_id", "date")

    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.PROTECT, related_name="attendance_registers"
    )
    class_grade = models.ForeignKey(
        ClassGrade, on_delete=models.PROTECT, related_name="attendance_registers"
    )
    section = models.ForeignKey(
        Section, on_delete=models.PROTECT, related_name="attendance_registers"
    )
    date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="submitted_attendance_registers",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "section"]
        constraints = [
            models.UniqueConstraint(
                fields=["section", "date"],
                name="attendanceregister_unique_section_date",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status="DRAFT",
                        submitted_by__isnull=True,
                        submitted_at__isnull=True,
                    )
                    | models.Q(
                        status="SUBMITTED",
                        submitted_by__isnull=False,
                        submitted_at__isnull=False,
                    )
                ),
                name="attendanceregister_submission_fields_match_status",
            ),
        ]

    class AttendanceState(models.TextChoices):
        NOT_TAKEN = "NOT_TAKEN", "Not taken"
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"

    @classmethod
    def attendance_state(cls, section, on_date):
        """NOT_TAKEN, DRAFT or SUBMITTED for a Section on a date."""
        status = (
            cls.objects.filter(section=section, date=_as_date(on_date))
            .values_list("status", flat=True)
            .first()
        )
        if status is None:
            return cls.AttendanceState.NOT_TAKEN
        return cls.AttendanceState(status)

    @property
    def is_submitted(self):
        return self.status == self.Status.SUBMITTED

    def clean(self):
        super().clean()
        if self.pk is None and self.status != self.Status.DRAFT:
            raise ValidationError("A new attendance register always starts as a draft.")
        if self.pk is None and self.date and self.academic_year_id:
            on_date = _as_date(self.date)
            if on_date > business_today():
                raise ValidationError(
                    {"date": "Attendance cannot be recorded for a future date."}
                )
            if self.academic_year.contains(on_date) and not (
                self.academic_year.is_instructional_day(on_date)
            ):
                raise ValidationError(
                    {"date": "This date is not an instructional day in the school calendar."}
                )
        if (
            self.section_id
            and self.class_grade_id
            and self.section.class_grade_id != self.class_grade_id
        ):
            raise ValidationError(
                {"section": "Selected Section does not belong to the selected Class/Grade."}
            )
        if self.date and self.academic_year_id and not self.academic_year.contains(self.date):
            raise ValidationError(
                {"date": "Attendance date must fall within the selected Academic Year."}
            )
        if self.pk is not None:
            original = AttendanceRegister.objects.filter(pk=self.pk).values(
                *self.CONTEXT_FIELDS
            ).first()
            if original is not None and self.entries.exists():
                current = {
                    "academic_year_id": self.academic_year_id,
                    "class_grade_id": self.class_grade_id,
                    "section_id": self.section_id,
                    "date": _as_date(self.date),
                }
                if current != original:
                    raise ValidationError(
                        "This register already has attendance entries; its Academic Year, "
                        "Class/Grade, Section and date cannot change."
                    )

    def eligible_enrollments(self):
        """The date-effective roster for this register.

        Enrollments in the register's Academic Year, Class/Grade and Section
        whose effective range contains the register date (ADR 0006). A later
        transfer never removes a Student from an earlier date's roster, and a
        Student who joins later is not on it.
        """
        return (
            AcademicEnrollment.objects.effective_on(self.date)
            .filter(
                academic_year_id=self.academic_year_id,
                class_grade_id=self.class_grade_id,
                section_id=self.section_id,
            )
            .select_related("student")
            .order_by("student__full_name", "pk")
        )

    def unmarked_enrollments(self):
        """Roster enrollments that do not yet have an entry in this register."""
        return self.eligible_enrollments().exclude(attendance_entries__register=self)

    def ineligible_entries(self):
        """Entries whose enrollment is not on this register's effective roster."""
        return self.entries.exclude(
            academic_enrollment__in=self.eligible_enrollments().values("pk")
        )

    def _lock(self):
        """Re-read this register under a row lock; return its current status."""
        return (
            AttendanceRegister.objects.select_for_update()
            .filter(pk=self.pk)
            .values_list("status", flat=True)
            .get()
        )

    def submit(self, *, actor):
        """Officially submit attendance (DRAFT -> SUBMITTED).

        Rejected without any change when: the register is not DRAFT; there is
        no acting user; the date is in the future or not instructional; the
        effective roster is empty (there is nothing to attest); any roster
        enrollment lacks an entry; or any entry belongs to an enrollment not on
        the effective roster. On success, records the submitting user and time.
        """
        if actor is None or not getattr(actor, "pk", None):
            raise ValidationError("A submitting user is required.")
        with transaction.atomic():
            if self._lock() != self.Status.DRAFT:
                raise ValidationError("This register has already been submitted.")
            on_date = _as_date(self.date)
            if on_date > business_today():
                raise ValidationError("Attendance cannot be submitted for a future date.")
            if not self.academic_year.is_instructional_day(on_date):
                raise ValidationError(
                    "This date is not an instructional day in the school calendar."
                )
            if not self.eligible_enrollments().exists():
                raise ValidationError(
                    "No Students are enrolled in this Section on this date; "
                    "there is no attendance to submit."
                )
            if self.ineligible_entries().exists():
                raise ValidationError(
                    "This register contains entries for Students not enrolled in this "
                    "Section on this date."
                )
            unmarked = self.unmarked_enrollments().count()
            if unmarked:
                raise ValidationError(
                    f"Attendance is incomplete: {unmarked} Student(s) still need a "
                    "Present or Absent status."
                )
            self.status = self.Status.SUBMITTED
            self.submitted_by = actor
            self.submitted_at = timezone.now()
            self.save(update_fields=["status", "submitted_by", "submitted_at", "updated_at"])
            from core import notification_producers

            notification_producers.absence_alerts_for_register(self)

    def capture(self, *, enrollment, status, absence_note=""):
        """Capture an initial attendance status for an enrolled Student.

        The enrollment must belong to the register's Academic Year,
        Class/Grade and Section and be effective on the register date, so a
        historical enrollment remains valid for its own dates after a later
        transfer. An unknown status, an absence note on a PRESENT entry, a
        mismatched or non-effective enrollment, or a duplicate entry is
        rejected without leaving a partial record. Correcting a captured
        status goes through `AttendanceEntry.record_status_change` instead.
        """
        entry = AttendanceEntry(
            register=self,
            academic_enrollment=enrollment,
            status=status,
            absence_note=(absence_note or "").strip(),
        )
        entry.full_clean(validate_constraints=False)
        if _as_date(self.date) > business_today():
            raise ValidationError("Attendance cannot be recorded for a future date.")
        try:
            with transaction.atomic():
                if self._lock() != self.Status.DRAFT:
                    raise ValidationError(
                        "This register has been submitted; change attendance through a "
                        "correction."
                    )
                entry.save()
        except IntegrityError:
            raise ValidationError(
                "This Student already has an attendance entry for this register."
            ) from None
        return entry

    def save_draft_entry(self, *, enrollment, status, absence_note=""):
        """Create or update one Student's entry while the register is DRAFT.

        DRAFT attendance is work in progress, so changing it is a normal edit
        and creates no AttendanceCorrection (docs/PHASE_2_RECONCILIATION_PLAN.md
        Gate 6). A SUBMITTED register is changed only through
        `AttendanceEntry.record_status_change`. Returns the entry.
        """
        absence_note = (absence_note or "").strip()
        existing = self.entries.filter(academic_enrollment=enrollment).first()
        if existing is None:
            return self.capture(enrollment=enrollment, status=status, absence_note=absence_note)
        existing.status = status
        existing.absence_note = absence_note
        existing.full_clean(validate_constraints=False)
        with transaction.atomic():
            if self._lock() != self.Status.DRAFT:
                raise ValidationError(
                    "This register has been submitted; change attendance through a "
                    "correction."
                )
            existing.save(update_fields=["status", "absence_note", "updated_at"])
        return existing

    def __str__(self):
        return f"{self.section} - {self.date}"


class AttendanceEntry(models.Model):
    """One Student's attendance status within a register.

    Historical record (docs/adr/0007-phase-2-attendance-model.md): the current
    `status` is the accepted value, and every later change is stored as an
    AttendanceCorrection carrying the previous value, the actor, the
    timestamp and a reason. Entries are not hard deleted.

    The entry's enrollment must match the register's Academic Year,
    Class/Grade and Section and be effective on the register date (ADR 0006).
    An ABSENT entry may carry an optional `absence_note`; a PRESENT entry may
    not (also enforced by a database check constraint).
    """

    register = models.ForeignKey(
        AttendanceRegister, on_delete=models.PROTECT, related_name="entries"
    )
    academic_enrollment = models.ForeignKey(
        AcademicEnrollment, on_delete=models.PROTECT, related_name="attendance_entries"
    )
    status = models.CharField(
        max_length=10, choices=AttendanceStatus.choices, default=AttendanceStatus.PRESENT
    )
    absence_note = models.TextField(
        blank=True, default="", help_text="Optional note for an ABSENT entry."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["register__date", "academic_enrollment__student__full_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["register", "academic_enrollment"],
                name="attendanceentry_unique_register_enrollment",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=ATTENDANCE_STATUS_VALUES),
                name="attendanceentry_status_present_or_absent",
            ),
            models.CheckConstraint(
                condition=models.Q(status="ABSENT") | models.Q(absence_note=""),
                name="attendanceentry_absence_note_only_when_absent",
            ),
        ]

    def clean(self):
        super().clean()
        if self.status != AttendanceStatus.ABSENT and (self.absence_note or "").strip():
            raise ValidationError({"absence_note": "Only an ABSENT entry may have a note."})
        if self.register_id and self.academic_enrollment_id:
            enrollment = self.academic_enrollment
            register = self.register
            if (
                enrollment.academic_year_id != register.academic_year_id
                or enrollment.class_grade_id != register.class_grade_id
                or enrollment.section_id != register.section_id
            ):
                raise ValidationError(
                    {
                        "academic_enrollment": (
                            "The Student is not enrolled in this register's "
                            "Academic Year, Class/Grade and Section."
                        )
                    }
                )
            if not enrollment.is_effective_on(register.date):
                raise ValidationError(
                    {
                        "academic_enrollment": (
                            "The Student's enrollment is not effective on this register's date."
                        )
                    }
                )

    def record_status_change(self, new_status, *, actor, reason, absence_note=""):
        """Correct the accepted status of SUBMITTED attendance (Gate 6).

        Only entries in a SUBMITTED register are corrected; DRAFT attendance is
        edited normally through `AttendanceRegister.save_draft_entry`. An
        unknown status, a no-op change, a missing reason or actor, or an
        absence note on a PRESENT correction is rejected without changing
        anything. A valid correction writes an immutable AttendanceCorrection
        (previous/new status and note, actor, timestamp, reason) and then
        updates the accepted status and note, so earlier values are never
        lost. Only status and note change: the register and enrollment context
        are untouched. Changing to PRESENT clears the absence note.
        """
        if new_status not in AttendanceStatus.values:
            raise ValidationError("Invalid attendance status.")
        if new_status == self.status:
            raise ValidationError("Attendance already has this status.")
        reason = (reason or "").strip()
        if not reason:
            raise ValidationError("A reason is required when correcting attendance.")
        if actor is None or not getattr(actor, "pk", None):
            raise ValidationError("A correcting user is required.")
        absence_note = (absence_note or "").strip()
        if absence_note and new_status != AttendanceStatus.ABSENT:
            raise ValidationError("Only an absent Student can have a note.")

        with transaction.atomic():
            register_status = (
                AttendanceRegister.objects.select_for_update()
                .filter(pk=self.register_id)
                .values_list("status", flat=True)
                .get()
            )
            if register_status != AttendanceRegister.Status.SUBMITTED:
                raise ValidationError(
                    "This register is still a draft; edit its attendance directly instead "
                    "of recording a correction."
                )
            AttendanceCorrection.objects.create(
                entry=self,
                previous_status=self.status,
                new_status=new_status,
                previous_absence_note=self.absence_note,
                new_absence_note=absence_note,
                reason=reason,
                corrected_by=actor,
            )
            self.status = new_status
            self.absence_note = absence_note
            self.save(update_fields=["status", "absence_note", "updated_at"])
            from core import notification_producers

            notification_producers.absence_corrected(self, actor=actor)

    @property
    def student(self):
        return self.academic_enrollment.student

    def __str__(self):
        return f"{self.academic_enrollment.student} - {self.register.date}"


class AttendanceCorrection(models.Model):
    """An immutable record of a correction to a captured attendance status.

    Per docs/adr/0007-phase-2-attendance-model.md, corrections preserve
    history rather than overwriting it: each row captures the previous status,
    the new status, the previous and new absence note, the correcting actor,
    the timestamp, and the reason. Both statuses are limited to PRESENT/ABSENT
    by database check constraints. Rows are never edited or deleted through
    the application, and the PROTECT relations keep them attached.
    """

    entry = models.ForeignKey(
        AttendanceEntry, on_delete=models.PROTECT, related_name="corrections"
    )
    previous_status = models.CharField(max_length=10, choices=AttendanceStatus.choices)
    new_status = models.CharField(max_length=10, choices=AttendanceStatus.choices)
    previous_absence_note = models.TextField(blank=True, default="")
    new_absence_note = models.TextField(blank=True, default="")
    reason = models.TextField()
    corrected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="attendance_corrections"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(previous_status__in=ATTENDANCE_STATUS_VALUES)
                    & models.Q(new_status__in=ATTENDANCE_STATUS_VALUES)
                ),
                name="attendancecorrection_statuses_present_or_absent",
            ),
        ]

    def __str__(self):
        return f"{self.entry} {self.previous_status} -> {self.new_status}"


# ---------------------------------------------------------------------------
# Phase 4 - academic structures for assessments (ADR 0009, Gate 1)
# ---------------------------------------------------------------------------


class Subject(models.Model):
    """A long-lived academic subject identity (ADR 0009).

    Not tied to a Grade or Academic Year; offerings place it in a year/grade.
    Renaming keeps every historical reference intact because history points
    at this row, not at the name. Retire a subject by deactivating it.
    """

    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["code"],
                condition=~models.Q(code=""),
                name="subject_unique_code_when_set",
            )
        ]

    def clean(self):
        super().clean()
        self.name = (self.name or "").strip()
        self.code = (self.code or "").strip().upper()

    def __str__(self):
        return f"{self.name} ({self.code})" if self.code else self.name


class AcademicTerm(models.Model):
    """An explicitly ordered term inside one Academic Year (ADR 0009).

    Dates fall inside the year, end after start, and terms of one year never
    overlap. `display_order` is explicit, never inferred from the name.
    """

    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.PROTECT, related_name="terms"
    )
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    display_order = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["academic_year", "display_order"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gt=models.F("start_date")),
                name="academicterm_end_date_after_start_date",
            ),
            models.UniqueConstraint(
                fields=["academic_year", "name"], name="academicterm_unique_name_per_year"
            ),
            models.UniqueConstraint(
                fields=["academic_year", "display_order"],
                name="academicterm_unique_order_per_year",
            ),
        ]

    def clean(self):
        super().clean()
        start, end = _as_date(self.start_date), _as_date(self.end_date)
        if start is None or end is None:
            return
        if end <= start:
            raise ValidationError({"end_date": "End date must be after the start date."})
        if not self.academic_year_id:
            return
        year = self.academic_year
        if not (year.contains(start) and year.contains(end)):
            raise ValidationError("Term dates must fall inside the Academic Year.")
        overlapping = AcademicTerm.objects.filter(
            academic_year_id=self.academic_year_id, start_date__lte=end, end_date__gte=start
        )
        if self.pk is not None:
            overlapping = overlapping.exclude(pk=self.pk)
        clash = overlapping.first()
        if clash is not None:
            raise ValidationError(
                f"These dates overlap {clash.name} ({clash.start_date} to {clash.end_date})."
            )
        self._check_dates_against_assessments(start, end)

    def _check_dates_against_assessments(self, start, end):
        """Keep Term dates from moving underneath assessments and finalized results.

        While nothing in the Term is finalized the dates may change, but every
        existing Assessment must stay inside the new range. Once any Assessment
        is finalized the date boundaries are frozen: Term rosters, placement at
        Term end, remarks, report cards and publications all read them.
        """
        if self.pk is None:
            return
        original = AcademicTerm.objects.filter(pk=self.pk).values("start_date", "end_date").first()
        if original is None or (original["start_date"], original["end_date"]) == (start, end):
            return
        assessments = Assessment.objects.filter(term_id=self.pk)
        if assessments.filter(status=Assessment.Status.FINALIZED).exists():
            raise ValidationError(
                "Results in this Term are finalized, so its start and end dates can "
                "no longer change."
            )
        outside = assessments.exclude(assessment_date__range=(start, end)).order_by(
            "assessment_date"
        )
        if outside.exists():
            names = ", ".join(
                f"{a.name} ({a.assessment_date:%d %B %Y})" for a in outside[:5]
            )
            more = outside.count() - 5
            raise ValidationError(
                "These dates would leave existing assessments outside the Term: "
                f"{names}{f' and {more} more' if more > 0 else ''}."
            )

    def contains(self, on_date):
        on_date = _as_date(on_date)
        return _as_date(self.start_date) <= on_date <= _as_date(self.end_date)

    def enrollment_for(self, student):
        """The Student's placement for this Term (Gate 8).

        The enrollment effective on the Term's last day; if the Student left
        before then, their last enrollment of this Academic Year that was
        effective at some point during the Term.
        """
        in_year = AcademicEnrollment.objects.filter(
            student=student, academic_year_id=self.academic_year_id
        )
        on_last_day = in_year.effective_on(self.end_date).first()
        if on_last_day is not None:
            return on_last_day
        return (
            in_year.filter(start_date__lte=self.end_date)
            .filter(models.Q(end_date__isnull=True) | models.Q(end_date__gte=self.start_date))
            .order_by("-start_date")
            .first()
        )

    def section_roster(self, section):
        """Students whose Term placement (see enrollment_for) is in `section`."""
        candidates = (
            AcademicEnrollment.objects.filter(
                academic_year_id=self.academic_year_id,
                section=section,
                start_date__lte=self.end_date,
            )
            .filter(models.Q(end_date__isnull=True) | models.Q(end_date__gte=self.start_date))
            .select_related("student")
            .order_by("student__full_name", "pk")
        )
        students = []
        for enrollment in candidates:
            student = enrollment.student
            if student not in students:
                placement = self.enrollment_for(student)
                if placement is not None and placement.section_id == section.pk:
                    students.append(student)
        return students

    def section_rosters(self, sections):
        """`section_roster` for several Sections at once, in two queries.

        Returns {section_id: [Student, ...]} using exactly the placement rule
        of `enrollment_for`, ordered by Student name.
        """
        section_ids = {section.pk for section in sections}
        candidate_ids = (
            AcademicEnrollment.objects.filter(
                academic_year_id=self.academic_year_id,
                section_id__in=section_ids,
                start_date__lte=self.end_date,
            )
            .filter(models.Q(end_date__isnull=True) | models.Q(end_date__gte=self.start_date))
            .values("student_id")
        )
        by_student = {}
        for enrollment in (
            AcademicEnrollment.objects.filter(
                academic_year_id=self.academic_year_id, student_id__in=candidate_ids
            )
            .select_related("student")
            .order_by("-start_date")
        ):
            by_student.setdefault(enrollment.student_id, []).append(enrollment)
        end, start = _as_date(self.end_date), _as_date(self.start_date)
        rosters = {section_id: [] for section_id in section_ids}
        for enrollments in by_student.values():
            placement = next((e for e in enrollments if e.is_effective_on(end)), None)
            if placement is None:
                placement = next(
                    (
                        e for e in enrollments
                        if _as_date(e.start_date) <= end
                        and (e.end_date is None or _as_date(e.end_date) >= start)
                    ),
                    None,
                )
            if placement is not None and placement.section_id in rosters:
                rosters[placement.section_id].append(placement.student)
        for students in rosters.values():
            students.sort(key=lambda student: (student.full_name, student.pk))
        return rosters

    def __str__(self):
        return f"{self.academic_year} - {self.name}"


class AcademicSubjectOfferingQuerySet(models.QuerySet):
    def for_section(self, academic_year, section):
        """Offerings that apply to `section` in `academic_year`.

        An offering applies when it is for the Section's Class/Grade in that
        year and either lists no Sections (all Sections) or lists this one.
        """
        return (
            self.filter(academic_year=academic_year, class_grade_id=section.class_grade_id)
            .filter(
                models.Q(section_links__isnull=True) | models.Q(section_links__section=section)
            )
            .distinct()
        )

    def for_term_section(self, term, section):
        return self.for_section(term.academic_year, section)


class AcademicSubjectOffering(models.Model):
    """A Subject taught to a Class/Grade in one Academic Year (ADR 0009).

    Section scope: with no linked Sections the offering applies to every
    Section of the Grade; otherwise only to the linked Sections, each of which
    must belong to the offering's Grade. Change the scope with
    `set_sections()`, which validates it.
    """

    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.PROTECT, related_name="subject_offerings"
    )
    class_grade = models.ForeignKey(
        ClassGrade, on_delete=models.PROTECT, related_name="subject_offerings"
    )
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="offerings")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = AcademicSubjectOfferingQuerySet.as_manager()

    class Meta:
        ordering = ["academic_year", "class_grade", "subject"]
        constraints = [
            models.UniqueConstraint(
                fields=["academic_year", "class_grade", "subject"],
                name="subjectoffering_unique_year_grade_subject",
            )
        ]

    def clean(self):
        super().clean()
        if self.pk is None and self.subject_id and not self.subject.is_active:
            raise ValidationError({"subject": "An inactive Subject cannot be offered."})

    @property
    def sections(self):
        return Section.objects.filter(subject_offering_links__offering=self)

    @property
    def applies_to_all_sections(self):
        return not self.section_links.exists()

    def set_sections(self, sections):
        """Replace the Section scope. An empty iterable means all Sections.

        A Section that has an assigned teacher cannot be dropped from a
        restricted scope (remove the assignment first).
        """
        sections = list(sections)
        wrong = [s for s in sections if s.class_grade_id != self.class_grade_id]
        if wrong:
            raise ValidationError(
                "Every Section must belong to the offering's Class/Grade "
                f"({self.class_grade}): {', '.join(str(s) for s in wrong)}."
            )
        if sections:
            dropped = self.teacher_assignments.exclude(section__in=sections).select_related(
                "section"
            )
            if dropped.exists():
                names = ", ".join(sorted({a.section.name for a in dropped}))
                raise ValidationError(
                    f"Section(s) {names} have an assigned teacher; remove the assignment "
                    "before taking them out of this offering."
                )
        with transaction.atomic():
            self.section_links.exclude(section__in=sections).delete()
            existing = set(self.section_links.values_list("section_id", flat=True))
            AcademicSubjectOfferingSection.objects.bulk_create(
                AcademicSubjectOfferingSection(offering=self, section=section)
                for section in sections
                if section.pk not in existing
            )

    def applies_to(self, section):
        if section.class_grade_id != self.class_grade_id:
            return False
        links = set(self.section_links.values_list("section_id", flat=True))
        return not links or section.pk in links

    def __str__(self):
        return f"{self.academic_year} - {self.class_grade} - {self.subject.name}"


class AcademicSubjectOfferingSection(models.Model):
    """One Section an offering is limited to (see AcademicSubjectOffering)."""

    offering = models.ForeignKey(
        AcademicSubjectOffering, on_delete=models.CASCADE, related_name="section_links"
    )
    section = models.ForeignKey(
        Section, on_delete=models.PROTECT, related_name="subject_offering_links"
    )

    class Meta:
        ordering = ["section"]
        constraints = [
            models.UniqueConstraint(
                fields=["offering", "section"], name="subjectofferingsection_unique"
            )
        ]

    def clean(self):
        super().clean()
        if (
            self.offering_id
            and self.section_id
            and self.section.class_grade_id != self.offering.class_grade_id
        ):
            raise ValidationError(
                {"section": "The Section must belong to the offering's Class/Grade."}
            )

    def __str__(self):
        return f"{self.offering} - {self.section.name}"


TEACHERS_GROUP_NAME = "Teachers"


class AssessmentTeacherAssignmentQuerySet(models.QuerySet):
    def effective_on(self, on_date):
        """Assignments whose inclusive date range contains `on_date`.

        An open-ended assignment runs to the end of its offering's Academic
        Year and never carries into the next one (ADR 0018 D1).
        """
        on_date = _as_date(on_date)
        return self.filter(start_date__lte=on_date).filter(
            models.Q(end_date__gte=on_date)
            | models.Q(end_date__isnull=True, offering__academic_year__end_date__gte=on_date)
        )

    def delete(self):
        """Bulk deletes obey the same rule as single ones (ADR 0018 D5)."""
        rows = list(self.select_related("offering__academic_year"))
        if any(row.is_historically_relevant for row in rows):
            raise ValidationError(
                "Teacher assignments that have taken effect or have dependent records "
                "cannot be deleted; end them instead."
            )
        return super().delete()


class AssessmentTeacherAssignment(models.Model):
    """Which teacher enters results for one Subject offering in one Section (ADR 0010).

    A teacher is an active login in the "Teachers" group; school-domain records
    are never the login itself (ADR 0004). Per ADR 0018 an assignment is
    effective-dated like a class teacher assignment (ADR 0011): at most one is
    effective for an offering + Section on any date, a change of teacher ends
    the current row and starts a new one, and a row that has taken effect is
    ended, never deleted. Shared multi-teacher ownership is outside scope.
    This is not a timetable, workload, substitution or HR record.
    """

    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="assessment_assignments",
    )
    offering = models.ForeignKey(
        AcademicSubjectOffering, on_delete=models.PROTECT, related_name="teacher_assignments"
    )
    section = models.ForeignKey(
        Section, on_delete=models.PROTECT, related_name="teacher_assignments"
    )
    start_date = models.DateField(help_text="First date this assignment is effective.")
    end_date = models.DateField(
        null=True, blank=True, help_text="Last date this assignment is effective (inclusive)."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = AssessmentTeacherAssignmentQuerySet.as_manager()

    class Meta:
        ordering = ["offering", "section", "start_date"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(end_date__isnull=True)
                    | models.Q(end_date__gte=models.F("start_date"))
                ),
                name="assessmentteacherassignment_end_not_before_start",
            ),
            models.UniqueConstraint(
                fields=["offering", "section", "start_date"],
                name="assessmentteacherassignment_unique_offering_section_start",
            ),
        ]

    # --- validation ---

    def clean(self):
        super().clean()
        # Only new rows need an active teacher, so a departed teacher's row can
        # still be ended (ADR 0018 D9).
        if self.pk is None and self.teacher_id:
            teacher = self.teacher
            if not teacher.is_active or not teacher.groups.filter(
                name=TEACHERS_GROUP_NAME
            ).exists():
                raise ValidationError(
                    {"teacher": "Choose an active login in the Teachers group."}
                )
        if self.offering_id and self.section_id and not self.offering.applies_to(self.section):
            raise ValidationError(
                {"section": "This Section does not take this Subject offering."}
            )
        start_date = _as_date(self.start_date)
        end_date = _as_date(self.end_date)
        if start_date is None:
            return
        if end_date is not None and end_date < start_date:
            raise ValidationError({"end_date": "End date cannot be before the start date."})
        if self.offering_id:
            year = self.offering.academic_year
            if not year.contains(start_date):
                raise ValidationError(
                    {"start_date": "Start date must fall within the Academic Year."}
                )
            if end_date is not None and not year.contains(end_date):
                raise ValidationError(
                    {"end_date": "End date must fall within the Academic Year."}
                )
        if self.offering_id and self.section_id and self.overlapping().exists():
            raise ValidationError(
                "These dates overlap another teacher assignment for this Subject and Section."
            )

    def overlapping(self):
        """Other assignments for this offering + Section whose range meets this one."""
        start_date = _as_date(self.start_date)
        end_date = _as_date(self.end_date)
        others = AssessmentTeacherAssignment.objects.filter(
            offering_id=self.offering_id, section_id=self.section_id
        ).filter(models.Q(end_date__isnull=True) | models.Q(end_date__gte=start_date))
        if end_date is not None:
            others = others.filter(start_date__lte=end_date)
        if self.pk is not None:
            others = others.exclude(pk=self.pk)
        return others

    # --- state ---

    def is_effective_on(self, on_date):
        on_date = _as_date(on_date)
        return _as_date(self.start_date) <= on_date <= self.last_effective_date

    @property
    def last_effective_date(self):
        return _as_date(self.end_date) or _as_date(self.offering.academic_year.end_date)

    def dependent_results(self):
        """Results this teacher entered for this offering + Section inside the range."""
        return StudentResult.objects.filter(
            assessment__offering_id=self.offering_id,
            assessment__section_id=self.section_id,
            entered_by_id=self.teacher_id,
            assessment__assessment_date__gte=self.start_date,
            assessment__assessment_date__lte=self.last_effective_date,
        )

    def has_dependents(self):
        return self.dependent_results().exists()

    @property
    def is_historically_relevant(self):
        """Started, or depended on: end it, never delete it (ADR 0018 D5).

        A row is historical as soon as its start date arrives, even with no
        results at all.
        """
        return _as_date(self.start_date) <= business_today() or self.has_dependents()

    # --- workflows ---

    @classmethod
    def _lock_offering(cls, offering):
        AcademicSubjectOffering.objects.select_for_update().filter(pk=offering.pk).get()

    @classmethod
    def assign(cls, *, teacher, offering, section, start_date):
        """Make `teacher` the teacher of `offering` + `section` from `start_date`.

        If another assignment is effective on the day before `start_date` and
        is open-ended or runs past it, it is ended the day before (a
        hand-over). Any other overlap is rejected; nothing is overwritten.
        """
        start_date = _as_date(start_date)
        with transaction.atomic():
            cls._lock_offering(offering)
            current = (
                cls.objects.filter(offering=offering, section=section, start_date__lt=start_date)
                .filter(models.Q(end_date__isnull=True) | models.Q(end_date__gte=start_date))
                .first()
            )
            if current is not None:
                current.end(start_date - datetime.timedelta(days=1), _locked=True)
            assignment = cls(
                teacher=teacher, offering=offering, section=section, start_date=start_date
            )
            assignment.full_clean()
            assignment.save()
            return assignment

    def end(self, end_date, *, _locked=False):
        """End this assignment on `end_date` (inclusive); history is kept."""
        end_date = _as_date(end_date)
        with transaction.atomic():
            if not _locked:
                self._lock_offering(self.offering)
            self.refresh_from_db()
            if self.end_date is not None and end_date > _as_date(self.end_date):
                raise ValidationError("An assignment can only be ended earlier, not extended.")
            if self.dependent_results().filter(assessment__assessment_date__gt=end_date).exists():
                raise ValidationError(
                    "This teacher entered results for this Subject and Section after that "
                    "date; choose a later end date."
                )
            self.end_date = end_date
            self.full_clean()
            self.save(update_fields=["end_date", "updated_at"])

    def delete(self, *args, **kwargs):
        if self.is_historically_relevant:
            raise ValidationError(
                "This teacher assignment has taken effect or has dependent records; "
                "end it instead of deleting it."
            )
        return super().delete(*args, **kwargs)

    def __str__(self):
        until = f" to {self.end_date}" if self.end_date else ""
        return (
            f"{self.teacher} - {self.offering} - {self.section.name} "
            f"from {self.start_date}{until}"
        )


# ---------------------------------------------------------------------------
# Phase 5 Gate 1 - class teacher assignment (ADR 0011)
# ---------------------------------------------------------------------------


class SectionClassTeacherQuerySet(models.QuerySet):
    def effective_on(self, on_date):
        """Assignments whose inclusive date range contains `on_date`.

        An open-ended assignment runs to the end of its own Academic Year;
        Sections are year-agnostic, so it never carries into the next year.
        """
        on_date = _as_date(on_date)
        return self.filter(start_date__lte=on_date).filter(
            models.Q(end_date__gte=on_date)
            | models.Q(end_date__isnull=True, academic_year__end_date__gte=on_date)
        )

    def delete(self):
        """Bulk deletes obey the same rule as single ones (ADR 0011 D3)."""
        rows = list(self.select_related("academic_year"))
        if any(row.is_historically_relevant for row in rows):
            raise ValidationError(
                "Class teacher assignments that have taken effect or have dependent records "
                "cannot be deleted; end them instead."
            )
        return super().delete()


class SectionClassTeacher(models.Model):
    """The class teacher of one Section for a dated range in an Academic Year.

    Per ADR 0011: independent of subject teaching (D1); at most one class
    teacher is effective for a Section on any date (D2); assignments are
    dated and never overwritten - a change of class teacher ends the current
    row and starts a new one (D3). Once a row has taken effect, or once any
    record depends on it, normal workflows end it and never delete it; only a
    not-yet-effective row without dependents may be deleted. Losing teacher
    status removes access but never changes these rows (D14).
    """

    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="class_teacher_assignments",
    )
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.PROTECT, related_name="class_teacher_assignments"
    )
    section = models.ForeignKey(
        Section, on_delete=models.PROTECT, related_name="class_teacher_assignments"
    )
    start_date = models.DateField(help_text="First date this assignment is effective.")
    end_date = models.DateField(
        null=True, blank=True, help_text="Last date this assignment is effective (inclusive)."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = SectionClassTeacherQuerySet.as_manager()

    class Meta:
        ordering = ["section", "start_date"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(end_date__isnull=True)
                    | models.Q(end_date__gte=models.F("start_date"))
                ),
                name="sectionclassteacher_end_not_before_start",
            ),
            models.UniqueConstraint(
                fields=["section", "start_date"],
                name="sectionclassteacher_unique_section_start",
            ),
        ]

    # --- validation ---

    def clean(self):
        super().clean()
        if self.pk is None and self.teacher_id:
            teacher = self.teacher
            if not teacher.is_active or not teacher.groups.filter(
                name=TEACHERS_GROUP_NAME
            ).exists():
                raise ValidationError(
                    {"teacher": "Choose an active login in the Teachers group."}
                )
        start_date = _as_date(self.start_date)
        end_date = _as_date(self.end_date)
        if start_date is None:
            return
        if end_date is not None and end_date < start_date:
            raise ValidationError({"end_date": "End date cannot be before the start date."})
        if self.academic_year_id:
            year = self.academic_year
            if not year.contains(start_date):
                raise ValidationError(
                    {"start_date": "Start date must fall within the Academic Year."}
                )
            if end_date is not None and not year.contains(end_date):
                raise ValidationError(
                    {"end_date": "End date must fall within the Academic Year."}
                )
        if self.section_id and self.overlapping().exists():
            raise ValidationError(
                "These dates overlap another class teacher assignment for this Section."
            )

    def overlapping(self):
        """Other assignments for this Section in this year whose range meets this one."""
        start_date = _as_date(self.start_date)
        end_date = _as_date(self.end_date)
        others = SectionClassTeacher.objects.filter(
            section_id=self.section_id, academic_year_id=self.academic_year_id
        ).filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gte=start_date)
        )
        if end_date is not None:
            others = others.filter(start_date__lte=end_date)
        if self.pk is not None:
            others = others.exclude(pk=self.pk)
        return others

    # --- state ---

    def is_effective_on(self, on_date):
        on_date = _as_date(on_date)
        return _as_date(self.start_date) <= on_date <= self.last_effective_date

    @property
    def last_effective_date(self):
        return _as_date(self.end_date) or _as_date(self.academic_year.end_date)

    def dependent_registers(self):
        """Registers this teacher submitted for this Section inside the range."""
        return AttendanceRegister.objects.filter(
            section_id=self.section_id,
            submitted_by_id=self.teacher_id,
            date__gte=self.start_date,
            date__lte=self.last_effective_date,
        )

    def has_dependents(self):
        return self.dependent_registers().exists()

    @property
    def is_historically_relevant(self):
        """Taken effect, or depended on: end it, never delete it (ADR 0011 D3)."""
        return _as_date(self.start_date) <= business_today() or self.has_dependents()

    # --- workflows ---

    @classmethod
    def _lock_section(cls, section):
        Section.objects.select_for_update().filter(pk=section.pk).get()

    @classmethod
    def assign(cls, *, teacher, academic_year, section, start_date):
        """Make `teacher` class teacher of `section` from `start_date`.

        If another assignment is effective on the day before `start_date` and
        is open-ended or runs past it, that assignment is ended the day before
        (a hand-over). Any other overlap is rejected; nothing is overwritten.
        """
        start_date = _as_date(start_date)
        with transaction.atomic():
            cls._lock_section(section)
            current = (
                cls.objects.filter(
                    section=section, academic_year=academic_year, start_date__lt=start_date
                )
                .filter(models.Q(end_date__isnull=True) | models.Q(end_date__gte=start_date))
                .first()
            )
            if current is not None:
                current.end(start_date - datetime.timedelta(days=1), _locked=True)
            assignment = cls(
                teacher=teacher, academic_year=academic_year, section=section,
                start_date=start_date,
            )
            assignment.full_clean()
            assignment.save()
            return assignment

    def end(self, end_date, *, _locked=False):
        """End this assignment on `end_date` (inclusive); history is kept."""
        end_date = _as_date(end_date)
        with transaction.atomic():
            if not _locked:
                self._lock_section(self.section)
            self.refresh_from_db()
            if self.end_date is not None and end_date > _as_date(self.end_date):
                raise ValidationError("An assignment can only be ended earlier, not extended.")
            later = self.dependent_registers().filter(date__gt=end_date)
            if later.exists():
                raise ValidationError(
                    "This teacher submitted attendance for this Section after that date; "
                    "choose a later end date."
                )
            self.end_date = end_date
            self.full_clean()
            self.save(update_fields=["end_date", "updated_at"])

    def delete(self, *args, **kwargs):
        if self.is_historically_relevant:
            raise ValidationError(
                "This class teacher assignment has taken effect or has dependent records; "
                "end it instead of deleting it."
            )
        return super().delete(*args, **kwargs)

    def __str__(self):
        until = f" to {self.end_date}" if self.end_date else ""
        return f"{self.teacher} - {self.section} from {self.start_date}{until}"


# ---------------------------------------------------------------------------
# Phase 4 Gate 3 - grading scales (ADR 0009)
# ---------------------------------------------------------------------------


def grade_from_bands(bands, percentage):
    """Resolve a percentage against bands of (min_percentage, label).

    The grade is the label of the band with the highest minimum that is at or
    below the percentage. Returns None when there is no percentage or no band
    applies. Used both with live scales and with the frozen snapshot stored on
    a finalized assessment, so both resolve identically.
    """
    if percentage is None:
        return None
    best = None
    for minimum, label in bands:
        minimum = Decimal(str(minimum))
        if minimum <= Decimal(str(percentage)) and (best is None or minimum > best[0]):
            best = (minimum, label)
    return best[1] if best else None


class GradingScale(models.Model):
    """A reusable grading policy for an Academic Year (ADR 0009).

    It applies to the Class/Grades linked through GradingScaleClassGrade;
    each Year + Grade has at most one scale, so a grade is never ambiguous.
    Bands are GradeBoundary rows: "from min_percentage upward -> label". A
    scale is complete once it has a band starting at 0%, so every percentage
    from 0 to 100 resolves deterministically. Numeric marks stay canonical;
    finalized assessments keep a frozen copy of the bands they used, so later
    edits never rewrite historical grades.
    """

    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.PROTECT, related_name="grading_scales"
    )
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["academic_year", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["academic_year", "name"], name="gradingscale_unique_name_per_year"
            )
        ]

    @classmethod
    def for_grade(cls, academic_year, class_grade):
        link = (
            GradingScaleClassGrade.objects.filter(
                academic_year=academic_year, class_grade=class_grade
            )
            .select_related("scale")
            .first()
        )
        return link.scale if link else None

    def bands(self):
        return list(self.boundaries.order_by("-min_percentage").values_list(
            "min_percentage", "label"
        ))

    @property
    def is_complete(self):
        return self.boundaries.filter(min_percentage=0).exists()

    def grade_for(self, percentage):
        if percentage is not None and not (0 <= Decimal(str(percentage)) <= 100):
            raise ValueError("A percentage must be between 0 and 100.")
        return grade_from_bands(self.bands(), percentage)

    def snapshot(self):
        """The frozen form stored on a finalized assessment."""
        return {
            "scale": self.name,
            "bands": [[str(minimum), label] for minimum, label in self.bands()],
        }

    def set_class_grades(self, class_grades):
        """Replace the Grades this scale applies to; refuse Grades already taken."""
        class_grades = list(class_grades)
        taken = (
            GradingScaleClassGrade.objects.filter(
                academic_year=self.academic_year, class_grade__in=class_grades
            )
            .exclude(scale=self)
            .select_related("class_grade", "scale")
        )
        if taken.exists():
            raise ValidationError(
                "; ".join(f"{t.class_grade} already uses {t.scale.name}" for t in taken)
                + "."
            )
        with transaction.atomic():
            self.class_grade_links.exclude(class_grade__in=class_grades).delete()
            existing = set(self.class_grade_links.values_list("class_grade_id", flat=True))
            GradingScaleClassGrade.objects.bulk_create(
                GradingScaleClassGrade(
                    scale=self, academic_year=self.academic_year, class_grade=grade
                )
                for grade in class_grades
                if grade.pk not in existing
            )

    @property
    def class_grades(self):
        return ClassGrade.objects.filter(grading_scale_links__scale=self)

    def __str__(self):
        return f"{self.academic_year} - {self.name}"


class GradingScaleClassGrade(models.Model):
    """Applies a grading scale to one Class/Grade; one scale per Year + Grade."""

    scale = models.ForeignKey(
        GradingScale, on_delete=models.CASCADE, related_name="class_grade_links"
    )
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.PROTECT, related_name="grading_scale_links"
    )
    class_grade = models.ForeignKey(
        ClassGrade, on_delete=models.PROTECT, related_name="grading_scale_links"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["academic_year", "class_grade"],
                name="gradingscaleclassgrade_one_scale_per_year_grade",
            )
        ]

    def clean(self):
        super().clean()
        if self.scale_id and self.academic_year_id != self.scale.academic_year_id:
            raise ValidationError("The link's Academic Year must match the scale's.")

    def save(self, *args, **kwargs):
        if self.scale_id and not self.academic_year_id:
            self.academic_year_id = self.scale.academic_year_id
        super().save(*args, **kwargs)


class GradeBoundary(models.Model):
    """One band of a grading scale: from `min_percentage` upward -> `label`."""

    scale = models.ForeignKey(GradingScale, on_delete=models.CASCADE, related_name="boundaries")
    label = models.CharField(max_length=10)
    min_percentage = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        ordering = ["scale", "-min_percentage"]
        constraints = [
            models.UniqueConstraint(fields=["scale", "label"], name="gradeboundary_unique_label"),
            models.UniqueConstraint(
                fields=["scale", "min_percentage"], name="gradeboundary_unique_minimum"
            ),
            models.CheckConstraint(
                condition=models.Q(min_percentage__gte=0) & models.Q(min_percentage__lte=100),
                name="gradeboundary_minimum_between_0_and_100",
            ),
        ]

    def clean(self):
        super().clean()
        self.label = (self.label or "").strip()
        if self.min_percentage is not None and not (0 <= self.min_percentage <= 100):
            raise ValidationError(
                {"min_percentage": "The starting percentage must be between 0 and 100."}
            )

    def __str__(self):
        return f"{self.label} (from {self.min_percentage}%)"


# ---------------------------------------------------------------------------
# Phase 4 Gate 4 - assessment planning (ADR 0009)
# ---------------------------------------------------------------------------


class Assessment(models.Model):
    """One subject assessment for one Section in one Term (ADR 0009).

    Not a multi-subject examination. Lifecycle DRAFT -> FINALIZED. The date
    falls inside the Term (and so the Academic Year); future assessments may
    be planned, but results cannot be entered before the date. Once results
    exist (or the assessment is finalized) its context and maximum marks are
    locked and it cannot be deleted.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        FINALIZED = "FINALIZED", "Finalized"

    LOCKED_FIELDS = (
        "term_id", "offering_id", "section_id", "assessment_date", "maximum_marks",
    )

    term = models.ForeignKey(AcademicTerm, on_delete=models.PROTECT, related_name="assessments")
    offering = models.ForeignKey(
        AcademicSubjectOffering, on_delete=models.PROTECT, related_name="assessments"
    )
    section = models.ForeignKey(Section, on_delete=models.PROTECT, related_name="assessments")
    name = models.CharField(max_length=100)
    assessment_date = models.DateField()
    maximum_marks = models.DecimalField(max_digits=6, decimal_places=2)
    pass_mark = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    finalized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="finalized_assessments",
    )
    finalized_at = models.DateTimeField(null=True, blank=True)
    grading_snapshot = models.JSONField(
        null=True,
        blank=True,
        help_text="Frozen grading scale (name and bands) captured at finalization.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-assessment_date", "offering", "section", "name"]
        permissions = [("finalize_assessment", "Can finalize assessment results")]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status="DRAFT",
                        finalized_by__isnull=True,
                        finalized_at__isnull=True,
                        grading_snapshot__isnull=True,
                    )
                    | models.Q(
                        status="FINALIZED",
                        finalized_by__isnull=False,
                        finalized_at__isnull=False,
                    )
                ),
                name="assessment_finalization_fields_match_status",
            ),
            models.UniqueConstraint(
                fields=["offering", "section", "term", "name"],
                name="assessment_unique_name_per_offering_section_term",
            ),
            models.CheckConstraint(
                condition=models.Q(maximum_marks__gt=0),
                name="assessment_maximum_marks_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(pass_mark__isnull=True)
                | (models.Q(pass_mark__gte=0) & models.Q(pass_mark__lte=models.F("maximum_marks"))),
                name="assessment_pass_mark_within_maximum",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["DRAFT", "FINALIZED"]),
                name="assessment_status_valid",
            ),
        ]

    @property
    def is_finalized(self):
        return self.status == self.Status.FINALIZED

    def has_results(self):
        """Whether any StudentResult depends on this assessment (from Gate 5)."""
        related = getattr(self, "results", None)
        return bool(self.pk and related is not None and related.exists())

    @property
    def is_locked(self):
        """Context and maximum marks can no longer change."""
        if not self.pk:
            return False
        stored = Assessment.objects.filter(pk=self.pk).values_list("status", flat=True).first()
        return stored == self.Status.FINALIZED or self.has_results()

    def clean(self):
        super().clean()
        if self.pk is None and self.status != self.Status.DRAFT:
            raise ValidationError("A new assessment always starts as a draft.")
        if self.pk is not None and self.is_locked:
            original = Assessment.objects.filter(pk=self.pk).values(*self.LOCKED_FIELDS).get()
            current = {
                "term_id": self.term_id,
                "offering_id": self.offering_id,
                "section_id": self.section_id,
                "assessment_date": _as_date(self.assessment_date),
                "maximum_marks": (
                    Decimal(str(self.maximum_marks)) if self.maximum_marks is not None else None
                ),
            }
            if current != original:
                raise ValidationError(
                    "Results already depend on this assessment; its Term, Subject, Section, "
                    "date and maximum marks can no longer change."
                )
        errors = {}
        if self.term_id and self.offering_id:
            if self.term.academic_year_id != self.offering.academic_year_id:
                errors["term"] = (
                    "The Term and the Subject offering are in different Academic Years."
                )
        if self.offering_id and self.section_id and not self.offering.applies_to(self.section):
            errors["section"] = "This Section does not take this Subject offering."
        if self.term_id and self.assessment_date and not self.term.contains(self.assessment_date):
            errors["assessment_date"] = (
                f"The date must fall inside {self.term.name} "
                f"({self.term.start_date} to {self.term.end_date})."
            )
        if self.maximum_marks is not None and self.maximum_marks <= 0:
            errors["maximum_marks"] = "Maximum marks must be greater than zero."
        if self.pass_mark is not None:
            if self.pass_mark < 0:
                errors["pass_mark"] = "The pass mark cannot be negative."
            elif self.maximum_marks is not None and self.pass_mark > self.maximum_marks:
                errors["pass_mark"] = "The pass mark cannot exceed the maximum marks."
        if errors:
            raise ValidationError(errors)

    def delete(self, *args, **kwargs):
        if self.is_locked:
            raise ValidationError(
                "This assessment has results or is finalized and cannot be deleted."
            )
        return super().delete(*args, **kwargs)

    # --- roster and DRAFT result entry (Gate 5) ---

    def roster(self):
        """Enrollments eligible on the assessment date (ADR 0006/0009).

        Effective on the date, in the offering's Academic Year and Grade, and
        in this assessment's Section - never just the current placement.
        """
        return (
            AcademicEnrollment.objects.effective_on(self.assessment_date)
            .filter(
                academic_year_id=self.offering.academic_year_id,
                class_grade_id=self.offering.class_grade_id,
                section_id=self.section_id,
            )
            .select_related("student")
            .order_by("student__full_name", "pk")
        )

    def unmarked_enrollments(self):
        return self.roster().exclude(assessment_results__assessment=self)

    def ineligible_results(self):
        return self.results.exclude(academic_enrollment__in=self.roster().values("pk"))

    @property
    def is_open_for_entry(self):
        return (
            self.status == self.Status.DRAFT
            and _as_date(self.assessment_date) <= business_today()
        )

    def _lock(self):
        return (
            Assessment.objects.select_for_update()
            .filter(pk=self.pk)
            .values_list("status", flat=True)
            .get()
        )

    # --- finalization (Gate 6) ---

    def applicable_scale(self):
        return GradingScale.for_grade(self.offering.academic_year, self.offering.class_grade)

    def finalization_problems(self):
        """Reasons this DRAFT assessment cannot be finalized yet (empty = ready)."""
        problems = []
        if self.status != self.Status.DRAFT:
            return ["This assessment is already finalized."]
        if _as_date(self.assessment_date) > business_today():
            problems.append("The assessment date has not been reached.")
        if not self.roster().exists():
            problems.append("No Students are on this assessment's roster.")
        unmarked = self.unmarked_enrollments().count()
        if unmarked:
            problems.append(f"{unmarked} Student(s) still have no result.")
        if self.ineligible_results().exists():
            problems.append("Some results belong to Students not on the roster.")
        over = self.results.filter(
            status=ResultStatus.MARKED, score__gt=self.maximum_marks
        ).count()
        if over:
            problems.append(f"{over} score(s) exceed the maximum marks.")
        scale = self.applicable_scale()
        if scale is not None and not scale.is_complete:
            problems.append(
                f"The grading scale {scale.name} needs a band starting at 0% before results "
                "can be finalized."
            )
        return problems

    def finalize(self, *, actor):
        """DRAFT -> FINALIZED (Gate 6). Administrator-only; records who and when.

        Requires the date to have passed, a non-empty roster, exactly one
        valid result per roster enrollment and none for others. Freezes the
        applicable grading scale's bands onto the assessment so later scale
        edits never change these grades. Normal editing stops afterwards.
        """
        if actor is None or not getattr(actor, "pk", None):
            raise ValidationError("A finalizing user is required.")
        if not actor.has_perm("core.finalize_assessment"):
            raise ValidationError("Only an administrator can finalize results.")
        with transaction.atomic():
            if self._lock() != self.Status.DRAFT:
                raise ValidationError("This assessment is already finalized.")
            problems = self.finalization_problems()
            if problems:
                raise ValidationError(problems)
            scale = self.applicable_scale()
            self.grading_snapshot = scale.snapshot() if scale is not None else None
            self.status = self.Status.FINALIZED
            self.finalized_by = actor
            self.finalized_at = timezone.now()
            self.save(
                update_fields=[
                    "status", "finalized_by", "finalized_at", "grading_snapshot", "updated_at",
                ]
            )

    def grade_for(self, result):
        """Derived grade: frozen bands once finalized, the live scale before."""
        if result.status != ResultStatus.MARKED:
            return None
        if self.status == self.Status.FINALIZED:
            if not self.grading_snapshot:
                return None
            return grade_from_bands(self.grading_snapshot["bands"], result.percentage)
        scale = self.applicable_scale()
        return scale.grade_for(result.percentage) if scale is not None else None

    @property
    def grading_scale_name(self):
        if self.status == self.Status.FINALIZED:
            return (self.grading_snapshot or {}).get("scale")
        scale = self.applicable_scale()
        return scale.name if scale is not None else None

    def save_draft_result(self, *, enrollment, status, score=None, actor):
        """Create or update one Student's DRAFT result (Gate 5).

        Only the teacher assigned to this offering and Section may enter
        results (ADR 0010), only from the assessment date, and only while the
        assessment is DRAFT. The enrollment must be on the date-effective
        roster. Editing a DRAFT result is a normal edit, not a correction.
        """
        from core.authorization import can_enter_results

        if not can_enter_results(actor, self.offering, self.section):
            raise ValidationError(
                "Only the teacher assigned to this Subject and Section can enter results."
            )
        if _as_date(self.assessment_date) > business_today():
            raise ValidationError("Results cannot be entered before the assessment date.")
        if status == ResultStatus.ABSENT:
            score = None
        result = self.results.filter(academic_enrollment=enrollment).first() or StudentResult(
            assessment=self, academic_enrollment=enrollment
        )
        result.status = status
        result.score = None if score in (None, "") else Decimal(str(score))
        result.entered_by = actor
        result.full_clean(validate_constraints=False)
        try:
            with transaction.atomic():
                if self._lock() != self.Status.DRAFT:
                    raise ValidationError(
                        "This assessment is finalized; results can only be corrected by an "
                        "administrator."
                    )
                result.save()
        except IntegrityError:
            raise ValidationError(
                "This Student already has a result for this assessment."
            ) from None
        return result

    @property
    def class_grade(self):
        return self.offering.class_grade

    @property
    def subject(self):
        return self.offering.subject

    def __str__(self):
        return f"{self.offering.subject.name} {self.section} - {self.name}"


# ---------------------------------------------------------------------------
# Phase 4 Gate 5 - date-effective roster and DRAFT results (ADR 0009/0010)
# ---------------------------------------------------------------------------


class ResultStatus(models.TextChoices):
    """Exactly MARKED and ABSENT. ABSENT is never stored as a zero score."""

    MARKED = "MARKED", "Marked"
    ABSENT = "ABSENT", "Absent"


class StudentResult(models.Model):
    """One eligible enrollment's result in one assessment (ADR 0009).

    MARKED requires 0 <= score <= the assessment's maximum marks; ABSENT has
    no score (DB check for the status/score pairing and non-negative score;
    the maximum is checked in clean()). The result references the
    AcademicEnrollment effective on the assessment date, so later transfers
    never rewrite it. A missing result means entry is incomplete - never
    ABSENT.
    """

    assessment = models.ForeignKey(Assessment, on_delete=models.PROTECT, related_name="results")
    academic_enrollment = models.ForeignKey(
        AcademicEnrollment, on_delete=models.PROTECT, related_name="assessment_results"
    )
    status = models.CharField(max_length=10, choices=ResultStatus.choices)
    score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="entered_results"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["assessment", "academic_enrollment__student__full_name"]
        permissions = [("correct_studentresult", "Can correct finalized results")]
        constraints = [
            models.UniqueConstraint(
                fields=["assessment", "academic_enrollment"],
                name="studentresult_unique_assessment_enrollment",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status="MARKED", score__isnull=False, score__gte=0)
                    | models.Q(status="ABSENT", score__isnull=True)
                ),
                name="studentresult_status_matches_score",
            ),
        ]

    def clean(self):
        super().clean()
        if self.status == ResultStatus.MARKED:
            if self.score is None:
                raise ValidationError({"score": "A marked result needs a score."})
            if self.score < 0:
                raise ValidationError({"score": "A score cannot be negative."})
            if self.assessment_id and self.score > self.assessment.maximum_marks:
                raise ValidationError(
                    {"score": f"A score cannot exceed {self.assessment.maximum_marks}."}
                )
        elif self.status == ResultStatus.ABSENT and self.score is not None:
            raise ValidationError({"score": "An absent result has no score."})
        if self.assessment_id and self.academic_enrollment_id:
            if not self.assessment.roster().filter(pk=self.academic_enrollment_id).exists():
                raise ValidationError(
                    {
                        "academic_enrollment": (
                            "This Student is not on the assessment's roster for its date."
                        )
                    }
                )

    @property
    def student(self):
        return self.academic_enrollment.student

    @property
    def percentage(self):
        if self.status != ResultStatus.MARKED or self.score is None:
            return None
        return (self.score * 100 / self.assessment.maximum_marks).quantize(Decimal("0.01"))

    @property
    def pass_fail(self):
        """PASS/FAIL derived from the pass mark; None without one; ABSENT stays ABSENT."""
        if self.status == ResultStatus.ABSENT:
            return "ABSENT"
        if self.assessment.pass_mark is None or self.score is None:
            return None
        return "PASS" if self.score >= self.assessment.pass_mark else "FAIL"

    @property
    def grade(self):
        return self.assessment.grade_for(self)

    def correct(self, *, new_status, new_score=None, actor, reason):
        """Audited correction of a FINALIZED result (Gate 7, ADR 0009).

        Administrator-only (correct_studentresult). MARKED->MARKED,
        MARKED->ABSENT and ABSENT->MARKED are allowed; a no-op, an invalid
        score, a blank reason or a draft assessment is rejected without
        change. An immutable ResultCorrection keeps the previous and new
        values, actor, time and reason; only this result changes - the
        assessment is not reopened.
        """
        if actor is None or not getattr(actor, "pk", None):
            raise ValidationError("A correcting user is required.")
        if not actor.has_perm("core.correct_studentresult"):
            raise ValidationError("Only an administrator can correct finalized results.")
        reason = (reason or "").strip()
        if not reason:
            raise ValidationError("A reason is required when correcting a result.")
        if new_status not in ResultStatus.values:
            raise ValidationError("Invalid result status.")
        if new_status == ResultStatus.ABSENT:
            new_score = None
        else:
            if new_score in (None, ""):
                raise ValidationError("A marked result needs a score.")
            new_score = Decimal(str(new_score))
            if new_score < 0 or new_score > self.assessment.maximum_marks:
                raise ValidationError(
                    f"A score must be between 0 and {self.assessment.maximum_marks}."
                )
        if new_status == self.status and new_score == self.score:
            raise ValidationError("The result already has this value.")
        with transaction.atomic():
            status = (
                Assessment.objects.select_for_update()
                .filter(pk=self.assessment_id)
                .values_list("status", flat=True)
                .get()
            )
            if status != Assessment.Status.FINALIZED:
                raise ValidationError(
                    "This assessment is still a draft; the teacher edits its results directly."
                )
            ResultCorrection.objects.create(
                result=self,
                previous_status=self.status,
                previous_score=self.score,
                new_status=new_status,
                new_score=new_score,
                reason=reason,
                corrected_by=actor,
            )
            self.status = new_status
            self.score = new_score
            self.save(update_fields=["status", "score", "updated_at"])
            # Phase 6 (ADR 0014): released information never changes silently.
            from core.publication import mark_stale_for_result

            mark_stale_for_result(self, actor=actor)

    def __str__(self):
        shown = self.score if self.status == ResultStatus.MARKED else "Absent"
        return f"{self.assessment} - {self.academic_enrollment.student}: {shown}"


# ---------------------------------------------------------------------------
# Phase 4 Gate 7 - audited result corrections (ADR 0009)
# ---------------------------------------------------------------------------


class ResultCorrection(models.Model):
    """Immutable history of a correction to a finalized result (ADR 0009).

    Keeps previous and new status and score, the administrator, the time and
    the reason. Repeated corrections keep the full sequence. Status/score
    pairing on both sides is enforced by database checks.
    """

    result = models.ForeignKey(
        StudentResult, on_delete=models.PROTECT, related_name="corrections"
    )
    previous_status = models.CharField(max_length=10, choices=ResultStatus.choices)
    previous_score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    new_status = models.CharField(max_length=10, choices=ResultStatus.choices)
    new_score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    reason = models.TextField()
    corrected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="result_corrections"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(previous_status="MARKED", previous_score__isnull=False)
                    | models.Q(previous_status="ABSENT", previous_score__isnull=True)
                ),
                name="resultcorrection_previous_status_matches_score",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(new_status="MARKED", new_score__isnull=False, new_score__gte=0)
                    | models.Q(new_status="ABSENT", new_score__isnull=True)
                ),
                name="resultcorrection_new_status_matches_score",
            ),
        ]

    def __str__(self):
        return f"{self.result} corrected by {self.corrected_by}"


# ---------------------------------------------------------------------------
# Phase 4 Gate 8 - optional Term teacher remark (ADR 0009)
# ---------------------------------------------------------------------------


class TermRemark(models.Model):
    """One optional remark per Student per Term, shown on the report card.

    Separate from marks, grades and results; never used in any calculation.
    """

    term = models.ForeignKey(AcademicTerm, on_delete=models.PROTECT, related_name="remarks")
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="term_remarks")
    remark = models.TextField()
    written_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="term_remarks"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["term", "student__full_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["term", "student"], name="termremark_one_per_student_per_term"
            ),
            models.CheckConstraint(
                condition=~models.Q(remark=""), name="termremark_not_blank"
            ),
        ]

    def __str__(self):
        return f"{self.term} - {self.student}"


# ---------------------------------------------------------------------------
# Phase 6 Gate 1 - guardian accounts and explicit access grants (ADR 0013)
# ---------------------------------------------------------------------------


class GuardianAccount(models.Model):
    """Links one login to one Guardian record (ADR 0013).

    Created only by an administrator after verifying identity. Revoked, never
    deleted: database triggers refuse deleting a row, changing who it links
    or how it was verified, and clearing a revocation. At most one active
    link per login and per Guardian.
    """

    class VerificationMethod(models.TextChoices):
        IN_PERSON_DOCUMENTS = "IN_PERSON_DOCUMENTS", "In person, with identity documents"
        EXISTING_RECORDS = "EXISTING_RECORDS", "Against existing school records"
        OTHER = "OTHER", "Other (described in the note)"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="guardian_accounts"
    )
    guardian = models.ForeignKey(Guardian, on_delete=models.PROTECT, related_name="accounts")
    identity_verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    identity_verification_method = models.CharField(
        max_length=30, choices=VerificationMethod.choices
    )
    identity_verification_note = models.CharField(max_length=200)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(default=timezone.now)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="+",
    )
    revocation_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        permissions = [
            ("reset_guardian_password", "Can reset a guardian's password"),
            ("change_guardian_username", "Can change a guardian's username"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user"], condition=models.Q(revoked_at__isnull=True),
                name="guardianaccount_one_active_per_user",
            ),
            models.UniqueConstraint(
                fields=["guardian"], condition=models.Q(revoked_at__isnull=True),
                name="guardianaccount_one_active_per_guardian",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(revoked_at__isnull=True, revoked_by__isnull=True,
                             revocation_reason="")
                    | (models.Q(revoked_at__isnull=False, revoked_by__isnull=False)
                       & ~models.Q(revocation_reason=""))
                ),
                name="guardianaccount_revocation_complete",
            ),
            models.CheckConstraint(
                condition=~models.Q(identity_verification_note=""),
                name="guardianaccount_verification_note_required",
            ),
        ]

    @property
    def is_active(self):
        return self.revoked_at is None

    def __str__(self):
        state = "" if self.is_active else " (revoked)"
        return f"{self.user} → {self.guardian}{state}"


class GuardianStudentAccess(models.Model):
    """An explicit grant: this Guardian may see this Student (ADR 0013, P5).

    Attached to the recorded StudentGuardian relationship; the relationship
    type never decides anything. Created one at a time by an administrator.
    Revoked, never deleted (database triggers). `public_id` identifies the
    Student in portal URLs instead of database ids (ADR 0014).
    """

    student_guardian = models.ForeignKey(
        StudentGuardian, on_delete=models.PROTECT, related_name="access_grants"
    )
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    granted_at = models.DateTimeField(default=timezone.now)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="+",
    )
    revocation_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-granted_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["student_guardian"], condition=models.Q(revoked_at__isnull=True),
                name="guardianstudentaccess_one_active_per_relationship",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(revoked_at__isnull=True, revoked_by__isnull=True,
                             revocation_reason="")
                    | (models.Q(revoked_at__isnull=False, revoked_by__isnull=False)
                       & ~models.Q(revocation_reason=""))
                ),
                name="guardianstudentaccess_revocation_complete",
            ),
        ]

    @property
    def is_active(self):
        return self.revoked_at is None

    def __str__(self):
        state = "" if self.is_active else " (revoked)"
        return f"{self.student_guardian}{state}"


class GuardianAccessReview(models.Model):
    """An administrator's explicit retain/revoke decision for one grant (ADR 0013).

    Required when a Student is made INACTIVE (STUDENT_INACTIVE), when a new
    placement ends the current one (PLACEMENT_ENDED), and when the Student
    has no enrollment effective on the business date (NO_CURRENT_ENROLLMENT,
    date-based, fail closed until decided — OD-8). `enrollment` is the
    placement the decision concerns, so a later ended placement asks again.
    Immutable: database triggers refuse UPDATE and DELETE.
    """

    class Trigger(models.TextChoices):
        STUDENT_INACTIVE = "STUDENT_INACTIVE", "Student made inactive"
        PLACEMENT_ENDED = "PLACEMENT_ENDED", "Placement ended"
        NO_CURRENT_ENROLLMENT = "NO_CURRENT_ENROLLMENT", "No current enrollment"

    class Decision(models.TextChoices):
        RETAINED = "RETAINED", "Retain access"
        REVOKED = "REVOKED", "Revoke access"

    grant = models.ForeignKey(
        GuardianStudentAccess, on_delete=models.PROTECT, related_name="reviews"
    )
    trigger = models.CharField(max_length=30, choices=Trigger.choices)
    enrollment = models.ForeignKey(
        AcademicEnrollment, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    decision = models.CharField(max_length=10, choices=Decision.choices)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    decided_at = models.DateTimeField(default=timezone.now)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-decided_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["grant", "trigger", "enrollment"],
                name="guardianaccessreview_one_per_placement",
            ),
            models.UniqueConstraint(
                fields=["grant", "trigger"],
                condition=models.Q(enrollment__isnull=True),
                name="guardianaccessreview_one_without_placement",
            ),
            models.CheckConstraint(
                condition=models.Q(decision__in=["RETAINED", "REVOKED"]),
                name="guardianaccessreview_decision_valid",
            ),
        ]

    def __str__(self):
        return f"{self.grant}: {self.get_decision_display()} ({self.get_trigger_display()})"


# ---------------------------------------------------------------------------
# Phase 6 Gate 6 - explicit Term publication to guardians (ADR 0014)
# ---------------------------------------------------------------------------


class TermPublication(models.Model):
    """One released version of a Student's Term report card (ADR 0014).

    Publication is separate from finalization. Each version stores an
    immutable snapshot of exactly what the guardian report card displays
    (header labels here, one TermPublicationEntry per result, the remark
    text) plus a fingerprint of the released source values. A correction of
    a released result or remark marks the current version STALE; the portal
    shows only the current PUBLISHED version whose fingerprint still matches
    the live source. Versions are permanent history: database triggers refuse
    DELETE, any change except the status fields, and status changes other
    than PUBLISHED -> STALE/SUPERSEDED/WITHDRAWN and STALE ->
    SUPERSEDED/WITHDRAWN.
    """

    class Status(models.TextChoices):
        PUBLISHED = "PUBLISHED", "Published"
        STALE = "STALE", "Stale — needs review"
        SUPERSEDED = "SUPERSEDED", "Superseded"
        WITHDRAWN = "WITHDRAWN", "Withdrawn"

    CURRENT_STATUSES = ("PUBLISHED", "STALE")

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="publications")
    term = models.ForeignKey(AcademicTerm, on_delete=models.PROTECT, related_name="publications")
    placement = models.ForeignKey(
        AcademicEnrollment, on_delete=models.PROTECT, related_name="+"
    )
    version = models.PositiveIntegerField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PUBLISHED)
    is_partial = models.BooleanField(default=False)
    pending_assessments = models.PositiveIntegerField(default=0)
    term_label = models.CharField(max_length=100)
    academic_year_label = models.CharField(max_length=100)
    class_grade_label = models.CharField(max_length=100)
    section_label = models.CharField(max_length=100)
    remark_id_ref = models.PositiveBigIntegerField(null=True, blank=True)
    remark_text = models.TextField(null=True, blank=True)
    fingerprint = models.CharField(max_length=64)
    fingerprint_scheme = models.PositiveSmallIntegerField(default=1)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    published_at = models.DateTimeField(default=timezone.now)
    status_changed_at = models.DateTimeField(null=True, blank=True)
    status_changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="+",
    )
    status_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["student", "term", "-version"]
        permissions = [("publish_termpublication", "Can publish Term results to guardians")]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "term", "version"], name="termpublication_unique_version"
            ),
            models.UniqueConstraint(
                fields=["student", "term"],
                condition=models.Q(status__in=["PUBLISHED", "STALE"]),
                name="termpublication_one_current",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["PUBLISHED", "STALE", "SUPERSEDED", "WITHDRAWN"]),
                name="termpublication_status_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(version__gte=1), name="termpublication_version_positive"
            ),
        ]

    @property
    def is_current(self):
        return self.status in self.CURRENT_STATUSES

    def __str__(self):
        return f"{self.student} - {self.term_label} v{self.version} ({self.get_status_display()})"


class TermPublicationEntry(models.Model):
    """One released result, exactly as displayed (ADR 0014). Immutable."""

    publication = models.ForeignKey(
        TermPublication, on_delete=models.PROTECT, related_name="entries"
    )
    result = models.ForeignKey(StudentResult, on_delete=models.PROTECT, related_name="+")
    display_order = models.PositiveIntegerField()
    subject_label = models.CharField(max_length=100)
    assessment_label = models.CharField(max_length=200)
    assessment_date = models.DateField()
    maximum_marks = models.DecimalField(max_digits=6, decimal_places=2)
    pass_mark = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=10)
    score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    percentage = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    grade_label = models.CharField(max_length=50, null=True, blank=True)
    pass_fail_label = models.CharField(max_length=10, null=True, blank=True)

    class Meta:
        ordering = ["publication", "display_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["publication", "result"], name="termpublicationentry_unique_result"
            ),
        ]


# --- Phase 7: bulk import (ADR 0017) ----------------------------------------


class ImportBatch(models.Model):
    """One uploaded import workbook and its outcome (ADR 0017).

    Validation (a dry run) creates the batch. A batch without errors is
    VALIDATED and keeps its parsed rows in `payload` until it is committed,
    discarded or expires; a batch with errors is REJECTED and keeps no
    payload. Database triggers refuse DELETE, refuse changes to the upload
    facts, allow status changes only out of VALIDATED, and freeze the batch
    once it leaves VALIDATED.
    """

    class Status(models.TextChoices):
        VALIDATED = "VALIDATED", "Validated — awaiting confirmation"
        REJECTED = "REJECTED", "Rejected — has errors"
        COMMITTED = "COMMITTED", "Imported"
        DISCARDED = "DISCARDED", "Discarded"
        EXPIRED = "EXPIRED", "Expired"
        FAILED = "FAILED", "Failed at import"

    FINAL_STATUSES = ("COMMITTED", "DISCARDED", "EXPIRED", "FAILED")

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    uploaded_at = models.DateTimeField(default=timezone.now)
    file_name = models.CharField(max_length=255)
    file_sha256 = models.CharField(max_length=64)
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.PROTECT, related_name="import_batches"
    )
    enrollment_start_date = models.DateField()
    student_rows = models.PositiveIntegerField(default=0)
    class_rows = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    warning_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=10, choices=Status.choices)
    payload = models.JSONField(default=dict, blank=True)
    summary = models.JSONField(default=dict, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    finished_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="+",
    )
    failure_reason = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-uploaded_at", "-pk"]
        permissions = [("run_import", "Can run bulk imports")]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    status__in=["VALIDATED", "REJECTED", "COMMITTED", "DISCARDED",
                                "EXPIRED", "FAILED"]
                ),
                name="importbatch_status_valid",
            ),
        ]

    @property
    def is_pending(self):
        return self.status == self.Status.VALIDATED

    def __str__(self):
        return f"Import {self.pk} ({self.get_status_display()})"


class ImportRowResult(models.Model):
    """A validation message for one row of an import batch. Immutable.

    Messages name sheets, rows and columns, never personal data.
    """

    class Level(models.TextChoices):
        ERROR = "ERROR", "Error"
        WARNING = "WARNING", "Warning"

    batch = models.ForeignKey(ImportBatch, on_delete=models.PROTECT, related_name="row_results")
    sheet = models.CharField(max_length=50)
    row_number = models.PositiveIntegerField(null=True, blank=True)
    column = models.CharField(max_length=50, blank=True)
    level = models.CharField(max_length=10, choices=Level.choices)
    message = models.CharField(max_length=500)

    class Meta:
        ordering = ["batch", "sheet", "row_number", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(level__in=["ERROR", "WARNING"]),
                name="importrowresult_level_valid",
            ),
        ]

    def __str__(self):
        return f"{self.sheet} row {self.row_number}: {self.message}"


# --- Phase 7 Gate 1: consent and notification outbox (ADR 0015) -------------

NOTIFICATION_PARAMETERS = ("first_name", "date", "portal_url")


class GuardianContactConsent(models.Model):
    """One recorded opt-in or opt-out. Append-only; the latest row is current."""

    class Channel(models.TextChoices):
        WHATSAPP = "WHATSAPP", "WhatsApp"

    class Status(models.TextChoices):
        OPTED_IN = "OPTED_IN", "Opted in"
        OPTED_OUT = "OPTED_OUT", "Opted out"

    class Source(models.TextChoices):
        PAPER_FORM = "PAPER_FORM", "Paper form"
        IN_PERSON = "IN_PERSON", "In person"
        PHONE_CALL = "PHONE_CALL", "Phone call"
        OTHER = "OTHER", "Other"

    guardian = models.ForeignKey(
        Guardian, on_delete=models.PROTECT, related_name="contact_consents"
    )
    channel = models.CharField(max_length=12, choices=Channel.choices, default=Channel.WHATSAPP)
    status = models.CharField(max_length=10, choices=Status.choices)
    source = models.CharField(max_length=12, choices=Source.choices)
    note = models.CharField(max_length=200, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    recorded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-recorded_at", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=["OPTED_IN", "OPTED_OUT"]),
                name="guardiancontactconsent_status_valid",
            ),
        ]

    def __str__(self):
        return f"{self.guardian} {self.get_channel_display()} {self.get_status_display()}"


class NotificationTemplate(models.Model):
    """A versioned message text. Approved bodies never change; edit = new version."""

    key = models.SlugField(max_length=50)
    channel = models.CharField(
        max_length=12,
        choices=GuardianContactConsent.Channel.choices,
        default=GuardianContactConsent.Channel.WHATSAPP,
    )
    language = models.CharField(max_length=10, default="en")
    version = models.PositiveIntegerField()
    body = models.TextField()
    approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["key", "channel", "language", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["key", "channel", "language", "version"],
                name="notificationtemplate_unique_version",
            ),
        ]

    def clean(self):
        super().clean()
        try:
            fields = [
                (name, spec, conversion)
                for _, name, spec, conversion in string.Formatter().parse(self.body)
                if name is not None
            ]
        except ValueError:
            raise ValidationError({"body": "The text has an unmatched { or }."}) from None
        allowed = ", ".join(f"{{{name}}}" for name in NOTIFICATION_PARAMETERS)
        if any(name not in NOTIFICATION_PARAMETERS for name, _, _ in fields):
            raise ValidationError({"body": f"Only these placeholders are allowed: {allowed}."})
        if any(spec or conversion for _, spec, conversion in fields):
            raise ValidationError({
                "body": "Placeholders cannot have formatting; use "
                "{first_name}, {date} or {portal_url} as they are."
            })

    def __str__(self):
        return f"{self.key} v{self.version} ({self.language})"


class Notification(models.Model):
    """One message to one guardian, in the outbox (ADR 0015)."""

    class Type(models.TextChoices):
        ABSENCE = "ABSENCE", "Absence alert"
        RESULT_PUBLISHED = "RESULT_PUBLISHED", "Report card published"
        ANNOUNCEMENT = "ANNOUNCEMENT", "Announcement"

    class Status(models.TextChoices):
        QUEUED = "QUEUED", "Queued"
        PREPARED = "PREPARED", "Ready to send"
        SENT = "SENT", "Sent"
        DELIVERED = "DELIVERED", "Delivered"
        FAILED = "FAILED", "Failed"
        SKIPPED_NO_CONSENT = "SKIPPED_NO_CONSENT", "Skipped — no consent"
        DISMISSED = "DISMISSED", "Dismissed"

    guardian = models.ForeignKey(Guardian, on_delete=models.PROTECT, related_name="notifications")
    student = models.ForeignKey(
        "Student", on_delete=models.PROTECT, null=True, blank=True, related_name="notifications"
    )
    type = models.CharField(max_length=20, choices=Type.choices)
    template = models.ForeignKey(
        NotificationTemplate, on_delete=models.PROTECT, related_name="notifications"
    )
    parameters = models.JSONField(default=dict)
    channel_mode = models.CharField(max_length=12, choices=School.NotificationMode.choices)
    status = models.CharField(max_length=20, choices=Status.choices)
    idempotency_key = models.CharField(max_length=200, unique=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    error_code = models.CharField(max_length=50, blank=True)
    provider_message_id = models.CharField(max_length=100, blank=True)
    marked_sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="+",
    )
    marked_sent_at = models.DateTimeField(null=True, blank=True)
    dismissed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="+",
    )
    dismissed_at = models.DateTimeField(null=True, blank=True)
    dismiss_reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "pk"]
        permissions = [("send_notification", "Can send prepared notifications")]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=[
                    "QUEUED", "PREPARED", "SENT", "DELIVERED", "FAILED",
                    "SKIPPED_NO_CONSENT", "DISMISSED",
                ]),
                name="notification_status_valid",
            ),
        ]

    def __str__(self):
        return f"{self.get_type_display()} to {self.guardian} ({self.get_status_display()})"




# --- Phase 7 Gate 3: announcements (ADR 0015) --------------------------------


class Announcement(models.Model):
    """A school notice for guardians. Immutable once published; withdrawn, never deleted.

    Published by administrators to the whole school, one Class/Grade or one
    Section; guardians with portal access read it in the portal. Database
    triggers refuse deleting a row, changing its content, and changing a
    withdrawal once recorded.
    """

    class Audience(models.TextChoices):
        ALL = "ALL", "Whole school"
        CLASS = "CLASS", "One class"
        SECTION = "SECTION", "One section"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    title = models.CharField(max_length=120)
    body = models.TextField(validators=[MaxLengthValidator(2000)])
    audience = models.CharField(max_length=10, choices=Audience.choices)
    class_grade = models.ForeignKey(
        ClassGrade, on_delete=models.PROTECT, null=True, blank=True,
        related_name="announcements",
    )
    section = models.ForeignKey(
        Section, on_delete=models.PROTECT, null=True, blank=True,
        related_name="announcements",
    )
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    published_at = models.DateTimeField(default=timezone.now)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    withdrawn_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="+",
    )
    withdrawal_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-published_at", "-pk"]
        permissions = [("withdraw_announcement", "Can withdraw an announcement")]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(audience__in=["ALL", "CLASS", "SECTION"]),
                name="announcement_audience_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(audience="ALL", class_grade__isnull=True, section__isnull=True)
                    | models.Q(audience="CLASS", class_grade__isnull=False,
                               section__isnull=True)
                    | models.Q(audience="SECTION", class_grade__isnull=True,
                               section__isnull=False)
                ),
                name="announcement_audience_target",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(withdrawn_at__isnull=True, withdrawn_by__isnull=True,
                             withdrawal_reason="")
                    | (models.Q(withdrawn_at__isnull=False, withdrawn_by__isnull=False)
                       & ~models.Q(withdrawal_reason=""))
                ),
                name="announcement_withdrawal_complete",
            ),
        ]

    def clean(self):
        super().clean()
        if self.audience == self.Audience.CLASS and not self.class_grade_id:
            raise ValidationError({"class_grade": "Choose the class."})
        if self.audience == self.Audience.SECTION and not self.section_id:
            raise ValidationError({"section": "Choose the section."})
        if self.audience != self.Audience.CLASS and self.class_grade_id:
            raise ValidationError({"class_grade": "Only a notice to one class has a class."})
        if self.audience != self.Audience.SECTION and self.section_id:
            raise ValidationError({"section": "Only a notice to one section has a section."})

    @property
    def is_withdrawn(self):
        return self.withdrawn_at is not None

    def audience_label(self):
        if self.audience == self.Audience.CLASS:
            return str(self.class_grade)
        if self.audience == self.Audience.SECTION:
            return str(self.section)
        return self.get_audience_display()

    def __str__(self):
        return self.title


# --- Phase 7 piece C: issued documents ---------------------------------------


class IssuedDocument(models.Model):
    """A serial-numbered document issued by the school (Phase 7 piece C).

    `payload` is the exact content printed, letterhead included; reprints
    render from it, never from live data. Database triggers refuse every
    UPDATE and DELETE.
    """

    class DocumentType(models.TextChoices):
        BONAFIDE = "BONAFIDE", "Bonafide certificate"
        REPORT_CARD = "REPORT_CARD", "Report card"
        ATTENDANCE_SUMMARY = "ATTENDANCE_SUMMARY", "Attendance summary"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    document_type = models.CharField(max_length=20, choices=DocumentType.choices)
    serial = models.CharField(max_length=40, unique=True)
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="+")
    student = models.ForeignKey(
        Student, on_delete=models.PROTECT, null=True, blank=True, related_name="issued_documents"
    )
    publication = models.OneToOneField(
        "TermPublication", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    payload = models.JSONField()
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="+",
    )
    issued_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-issued_at", "-pk"]
        permissions = [("issue_document", "Can issue documents")]

    def __str__(self):
        return self.serial


class DocumentSerialCounter(models.Model):
    """Last number used per document type and academic year (locked on use)."""

    document_type = models.CharField(max_length=20)
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="+")
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["document_type", "academic_year"], name="documentserialcounter_unique"
            ),
        ]
