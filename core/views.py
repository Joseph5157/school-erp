from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from core.authorization import administrator_required
from core.forms import (
    AcademicEnrollmentForm,
    AcademicYearForm,
    AdmissionDecisionForm,
    ApplicantForm,
    ApplicantGuardianForm,
    AttendanceCaptureForm,
    AttendanceCorrectionForm,
    AttendanceRangeForm,
    AttendanceRegisterFilterForm,
    AttendanceRegisterForm,
    ClassGradeForm,
    GuardianForm,
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
        counts = {
            row["status"]: row["n"]
            for row in AttendanceEntry.objects.filter(register__in=registers)
            .order_by()
            .values("status")
            .annotate(n=Count("id"))
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
            messages.success(request, "Attendance register created.")
            return redirect("core:attendance-register-detail", pk=register.pk)
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
        {"register": register, "entries": entries, "capture_form": capture_form},
    )


@administrator_required("core.add_attendanceentry")
def attendance_capture(request, pk):
    register = get_object_or_404(AttendanceRegister, pk=pk)
    if request.method != "POST":
        return redirect("core:attendance-register-detail", pk=register.pk)

    form = AttendanceCaptureForm(request.POST, register=register)
    if not form.is_valid():
        messages.error(request, "Attendance was not captured. Choose a status for every Student.")
        return redirect("core:attendance-register-detail", pk=register.pk)

    try:
        with transaction.atomic():
            for enrollment, status in form.statuses():
                register.capture(enrollment=enrollment, status=status)
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        messages.success(request, "Attendance captured.")
    return redirect("core:attendance-register-detail", pk=register.pk)


@administrator_required("core.change_attendanceentry")
def attendance_entry_correct(request, pk):
    entry = get_object_or_404(
        AttendanceEntry.objects.select_related(
            "register__section", "academic_enrollment__student"
        ),
        pk=pk,
    )
    if request.method == "POST":
        form = AttendanceCorrectionForm(request.POST, entry=entry)
        if form.is_valid():
            try:
                entry.record_status_change(
                    form.cleaned_data["status"],
                    actor=request.user,
                    reason=form.cleaned_data["reason"],
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
    student = get_object_or_404(Student, pk=pk)
    form = AttendanceRangeForm(request.GET or None)
    entries = AttendanceEntry.objects.filter(
        academic_enrollment__student=student
    ).select_related("register__academic_year", "register__section")
    if form.is_valid():
        start = form.cleaned_data.get("start")
        end = form.cleaned_data.get("end")
        if start is not None:
            entries = entries.filter(register__date__gte=start)
        if end is not None:
            entries = entries.filter(register__date__lte=end)
    counts = {
        row["status"]: row["n"]
        for row in entries.order_by().values("status").annotate(n=Count("id"))
    }
    summary = [
        {"label": label, "count": counts.get(value, 0)}
        for value, label in AttendanceStatus.choices
    ]
    return render(
        request,
        "core/student_attendance.html",
        {
            "student": student,
            "form": form,
            "entries": entries.order_by("register__date"),
            "summary": summary,
            "total": sum(counts.values()),
        },
    )
