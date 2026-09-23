from django import forms
from django.core.exceptions import ValidationError

from core.models import (
    AcademicEnrollment,
    AcademicYear,
    Applicant,
    ApplicantGuardian,
    AttendanceEntry,
    AttendanceRegister,
    AttendanceStatus,
    ClassGrade,
    Guardian,
    School,
    Section,
    Student,
)


class SchoolForm(forms.ModelForm):
    class Meta:
        model = School
        fields = ["name"]


class AcademicYearForm(forms.ModelForm):
    class Meta:
        model = AcademicYear
        fields = ["name", "start_date", "end_date"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }


class ClassGradeForm(forms.ModelForm):
    class Meta:
        model = ClassGrade
        fields = ["name"]


class SectionForm(forms.ModelForm):
    """Create a Section within a specific Class/Grade context.

    `class_grade` is supplied by the view from the URL rather than taken from
    the request, so a Section cannot be created against an arbitrary or
    missing Class/Grade. Because `class_grade` is not a form field, Django's
    automatic unique validation cannot see it, so the per-Class/Grade name
    uniqueness rule (docs/adr/0001) is checked explicitly here.
    """

    class Meta:
        model = Section
        fields = ["name"]

    def __init__(self, *args, class_grade=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.class_grade = class_grade
        if class_grade is not None:
            self.instance.class_grade = class_grade

    def clean_name(self):
        name = self.cleaned_data["name"]
        class_grade = self.class_grade or self.instance.class_grade
        duplicates = Section.objects.filter(class_grade=class_grade, name=name)
        if self.instance.pk is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise ValidationError("A Section with this name already exists for this Class/Grade.")
        return name


class AcademicEnrollmentForm(forms.ModelForm):
    """Create a new ACTIVE Academic Enrollment for a Student.

    `status` is intentionally excluded: a new placement is always ACTIVE, and
    the previous ACTIVE placement is completed by `Student.enroll` rather than
    through this form (docs/adr/0003-phase-1-status-and-transition-rules.md).
    The Section-must-belong-to-Class/Grade rule is checked here for a friendly
    error and again in the model workflow.
    """

    class Meta:
        model = AcademicEnrollment
        fields = ["academic_year", "class_grade", "section"]

    def clean(self):
        cleaned_data = super().clean()
        class_grade = cleaned_data.get("class_grade")
        section = cleaned_data.get("section")
        if class_grade is not None and section is not None:
            if section.class_grade_id != class_grade.pk:
                raise ValidationError(
                    {"section": "Selected Section does not belong to the selected Class/Grade."}
                )
        return cleaned_data


class ApplicantForm(forms.ModelForm):
    """Register an Applicant.

    `admission_status` is intentionally excluded: the admission state changes
    only through the explicit admission-decision workflow
    (docs/adr/0003-phase-1-status-and-transition-rules.md), so a new
    Applicant is always created as PENDING.
    """

    class Meta:
        model = Applicant
        fields = ["full_name", "date_of_birth", "email", "phone"]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
        }


class AdmissionDecisionForm(forms.Form):
    """The explicit admission decision for a pending Applicant.

    Only the two Phase 1 final decisions are offered; PENDING is not a
    choosable value, so this form can never move an Applicant back to
    pending (docs/adr/0003-phase-1-status-and-transition-rules.md).
    """

    decision = forms.ChoiceField(
        choices=[
            (Applicant.AdmissionStatus.ACCEPTED, "Accepted"),
            (Applicant.AdmissionStatus.REJECTED, "Rejected"),
        ]
    )


class StudentStatusForm(forms.Form):
    """The explicit Student status change permitted in Phase 1.

    Only the frozen ACTIVE/INACTIVE set is offered
    (docs/adr/0003-phase-1-status-and-transition-rules.md); the model workflow
    rejects unknown values or no-op changes as a second line of defence.
    """

    status = forms.ChoiceField(choices=Student.Status.choices)


class GuardianForm(forms.ModelForm):
    class Meta:
        model = Guardian
        fields = ["full_name", "phone", "email"]


class ApplicantGuardianForm(forms.ModelForm):
    """Associate a Guardian with a specific Applicant.

    `applicant` is supplied by the view from the URL rather than taken from
    the request, so a relationship cannot be created against an arbitrary or
    missing Applicant. Because `applicant` is not a form field, Django's
    automatic unique validation cannot see it, so the one-Guardian-per-
    Applicant rule is checked explicitly here.
    """

    class Meta:
        model = ApplicantGuardian
        fields = ["guardian", "relationship_type"]

    def __init__(self, *args, applicant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.applicant = applicant
        if applicant is not None:
            self.instance.applicant = applicant

    def clean(self):
        cleaned_data = super().clean()
        guardian = cleaned_data.get("guardian")
        if self.applicant is not None and guardian is not None:
            duplicates = ApplicantGuardian.objects.filter(
                applicant=self.applicant, guardian=guardian
            )
            if self.instance.pk is not None:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                raise ValidationError("This Guardian is already associated with this Applicant.")
        return cleaned_data


class AttendanceRegisterForm(forms.ModelForm):
    """Open an attendance register for a Class/Grade + Section and a date.

    The Section-belongs-to-Class/Grade rule is checked here for a friendly
    error and again in the model (docs/adr/0005). The date-within-Academic-Year
    rule and the one-register-per-section-per-date rule are enforced by the
    model's clean/constraints when the form is validated.
    """

    class Meta:
        model = AttendanceRegister
        fields = ["academic_year", "class_grade", "section", "date"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}

    def clean(self):
        cleaned_data = super().clean()
        class_grade = cleaned_data.get("class_grade")
        section = cleaned_data.get("section")
        if class_grade is not None and section is not None:
            if section.class_grade_id != class_grade.pk:
                raise ValidationError(
                    {"section": "Selected Section does not belong to the selected Class/Grade."}
                )
        return cleaned_data


class AttendanceCaptureForm(forms.Form):
    """Capture an initial status for each not-yet-marked Student in a register.

    One required choice field is created per eligible enrollment that has no
    entry yet, so opening the register always offers exactly the Students who
    still need marking. Existing entries are corrected through
    `AttendanceCorrectionForm` rather than re-captured here.
    """

    def __init__(self, *args, register=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.register = register
        self.enrollments = []
        if register is not None:
            marked = AttendanceEntry.objects.filter(register=register).values_list(
                "academic_enrollment_id", flat=True
            )
            self.enrollments = list(register.eligible_enrollments().exclude(pk__in=marked))
            for enrollment in self.enrollments:
                self.fields[self.field_name(enrollment)] = forms.ChoiceField(
                    choices=AttendanceStatus.choices,
                    label=str(enrollment.student),
                )

    @staticmethod
    def field_name(enrollment):
        return f"status_{enrollment.pk}"

    def statuses(self):
        for enrollment in self.enrollments:
            status = self.cleaned_data.get(self.field_name(enrollment))
            if status:
                yield enrollment, status


class AttendanceCorrectionForm(forms.Form):
    """Correct a captured attendance status, recording a reason."""

    status = forms.ChoiceField(choices=AttendanceStatus.choices)
    reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, entry=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.entry = entry
        if entry is not None and not self.is_bound:
            self.fields["status"].initial = entry.status


class AttendanceRangeForm(forms.Form):
    """An optional start/end date range for attendance reporting."""

    start = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    end = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get("start")
        end = cleaned_data.get("end")
        if start is not None and end is not None and start > end:
            raise ValidationError("Start date must not be after the end date.")
        return cleaned_data


class AttendanceRegisterFilterForm(AttendanceRangeForm):
    """Optional Section and date-range filter for the register list."""

    section = forms.ModelChoiceField(
        queryset=Section.objects.select_related("class_grade"), required=False
    )
