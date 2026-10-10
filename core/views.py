from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from core import reports
from core.authorization import administrator_required
from core.forms import (
    AcademicEnrollmentForm,
    AcademicYearForm,
    AdmissionDecisionForm,
    ApplicantForm,
    ApplicantGuardianForm,
    AttendanceCaptureForm,
    AttendanceCorrectionForm,
    AttendanceDateForm,
    AttendanceRangeForm,
    AttendanceRegisterFilterForm,
    AttendanceRegisterForm,
    CalendarDateCheckForm,
    ClassGradeForm,
    GuardianForm,
    MissingAttendanceForm,
    MonthlySectionSummaryForm,
    SchoolCalendarDayForm,
    SchoolCalendarDayLabelForm,
    SchoolForm,
    SectionForm,
    StudentStatusForm,
)
from core.models import (
    AcademicEnrollment,
    AcademicYear,
    Applicant,
    AttendanceEntry,
    AttendanceRegister,
    AttendanceStatus,
    ClassGrade,
    Guardian,
    School,
    SchoolCalendarDay,
    Student,
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
    enrollments = student.enrollments.select_related("academic_year", "class_grade", "section")
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
        "academic_year", "class_grade", "section"
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
        AttendanceRegister.objects.select_related("academic_year", "class_grade", "section"),
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
            "register__section", "academic_enrollment__student"
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
