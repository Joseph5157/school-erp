from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
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

    def enroll(self, *, academic_year, class_grade, section):
        """Place the Student into a new academic placement.

        Per docs/adr/0003-phase-1-status-and-transition-rules.md, a Student has
        at most one ACTIVE Academic Enrollment. Recording a new placement
        completes the previous ACTIVE enrollment and creates a new ACTIVE one,
        preserving the earlier record rather than overwriting it. The Section
        must belong to the enrollment's Class/Grade. An incompatible placement
        or an exact repeat of the current one is rejected without changing
        anything.
        """
        if section.class_grade_id != class_grade.pk:
            raise ValidationError("Selected Section does not belong to the selected Class/Grade.")

        try:
            with transaction.atomic():
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
                    AcademicEnrollment.objects.filter(pk=current.pk).update(
                        status=AcademicEnrollment.Status.COMPLETED,
                        updated_at=timezone.now(),
                    )
                return AcademicEnrollment.objects.create(
                    student=self,
                    academic_year=academic_year,
                    class_grade=class_grade,
                    section=section,
                )
        except IntegrityError:
            raise ValidationError(
                "This Student already has an active enrollment for this placement."
            ) from None

    @property
    def current_enrollment(self):
        return self.enrollments.filter(status=AcademicEnrollment.Status.ACTIVE).first()

    def __str__(self):
        return self.full_name


class AcademicEnrollment(models.Model):
    """A Student's academic placement for a specific Academic Year.

    Connects Student, Academic Year, Class/Grade, Section, and a status
    (docs/DOMAIN_MODEL.md - Academic Enrollment). Placement is historical:
    changing placement completes the previous ACTIVE enrollment rather than
    overwriting it, and a Student may accumulate many COMPLETED enrollments
    (docs/adr/0001-academic-structure-and-enrollment-history.md,
    docs/adr/0003-phase-1-status-and-transition-rules.md). The database
    enforces at most one ACTIVE enrollment per Student.
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["student"],
                condition=models.Q(status="ACTIVE"),
                name="academicenrollment_one_active_per_student",
            )
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
    """The minimum Phase 2 attendance status vocabulary.

    Fixed to these four values by
    docs/adr/0005-phase-2-attendance-domain-model.md; the set expands only
    through an explicit decision, not by silently adding enum members.
    """

    PRESENT = "PRESENT", "Present"
    ABSENT = "ABSENT", "Absent"
    LATE = "LATE", "Late"
    EXCUSED = "EXCUSED", "Excused"


class AttendanceRegister(models.Model):
    """One attendance register for a Class/Grade + Section on a single date.

    Per docs/adr/0005-phase-2-attendance-domain-model.md, attendance is
    enrollment-scoped and year-aware: the register fixes the Academic Year and
    the Class/Grade + Section context, and every entry must reference an
    Academic Enrollment from that same context. A Section may have at most one
    register per date. Registers are historical records and are not hard
    deleted through normal operation.
    """

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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "section"]
        constraints = [
            models.UniqueConstraint(
                fields=["section", "date"],
                name="attendanceregister_unique_section_date",
            )
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
        if self.date and self.academic_year_id:
            if not (self.academic_year.start_date <= self.date <= self.academic_year.end_date):
                raise ValidationError(
                    {"date": "Attendance date must fall within the selected Academic Year."}
                )

    def eligible_enrollments(self):
        """The enrollments that may be marked in this register.

        The Student's current (ACTIVE) placement for the register's Academic
        Year, Class/Grade, and Section. A Student who has moved elsewhere is
        represented by a COMPLETED enrollment and is not eligible here.
        """
        return AcademicEnrollment.objects.filter(
            academic_year_id=self.academic_year_id,
            class_grade_id=self.class_grade_id,
            section_id=self.section_id,
            status=AcademicEnrollment.Status.ACTIVE,
        ).select_related("student")

    def capture(self, *, enrollment, status):
        """Capture an initial attendance status for an enrolled Student.

        Rejects an unknown status or an enrollment outside the register's
        Academic Year and Class/Grade + Section context, and a duplicate entry
        for the same Student, without leaving a partial record. Correcting a
        status that has already been captured goes through
        `AttendanceEntry.record_status_change` instead.
        """
        if status not in AttendanceStatus.values:
            raise ValidationError("Invalid attendance status.")
        if (
            enrollment.academic_year_id != self.academic_year_id
            or enrollment.class_grade_id != self.class_grade_id
            or enrollment.section_id != self.section_id
            or enrollment.status != AcademicEnrollment.Status.ACTIVE
        ):
            raise ValidationError(
                "This Student is not enrolled in this register's Class/Grade and Section."
            )
        try:
            with transaction.atomic():
                return AttendanceEntry.objects.create(
                    register=self, academic_enrollment=enrollment, status=status
                )
        except IntegrityError:
            raise ValidationError(
                "This Student already has an attendance entry for this register."
            ) from None

    def __str__(self):
        return f"{self.section} - {self.date}"


class AttendanceEntry(models.Model):
    """One Student's attendance status within a register.

    Historical record (docs/adr/0005-phase-2-attendance-domain-model.md): the
    current `status` is the effective value, and every later change is stored
    as an AttendanceCorrection carrying the previous value, the actor, the
    timestamp, and a reason. Entries are not hard deleted.
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["register__date", "academic_enrollment__student__full_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["register", "academic_enrollment"],
                name="attendanceentry_unique_register_enrollment",
            )
        ]

    def clean(self):
        super().clean()
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
                            "Class/Grade and Section."
                        )
                    }
                )

    def record_status_change(self, new_status, *, actor, reason):
        """Correct a captured status, preserving the previous value.

        An unknown status, a no-op change, a missing reason, or a missing actor
        is rejected without changing anything. A valid correction writes an
        immutable AttendanceCorrection and then updates the effective status,
        so the prior value is never lost.
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
            self.save(update_fields=["status", "updated_at"])

    @property
    def student(self):
        return self.academic_enrollment.student

    def __str__(self):
        return f"{self.academic_enrollment.student} - {self.register.date}"


class AttendanceCorrection(models.Model):
    """An immutable record of a correction to a captured attendance status.

    Per docs/adr/0005-phase-2-attendance-domain-model.md, corrections preserve
    history rather than overwriting it: each row captures the previous status,
    the new status, the correcting actor, the timestamp, and the reason.
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

    def __str__(self):
        return f"{self.entry} {self.previous_status} -> {self.new_status}"
