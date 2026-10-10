import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name"]

    def record_status_change(self, new_status):
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
        self.status = new_status
        self.status_changed_at = timezone.now()
        self.save(update_fields=["status", "status_changed_at", "updated_at"])

    def enroll(self, *, academic_year, class_grade, section, start_date):
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

    def record_status_change(self, new_status, *, actor, reason):
        """Correct a captured status, preserving the previous value.

        An unknown status, a no-op change, a missing reason, or a missing actor
        is rejected without changing anything. A valid correction writes an
        immutable AttendanceCorrection and then updates the accepted status,
        so the prior value is never lost. Changing to PRESENT clears any
        absence note, because a PRESENT entry may not retain one.
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

        with transaction.atomic():
            AttendanceCorrection.objects.create(
                entry=self,
                previous_status=self.status,
                new_status=new_status,
                reason=reason,
                corrected_by=actor,
            )
            self.status = new_status
            if new_status != AttendanceStatus.ABSENT:
                self.absence_note = ""
            self.save(update_fields=["status", "absence_note", "updated_at"])

    @property
    def student(self):
        return self.academic_enrollment.student

    def __str__(self):
        return f"{self.academic_enrollment.student} - {self.register.date}"


class AttendanceCorrection(models.Model):
    """An immutable record of a correction to a captured attendance status.

    Per docs/adr/0007-phase-2-attendance-model.md, corrections preserve
    history rather than overwriting it: each row captures the previous status,
    the new status, the correcting actor, the timestamp, and the reason. Both
    statuses are limited to PRESENT/ABSENT by database check constraints.
    """

    entry = models.ForeignKey(
        AttendanceEntry, on_delete=models.PROTECT, related_name="corrections"
    )
    previous_status = models.CharField(max_length=10, choices=AttendanceStatus.choices)
    new_status = models.CharField(max_length=10, choices=AttendanceStatus.choices)
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
