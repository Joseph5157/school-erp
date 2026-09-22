from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render

from core.authorization import administrator_required
from core.forms import (
    AcademicEnrollmentForm,
    AcademicYearForm,
    AdmissionDecisionForm,
    ApplicantForm,
    ApplicantGuardianForm,
    ClassGradeForm,
    GuardianForm,
    SchoolForm,
    SectionForm,
)
from core.models import (
    AcademicEnrollment,
    AcademicYear,
    Applicant,
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
