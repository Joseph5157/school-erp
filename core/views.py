from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404, redirect, render

from core import assessment_reports, reports
from core.authorization import (
    administrator_required,
    can_enter_results,
    can_take_attendance,
    can_write_term_remarks,
    class_teacher_assignments,
    class_teacher_on,
    is_teacher,
    teacher_assignments,
    teacher_required,
)
from core.forms import (
    AcademicEnrollmentForm,
    AcademicTermForm,
    AcademicYearForm,
    AdmissionDecisionForm,
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
    GradeBoundaryForm,
    GradingScaleForm,
    GuardianForm,
    MissingAttendanceForm,
    MonthlySectionSummaryForm,
    OfferedSubjectsLookupForm,
    ResultCorrectionForm,
    ResultEntryForm,
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
    School,
    SchoolCalendarDay,
    Section,
    SectionClassTeacher,
    Student,
    StudentResult,
    Subject,
    TermRemark,
    business_today,
)


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
        sections = Section.objects.filter(
            teacher_assignments__teacher=request.user,
            teacher_assignments__offering__academic_year=term.academic_year,
        ).select_related("class_grade").distinct()
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
                    elif not text and existing is not None:
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
    """Send each login to its own landing page."""
    if is_teacher(request.user) and not request.user.has_perm("core.view_school"):
        return redirect("core:my-home")
    return redirect("core:school-detail")


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


# --- Phase 4 Gate 5: teacher DRAFT result entry (ADR 0010) -----------------


@teacher_required
def my_assessments(request):
    duties = list(teacher_assignments(request.user))
    query = Q(pk__in=[])
    for duty in duties:
        query |= Q(offering=duty.offering, section=duty.section)
    assessments = _assessments().filter(query).order_by("-assessment_date", "name")
    remark_links = []
    seen = set()
    for duty in duties:
        for term in duty.offering.academic_year.terms.all():
            key = (term.pk, duty.section_id)
            if key not in seen:
                seen.add(key)
                remark_links.append((term, duty.section))
    return render(
        request,
        "core/my_assessments.html",
        {"duties": duties, "assessments": assessments, "remark_links": remark_links},
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


@administrator_required("core.view_applicant")
def applicant_list(request):
    applicants = Applicant.objects.all()
    return render(request, "core/applicant_list.html", {"applicants": applicants})


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
        applicant.record_admission_decision(form.cleaned_data["decision"])
    except ValidationError as error:
        messages.error(request, error.messages[0])
        return redirect("core:applicant-detail", pk=applicant.pk)

    messages.success(request, f"Admission decision recorded: {applicant.admission_status}.")
    return redirect("core:applicant-detail", pk=applicant.pk)


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
    return render(
        request,
        "core/guardian_detail.html",
        {"guardian": guardian, "applicant_links": applicant_links},
    )


@administrator_required("core.view_student")
def student_list(request):
    query = request.GET.get("q", "").strip()
    students = Student.objects.all()
    if query:
        students = students.filter(
            Q(full_name__icontains=query)
            | Q(email__icontains=query)
            | Q(phone__icontains=query)
        )
    return render(
        request,
        "core/student_list.html",
        {"students": students, "query": query},
    )


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
        },
    )


@administrator_required("core.add_academicenrollment")
def student_enroll(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == "POST":
        form = AcademicEnrollmentForm(request.POST)
        if form.is_valid():
            try:
                student.enroll(
                    academic_year=form.cleaned_data["academic_year"],
                    class_grade=form.cleaned_data["class_grade"],
                    section=form.cleaned_data["section"],
                    start_date=form.cleaned_data["start_date"],
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

    try:
        student.record_status_change(form.cleaned_data["status"])
    except ValidationError as error:
        messages.error(request, error.messages[0])
        return redirect("core:student-detail", pk=student.pk)

    messages.success(request, f"Student status changed: {student.status}.")
    return redirect("core:student-detail", pk=student.pk)


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
    return render(
        request,
        "core/attendance_register_list.html",
        {
            "registers": registers,
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
