from datetime import timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, OuterRef, Q, Subquery
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import add_never_cache_headers

from accounts.models import SecurityEvent
from core import (
    assessment_reports,
    assignments,
    dashboard,
    guardian_access,
    guardian_accounts,
    publication,
    reports,
    setup_checklist,
)
from core.authorization import (
    administrator_required,
    can_enter_results,
    can_take_attendance,
    can_view_report_card_as_teacher,
    can_write_term_remarks,
    class_teacher_assignments,
    class_teacher_on,
    guardian_contact_visible,
    is_teacher,
    teacher_assignments,
    teacher_required,
    teacher_student_scope,
    term_remark_sections,
    user_areas,
)
from core.forms import (
    AcademicEnrollmentForm,
    AcademicTermForm,
    AcademicYearForm,
    AdmissionDecisionForm,
    AdmissionNumberForm,
    ApplicantForm,
    ApplicantGuardianForm,
    AssessmentFilterForm,
    AssessmentForm,
    AttendanceCaptureForm,
    AttendanceCorrectionForm,
    AttendanceDateForm,
    AttendanceRangeForm,
    AttendanceRegisterFilterForm,
    AttendanceRegisterForm,
    CalendarDateCheckForm,
    ClassGradeForm,
    ClassTeacherAssignForm,
    ClassTeacherEndForm,
    ContactConsentForm,
    GradeBoundaryForm,
    GradingScaleForm,
    GuardianAccountCreateForm,
    GuardianAccountLinkForm,
    GuardianForm,
    GuardianUsernameForm,
    MissingAttendanceForm,
    MonthlySectionSummaryForm,
    OfferedSubjectsLookupForm,
    ResultCorrectionForm,
    ResultEntryForm,
    RevocationForm,
    RollNumberForm,
    SchoolCalendarDayForm,
    SchoolCalendarDayLabelForm,
    SchoolForm,
    SectionForm,
    StudentStatusForm,
    SubjectForm,
    SubjectOfferingForm,
    TeacherAssignmentForm,
)
from core.models import (
    AcademicEnrollment,
    AcademicSubjectOffering,
    AcademicTerm,
    AcademicYear,
    Applicant,
    Assessment,
    AssessmentTeacherAssignment,
    AttendanceEntry,
    AttendanceRegister,
    AttendanceStatus,
    ClassGrade,
    GradeBoundary,
    GradingScale,
    Guardian,
    GuardianAccessReview,
    GuardianAccount,
    GuardianStudentAccess,
    School,
    SchoolCalendarDay,
    Section,
    SectionClassTeacher,
    Student,
    StudentGuardian,
    StudentResult,
    Subject,
    TermPublication,
    TermRemark,
    business_today,
)
from core.tables import Column, build_table, parse_choice


@administrator_required("core.view_school")
def school_detail(request):
    school = School.objects.first()
    if school is None:
        return redirect("core:school-create")
    return render(request, "core/school_detail.html", {"school": school})


@administrator_required("core.add_school")
def school_create(request):
    if School.objects.exists():
        return redirect("core:school-detail")

    if request.method == "POST":
        form = SchoolForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
            except IntegrityError:
                # Another request created the School between the exists()
                # check above and this save() -- treat it the same as the
                # early-exit above rather than surfacing a raw 500.
                messages.info(request, "A School configuration already exists.")
                return redirect("core:school-detail")
            messages.success(request, "School configuration created.")
            return redirect("core:school-detail")
    else:
        form = SchoolForm()
    return render(request, "core/school_form.html", {"form": form, "creating": True})


@administrator_required("core.change_school")
def school_update(request):
    school = School.objects.first()
    if school is None:
        return redirect("core:school-create")

    if request.method == "POST":
        form = SchoolForm(request.POST, instance=school)
        if form.is_valid():
            form.save()
            messages.success(request, "School configuration updated.")
            return redirect("core:school-detail")
    else:
        form = SchoolForm(instance=school)
    return render(request, "core/school_form.html", {"form": form, "creating": False})


@administrator_required("core.view_academicyear")
def academic_year_list(request):
    academic_years = AcademicYear.objects.all()
    return render(request, "core/academic_year_list.html", {"academic_years": academic_years})


@administrator_required("core.add_academicyear")
def academic_year_create(request):
    if request.method == "POST":
        form = AcademicYearForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Academic Year created.")
            return redirect("core:academic-year-list")
    else:
        form = AcademicYearForm()
    return render(request, "core/academic_year_form.html", {"form": form})


@administrator_required("core.view_schoolcalendarday")
def academic_year_calendar(request, pk):
    academic_year = get_object_or_404(AcademicYear, pk=pk)
    check_form = CalendarDateCheckForm(request.GET or None)
    check_result = None
    if check_form.is_bound and check_form.is_valid():
        checked = check_form.cleaned_data["date"]
        check_result = {
            "date": checked,
            "in_year": academic_year.contains(checked),
            "instructional": academic_year.is_instructional_day(checked),
        }
    return render(
        request,
        "core/academic_year_calendar.html",
        {
            "academic_year": academic_year,
            "calendar_days": academic_year.calendar_days.all(),
            "check_form": check_form,
            "check_result": check_result,
        },
    )


@administrator_required("core.add_schoolcalendarday")
def calendar_day_create(request, pk):
    academic_year = get_object_or_404(AcademicYear, pk=pk)
    if request.method == "POST":
        form = SchoolCalendarDayForm(request.POST, academic_year=academic_year)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
            except IntegrityError:
                messages.error(
                    request, "This date already has a calendar exception for this Academic Year."
                )
            else:
                messages.success(request, "Calendar exception recorded.")
                return redirect("core:academic-year-calendar", pk=academic_year.pk)
    else:
        form = SchoolCalendarDayForm(academic_year=academic_year)
    return render(
        request,
        "core/calendar_day_form.html",
        {"form": form, "academic_year": academic_year, "creating": True},
    )


@administrator_required("core.change_schoolcalendarday")
def calendar_day_update(request, pk):
    calendar_day = get_object_or_404(SchoolCalendarDay, pk=pk)
    if request.method == "POST":
        form = SchoolCalendarDayLabelForm(request.POST, instance=calendar_day)
        if form.is_valid():
            form.save()
            messages.success(request, "Calendar exception updated.")
            return redirect("core:academic-year-calendar", pk=calendar_day.academic_year_id)
    else:
        form = SchoolCalendarDayLabelForm(instance=calendar_day)
    return render(
        request,
        "core/calendar_day_form.html",
        {
            "form": form,
            "academic_year": calendar_day.academic_year,
            "calendar_day": calendar_day,
            "creating": False,
        },
    )


@administrator_required("core.delete_schoolcalendarday")
def calendar_day_delete(request, pk):
    calendar_day = get_object_or_404(SchoolCalendarDay, pk=pk)
    academic_year_id = calendar_day.academic_year_id
    if request.method == "POST":
        try:
            calendar_day.delete()
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            messages.success(request, "Calendar exception removed.")
    return redirect("core:academic-year-calendar", pk=academic_year_id)


@administrator_required("core.change_schoolcalendarday")
def academic_year_saturday_rule(request, pk):
    academic_year = get_object_or_404(AcademicYear, pk=pk)
    if request.method == "POST":
        try:
            academic_year.set_saturdays_instructional(
                request.POST.get("saturdays_instructional") == "true"
            )
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            messages.success(request, "Saturday rule updated.")
    return redirect("core:academic-year-calendar", pk=academic_year.pk)


# --- Phase 4 Gate 1: Subjects, Terms, subject offerings (ADR 0009) ---------


@administrator_required("core.view_subject")
def subject_list(request):
    return render(request, "core/subject_list.html", {"subjects": Subject.objects.all()})


@administrator_required("core.add_subject")
def subject_create(request):
    form = SubjectForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Subject created.")
        return redirect("core:subject-list")
    return render(request, "core/subject_form.html", {"form": form, "creating": True})


@administrator_required("core.change_subject")
def subject_update(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    form = SubjectForm(request.POST or None, instance=subject)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Subject updated.")
        return redirect("core:subject-list")
    return render(
        request, "core/subject_form.html", {"form": form, "creating": False, "subject": subject}
    )


@administrator_required("core.view_academicterm")
def academic_year_terms(request, pk):
    academic_year = get_object_or_404(AcademicYear, pk=pk)
    return render(
        request,
        "core/academic_year_terms.html",
        {"academic_year": academic_year, "terms": academic_year.terms.all()},
    )


@administrator_required("core.add_academicterm")
def term_create(request, pk):
    academic_year = get_object_or_404(AcademicYear, pk=pk)
    form = AcademicTermForm(request.POST or None, academic_year=academic_year)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Term created.")
        return redirect("core:academic-year-terms", pk=academic_year.pk)
    return render(
        request,
        "core/term_form.html",
        {"form": form, "academic_year": academic_year, "creating": True},
    )


@administrator_required("core.change_academicterm")
def term_update(request, pk):
    term = get_object_or_404(AcademicTerm.objects.select_related("academic_year"), pk=pk)
    form = AcademicTermForm(request.POST or None, instance=term)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Term updated.")
        return redirect("core:academic-year-terms", pk=term.academic_year_id)
    return render(
        request,
        "core/term_form.html",
        {"form": form, "academic_year": term.academic_year, "creating": False},
    )


@administrator_required("core.view_academicsubjectoffering")
def academic_year_offerings(request, pk):
    academic_year = get_object_or_404(AcademicYear, pk=pk)
    offerings = (
        AcademicSubjectOffering.objects.filter(academic_year=academic_year)
        .select_related("class_grade", "subject")
        .prefetch_related("section_links__section")
        .order_by("class_grade__name", "subject__name")
    )
    lookup = OfferedSubjectsLookupForm(request.GET or None, academic_year=academic_year)
    offered = None
    if lookup.is_valid():
        section = lookup.cleaned_data["section"]
        term = lookup.cleaned_data.get("term")
        queryset = (
            AcademicSubjectOffering.objects.for_term_section(term, section)
            if term is not None
            else AcademicSubjectOffering.objects.for_section(academic_year, section)
        )
        offered = queryset.select_related("subject").order_by("subject__name")
    return render(
        request,
        "core/academic_year_offerings.html",
        {
            "academic_year": academic_year,
            "offerings": offerings,
            "lookup": lookup,
            "offered": offered,
        },
    )


@administrator_required("core.add_academicsubjectoffering")
def offering_create(request, pk):
    academic_year = get_object_or_404(AcademicYear, pk=pk)
    form = SubjectOfferingForm(request.POST or None, academic_year=academic_year)
    if request.method == "POST" and form.is_valid():
        offering = AcademicSubjectOffering(
            academic_year=academic_year,
            class_grade=form.cleaned_data["class_grade"],
            subject=form.cleaned_data["subject"],
        )
        try:
            with transaction.atomic():
                offering.full_clean()
                offering.save()
                offering.set_sections(form.cleaned_data["sections"])
        except ValidationError as error:
            form.add_error(None, error)
        except IntegrityError:
            form.add_error(None, "This Subject is already offered to this Class/Grade this year.")
        else:
            messages.success(request, "Subject offering created.")
            return redirect("core:academic-year-offerings", pk=academic_year.pk)
    return render(
        request,
        "core/offering_form.html",
        {"form": form, "academic_year": academic_year, "offering": None},
    )


@administrator_required("core.change_academicsubjectoffering")
def offering_update(request, pk):
    offering = get_object_or_404(
        AcademicSubjectOffering.objects.select_related("academic_year", "class_grade", "subject"),
        pk=pk,
    )
    form = SubjectOfferingForm(
        request.POST or None, academic_year=offering.academic_year, offering=offering
    )
    if request.method == "POST" and form.is_valid():
        try:
            offering.set_sections(form.cleaned_data["sections"])
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Section scope updated.")
            return redirect("core:academic-year-offerings", pk=offering.academic_year_id)
    return render(
        request,
        "core/offering_form.html",
        {"form": form, "academic_year": offering.academic_year, "offering": offering},
    )


# --- Phase 4 Gate 4: assessment planning (ADR 0009) ------------------------


def _assessments():
    return Assessment.objects.select_related(
        "term__academic_year",
        "offering__subject",
        "offering__class_grade",
        "offering__academic_year",
        "section__class_grade",
    )


@administrator_required("core.view_assessment")
def academic_year_assessments(request, pk):
    academic_year = get_object_or_404(AcademicYear, pk=pk)
    form = AssessmentFilterForm(request.GET or None, academic_year=academic_year)
    assessments = _assessments().filter(term__academic_year=academic_year)
    if form.is_valid():
        if form.cleaned_data.get("term"):
            assessments = assessments.filter(term=form.cleaned_data["term"])
        if form.cleaned_data.get("section"):
            assessments = assessments.filter(section=form.cleaned_data["section"])
        if form.cleaned_data.get("status"):
            assessments = assessments.filter(status=form.cleaned_data["status"])
    return render(
        request,
        "core/assessment_list.html",
        {
            "academic_year": academic_year,
            "assessments": assessments.order_by("assessment_date", "offering__subject__name"),
            "form": form,
        },
    )


@administrator_required("core.add_assessment")
def assessment_create(request, pk):
    academic_year = get_object_or_404(AcademicYear, pk=pk)
    form = AssessmentForm(request.POST or None, academic_year=academic_year)
    if request.method == "POST" and form.is_valid():
        assessment = form.save()
        messages.success(request, "Assessment planned.")
        return redirect("core:assessment-detail", pk=assessment.pk)
    return render(
        request,
        "core/assessment_form.html",
        {"form": form, "academic_year": academic_year, "assessment": None},
    )


@administrator_required("core.view_assessment")
def assessment_detail(request, pk):
    assessment = get_object_or_404(_assessments(), pk=pk)
    return render(
        request, "core/assessment_detail.html", _assessment_context(assessment)
    )


def _assessment_context(assessment):
    results = {
        r.academic_enrollment_id: r
        for r in assessment.results.select_related("entered_by").prefetch_related("corrections")
    }
    roster = list(assessment.roster())
    rows = [(enrollment, results.get(enrollment.pk)) for enrollment in roster]
    teacher = assessment.offering.teacher_assignments.filter(
        section=assessment.section
    ).select_related("teacher").first()
    return {
        "assessment": assessment,
        "problems": (
            assessment.finalization_problems() if not assessment.is_finalized else []
        ),
        "rows": rows,
        "marked_count": sum(1 for _, r in rows if r is not None),
        "ineligible_results": assessment.ineligible_results().select_related(
            "academic_enrollment__student"
        ),
        "teacher": teacher.teacher if teacher else None,
    }


@administrator_required("core.finalize_assessment")
def assessment_finalize(request, pk):
    assessment = get_object_or_404(Assessment, pk=pk)
    if request.method == "POST":
        try:
            assessment.finalize(actor=request.user)
        except ValidationError as error:
            messages.error(request, "Not finalized: " + " ".join(error.messages))
        else:
            messages.success(request, "Results finalized.")
    return redirect("core:assessment-detail", pk=assessment.pk)


@administrator_required("core.correct_studentresult")
def result_correct(request, pk):
    result = get_object_or_404(
        StudentResult.objects.select_related(
            "assessment__offering__subject", "assessment__section__class_grade",
            "assessment__term", "academic_enrollment__student",
        ),
        pk=pk,
    )
    assessment = result.assessment
    if not assessment.is_finalized:
        messages.info(request, "This assessment is still a draft; the teacher edits results.")
        return redirect("core:assessment-detail", pk=assessment.pk)
    form = ResultCorrectionForm(request.POST or None, result=result)
    if request.method == "POST" and form.is_valid():
        try:
            result.correct(
                new_status=form.cleaned_data["status"],
                new_score=form.cleaned_data["score"],
                actor=request.user,
                reason=form.cleaned_data["reason"],
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Result corrected.")
            return redirect("core:assessment-detail", pk=assessment.pk)
    return render(
        request,
        "core/result_correction_form.html",
        {
            "form": form,
            "result": result,
            "assessment": assessment,
            "corrections": result.corrections.select_related("corrected_by"),
        },
    )


# --- Phase 4 Gate 9: result reports and Term report cards (ADR 0009) -------


@administrator_required("core.view_studentresult")
def report_result_sheet(request, pk):
    assessment = get_object_or_404(_assessments(), pk=pk)
    return render(
        request,
        "core/report_result_sheet.html",
        {"assessment": assessment, "results": assessment_reports.result_sheet(assessment)},
    )


@administrator_required("core.view_studentresult")
def report_student_results(request, pk):
    student = get_object_or_404(Student, pk=pk)
    terms = (
        AcademicTerm.objects.filter(academic_year__enrollments__student=student)
        .select_related("academic_year")
        .distinct()
        .order_by("academic_year__start_date", "display_order")
    )
    return render(
        request,
        "core/report_student_results.html",
        {
            "student": student,
            "results": assessment_reports.student_history(student),
            "terms": terms,
        },
    )


@administrator_required("core.view_studentresult")
def report_term_report_card(request, pk, term_pk):
    student = get_object_or_404(Student, pk=pk)
    term = get_object_or_404(AcademicTerm.objects.select_related("academic_year"), pk=term_pk)
    return render(
        request,
        "core/report_term_report_card.html",
        assessment_reports.term_report_card(student, term),
    )


@administrator_required("core.view_studentresult")
def report_subject_section_results(request, pk):
    academic_year = get_object_or_404(AcademicYear, pk=pk)
    offerings = AcademicSubjectOffering.objects.filter(academic_year=academic_year).select_related(
        "class_grade", "subject"
    )
    sections = Section.objects.select_related("class_grade")
    terms = academic_year.terms.all()
    offering = section = term = None
    assessments, rows = [], []
    try:
        if request.GET.get("offering"):
            offering = offerings.get(pk=request.GET["offering"])
        if request.GET.get("section"):
            section = sections.get(pk=request.GET["section"])
        if request.GET.get("term"):
            term = terms.get(pk=request.GET["term"])
    except (ValueError, AcademicSubjectOffering.DoesNotExist, Section.DoesNotExist,
            AcademicTerm.DoesNotExist):
        messages.error(request, "Choose a Subject, Section and Term from the lists.")
        offering = section = term = None
    if offering is not None and section is not None:
        assessments, rows = assessment_reports.subject_section_results(offering, section, term)
    return render(
        request,
        "core/report_subject_section_results.html",
        {
            "academic_year": academic_year,
            "offerings": offerings,
            "sections": sections,
            "terms": terms,
            "offering": offering,
            "section": section,
            "term": term,
            "assessments": assessments,
            "rows": rows,
        },
    )


# --- Phase 4 Gate 8: Term remarks (ADR 0009) ------------------------------


@login_required
def term_remarks(request, pk):
    """Write optional Term remarks for one Section (admins, or its teachers)."""
    if not (request.user.has_perm("core.change_termremark") or is_teacher(request.user)):
        raise PermissionDenied
    term = get_object_or_404(AcademicTerm.objects.select_related("academic_year"), pk=pk)
    if request.user.has_perm("core.change_termremark"):
        sections = Section.objects.select_related("class_grade")
    else:
        sections = term_remark_sections(request.user, term)
    section_id = request.POST.get("section") or request.GET.get("section")
    section = None
    if section_id:
        section = get_object_or_404(sections, pk=section_id)
        if not can_write_term_remarks(request.user, term, section):
            raise PermissionDenied
    students, remarks = [], {}
    if section is not None:
        students = term.section_roster(section)
        remarks = {
            r.student_id: r
            for r in TermRemark.objects.filter(term=term, student__in=students).select_related(
                "written_by"
            )
        }
        if request.method == "POST":
            with transaction.atomic():
                for student in students:
                    text = (request.POST.get(f"remark_{student.pk}") or "").strip()
                    existing = remarks.get(student.pk)
                    if text and (existing is None or existing.remark != text):
                        TermRemark.objects.update_or_create(
                            term=term,
                            student=student,
                            defaults={"remark": text, "written_by": request.user},
                        )
                        if existing is not None:
                            publication.mark_stale_for_remark(term, student, actor=request.user)
                    elif not text and existing is not None:
                        publication.mark_stale_for_remark(term, student, actor=request.user)
                        existing.delete()
            messages.success(request, "Remarks saved.")
            return redirect(f"{request.path}?section={section.pk}")
    rows = [(student, remarks.get(student.pk)) for student in students]
    return render(
        request,
        "core/term_remarks.html",
        {"term": term, "sections": sections, "section": section, "rows": rows},
    )


# --- Phase 5 Gate 2: teacher home page (ADR 0011 D11) ---------------------


@login_required
def home(request):
    """Send each login to its own landing page (ADR 0013 multi-role).

    One area: go there. Several: choose explicitly — no role is silently
    picked or hidden. None: the School page, which refuses without access.
    """
    areas = user_areas(request.user)
    if len(areas) > 1:
        return redirect("choose-area")
    if len(areas) == 1:
        return redirect(areas[0][2])
    return redirect("core:school-detail")


@login_required
def choose_area(request):
    areas = user_areas(request.user)
    if len(areas) <= 1:
        return redirect("home")
    return render(request, "core/choose_area.html", {"areas": areas})


@administrator_required("core.view_school")
def admin_overview(request):
    steps = setup_checklist.setup_steps()
    done_count = sum(1 for step in steps if step["done"])
    # The first incomplete step is the "next" one: only it gets the filled button.
    next_key = next((step["key"] for step in steps if not step["done"]), None)
    for step in steps:
        step["is_next"] = step["key"] == next_key
    return render(
        request,
        "core/admin_overview.html",
        {
            "cards": dashboard.overview_cards(request.user),
            "setup_steps": steps,
            "setup_complete": setup_checklist.setup_complete(steps),
            "setup_done": done_count,
            "setup_total": len(steps),
        },
    )


def _open_assessments_needing_marks(user, today):
    """DRAFT assessments in the teacher's Subject/Sections, open for entry,
    with at least one roster Student still unmarked (constant queries)."""
    duties = list(teacher_assignments(user).values_list("offering_id", "section_id"))
    if not duties:
        return []
    scope = Q(pk__in=[])
    for offering_id, section_id in duties:
        scope |= Q(offering_id=offering_id, section_id=section_id)
    roster = AcademicEnrollment.objects.filter(
        academic_year_id=OuterRef("offering__academic_year_id"),
        class_grade_id=OuterRef("offering__class_grade_id"),
        section_id=OuterRef("section_id"),
        start_date__lte=OuterRef("assessment_date"),
    ).filter(Q(end_date__isnull=True) | Q(end_date__gte=OuterRef("assessment_date")))
    unmarked = roster.exclude(
        Exists(
            StudentResult.objects.filter(
                assessment_id=OuterRef(OuterRef("pk")), academic_enrollment_id=OuterRef("pk")
            )
        )
    )
    return list(
        _assessments()
        .filter(scope, status=Assessment.Status.DRAFT, assessment_date__lte=today)
        .annotate(
            unmarked_count=Subquery(
                unmarked.order_by().values("section_id").annotate(n=Count("pk")).values("n")[:1]
            )
        )
        .filter(unmarked_count__gt=0)
        .order_by("assessment_date", "name")
    )


@teacher_required
def my_home(request):
    today = business_today()
    duties = list(
        class_teacher_assignments(request.user, today).select_related(
            "academic_year", "section__class_grade"
        )
    )
    registers = {
        register.section_id: register
        for register in AttendanceRegister.objects.filter(
            date=today, section_id__in=[duty.section_id for duty in duties]
        )
    }
    instructional = {}
    attendance = []
    for duty in duties:
        year = duty.academic_year
        if year.pk not in instructional:
            instructional[year.pk] = year.is_instructional_day(today)
        register = registers.get(duty.section_id)
        if not instructional[year.pk]:
            state = "NOT_INSTRUCTIONAL"
        elif register is None:
            state = AttendanceRegister.AttendanceState.NOT_TAKEN
        elif register.is_submitted:
            state = AttendanceRegister.AttendanceState.SUBMITTED
        else:
            state = AttendanceRegister.AttendanceState.DRAFT
        attendance.append({"duty": duty, "register": register, "state": state})

    remarks = []
    terms = AcademicTerm.objects.filter(
        academic_year_id__in={duty.academic_year_id for duty in duties},
        start_date__lte=today,
    ).select_related("academic_year").order_by("start_date")
    sections_by_year = {}
    for duty in duties:
        sections_by_year.setdefault(duty.academic_year_id, []).append(duty.section)
    for term in terms:
        rosters = term.section_rosters(sections_by_year[term.academic_year_id])
        written = set(
            TermRemark.objects.filter(
                term=term,
                student_id__in=[s.pk for students in rosters.values() for s in students],
            ).values_list("student_id", flat=True)
        )
        for section in sections_by_year[term.academic_year_id]:
            students = rosters[section.pk]
            remarks.append(
                {
                    "term": term,
                    "section": section,
                    "expected": len(students),
                    "written": sum(1 for s in students if s.pk in written),
                }
            )
    return render(
        request,
        "core/my_home.html",
        {
            "today": today,
            "attendance": attendance,
            "assessments": _open_assessments_needing_marks(request.user, today),
            "remarks": remarks,
        },
    )


# --- Phase 5 Gate 3: class teacher attendance (ADR 0012 D4, D5, D7) -------


@teacher_required
def my_attendance(request, section_pk):
    """Today's register for a Section the user is class teacher of today."""
    section = get_object_or_404(Section.objects.select_related("class_grade"), pk=section_pk)
    today = business_today()
    if not can_take_attendance(request.user, section, today):
        raise PermissionDenied
    duty = (
        class_teacher_assignments(request.user, today)
        .filter(section=section)
        .select_related("academic_year")
        .get()
    )
    year = duty.academic_year
    register = (
        AttendanceRegister.objects.filter(section=section, date=today)
        .select_related("submitted_by")
        .first()
    )
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "open" and register is None:
            register = AttendanceRegister(
                academic_year=year, class_grade=section.class_grade, section=section, date=today
            )
            try:
                with transaction.atomic():
                    register.full_clean()
                    register.save()
            except ValidationError as error:
                messages.error(request, " ".join(error.messages))
            except IntegrityError:
                messages.info(request, "A register for today already exists.")
            else:
                messages.success(request, "Register opened as a draft.")
        elif action in ("save", "submit") and register is not None:
            _teacher_capture(request, register, submit=action == "submit")
        return redirect("core:my-attendance", section_pk=section.pk)

    context = {
        "section": section,
        "today": today,
        "year": year,
        "register": register,
        "is_instructional": year.is_instructional_day(today),
    }
    if register is not None and register.is_submitted:
        context["entries"] = register.entries.select_related(
            "academic_enrollment__student"
        ).order_by("academic_enrollment__student__full_name")
    elif register is not None:
        context["capture_form"] = AttendanceCaptureForm(register=register)
        context["marked_count"] = register.entries.count()
    return render(request, "core/my_attendance.html", context)


def _teacher_capture(request, register, *, submit):
    if register.is_submitted:
        messages.error(
            request, "Today's attendance is already submitted; ask an administrator to correct it."
        )
        return
    form = AttendanceCaptureForm(request.POST, register=register)
    if not form.is_valid():
        errors = [message for field_errors in form.errors.values() for message in field_errors]
        messages.error(request, f"Attendance was not saved. {errors[0]}")
        return
    try:
        with transaction.atomic():
            for enrollment, status, note in form.statuses():
                register.save_draft_entry(enrollment=enrollment, status=status, absence_note=note)
    except ValidationError as error:
        messages.error(request, error.messages[0])
        return
    if not submit:
        messages.success(request, "Draft saved.")
        return
    try:
        register.submit(actor=request.user)
    except ValidationError as error:
        messages.error(request, f"Draft saved but not submitted. {error.messages[0]}")
    else:
        messages.success(request, "Attendance saved and submitted.")


# --- Phase 5 Gate 4: teacher attendance views (ADR 0012 D9) ----------------


def _months_between(start, end):
    months, year, month = [], start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def _my_class_teacher_rows(user, today):
    """The user's class teacher assignments that have taken effect (any end)."""
    return (
        class_teacher_assignments(user)
        .filter(start_date__lte=today)
        .select_related("academic_year", "section__class_grade")
        .order_by("-start_date")
    )


@teacher_required
def my_attendance_history(request):
    today = business_today()
    return render(
        request,
        "core/my_attendance_history.html",
        {"rows": _my_class_teacher_rows(request.user, today), "today": today},
    )


@teacher_required
def my_attendance_assignment(request, pk):
    """Attendance of one Section, limited to the teacher's assignment dates."""
    today = business_today()
    row = get_object_or_404(_my_class_teacher_rows(request.user, today), pk=pk)
    first, last = row.start_date, min(row.last_effective_date, today)
    months = _months_between(first, last)
    chosen = months[-1]
    try:
        year_text, month_text = (request.GET.get("month") or "").split("-")
        if (int(year_text), int(month_text)) in months:
            chosen = (int(year_text), int(month_text))
    except ValueError:
        pass
    month_start, month_end = reports.month_bounds(*chosen)
    index = months.index(chosen)
    previous_month = months[index - 1] if index > 0 else None
    next_month = months[index + 1] if index + 1 < len(months) else None
    start, end = max(first, month_start), min(last, month_end)
    summary = reports.section_summary(row.section, start, end)
    registers = list(
        AttendanceRegister.objects.filter(section=row.section, date__gte=start, date__lte=end)
        .annotate(
            present=Count("entries", filter=Q(entries__status=AttendanceStatus.PRESENT)),
            absent=Count("entries", filter=Q(entries__status=AttendanceStatus.ABSENT)),
        )
        .order_by("date")
    )
    taken = {register.date for register in registers}
    missing = [
        item for item in reports.missing_attendance(start, end, section=row.section)
        if item["date"] not in taken
    ]
    return render(
        request,
        "core/my_attendance_assignment.html",
        {
            "row": row,
            "summary": summary,
            "registers": registers,
            "missing": missing,
            "months": [f"{y:04d}-{m:02d}" for y, m in months],
            "chosen": f"{chosen[0]:04d}-{chosen[1]:02d}",
            "previous_month": f"{previous_month[0]:04d}-{previous_month[1]:02d}"
            if previous_month else None,
            "next_month": f"{next_month[0]:04d}-{next_month[1]:02d}" if next_month else None,
            "chosen_label": month_start.strftime("%B %Y"),
            "start": start,
            "end": end,
        },
    )


@teacher_required
def my_attendance_register(request, pk):
    """Read-only register for a date on which the user was class teacher."""
    register = get_object_or_404(
        AttendanceRegister.objects.select_related("section__class_grade", "submitted_by"),
        pk=pk,
    )
    if register.date > business_today() or not class_teacher_on(
        request.user, register.section, register.date
    ):
        raise PermissionDenied
    entries = register.entries.select_related("academic_enrollment__student").order_by(
        "academic_enrollment__student__full_name"
    )
    return render(
        request, "core/my_attendance_register.html", {"register": register, "entries": entries}
    )


# --- Phase 5 Gate 5: limited student access (ADR 0012 D8, D9) --------------


@teacher_required
def my_students(request):
    today = business_today()
    enrollments = list(
        teacher_student_scope(request.user, today)
        .select_related("student", "section__class_grade")
        .order_by("section__class_grade__name", "section__name", "student__full_name")
    )
    class_sections = set(
        class_teacher_assignments(request.user, today).values_list("section_id", flat=True)
    )
    submitted_sections = set(
        AttendanceRegister.objects.filter(
            date=today, section_id__in=class_sections,
            status=AttendanceRegister.Status.SUBMITTED,
        ).values_list("section_id", flat=True)
    )
    today_status = dict(
        AttendanceEntry.objects.filter(
            register__date=today, register__section_id__in=submitted_sections,
            register__status=AttendanceRegister.Status.SUBMITTED,
        ).values_list("academic_enrollment_id", "status")
    )
    groups = []
    for enrollment in enrollments:
        enrollment.today_status = today_status.get(enrollment.pk)
        if not groups or groups[-1]["section"].pk != enrollment.section_id:
            groups.append(
                {
                    "section": enrollment.section,
                    "is_class_teacher": enrollment.section_id in class_sections,
                    "attendance_submitted": enrollment.section_id in submitted_sections,
                    "enrollments": [],
                }
            )
        groups[-1]["enrollments"].append(enrollment)
    return render(request, "core/my_students.html", {"groups": groups, "today": today})


def _teacher_visible_results(user, student, academic_year):
    """Finalized results the teacher may see for this Student and year (D8, D9).

    Subject teacher: their offering + Section. Class teacher: every Subject
    assessed in their Section on dates they were its class teacher.
    """
    scope = Q(pk__in=[])
    for offering_id, section_id in teacher_assignments(user).values_list(
        "offering_id", "section_id"
    ):
        scope |= Q(assessment__offering_id=offering_id, assessment__section_id=section_id)
    for row in class_teacher_assignments(user).filter(academic_year=academic_year).select_related(
        "academic_year"
    ):
        scope |= Q(
            assessment__section_id=row.section_id,
            assessment__assessment_date__gte=row.start_date,
            assessment__assessment_date__lte=row.last_effective_date,
        )
    return list(
        assessment_reports.finalized_results(
            StudentResult.objects.filter(
                scope,
                academic_enrollment__student=student,
                assessment__term__academic_year=academic_year,
            )
        ).order_by("assessment__offering__subject__name", "assessment__assessment_date", "pk")
    )


@teacher_required
def my_student_detail(request, pk):
    """Read-only teacher student profile (ADR 0012 D8)."""
    today = business_today()
    enrollment = (
        teacher_student_scope(request.user, today)
        .filter(student_id=pk)
        .select_related("student", "academic_year", "section__class_grade")
        .first()
    )
    if enrollment is None:
        raise PermissionDenied
    student = enrollment.student
    year = enrollment.academic_year
    show_guardians = guardian_contact_visible(request.user, enrollment, today)
    return render(
        request,
        "core/my_student_detail.html",
        {
            "student": student,
            "enrollment": enrollment,
            "attendance": reports.student_summary(student, start=year.start_date, end=today),
            "results": _teacher_visible_results(request.user, student, year),
            "show_guardians": show_guardians,
            "guardian_links": (
                student.guardian_links.select_related("guardian") if show_guardians else []
            ),
        },
    )


# --- Phase 5 Gate 6: teacher result views (ADR 0012 D8-D10) ----------------


@teacher_required
def my_results(request):
    duties = teacher_assignments(request.user).order_by(
        "-offering__academic_year__start_date", "offering__subject__name", "section__name"
    )
    return render(request, "core/my_results.html", {"duties": duties})


@teacher_required
def my_subject_results(request, pk):
    """Finalized results for one of the teacher's Subject/Section assignments."""
    duty = get_object_or_404(teacher_assignments(request.user), pk=pk)
    terms = duty.offering.academic_year.terms.all()
    term_id = request.GET.get("term", "")
    term = terms.filter(pk=term_id).first() if term_id.isdigit() else None
    assessments, rows = assessment_reports.subject_section_results(
        duty.offering, duty.section, term
    )
    return render(
        request,
        "core/my_subject_results.html",
        {"duty": duty, "terms": terms, "term": term, "assessments": assessments, "rows": rows},
    )


@teacher_required
def my_report_card(request, term_pk, student_pk):
    """A Term report card, for the class teacher of the Student's Term Section."""
    term = get_object_or_404(AcademicTerm.objects.select_related("academic_year"), pk=term_pk)
    student = get_object_or_404(Student, pk=student_pk)
    if not can_view_report_card_as_teacher(request.user, student, term):
        raise PermissionDenied
    return render(
        request,
        "core/report_term_report_card.html",
        assessment_reports.term_report_card(student, term),
    )


# --- Phase 4 Gate 5: teacher DRAFT result entry (ADR 0010) -----------------


@teacher_required
def my_assessments(request):
    duties = list(teacher_assignments(request.user))
    query = Q(pk__in=[])
    for duty in duties:
        query |= Q(offering=duty.offering, section=duty.section)
    assessments = _assessments().filter(query).order_by("-assessment_date", "name")
    remark_links = []
    years = {
        row.academic_year
        for row in class_teacher_assignments(request.user).select_related("academic_year")
    }
    for year in sorted(years, key=lambda y: y.start_date):
        for term in year.terms.all():
            for section in term_remark_sections(request.user, term):
                remark_links.append((term, section))
    return render(
        request,
        "core/my_assessments.html",
        {"duties": duties, "assessments": assessments, "remark_links": remark_links},
    )


@teacher_required
def my_gradebook(request, pk):
    """Read-only marks for one of the teacher's Subject + Section assignments."""
    duty = get_object_or_404(teacher_assignments(request.user), pk=pk)
    assessments = list(
        _assessments()
        .filter(offering=duty.offering, section=duty.section)
        .order_by("assessment_date", "name", "pk")
    )
    students = {}
    for assessment in assessments:
        for enrollment in assessment.roster().select_related("student"):
            students[enrollment.student_id] = enrollment.student
    results = {
        (result.academic_enrollment.student_id, result.assessment_id): result
        for result in StudentResult.objects.filter(assessment__in=assessments).select_related(
            "academic_enrollment", "assessment"
        )
    }
    rows = [
        {"student": student, "cells": [results.get((student.pk, a.pk)) for a in assessments]}
        for student in sorted(students.values(), key=lambda s: (s.full_name.casefold(), s.pk))
    ]
    return render(
        request,
        "core/my_gradebook.html",
        {"duty": duty, "assessments": assessments, "rows": rows},
    )


@teacher_required
def assessment_marks_entry(request, pk):
    assessment = get_object_or_404(_assessments(), pk=pk)
    if not can_enter_results(request.user, assessment.offering, assessment.section):
        raise PermissionDenied
    form = None
    if assessment.is_open_for_entry:
        form = ResultEntryForm(request.POST or None, assessment=assessment)
        if request.method == "POST":
            if form.is_valid():
                try:
                    with transaction.atomic():
                        for enrollment, status, score in form.answers():
                            assessment.save_draft_result(
                                enrollment=enrollment, status=status, score=score,
                                actor=request.user,
                            )
                except ValidationError as error:
                    messages.error(request, error.messages[0])
                else:
                    messages.success(request, "Marks saved as draft.")
                    return redirect("core:assessment-marks-entry", pk=assessment.pk)
            else:
                messages.error(request, "Marks were not saved. Fix the highlighted rows.")
    context = _assessment_context(assessment)
    context["form"] = form
    return render(request, "core/assessment_marks_entry.html", context)


@administrator_required("core.change_assessment")
def assessment_update(request, pk):
    assessment = get_object_or_404(_assessments(), pk=pk)
    if assessment.is_finalized:
        messages.error(request, "A finalized assessment cannot be edited.")
        return redirect("core:assessment-detail", pk=assessment.pk)
    form = AssessmentForm(request.POST or None, instance=assessment)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Assessment updated.")
        return redirect("core:assessment-detail", pk=assessment.pk)
    return render(
        request,
        "core/assessment_form.html",
        {
            "form": form,
            "academic_year": assessment.term.academic_year,
            "assessment": assessment,
        },
    )


@administrator_required("core.delete_assessment")
def assessment_delete(request, pk):
    assessment = get_object_or_404(Assessment.objects.select_related("term"), pk=pk)
    if request.method != "POST":
        return redirect("core:assessment-detail", pk=assessment.pk)
    year_pk = assessment.term.academic_year_id
    try:
        assessment.delete()
    except ValidationError as error:
        messages.error(request, error.messages[0])
        return redirect("core:assessment-detail", pk=assessment.pk)
    messages.success(request, "Assessment deleted.")
    return redirect("core:academic-year-assessments", pk=year_pk)


# --- Phase 4 Gate 3: grading scales (ADR 0009) -----------------------------


@administrator_required("core.view_gradingscale")
def academic_year_grading_scales(request, pk):
    academic_year = get_object_or_404(AcademicYear, pk=pk)
    scales = academic_year.grading_scales.prefetch_related(
        "boundaries", "class_grade_links__class_grade"
    )
    return render(
        request,
        "core/grading_scales.html",
        {"academic_year": academic_year, "scales": scales},
    )


def _save_scale(form, scale):
    with transaction.atomic():
        scale.name = form.cleaned_data["name"]
        scale.full_clean()
        scale.save()
        scale.set_class_grades(form.cleaned_data["class_grades"])


@administrator_required("core.add_gradingscale")
def grading_scale_create(request, pk):
    academic_year = get_object_or_404(AcademicYear, pk=pk)
    form = GradingScaleForm(request.POST or None, academic_year=academic_year)
    if request.method == "POST" and form.is_valid():
        scale = GradingScale(academic_year=academic_year)
        try:
            _save_scale(form, scale)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Grading scale created. Now add its grade bands.")
            return redirect("core:grading-scale-detail", pk=scale.pk)
    return render(
        request,
        "core/grading_scale_form.html",
        {"form": form, "academic_year": academic_year, "scale": None},
    )


@administrator_required("core.view_gradingscale")
def grading_scale_detail(request, pk):
    scale = get_object_or_404(GradingScale.objects.select_related("academic_year"), pk=pk)
    return render(
        request,
        "core/grading_scale_detail.html",
        {
            "scale": scale,
            "boundaries": scale.boundaries.all(),
            "boundary_form": GradeBoundaryForm(scale=scale),
        },
    )


@administrator_required("core.change_gradingscale")
def grading_scale_update(request, pk):
    scale = get_object_or_404(GradingScale.objects.select_related("academic_year"), pk=pk)
    form = GradingScaleForm(request.POST or None, academic_year=scale.academic_year, scale=scale)
    if request.method == "POST" and form.is_valid():
        try:
            _save_scale(form, scale)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Grading scale updated.")
            return redirect("core:grading-scale-detail", pk=scale.pk)
    return render(
        request,
        "core/grading_scale_form.html",
        {"form": form, "academic_year": scale.academic_year, "scale": scale},
    )


@administrator_required("core.add_gradeboundary")
def grade_boundary_create(request, pk):
    scale = get_object_or_404(GradingScale, pk=pk)
    if request.method == "POST":
        form = GradeBoundaryForm(request.POST, scale=scale)
        if form.is_valid():
            form.save()
            messages.success(request, "Grade band added.")
        else:
            errors = [m for field_errors in form.errors.values() for m in field_errors]
            messages.error(request, f"Grade band not added. {errors[0]}")
    return redirect("core:grading-scale-detail", pk=scale.pk)


@administrator_required("core.delete_gradeboundary")
def grade_boundary_delete(request, pk):
    boundary = get_object_or_404(GradeBoundary, pk=pk)
    if request.method == "POST":
        boundary.delete()
        messages.success(request, "Grade band removed.")
    return redirect("core:grading-scale-detail", pk=boundary.scale_id)


# --- Phase 4 Gate 2: assessment teacher assignments (ADR 0010) -------------


@administrator_required("core.view_assessmentteacherassignment")
def academic_year_teacher_assignments(request, pk):
    academic_year = get_object_or_404(AcademicYear, pk=pk)
    assignments = (
        AssessmentTeacherAssignment.objects.filter(offering__academic_year=academic_year)
        .select_related("teacher", "offering__class_grade", "offering__subject", "section")
        .order_by("offering__class_grade__name", "offering__subject__name", "section__name")
    )
    form = TeacherAssignmentForm(academic_year=academic_year)
    return render(
        request,
        "core/teacher_assignments.html",
        {
            "academic_year": academic_year,
            "assignments": assignments,
            "form": form,
            "teacher_count": form.fields["teacher"].queryset.count(),
        },
    )


@administrator_required("core.add_assessmentteacherassignment")
def teacher_assignment_create(request, pk):
    academic_year = get_object_or_404(AcademicYear, pk=pk)
    form = TeacherAssignmentForm(request.POST or None, academic_year=academic_year)
    if request.method == "POST" and form.is_valid():
        assignment = AssessmentTeacherAssignment(
            teacher=form.cleaned_data["teacher"],
            offering=form.cleaned_data["offering"],
            section=form.cleaned_data["section"],
        )
        try:
            with transaction.atomic():
                assignment.full_clean()
                assignment.save()
        except ValidationError as error:
            form.add_error(None, error)
        except IntegrityError:
            form.add_error(None, "A teacher is already assigned to this Subject and Section.")
        else:
            messages.success(request, "Teacher assigned.")
            return redirect("core:academic-year-teacher-assignments", pk=academic_year.pk)
    return render(
        request,
        "core/teacher_assignment_form.html",
        {"form": form, "academic_year": academic_year},
    )


@administrator_required("core.delete_assessmentteacherassignment")
def teacher_assignment_delete(request, pk):
    assignment = get_object_or_404(
        AssessmentTeacherAssignment.objects.select_related("offering"), pk=pk
    )
    year_pk = assignment.offering.academic_year_id
    if request.method == "POST":
        assignment.delete()
        messages.success(request, "Teacher assignment removed.")
    return redirect("core:academic-year-teacher-assignments", pk=year_pk)


# --- Phase 5 Gate 1: class teacher assignment (ADR 0011) --------------------


@administrator_required("core.view_sectionclassteacher")
def academic_year_class_teachers(request, pk):
    academic_year = get_object_or_404(AcademicYear, pk=pk)
    today = business_today()
    by_section = {}
    for row in (
        SectionClassTeacher.objects.filter(academic_year=academic_year)
        .select_related("teacher")
        .order_by("start_date")
    ):
        by_section.setdefault(row.section_id, []).append(row)
    sections = []
    for section in Section.objects.select_related("class_grade").order_by(
        "class_grade__name", "name"
    ):
        history = by_section.get(section.pk, [])
        current = next((row for row in history if row.is_effective_on(today)), None)
        sections.append({"section": section, "current": current, "history": history})
    return render(
        request,
        "core/academic_year_class_teachers.html",
        {
            "academic_year": academic_year,
            "sections": sections,
            "today": today,
            "year_is_current": academic_year.contains(today),
        },
    )


@administrator_required("core.add_sectionclassteacher")
def class_teacher_assign(request, pk):
    academic_year = get_object_or_404(AcademicYear, pk=pk)
    today = business_today()
    default_start = min(max(today, academic_year.start_date), academic_year.end_date)
    initial = {"start_date": default_start, "section": request.GET.get("section")}
    form = ClassTeacherAssignForm(
        request.POST or None, academic_year=academic_year, initial=initial
    )
    if request.method == "POST" and form.is_valid():
        try:
            SectionClassTeacher.assign(
                teacher=form.cleaned_data["teacher"],
                academic_year=academic_year,
                section=form.cleaned_data["section"],
                start_date=form.cleaned_data["start_date"],
            )
        except ValidationError as error:
            form.add_error(None, error)
        except IntegrityError:
            form.add_error(None, "Another class teacher assignment starts on that date.")
        else:
            messages.success(request, "Class teacher assigned.")
            return redirect("core:academic-year-class-teachers", pk=academic_year.pk)
    return render(
        request,
        "core/class_teacher_form.html",
        {"form": form, "academic_year": academic_year},
    )


@administrator_required("core.change_sectionclassteacher")
def class_teacher_end(request, pk):
    assignment = get_object_or_404(
        SectionClassTeacher.objects.select_related(
            "teacher", "academic_year", "section__class_grade"
        ),
        pk=pk,
    )
    form = ClassTeacherEndForm(request.POST or None, initial={"end_date": business_today()})
    if request.method == "POST" and form.is_valid():
        try:
            assignment.end(form.cleaned_data["end_date"])
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Class teacher assignment ended.")
            return redirect(
                "core:academic-year-class-teachers", pk=assignment.academic_year_id
            )
    return render(
        request, "core/class_teacher_end_form.html", {"form": form, "assignment": assignment}
    )


@administrator_required("core.delete_sectionclassteacher")
def class_teacher_delete(request, pk):
    assignment = get_object_or_404(SectionClassTeacher, pk=pk)
    year_pk = assignment.academic_year_id
    if request.method == "POST":
        try:
            assignment.delete()
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(request, "Planned class teacher assignment deleted.")
    return redirect("core:academic-year-class-teachers", pk=year_pk)


# --- Phase 5 Gate 7: administrator assignment workflows (ADR 0011 D13, D14) --


@administrator_required("core.view_sectionclassteacher")
def academic_year_assignments(request, pk):
    academic_year = get_object_or_404(AcademicYear, pk=pk)
    context = assignments.overview(academic_year, business_today())
    context["academic_year"] = academic_year
    return render(request, "core/academic_year_assignments.html", context)


@administrator_required("core.view_sectionclassteacher")
def teacher_load(request, pk):
    teacher = get_object_or_404(get_user_model(), pk=pk)
    return render(
        request,
        "core/teacher_load.html",
        {
            "teacher": teacher,
            "is_active_teacher": is_teacher(teacher),
            "years": assignments.teacher_load(teacher),
        },
    )


@administrator_required("core.add_sectionclassteacher")
def assignment_copy(request, pk):
    """Preview-first, conservative copy of another year's assignments (D13)."""
    if not request.user.has_perm("core.add_assessmentteacherassignment"):
        raise PermissionDenied
    target = get_object_or_404(AcademicYear, pk=pk)
    sources = AcademicYear.objects.exclude(pk=target.pk).order_by("-start_date")
    source_id = request.POST.get("source") or request.GET.get("source")
    source = None
    if source_id and str(source_id).isdigit():
        source = sources.filter(pk=source_id).first()
    if source is None and not source_id:
        source = sources.filter(start_date__lt=target.start_date).first()
    if request.method == "POST" and source is not None:
        try:
            created = assignments.apply_copy(source, target, request.POST.get("token", ""))
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(request, f"Copied {created} assignment(s) from {source.name}.")
            return redirect("core:academic-year-assignments", pk=target.pk)
    plan = assignments.plan_copy(source, target) if source is not None else None
    return render(
        request,
        "core/assignment_copy.html",
        {"target": target, "sources": sources, "source": source, "plan": plan},
    )


@administrator_required("core.view_classgrade")
def class_grade_list(request):
    class_grades = ClassGrade.objects.all()
    return render(request, "core/class_grade_list.html", {"class_grades": class_grades})


@administrator_required("core.view_classgrade")
def class_grade_detail(request, pk):
    class_grade = get_object_or_404(ClassGrade, pk=pk)
    return render(
        request,
        "core/class_grade_detail.html",
        {"class_grade": class_grade, "sections": class_grade.sections.all()},
    )


@administrator_required("core.add_classgrade")
def class_grade_create(request):
    if request.method == "POST":
        form = ClassGradeForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Class/Grade created.")
            return redirect("core:class-grade-list")
    else:
        form = ClassGradeForm()
    return render(request, "core/class_grade_form.html", {"form": form})


@administrator_required("core.add_section")
def section_create(request, pk):
    class_grade = get_object_or_404(ClassGrade, pk=pk)
    if request.method == "POST":
        form = SectionForm(request.POST, class_grade=class_grade)
        if form.is_valid():
            form.save()
            messages.success(request, "Section created.")
            return redirect("core:class-grade-detail", pk=class_grade.pk)
    else:
        form = SectionForm(class_grade=class_grade)
    return render(
        request,
        "core/section_form.html",
        {"form": form, "class_grade": class_grade},
    )


APPLICANT_COLUMNS = (
    Column("Name", "name", ("full_name",)),
    Column("Admission status", "status", ("admission_status",)),
)


@administrator_required("core.view_applicant")
def applicant_list(request):
    status = parse_choice(request, "status", Applicant.AdmissionStatus.choices)
    applicants = Applicant.objects.all()
    if status:
        applicants = applicants.filter(admission_status=status)
    table = build_table(request, applicants, APPLICANT_COLUMNS, "name")
    return render(
        request,
        "core/applicant_list.html",
        {
            "applicants": table.page,
            "table": table,
            "status": status,
            "status_choices": Applicant.AdmissionStatus.choices,
        },
    )


@administrator_required("core.add_applicant")
def applicant_create(request):
    if request.method == "POST":
        form = ApplicantForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Applicant registered.")
            return redirect("core:applicant-list")
    else:
        form = ApplicantForm()
    return render(request, "core/applicant_form.html", {"form": form})


@administrator_required("core.view_applicant")
def applicant_detail(request, pk):
    applicant = get_object_or_404(Applicant, pk=pk)
    guardian_links = applicant.guardian_links.select_related("guardian")
    student = Student.objects.filter(applicant=applicant).first()
    return render(
        request,
        "core/applicant_detail.html",
        {"applicant": applicant, "guardian_links": guardian_links, "student": student},
    )


@administrator_required("core.change_applicant")
def applicant_admission_decision(request, pk):
    applicant = get_object_or_404(Applicant, pk=pk)
    if request.method != "POST":
        return redirect("core:applicant-detail", pk=applicant.pk)

    form = AdmissionDecisionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Invalid admission decision.")
        return redirect("core:applicant-detail", pk=applicant.pk)

    try:
        applicant.record_admission_decision(
            form.cleaned_data["decision"], reason=form.cleaned_data["reason"]
        )
    except ValidationError as error:
        messages.error(request, error.messages[0])
        if (
            form.cleaned_data["decision"] == Applicant.AdmissionStatus.REJECTED
            and applicant.admission_status == Applicant.AdmissionStatus.PENDING
        ):
            return redirect(
                "core:applicant-decision-confirm",
                pk=applicant.pk,
                decision=Applicant.AdmissionStatus.REJECTED,
            )
        return redirect("core:applicant-detail", pk=applicant.pk)

    messages.success(request, f"Admission decision recorded: {applicant.admission_status}.")
    return redirect("core:applicant-detail", pk=applicant.pk)


@administrator_required("core.change_applicant")
def applicant_decision_confirm(request, pk, decision):
    applicant = get_object_or_404(Applicant, pk=pk)
    if decision not in {
        Applicant.AdmissionStatus.ACCEPTED,
        Applicant.AdmissionStatus.REJECTED,
    }:
        raise Http404
    if applicant.admission_status != Applicant.AdmissionStatus.PENDING:
        return redirect("core:applicant-detail", pk=applicant.pk)
    if (
        decision == Applicant.AdmissionStatus.REJECTED
        and Student.objects.filter(applicant=applicant).exists()
    ):
        messages.error(
            request, "This Applicant already has a Student record, so it cannot be rejected."
        )
        return redirect("core:applicant-detail", pk=applicant.pk)
    return render(
        request,
        "core/applicant_decision_confirm.html",
        {
            "applicant": applicant,
            "decision": decision,
            "decision_label": (
                "Accept" if decision == Applicant.AdmissionStatus.ACCEPTED else "Reject"
            ),
        },
    )


@administrator_required("core.add_student")
def applicant_progress(request, pk):
    applicant = get_object_or_404(Applicant, pk=pk)
    if request.method != "POST":
        return redirect("core:applicant-detail", pk=applicant.pk)

    try:
        student = applicant.progress_to_student()
    except ValidationError as error:
        messages.error(request, error.messages[0])
        return redirect("core:applicant-detail", pk=applicant.pk)

    messages.success(request, "Student created from Applicant.")
    return redirect("core:student-detail", pk=student.pk)


@administrator_required("core.add_applicantguardian")
def applicant_guardian_create(request, pk):
    applicant = get_object_or_404(Applicant, pk=pk)
    if request.method == "POST":
        form = ApplicantGuardianForm(request.POST, applicant=applicant)
        if form.is_valid():
            form.save()
            messages.success(request, "Guardian associated with Applicant.")
            return redirect("core:applicant-detail", pk=applicant.pk)
    else:
        form = ApplicantGuardianForm(applicant=applicant)
    return render(
        request,
        "core/applicant_guardian_form.html",
        {"form": form, "applicant": applicant},
    )


@administrator_required("core.view_guardian")
def guardian_list(request):
    guardians = Guardian.objects.all()
    return render(request, "core/guardian_list.html", {"guardians": guardians})


@administrator_required("core.add_guardian")
def guardian_create(request):
    if request.method == "POST":
        form = GuardianForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Guardian created.")
            return redirect("core:guardian-list")
    else:
        form = GuardianForm()
    return render(request, "core/guardian_form.html", {"form": form})


@administrator_required("core.view_guardian")
def guardian_detail(request, pk):
    guardian = get_object_or_404(Guardian, pk=pk)
    applicant_links = guardian.applicant_links.select_related("applicant")
    context = {"guardian": guardian, "applicant_links": applicant_links}
    if request.user.has_perm("core.view_guardianaccount"):
        context["accounts"] = guardian.accounts.select_related(
            "user", "created_by", "revoked_by", "identity_verified_by"
        )
        context["active_account"] = next(
            (account for account in context["accounts"] if account.is_active), None
        )
    if request.user.has_perm("core.view_guardianstudentaccess"):
        relationships = []
        for link in guardian.student_links.select_related("student").prefetch_related(
            "access_grants__granted_by", "access_grants__revoked_by"
        ):
            grants = list(link.access_grants.all())
            active_grant = next((g for g in grants if g.is_active), None)
            relationships.append(
                {
                    "link": link,
                    "active_grant": active_grant,
                    "under_review": active_grant is not None
                    and guardian_access.is_review_pending(active_grant),
                    "grants": grants,
                }
            )
        context["relationships"] = relationships
    if request.user.has_perm("accounts.view_securityevent"):
        context["events"] = SecurityEvent.objects.filter(
            guardian_id_ref=guardian.pk, event_class=SecurityEvent.EventClass.HISTORY
        ).select_related("actor", "subject_user")[:50]
    if request.user.has_perm("core.view_guardiancontactconsent"):
        context["consents"] = list(guardian.contact_consents.select_related("recorded_by"))
        if request.user.has_perm("core.add_guardiancontactconsent"):
            context["consent_form"] = ContactConsentForm()
    context.update(
        profile_sections(
            ("applicants", "Associated applicants", True),
            ("portal-account", "Portal account", "accounts" in context),
            ("student-access", "Student access", "relationships" in context),
            ("history", "Account history", "events" in context),
        )
    )
    return render(request, "core/guardian_detail.html", context)


# --- Phase 6 Gate 7: sign-in lockouts (ADR 0013) ----------------------------


@administrator_required("accounts.clear_login_lockout")
def login_lockouts(request):
    from accounts import security

    if request.method == "POST":
        username = request.POST.get("username", "")
        if username in security.locked_usernames():
            security.clear_lockout(username)
            SecurityEvent.record(SecurityEvent.EventType.LOCKOUT_CLEARED, actor=request.user,
                                 detail={"username": username})
            messages.success(request, f"Sign-in lockout cleared for {username}.")
        return redirect("core:login-lockouts")
    return render(request, "core/login_lockouts.html",
                  {"locked": security.locked_usernames()})


# --- Phase 6 Gate 6: Term publication to guardians (ADR 0014) --------------


def _include_ids(source):
    return [value for value in source.getlist("include") if value.isdigit()]


@administrator_required("core.view_termpublication")
def term_publication(request, pk):
    """Preview (GET) and confirm (POST) publication for one Term and Section."""
    term = get_object_or_404(AcademicTerm.objects.select_related("academic_year"), pk=pk)
    sections = Section.objects.select_related("class_grade").order_by(
        "class_grade__name", "name"
    )
    source = request.POST if request.method == "POST" else request.GET
    section = None
    if source.get("section", "").isdigit():
        section = sections.filter(pk=source["section"]).first()
    include = _include_ids(source)
    if request.method == "POST" and section is not None:
        if not request.user.has_perm("core.publish_termpublication"):
            raise PermissionDenied
        try:
            created = publication.confirm_publication(
                term=term, section=section, include=include,
                token=request.POST.get("token", ""), actor=request.user,
            )
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(request, f"Published {len(created)} report card(s) to guardians.")
        query = "&".join([f"section={section.pk}"] + [f"include={i}" for i in include])
        return redirect(f"{reverse('core:term-publication', args=[term.pk])}?{query}")
    plan = publication.plan_publication(term, section, include) if section else None
    return render(
        request,
        "core/term_publication.html",
        {"term": term, "sections": sections, "section": section, "plan": plan,
         "include": include},
    )


@administrator_required("core.view_termpublication")
def publication_detail(request, pk):
    """Any version exactly as released, with its status history (ADR 0014)."""
    pub = get_object_or_404(
        TermPublication.objects.select_related(
            "student", "term__academic_year", "published_by", "status_changed_by"
        ),
        pk=pk,
    )
    versions = TermPublication.objects.filter(student=pub.student, term=pub.term).select_related(
        "published_by", "status_changed_by"
    ).order_by("-version")
    return render(
        request,
        "core/publication_detail.html",
        {"pub": pub, "entries": pub.entries.all(), "versions": versions,
         "live_matches": publication.live_fingerprint(pub) == pub.fingerprint},
    )


@administrator_required("core.publish_termpublication")
def publication_withdraw(request, pk):
    pub = get_object_or_404(TermPublication.objects.select_related("student", "term"), pk=pk)
    form = RevocationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            publication.withdraw(pub, actor=request.user, reason=form.cleaned_data["reason"])
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Publication withdrawn; guardians no longer see it.")
            return redirect("core:publication-detail", pk=pub.pk)
    return render(request, "core/publication_withdraw.html", {"pub": pub, "form": form})


@administrator_required("core.view_termpublication")
def publications_stale(request):
    return render(
        request,
        "core/publications_stale.html",
        {"stale": publication.stale_publications()},
    )


# --- Phase 6 Gate 4: admission and roll numbers (ADR 0014, OD-1) ----------


@administrator_required("core.change_student")
def student_admission_number(request, pk):
    student = get_object_or_404(Student, pk=pk)
    form = AdmissionNumberForm(
        request.POST or None, initial={"admission_number": student.admission_number}
    )
    if request.method == "POST" and form.is_valid():
        try:
            student.set_admission_number(form.cleaned_data["admission_number"])
        except ValidationError as error:
            form.add_error("admission_number", error)
        else:
            messages.success(request, "Admission number saved.")
            return redirect("core:student-detail", pk=student.pk)
    return render(
        request,
        "core/identifier_form.html",
        {"form": form, "student": student, "title": "Admission number"},
    )


@administrator_required("core.change_academicenrollment")
def enrollment_roll_number(request, pk):
    enrollment = get_object_or_404(
        AcademicEnrollment.objects.select_related(
            "student", "academic_year", "section__class_grade"
        ),
        pk=pk,
    )
    form = RollNumberForm(request.POST or None, initial={"roll_number": enrollment.roll_number})
    if request.method == "POST" and form.is_valid():
        try:
            enrollment.set_roll_number(form.cleaned_data["roll_number"])
        except ValidationError as error:
            form.add_error("roll_number", error)
        else:
            messages.success(request, "Roll number saved.")
            return redirect("core:student-detail", pk=enrollment.student_id)
    return render(
        request,
        "core/identifier_form.html",
        {
            "form": form,
            "student": enrollment.student,
            "title": f"Roll number — {enrollment.academic_year} {enrollment.section}",
        },
    )


# --- Phase 6 Gate 2: guardian access reviews (ADR 0013, OD-8) --------------


def _posted_decisions(request):
    """{grant pk: decision} from `decision_<pk>` fields of a review form."""
    return {
        key.removeprefix("decision_"): value
        for key, value in request.POST.items()
        if key.startswith("decision_") and key.removeprefix("decision_").isdigit()
    }


def _grants_needing_review(request, student, *, ending_placement=False):
    """Active grants still to decide, or None when no review step is needed.

    The review step is shown when the Student has active guardian grants and
    the administrator has not yet submitted the review form. For a new
    placement it applies only if a current placement would end.
    """
    if request.POST.get("access_review") == "1":
        return None
    if ending_placement and not student.enrollments.filter(
        status=AcademicEnrollment.Status.ACTIVE
    ).exists():
        return None
    grants = list(guardian_access.active_grants_for(student))
    return grants or None


def _access_review_page(request, student, grants, *, trigger, action):
    hidden = [
        (name, value)
        for name, value in request.POST.items()
        if name != "csrfmiddlewaretoken" and not name.startswith("decision_")
    ]
    return render(
        request,
        "core/student_access_review.html",
        {
            "student": student,
            "grants": grants,
            "trigger": GuardianAccessReview.Trigger(trigger).label,
            "action": action,
            "hidden": hidden,
            "decisions": GuardianAccessReview.Decision.choices,
        },
    )


@administrator_required("core.view_guardianaccessreview")
def guardian_access_reviews(request):
    """Date-based reviews pending (fail closed) and recent decisions."""
    rows = guardian_access.pending_reviews()
    guardian_access.record_pending_events(rows, actor=request.user)
    recent = GuardianAccessReview.objects.select_related(
        "grant__student_guardian__student", "grant__student_guardian__guardian",
        "decided_by", "enrollment__section__class_grade", "enrollment__academic_year",
    )[:50]
    return render(
        request,
        "core/guardian_access_reviews.html",
        {"rows": rows, "recent": recent, "decisions": GuardianAccessReview.Decision.choices},
    )


@administrator_required("core.add_guardianaccessreview")
def guardian_access_review_decide(request, pk):
    grant = get_object_or_404(GuardianStudentAccess, pk=pk)
    if request.method == "POST":
        try:
            guardian_access.decide_date_review(
                grant=grant,
                decision=request.POST.get("decision", ""),
                actor=request.user,
                note=request.POST.get("note", ""),
            )
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(request, "Access review recorded.")
    return redirect("core:guardian-access-reviews")


# --- Phase 6 Gate 1: guardian accounts and access grants (ADR 0013) ---------


def _credential_slip(request, account, password, *, heading):
    """Render the one-time temporary password; never cached, never stored."""
    response = render(
        request,
        "core/guardian_credential_slip.html",
        {"account": account, "password": password, "heading": heading},
    )
    add_never_cache_headers(response)
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    return response


@administrator_required("core.add_guardianaccount")
def guardian_account_create(request, pk):
    guardian = get_object_or_404(Guardian, pk=pk)
    form = GuardianAccountCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            account, password = guardian_accounts.create_guardian_account(
                guardian=guardian,
                username=form.cleaned_data["username"],
                method=form.cleaned_data["identity_verification_method"],
                note=form.cleaned_data["identity_verification_note"],
                actor=request.user,
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            return _credential_slip(request, account, password, heading="Guardian account created")
    return render(
        request,
        "core/guardian_account_form.html",
        {"guardian": guardian, "form": form, "mode": "create"},
    )


@administrator_required("core.add_guardianaccount")
def guardian_account_link(request, pk):
    guardian = get_object_or_404(Guardian, pk=pk)
    form = GuardianAccountLinkForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            guardian_accounts.link_existing_login(
                guardian=guardian,
                username=form.cleaned_data["username"],
                method=form.cleaned_data["identity_verification_method"],
                note=form.cleaned_data["identity_verification_note"],
                actor=request.user,
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Existing login linked to this guardian.")
            return redirect("core:guardian-detail", pk=guardian.pk)
    return render(
        request,
        "core/guardian_account_form.html",
        {"guardian": guardian, "form": form, "mode": "link"},
    )


@administrator_required("core.change_guardianaccount")
def guardian_account_revoke(request, pk):
    account = get_object_or_404(GuardianAccount.objects.select_related("guardian", "user"), pk=pk)
    form = RevocationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            guardian_accounts.revoke_account_link(
                account=account, actor=request.user, reason=form.cleaned_data["reason"]
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Guardian account link revoked; its sessions were ended.")
            return redirect("core:guardian-detail", pk=account.guardian_id)
    return render(
        request,
        "core/guardian_revoke_form.html",
        {"form": form, "subject": f"the portal account link for {account.user.username}",
         "guardian": account.guardian},
    )


@administrator_required("core.change_guardian_username")
def guardian_account_username(request, pk):
    account = get_object_or_404(GuardianAccount.objects.select_related("guardian", "user"), pk=pk)
    form = GuardianUsernameForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            guardian_accounts.change_guardian_username(
                account=account, new_username=form.cleaned_data["username"], actor=request.user
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Username changed.")
            return redirect("core:guardian-detail", pk=account.guardian_id)
    return render(
        request,
        "core/guardian_username_form.html",
        {"form": form, "account": account},
    )


@administrator_required("core.reset_guardian_password")
def guardian_account_reset_password(request, pk):
    account = get_object_or_404(GuardianAccount.objects.select_related("guardian", "user"), pk=pk)
    if request.method == "POST":
        try:
            password = guardian_accounts.reset_guardian_password(
                account=account, actor=request.user
            )
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
            return redirect("core:guardian-detail", pk=account.guardian_id)
        return _credential_slip(request, account, password, heading="Password reset")
    return render(request, "core/guardian_reset_confirm.html", {"account": account})


@administrator_required("core.add_guardianstudentaccess")
def guardian_access_grant(request, pk):
    link = get_object_or_404(StudentGuardian.objects.select_related("guardian"), pk=pk)
    if request.method == "POST":
        try:
            guardian_accounts.grant_student_access(student_guardian=link, actor=request.user)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(request, "Portal access granted for this Student.")
    return redirect("core:guardian-detail", pk=link.guardian_id)


@administrator_required("core.change_guardianstudentaccess")
def guardian_access_revoke(request, pk):
    grant = get_object_or_404(
        GuardianStudentAccess.objects.select_related(
            "student_guardian__guardian", "student_guardian__student"
        ),
        pk=pk,
    )
    guardian = grant.student_guardian.guardian
    form = RevocationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            guardian_accounts.revoke_student_access(
                grant=grant, actor=request.user, reason=form.cleaned_data["reason"]
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Portal access revoked for this Student.")
            return redirect("core:guardian-detail", pk=guardian.pk)
    return render(
        request,
        "core/guardian_revoke_form.html",
        {"form": form, "subject": f"portal access to {grant.student_guardian.student}",
         "guardian": guardian},
    )


STUDENT_COLUMNS = (
    Column("Name", "name", ("full_name",)),
    Column("Class"),
    Column("Section"),
    Column("Guardian"),
    Column("Status", "status", ("status",)),
)

# Quick-filter chips. Values are URL tokens; the order is the display order.
STUDENT_CHIP_CHOICES = (
    ("all", "All"),
    ("new", "New this month"),
    ("unplaced", "Not in a class"),
    ("absent", "Absent 3+ days"),
)


def _parse_id(request, name, valid_ids):
    """The GET value when it is an integer in `valid_ids`, else None."""
    raw = request.GET.get(name, "")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value in valid_ids else None


def _student_chips(request, chip):
    """Chip links: each keeps the other filters, only the active one is marked."""
    active = chip or "all"
    base = {k: v for k, v in request.GET.items() if v and k not in ("sort", "page", "chip")}
    chips = []
    for key, label in STUDENT_CHIP_CHOICES:
        data = dict(base)
        if key != "all":
            data["chip"] = key
        query = urlencode(data)
        chips.append(
            {
                "key": key,
                "label": label,
                "url": request.path + (f"?{query}" if query else ""),
                "active": key == active,
            }
        )
    return chips


@administrator_required("core.view_student")
def student_list(request):
    query = request.GET.get("q", "").strip()
    status = parse_choice(request, "status", Student.Status.choices)
    chip = parse_choice(request, "chip", STUDENT_CHIP_CHOICES)
    current_year = AcademicYear.objects.order_by("-start_date").first()

    students = Student.objects.all()
    if query:
        students = students.filter(
            Q(full_name__icontains=query)
            | Q(email__icontains=query)
            | Q(phone__icontains=query)
        )
    if status:
        students = students.filter(status=status)

    # Current-year placement and one guardian name, resolved in the page query
    # (subqueries) rather than per row.
    active_enrollments = AcademicEnrollment.objects.filter(
        student=OuterRef("pk"),
        status=AcademicEnrollment.Status.ACTIVE,
        academic_year=current_year,
    )
    students = students.annotate(
        current_class=Subquery(active_enrollments.values("class_grade__name")[:1]),
        current_section=Subquery(active_enrollments.values("section__name")[:1]),
        guardian_name=Subquery(
            StudentGuardian.objects.filter(student=OuterRef("pk"))
            .values("guardian__full_name")
            .order_by("guardian__full_name")[:1]
        ),
    )

    if chip == "new":
        students = students.filter(created_at__gte=timezone.now() - timedelta(days=30))
    elif chip == "unplaced":
        students = students.exclude(
            enrollments__status=AcademicEnrollment.Status.ACTIVE,
            enrollments__academic_year=current_year,
        )
    elif chip == "absent":
        students = students.annotate(
            absent_days=Count(
                "enrollments__attendance_entries",
                filter=Q(enrollments__attendance_entries__status=AttendanceStatus.ABSENT),
            )
        ).filter(absent_days__gte=3)

    class_choices = []
    section_choices = []
    class_filter = section_filter = None
    if current_year is not None:
        class_choices = list(ClassGrade.objects.order_by("name"))
        section_choices = list(
            Section.objects.select_related("class_grade").order_by(
                "class_grade__name", "name"
            )
        )
        class_filter = _parse_id(request, "class", {c.pk for c in class_choices})
        section_filter = _parse_id(request, "section", {s.pk for s in section_choices})
        if class_filter is not None:
            students = students.filter(
                enrollments__class_grade_id=class_filter,
                enrollments__status=AcademicEnrollment.Status.ACTIVE,
                enrollments__academic_year=current_year,
            )
        if section_filter is not None:
            students = students.filter(
                enrollments__section_id=section_filter,
                enrollments__status=AcademicEnrollment.Status.ACTIVE,
                enrollments__academic_year=current_year,
            )

    table = build_table(request, students, STUDENT_COLUMNS, "name")

    has_filters = bool(
        query or status or chip or class_filter is not None or section_filter is not None
    )
    only_search = query and not (
        status or chip or class_filter is not None or section_filter is not None
    )

    return render(
        request,
        "core/student_list.html",
        {
            "students": table.page,
            "table": table,
            "query": query,
            "status": status,
            "status_choices": Student.Status.choices,
            "chip": chip,
            "chips": _student_chips(request, chip),
            "class_filter": class_filter,
            "section_filter": section_filter,
            "class_choices": class_choices,
            "section_choices": section_choices,
            "has_filters": has_filters,
            "only_search": only_search,
        },
    )


def profile_sections(*candidates):
    """Context for a profile page's "On this page" menu (audit F20).

    Each candidate is (id, label, rendered). The same ``profile_section_ids`` list
    gates the section in the template, so the menu and the page cannot drift.
    """
    sections = [{"id": sid, "label": label} for sid, label, rendered in candidates if rendered]
    return {
        "profile_sections": sections,
        "profile_section_ids": [section["id"] for section in sections],
    }


@administrator_required("core.view_student")
def student_detail(request, pk):
    student = get_object_or_404(Student, pk=pk)
    guardian_links = student.guardian_links.select_related("guardian")
    enrollments = student.enrollments.select_related(
        "academic_year", "class_grade", "section__class_grade"
    )
    current_enrollment = enrollments.filter(status=AcademicEnrollment.Status.ACTIVE).first()
    return render(
        request,
        "core/student_detail.html",
        {
            "student": student,
            "guardian_links": guardian_links,
            "current_enrollment": current_enrollment,
            "enrollments": enrollments,
            **profile_sections(
                ("status-change", "Change status", request.user.has_perm("core.change_student")),
                ("status-history", "Status history", True),
                ("placement", "Current placement", True),
                ("enrollment-history", "Enrollment history", True),
                ("guardians", "Guardians", True),
            ),
        },
    )


@administrator_required("core.add_academicenrollment")
def student_enroll(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == "POST":
        form = AcademicEnrollmentForm(request.POST)
        if form.is_valid():
            grants = _grants_needing_review(request, student, ending_placement=True)
            if grants is not None:
                return _access_review_page(
                    request, student, grants,
                    trigger=GuardianAccessReview.Trigger.PLACEMENT_ENDED,
                    action=reverse("core:student-enroll", args=[student.pk]),
                )
            try:
                student.enroll(
                    academic_year=form.cleaned_data["academic_year"],
                    class_grade=form.cleaned_data["class_grade"],
                    section=form.cleaned_data["section"],
                    start_date=form.cleaned_data["start_date"],
                    actor=request.user,
                    access_decisions=_posted_decisions(request),
                    access_note=request.POST.get("access_note", ""),
                )
            except ValidationError as error:
                messages.error(request, error.messages[0])
            else:
                messages.success(request, "Academic Enrollment recorded.")
                return redirect("core:student-detail", pk=student.pk)
    else:
        form = AcademicEnrollmentForm()
    return render(
        request,
        "core/enrollment_form.html",
        {"form": form, "student": student},
    )


@administrator_required("core.change_student")
def student_status_change(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method != "POST":
        return redirect("core:student-detail", pk=student.pk)

    form = StudentStatusForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Invalid Student status.")
        return redirect("core:student-detail", pk=student.pk)

    if form.cleaned_data["status"] == Student.Status.INACTIVE:
        if not form.cleaned_data["reason"].strip():
            messages.error(request, "A reason is required to deactivate a Student.")
            return redirect("core:student-deactivate-confirm", pk=student.pk)
        grants = _grants_needing_review(request, student)
        if grants is not None:
            return _access_review_page(
                request, student, grants,
                trigger=GuardianAccessReview.Trigger.STUDENT_INACTIVE,
                action=reverse("core:student-status-change", args=[student.pk]),
            )
    try:
        student.record_status_change(
            form.cleaned_data["status"],
            actor=request.user,
            access_decisions=_posted_decisions(request),
            access_note=request.POST.get("access_note", ""),
            reason=form.cleaned_data["reason"],
        )
    except ValidationError as error:
        messages.error(request, error.messages[0])
        return redirect("core:student-detail", pk=student.pk)

    messages.success(request, f"Student status changed: {student.status}.")
    return redirect("core:student-detail", pk=student.pk)


@administrator_required("core.change_student")
def student_deactivate_confirm(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if student.status != Student.Status.ACTIVE:
        return redirect("core:student-detail", pk=student.pk)
    return render(
        request,
        "core/student_deactivate_confirm.html",
        {
            "student": student,
            "grants": list(guardian_access.active_grants_for(student)),
            "placement": student.enrollments.filter(
                status=AcademicEnrollment.Status.ACTIVE
            ).first(),
        },
    )


REGISTER_COLUMNS = (
    Column("Date", "date", ("date", "section__class_grade", "section"),
           ("-date", "section__class_grade", "section")),
    Column("Academic year"),
    Column("Class/Grade"),
    Column("Section", "section", ("section__class_grade", "section")),
    Column("Status", "status", ("status",)),
    Column("Entries", "entries", ("entry_count",)),
)


@administrator_required("core.view_attendanceregister")
def attendance_register_list(request):
    registers = AttendanceRegister.objects.select_related(
        "academic_year", "class_grade", "section__class_grade"
    ).annotate(entry_count=Count("entries"))
    form = AttendanceRegisterFilterForm(request.GET or None)
    if form.is_valid():
        section = form.cleaned_data.get("section")
        start = form.cleaned_data.get("start")
        end = form.cleaned_data.get("end")
        if section is not None:
            registers = registers.filter(section=section)
        if start is not None:
            registers = registers.filter(date__gte=start)
        if end is not None:
            registers = registers.filter(date__lte=end)
    section_summary = None
    if form.is_valid() and form.cleaned_data.get("section") is not None:
        # Reportable (submitted, eligible) attendance only - Gate 7 semantics.
        totals = reports.counts(
            reports.reportable_entries(AttendanceEntry.objects.filter(register__in=registers))
        )
        counts = {
            AttendanceStatus.PRESENT: totals["present"],
            AttendanceStatus.ABSENT: totals["absent"],
        }
        section_summary = [
            {"label": label, "count": counts.get(value, 0)}
            for value, label in AttendanceStatus.choices
        ]
    table = build_table(request, registers, REGISTER_COLUMNS, "-date")
    return render(
        request,
        "core/attendance_register_list.html",
        {
            "registers": table.page,
            "table": table,
            "form": form,
            "section_summary": section_summary,
            "section_total": sum(counts.values()) if section_summary is not None else None,
        },
    )


@administrator_required("core.add_attendanceregister")
def attendance_register_create(request):
    if request.method == "POST":
        form = AttendanceRegisterForm(request.POST)
        if form.is_valid():
            register = form.save()
            messages.success(request, "Attendance register opened as a draft.")
            return redirect("core:attendance-register-detail", pk=register.pk)
        # Opening a Section/date that already has a register goes to it.
        section = form.cleaned_data.get("section")
        on_date = form.cleaned_data.get("date")
        if section is not None and on_date is not None:
            existing = AttendanceRegister.objects.filter(section=section, date=on_date).first()
            if existing is not None:
                messages.info(request, "A register already exists for this Section and date.")
                return redirect("core:attendance-register-detail", pk=existing.pk)
    else:
        form = AttendanceRegisterForm()
    return render(request, "core/attendance_register_form.html", {"form": form})


@administrator_required("core.view_attendanceregister")
def attendance_register_detail(request, pk):
    register = get_object_or_404(
        AttendanceRegister.objects.select_related(
            "academic_year", "class_grade", "section__class_grade", "submitted_by"
        ),
        pk=pk,
    )
    entries = register.entries.select_related("academic_enrollment__student")
    capture_form = AttendanceCaptureForm(register=register)
    return render(
        request,
        "core/attendance_register_detail.html",
        {
            "register": register,
            "entries": entries,
            "capture_form": capture_form,
            "marked_count": entries.count(),
        },
    )


@administrator_required("core.change_attendanceregister")
def attendance_register_submit(request, pk):
    register = get_object_or_404(AttendanceRegister, pk=pk)
    if request.method == "POST":
        try:
            register.submit(actor=request.user)
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            messages.success(request, "Attendance submitted.")
    return redirect("core:attendance-register-detail", pk=register.pk)


@administrator_required("core.add_attendanceentry")
def attendance_capture(request, pk):
    register = get_object_or_404(AttendanceRegister, pk=pk)
    if request.method != "POST":
        return redirect("core:attendance-register-detail", pk=register.pk)

    if register.is_submitted:
        messages.error(
            request, "This register has been submitted; change attendance through a correction."
        )
        return redirect("core:attendance-register-detail", pk=register.pk)

    form = AttendanceCaptureForm(request.POST, register=register)
    if not form.is_valid():
        errors = [message for field_errors in form.errors.values() for message in field_errors]
        messages.error(request, f"Attendance was not saved. {errors[0]}")
        return redirect("core:attendance-register-detail", pk=register.pk)

    try:
        with transaction.atomic():
            for enrollment, status, note in form.statuses():
                register.save_draft_entry(enrollment=enrollment, status=status, absence_note=note)
    except ValidationError as error:
        messages.error(request, error.messages[0])
        return redirect("core:attendance-register-detail", pk=register.pk)

    if request.POST.get("action") == "submit":
        if not request.user.has_perm("core.change_attendanceregister"):
            messages.error(request, "Draft saved. You do not have permission to submit.")
            return redirect("core:attendance-register-detail", pk=register.pk)
        try:
            register.submit(actor=request.user)
        except ValidationError as error:
            messages.error(request, f"Draft saved but not submitted. {error.messages[0]}")
        else:
            messages.success(request, "Attendance saved and submitted.")
    else:
        messages.success(request, "Draft saved.")
    return redirect("core:attendance-register-detail", pk=register.pk)


@administrator_required("core.change_attendanceentry")
def attendance_entry_correct(request, pk):
    entry = get_object_or_404(
        AttendanceEntry.objects.select_related(
            "register__section__class_grade", "academic_enrollment__student"
        ),
        pk=pk,
    )
    if not entry.register.is_submitted:
        messages.info(
            request, "This register is still a draft; edit its attendance on the register page."
        )
        return redirect("core:attendance-register-detail", pk=entry.register_id)
    if request.method == "POST":
        form = AttendanceCorrectionForm(request.POST, entry=entry)
        if form.is_valid():
            try:
                entry.record_status_change(
                    form.cleaned_data["status"],
                    actor=request.user,
                    reason=form.cleaned_data["reason"],
                    absence_note=form.cleaned_data["absence_note"],
                )
            except ValidationError as error:
                messages.error(request, error.messages[0])
            else:
                messages.success(request, "Attendance corrected.")
                return redirect("core:attendance-register-detail", pk=entry.register_id)
    else:
        form = AttendanceCorrectionForm(entry=entry)
    corrections = entry.corrections.select_related("corrected_by")
    return render(
        request,
        "core/attendance_correction_form.html",
        {"form": form, "entry": entry, "corrections": corrections},
    )


@administrator_required("core.view_attendanceentry")
def student_attendance(request, pk):
    """Report 3 + 4: continuous history and reportable percentage for a Student.

    History lists every entry with the register's own Section and status, so
    context stays historical across transfers. Counts and percentage use only
    reportable attendance (core.reports).
    """
    student = get_object_or_404(Student, pk=pk)
    form = AttendanceRangeForm(request.GET or None)
    entries = AttendanceEntry.objects.filter(
        academic_enrollment__student=student
    ).select_related("register__academic_year", "register__section__class_grade")
    start = end = None
    if form.is_valid():
        start = form.cleaned_data.get("start")
        end = form.cleaned_data.get("end")
        if start is not None:
            entries = entries.filter(register__date__gte=start)
        if end is not None:
            entries = entries.filter(register__date__lte=end)
    totals = reports.student_summary(student, start=start, end=end)
    summary = [
        {"label": AttendanceStatus.PRESENT.label, "count": totals["present"]},
        {"label": AttendanceStatus.ABSENT.label, "count": totals["absent"]},
    ]
    return render(
        request,
        "core/student_attendance.html",
        {
            "student": student,
            "form": form,
            "entries": entries.order_by("register__date"),
            "summary": summary,
            "total": totals["total"],
            "percentage": totals["percentage"],
        },
    )


@administrator_required("core.view_attendanceentry")
def attendance_reports(request):
    return render(request, "core/attendance_reports.html")


@administrator_required("core.view_attendanceentry")
def report_daily_absentees(request):
    form = AttendanceDateForm(request.GET or None)
    absentees = None
    if form.is_valid():
        absentees = reports.daily_absentees(form.cleaned_data["date"])
    return render(
        request, "core/report_daily_absentees.html", {"form": form, "absentees": absentees}
    )


@administrator_required("core.view_attendanceregister")
def report_missing_attendance(request):
    form = MissingAttendanceForm(request.GET or None)
    rows = None
    if form.is_valid():
        rows = reports.missing_attendance(
            form.cleaned_data["start"],
            form.cleaned_data["end"],
            section=form.cleaned_data.get("section"),
        )
    return render(request, "core/report_missing_attendance.html", {"form": form, "rows": rows})


@administrator_required("core.view_attendanceentry")
def report_monthly_section(request):
    form = MonthlySectionSummaryForm(request.GET or None)
    summary = None
    if form.is_valid():
        year, month = form.cleaned_data["month"]
        summary = reports.monthly_section_summary(form.cleaned_data["section"], year, month)
    return render(
        request, "core/report_monthly_section.html", {"form": form, "summary": summary}
    )
