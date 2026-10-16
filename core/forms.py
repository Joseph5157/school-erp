from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator

from accounts.usernames import USERNAME_HELP
from core.documents import bonafide
from core.models import (
    TEACHERS_GROUP_NAME,
    AcademicEnrollment,
    AcademicSubjectOffering,
    AcademicTerm,
    AcademicYear,
    Announcement,
    Applicant,
    ApplicantGuardian,
    Assessment,
    AssessmentTeacherAssignment,
    AttendanceRegister,
    AttendanceStatus,
    ClassGrade,
    GradeBoundary,
    GradingScale,
    Guardian,
    GuardianAccount,
    GuardianContactConsent,
    ResultStatus,
    School,
    SchoolCalendarDay,
    Section,
    Student,
    Subject,
    business_today,
)


class SchoolForm(forms.ModelForm):
    SELECTABLE_MODES = (School.NotificationMode.PORTAL_ONLY, School.NotificationMode.ASSIST)

    class Meta:
        model = School
        fields = ["name", "address", "affiliation_number", "principal_name",
                  "notification_channel"]
        widgets = {
            "notification_channel": forms.RadioSelect,
            "address": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["notification_channel"].choices = [
            (value, label) for value, label in School.NotificationMode.choices
            if value in self.SELECTABLE_MODES
        ]

    def clean_notification_channel(self):
        mode = self.cleaned_data["notification_channel"]
        if mode == School.NotificationMode.ASSIST and not settings.PORTAL_BASE_URL:
            raise forms.ValidationError(
                "Set the portal address (PORTAL_BASE_URL) before sending WhatsApp messages."
            )
        return mode


class AcademicYearForm(forms.ModelForm):
    class Meta:
        model = AcademicYear
        fields = ["name", "start_date", "end_date", "saturdays_instructional"]
        labels = {"saturdays_instructional": "Saturdays are instructional days"}
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }


class SchoolCalendarDayForm(forms.ModelForm):
    """Record one calendar exception for a specific Academic Year.

    `academic_year` comes from the URL, not the request body
    (docs/adr/0008-phase-2-school-calendar-rules.md).
    """

    is_instructional = forms.TypedChoiceField(
        label="Type",
        choices=[
            ("False", "Holiday / closure (no attendance expected)"),
            ("True", "Extra instructional day (e.g. working Saturday)"),
        ],
        coerce=lambda value: value == "True",
        widget=forms.RadioSelect,
    )

    class Meta:
        model = SchoolCalendarDay
        fields = ["date", "is_instructional", "label"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, academic_year=None, **kwargs):
        super().__init__(*args, **kwargs)
        if academic_year is not None:
            self.instance.academic_year = academic_year

    def clean(self):
        cleaned_data = super().clean()
        # The (academic_year, date) uniqueness rule cannot be seen by the
        # automatic unique check because academic_year is not a form field.
        date = cleaned_data.get("date")
        if date and SchoolCalendarDay.objects.filter(
            academic_year=self.instance.academic_year, date=date
        ).exists():
            raise ValidationError(
                {"date": "This date already has a calendar exception for this Academic Year."}
            )
        return cleaned_data


class SchoolCalendarDayLabelForm(forms.ModelForm):
    """Change only the label of an existing calendar exception."""

    class Meta:
        model = SchoolCalendarDay
        fields = ["label"]


class CalendarDateCheckForm(forms.Form):
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))


class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ["name", "code", "is_active"]
        labels = {"is_active": "Active"}
        help_texts = {"code": "Optional short code, e.g. MATH. Stored in capitals."}


class AcademicTermForm(forms.ModelForm):
    """Create or change a Term; `academic_year` comes from the URL."""

    class Meta:
        model = AcademicTerm
        fields = ["name", "start_date", "end_date", "display_order"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, academic_year=None, **kwargs):
        super().__init__(*args, **kwargs)
        if academic_year is not None:
            self.instance.academic_year = academic_year

    def clean(self):
        cleaned_data = super().clean()
        year = self.instance.academic_year
        for field in ("name", "display_order"):
            value = cleaned_data.get(field)
            if value in (None, ""):
                continue
            clash = AcademicTerm.objects.filter(academic_year=year, **{field: value})
            if self.instance.pk is not None:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                self.add_error(field, "Another Term in this Academic Year already uses this.")
        return cleaned_data


class SubjectOfferingForm(forms.Form):
    """Offer a Subject to a Class/Grade in an Academic Year, optionally to some Sections.

    Leaving every Section unticked means the offering applies to all Sections
    of the Grade (ADR 0009).
    """

    class_grade = forms.ModelChoiceField(queryset=ClassGrade.objects.all(), label="Class/Grade")
    subject = forms.ModelChoiceField(queryset=Subject.objects.filter(is_active=True))
    sections = forms.ModelMultipleChoiceField(
        queryset=Section.objects.select_related("class_grade"),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Leave all unticked to offer the Subject to every Section of the Grade.",
    )

    def __init__(self, *args, academic_year=None, offering=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.academic_year = academic_year
        self.offering = offering
        if offering is not None:
            # Grade and Subject are fixed once offered; only the scope changes.
            del self.fields["class_grade"]
            del self.fields["subject"]
            self.fields["sections"].queryset = offering.class_grade.sections.all()
            if not self.is_bound:
                self.fields["sections"].initial = list(offering.sections)

    def clean(self):
        cleaned_data = super().clean()
        grade = (
            self.offering.class_grade if self.offering else cleaned_data.get("class_grade")
        )
        sections = cleaned_data.get("sections") or []
        if grade is not None and any(s.class_grade_id != grade.pk for s in sections):
            self.add_error("sections", "Every Section must belong to the selected Class/Grade.")
        subject = cleaned_data.get("subject")
        if (
            self.offering is None
            and grade is not None
            and subject is not None
            and AcademicSubjectOffering.objects.filter(
                academic_year=self.academic_year, class_grade=grade, subject=subject
            ).exists()
        ):
            raise ValidationError("This Subject is already offered to this Class/Grade this year.")
        return cleaned_data


class ClassTeacherAssignForm(forms.Form):
    """Make a teacher class teacher of a Section from a date (ADR 0011)."""

    section = forms.ModelChoiceField(queryset=Section.objects.select_related("class_grade"))
    teacher = forms.ModelChoiceField(queryset=get_user_model().objects.none())
    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, academic_year=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.academic_year = academic_year
        self.fields["teacher"].queryset = (
            get_user_model()
            .objects.filter(groups__name=TEACHERS_GROUP_NAME, is_active=True)
            .order_by("username")
        )
        self.fields["teacher"].label_from_instance = (
            lambda user: f"{user.get_full_name() or user.username} ({user.username})"
        )


class ClassTeacherEndForm(forms.Form):
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Last day (inclusive) this teacher is class teacher.",
    )


class TeacherAssignmentForm(forms.Form):
    """Assign the teacher who enters results for one offering in one Section."""

    teacher = forms.ModelChoiceField(queryset=get_user_model().objects.none())
    offering = forms.ModelChoiceField(
        queryset=AcademicSubjectOffering.objects.none(), label="Subject offering"
    )
    section = forms.ModelChoiceField(queryset=Section.objects.select_related("class_grade"))

    def __init__(self, *args, academic_year=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.academic_year = academic_year
        self.fields["teacher"].queryset = (
            get_user_model()
            .objects.filter(groups__name=TEACHERS_GROUP_NAME, is_active=True)
            .order_by("username")
        )
        self.fields["teacher"].label_from_instance = (
            lambda user: f"{user.get_full_name() or user.username} ({user.username})"
        )
        if academic_year is not None:
            self.fields["offering"].queryset = AcademicSubjectOffering.objects.filter(
                academic_year=academic_year
            ).select_related("class_grade", "subject", "academic_year")

    def clean(self):
        cleaned_data = super().clean()
        offering = cleaned_data.get("offering")
        section = cleaned_data.get("section")
        if offering is None or section is None:
            return cleaned_data
        if not offering.applies_to(section):
            self.add_error("section", "This Section does not take this Subject offering.")
        elif AssessmentTeacherAssignment.objects.filter(
            offering=offering, section=section
        ).exists():
            raise ValidationError(
                "A teacher is already assigned to this Subject and Section; remove that "
                "assignment first."
            )
        return cleaned_data


class GradingScaleForm(forms.Form):
    """Name a grading scale and choose the Grades it applies to."""

    name = forms.CharField(max_length=100)
    class_grades = forms.ModelMultipleChoiceField(
        queryset=ClassGrade.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Applies to Class/Grades",
        help_text="Each Grade can use only one scale per Academic Year.",
    )

    def __init__(self, *args, academic_year=None, scale=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.academic_year = academic_year
        self.scale = scale
        if scale is not None and not self.is_bound:
            self.fields["name"].initial = scale.name
            self.fields["class_grades"].initial = list(scale.class_grades)

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        clash = GradingScale.objects.filter(academic_year=self.academic_year, name=name)
        if self.scale is not None:
            clash = clash.exclude(pk=self.scale.pk)
        if clash.exists():
            raise ValidationError("Another scale in this Academic Year has this name.")
        return name


class GradeBoundaryForm(forms.ModelForm):
    class Meta:
        model = GradeBoundary
        fields = ["min_percentage", "label"]
        labels = {"min_percentage": "From percentage", "label": "Grade"}

    def __init__(self, *args, scale=None, **kwargs):
        super().__init__(*args, **kwargs)
        if scale is not None:
            self.instance.scale = scale

    def clean(self):
        cleaned_data = super().clean()
        scale = self.instance.scale
        for field in ("label", "min_percentage"):
            value = cleaned_data.get(field)
            if value not in (None, "") and scale.boundaries.filter(**{field: value}).exists():
                self.add_error(field, "This scale already has a band with this value.")
        return cleaned_data


class AssessmentForm(forms.ModelForm):
    """Plan an assessment in one Academic Year (ADR 0009)."""

    class Meta:
        model = Assessment
        fields = [
            "term", "offering", "section", "name", "assessment_date",
            "maximum_marks", "pass_mark",
        ]
        labels = {"offering": "Subject"}
        help_texts = {"pass_mark": "Optional. Leave empty for no pass/fail."}
        widgets = {"assessment_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, academic_year=None, **kwargs):
        super().__init__(*args, **kwargs)
        year = academic_year or (self.instance.term.academic_year if self.instance.pk else None)
        if year is not None:
            self.fields["term"].queryset = year.terms.all()
            self.fields["offering"].queryset = AcademicSubjectOffering.objects.filter(
                academic_year=year
            ).select_related("class_grade", "subject", "academic_year")
        self.fields["section"].queryset = Section.objects.select_related("class_grade")
        if self.instance.pk and self.instance.is_locked:
            for name in ("term", "offering", "section", "assessment_date", "maximum_marks"):
                self.fields[name].disabled = True


class AssessmentFilterForm(forms.Form):
    term = forms.ModelChoiceField(queryset=AcademicTerm.objects.none(), required=False)
    status = forms.ChoiceField(
        choices=[("", "Any status"), *Assessment.Status.choices], required=False
    )
    section = forms.ModelChoiceField(
        queryset=Section.objects.select_related("class_grade"), required=False
    )

    def __init__(self, *args, academic_year=None, **kwargs):
        super().__init__(*args, **kwargs)
        if academic_year is not None:
            self.fields["term"].queryset = academic_year.terms.all()


class ResultEntryForm(forms.Form):
    """Bulk DRAFT marks entry for an assessment's date-effective roster.

    One optional status (Marked/Absent) and score per Student, pre-filled
    from saved results. A score with no status counts as Marked; Absent takes
    no score; unanswered rows stay unmarked (never Absent).
    """

    def __init__(self, *args, assessment=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.assessment = assessment
        saved = {r.academic_enrollment_id: r for r in assessment.results.all()}
        self.enrollments = list(assessment.roster())
        for enrollment in self.enrollments:
            result = saved.get(enrollment.pk)
            self.fields[self.status_name(enrollment)] = forms.ChoiceField(
                # A saved result cannot be un-entered here, so do not offer it.
                choices=(list(ResultStatus.choices) if result
                         else [("", "Not entered"), *ResultStatus.choices]),
                required=False,
                label=str(enrollment.student),
                initial=result.status if result else "",
                widget=forms.RadioSelect,
            )
            self.fields[self.score_name(enrollment)] = forms.DecimalField(
                required=False,
                min_value=0,
                max_value=assessment.maximum_marks,
                decimal_places=2,
                max_digits=6,
                label="Score",
                initial=result.score if result else None,
                widget=forms.NumberInput(attrs={
                    "step": "0.01", "inputmode": "decimal", "enterkeyhint": "next",
                    "class": "form-control erp-score",
                }),
            )

    @staticmethod
    def status_name(enrollment):
        return f"status_{enrollment.pk}"

    @staticmethod
    def score_name(enrollment):
        return f"score_{enrollment.pk}"

    def clean(self):
        cleaned_data = super().clean()
        for enrollment in self.enrollments:
            status = cleaned_data.get(self.status_name(enrollment))
            score = cleaned_data.get(self.score_name(enrollment))
            if not status and score is not None:
                cleaned_data[self.status_name(enrollment)] = status = ResultStatus.MARKED
            if status == ResultStatus.MARKED and score is None:
                self.add_error(self.score_name(enrollment), "Enter a score or choose Absent.")
            if status == ResultStatus.ABSENT and score is not None:
                self.add_error(self.score_name(enrollment), "An absent Student has no score.")
        return cleaned_data

    def rows(self):
        for enrollment in self.enrollments:
            yield (
                enrollment,
                self[self.status_name(enrollment)],
                self[self.score_name(enrollment)],
            )

    def counts(self):
        """Display counts: a score with no status is marked; blank is never absent."""
        marked = absent = 0
        for enrollment in self.enrollments:
            status = self[self.status_name(enrollment)].value() or ""
            score = self[self.score_name(enrollment)].value()
            if status == ResultStatus.ABSENT:
                absent += 1
            elif status == ResultStatus.MARKED or score not in (None, ""):
                marked += 1
        total = len(self.enrollments)
        return {"all": total, "marked": marked, "absent": absent,
                "unmarked": total - marked - absent}

    def answers(self):
        for enrollment in self.enrollments:
            status = self.cleaned_data.get(self.status_name(enrollment))
            if status:
                yield enrollment, status, self.cleaned_data.get(self.score_name(enrollment))


class ResultCorrectionForm(forms.Form):
    """Correct one finalized result, with a required reason."""

    status = forms.ChoiceField(choices=ResultStatus.choices, label="Correct result")
    score = forms.DecimalField(
        required=False, min_value=0, decimal_places=2, max_digits=6,
        help_text="Required for Marked; leave empty for Absent.",
    )
    reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, result=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.result = result
        self.fields["score"].max_value = result.assessment.maximum_marks
        self.fields["score"].validators.append(
            MaxValueValidator(
                result.assessment.maximum_marks
            )
        )
        if not self.is_bound:
            self.fields["status"].initial = result.status
            self.fields["score"].initial = result.score

    def clean(self):
        cleaned_data = super().clean()
        status, score = cleaned_data.get("status"), cleaned_data.get("score")
        if status == ResultStatus.MARKED and score is None:
            self.add_error("score", "Enter the corrected score.")
        if status == ResultStatus.ABSENT and score is not None:
            self.add_error("score", "An absent Student has no score.")
        return cleaned_data


class OfferedSubjectsLookupForm(forms.Form):
    section = forms.ModelChoiceField(queryset=Section.objects.select_related("class_grade"))
    term = forms.ModelChoiceField(queryset=AcademicTerm.objects.none(), required=False)

    def __init__(self, *args, academic_year=None, **kwargs):
        super().__init__(*args, **kwargs)
        if academic_year is not None:
            self.fields["term"].queryset = academic_year.terms.all()


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

    `start_date` is the business-effective date of the new placement
    (docs/adr/0006-academic-enrollment-effective-dating.md). It must be stated
    explicitly; when it replaces a current placement, that placement is closed
    on the day before.
    """

    class Meta:
        model = AcademicEnrollment
        fields = ["academic_year", "class_grade", "section", "start_date"]
        labels = {"start_date": "Effective start date"}
        widgets = {"start_date": forms.DateInput(attrs={"type": "date"})}

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
    reason = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))


class StudentStatusForm(forms.Form):
    """The explicit Student status change permitted in Phase 1.

    Only the frozen ACTIVE/INACTIVE set is offered
    (docs/adr/0003-phase-1-status-and-transition-rules.md); the model workflow
    rejects unknown values or no-op changes as a second line of defence.
    """

    status = forms.ChoiceField(choices=Student.Status.choices)
    reason = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))


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
    error and again in the model (docs/adr/0007). The date-within-Academic-Year
    rule and the one-register-per-section-per-date rule are enforced by the
    model's clean/constraints when the form is validated. `status` and the
    submission fields are deliberately not form fields: a register opened
    here is always DRAFT, and submission is a separate Gate 4 workflow.
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
    """Mark the date-effective roster of a DRAFT register.

    One optional PRESENT/ABSENT choice and one optional absence note per
    roster enrollment, pre-filled from any existing entries. Unanswered rows
    stay unmarked (a draft may be incomplete; unmarked is never ABSENT). A
    note is accepted only for an ABSENT choice.
    """

    def __init__(self, *args, register=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.register = register
        self.enrollments = []
        if register is not None:
            existing = {
                entry.academic_enrollment_id: entry for entry in register.entries.all()
            }
            self.enrollments = list(register.eligible_enrollments())
            for enrollment in self.enrollments:
                entry = existing.get(enrollment.pk)
                self.fields[self.field_name(enrollment)] = forms.ChoiceField(
                    choices=AttendanceStatus.choices,
                    required=False,
                    widget=forms.RadioSelect,
                    label=str(enrollment.student),
                    initial=entry.status if entry else None,
                )
                self.fields[self.note_name(enrollment)] = forms.CharField(
                    required=False,
                    label="Absence note",
                    initial=entry.absence_note if entry else "",
                    widget=forms.TextInput(attrs={"placeholder": "Optional, absent only"}),
                )

    @staticmethod
    def field_name(enrollment):
        return f"status_{enrollment.pk}"

    @staticmethod
    def note_name(enrollment):
        return f"note_{enrollment.pk}"

    def clean(self):
        cleaned_data = super().clean()
        for enrollment in self.enrollments:
            status = cleaned_data.get(self.field_name(enrollment))
            note = (cleaned_data.get(self.note_name(enrollment)) or "").strip()
            if note and status != AttendanceStatus.ABSENT:
                self.add_error(
                    self.note_name(enrollment), "Only an absent Student can have a note."
                )
        return cleaned_data

    def rows(self):
        """(enrollment, status bound field, note bound field) for templates."""
        for enrollment in self.enrollments:
            yield enrollment, self[self.field_name(enrollment)], self[self.note_name(enrollment)]

    def statuses(self):
        """(enrollment, status, note) for every answered roster row."""
        for enrollment in self.enrollments:
            status = self.cleaned_data.get(self.field_name(enrollment))
            if status:
                note = (self.cleaned_data.get(self.note_name(enrollment)) or "").strip()
                yield enrollment, status, note

    def counts(self):
        """Roster counts for display: all, present, absent and unmarked rows.

        Uses each field's current value, so a re-rendered bound form counts
        the posted choices. Unanswered rows are unmarked, never absent.
        """
        values = [self[self.field_name(e)].value() or "" for e in self.enrollments]
        present = sum(1 for v in values if v == AttendanceStatus.PRESENT)
        absent = sum(1 for v in values if v == AttendanceStatus.ABSENT)
        return {
            "all": len(values),
            "present": present,
            "absent": absent,
            "unmarked": len(values) - present - absent,
        }


class AttendanceCorrectionForm(forms.Form):
    """Correct submitted attendance, recording a reason and optional absence note."""

    status = forms.ChoiceField(choices=AttendanceStatus.choices)
    absence_note = forms.CharField(
        required=False,
        label="Absence note",
        help_text="Optional; only for a correction to Absent.",
    )
    reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}))

    def clean(self):
        cleaned_data = super().clean()
        note = (cleaned_data.get("absence_note") or "").strip()
        if note and cleaned_data.get("status") != AttendanceStatus.ABSENT:
            self.add_error("absence_note", "Only an absent Student can have a note.")
        return cleaned_data

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


class AttendanceDateForm(forms.Form):
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))


class MissingAttendanceForm(AttendanceRangeForm):
    """Date range (required) and optional Section for the missing report."""

    start = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    end = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    section = forms.ModelChoiceField(
        queryset=Section.objects.select_related("class_grade"), required=False
    )

    MAX_DAYS = 400

    def clean(self):
        cleaned_data = super().clean()
        start, end = cleaned_data.get("start"), cleaned_data.get("end")
        if start and end and (end - start).days > self.MAX_DAYS:
            raise ValidationError(f"Choose a range of at most {self.MAX_DAYS} days.")
        return cleaned_data


class MonthlySectionSummaryForm(forms.Form):
    section = forms.ModelChoiceField(queryset=Section.objects.select_related("class_grade"))
    month = forms.CharField(
        widget=forms.DateInput(attrs={"type": "month"}), help_text="YYYY-MM"
    )

    def clean_month(self):
        value = self.cleaned_data["month"].strip()
        try:
            year, month = (int(part) for part in value.split("-"))
            if not 1 <= month <= 12 or year < 1900:
                raise ValueError
        except ValueError:
            raise ValidationError("Enter a month as YYYY-MM.") from None
        return year, month


class AttendanceRegisterFilterForm(AttendanceRangeForm):
    """Optional Section and date-range filter for the register list."""

    section = forms.ModelChoiceField(
        queryset=Section.objects.select_related("class_grade"), required=False
    )


# --- Phase 6 Gate 1: guardian accounts (ADR 0013) ----------------------------


class GuardianVerificationForm(forms.Form):
    identity_verification_method = forms.ChoiceField(
        choices=GuardianAccount.VerificationMethod.choices,
        label="How was the guardian's identity verified?",
    )
    identity_verification_note = forms.CharField(
        max_length=200, label="Verification note",
        help_text="For example which document was seen and by whom. No document numbers.",
    )


class GuardianAccountCreateForm(GuardianVerificationForm):
    username = forms.CharField(max_length=30, help_text=USERNAME_HELP)
    field_order = ["username", "identity_verification_method", "identity_verification_note"]


class GuardianAccountLinkForm(GuardianVerificationForm):
    username = forms.CharField(
        max_length=150, label="Existing login username",
        help_text="The exact username of the person's existing login. Nothing is matched "
                  "by name, phone or email.",
    )
    field_order = ["username", "identity_verification_method", "identity_verification_note"]


class GuardianUsernameForm(forms.Form):
    username = forms.CharField(max_length=30, label="New username", help_text=USERNAME_HELP)


class RevocationForm(forms.Form):
    reason = forms.CharField(max_length=200, help_text="Recorded permanently with the revocation.")


# --- Phase 6 Gate 4: administrator-entered identifiers (ADR 0014, OD-1) ------


class AdmissionNumberForm(forms.Form):
    admission_number = forms.CharField(
        max_length=30, required=False,
        help_text="Leave empty to clear. Never generated; must be unique in the school.",
    )


class RollNumberForm(forms.Form):
    roll_number = forms.IntegerField(
        min_value=1, max_value=32767, required=False,
        help_text="Leave empty to clear. Unique within this Section and Academic Year.",
    )


# --- Phase 7: bulk import (ADR 0017) -----------------------------------------


class ImportUploadForm(forms.Form):
    """Choose the Academic Year, the enrollment start date and the workbook."""

    academic_year = forms.ModelChoiceField(queryset=AcademicYear.objects.all())
    enrollment_start_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Every imported student is placed from this date. It must fall within "
        "the Academic Year and cannot be in the future.",
    )
    file = forms.FileField(help_text="An .xlsx workbook based on the import template, up to 2 MB.")

    def clean_file(self):
        from core.imports import MAX_FILE_BYTES

        upload = self.cleaned_data["file"]
        if not upload.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Upload an Excel .xlsx workbook.")
        if upload.size > MAX_FILE_BYTES:
            raise forms.ValidationError("The file is larger than 2 MB.")
        return upload

    def clean(self):
        cleaned = super().clean()
        year = cleaned.get("academic_year")
        start = cleaned.get("enrollment_start_date")
        if year and start:
            if not year.contains(start):
                self.add_error("enrollment_start_date",
                               "The start date must fall within the Academic Year.")
            elif start > business_today():
                self.add_error("enrollment_start_date", "The start date cannot be in the future.")
        return cleaned


# --- Phase 7 Gate 1: guardian consent (ADR 0015) ---------------------------


class ContactConsentForm(forms.Form):
    status = forms.ChoiceField(
        choices=GuardianContactConsent.Status.choices, widget=forms.RadioSelect, label="Decision"
    )
    source = forms.ChoiceField(
        choices=GuardianContactConsent.Source.choices, label="How",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    note = forms.CharField(
        max_length=200, required=False, label="Note (optional)",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )


class AttendanceSummaryForm(forms.Form):
    section = forms.ModelChoiceField(
        Section.objects.select_related("class_grade").order_by("class_grade__name", "name")
    )
    start = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    end = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))


class DocumentStudentForm(forms.Form):
    student = forms.ModelChoiceField(Student.objects.order_by("full_name"))


class BonafideForm(forms.Form):
    student = forms.ModelChoiceField(Student.objects.order_by("full_name"))
    purpose = forms.ChoiceField(choices=bonafide.PURPOSES)
    purpose_text = forms.CharField(
        max_length=120, required=False, label="Purpose (if Other)",
    )


class AnnouncementForm(forms.Form):
    title = forms.CharField(max_length=120)
    body = forms.CharField(max_length=2000, widget=forms.Textarea(attrs={"rows": 6}),
                           help_text="Plain text. Line breaks are kept.")
    audience = forms.ChoiceField(choices=Announcement.Audience.choices,
                                 widget=forms.RadioSelect, initial=Announcement.Audience.ALL)
    class_grade = forms.ModelChoiceField(ClassGrade.objects.order_by("name"), required=False,
                                         label="Class")
    section = forms.ModelChoiceField(
        Section.objects.select_related("class_grade").order_by("class_grade__name", "name"),
        required=False,
    )

    def clean(self):
        data = super().clean()
        audience = data.get("audience")
        if audience == Announcement.Audience.CLASS and not data.get("class_grade"):
            self.add_error("class_grade", "Choose the class.")
        if audience == Announcement.Audience.SECTION and not data.get("section"):
            self.add_error("section", "Choose the section.")
        return data
