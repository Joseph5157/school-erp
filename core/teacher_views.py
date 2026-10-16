"""Phase 3D office views: teacher logins (audit F09). Administrators only."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.cache import add_never_cache_headers

from accounts.models import SecurityEvent
from core import teacher_accounts
from core.authorization import administrator_required
from core.forms import TeacherCreateForm, TeacherDeactivateForm, TeacherUsernameForm
from core.tables import Column, build_table, parse_choice

PERMISSION = "accounts.manage_teacher_accounts"
STATUS_CHOICES = [("active", "Active"), ("inactive", "Inactive")]

TEACHER_COLUMNS = (
    Column("Name", "name", ("first_name", "last_name", "username")),
    Column("Username", "username", ("username",)),
    Column("Email"),
    Column("Status", "status", ("is_active", "username"), ("-is_active", "username")),
    Column("Assignments (all years)", "assignments", ("assignment_count", "username")),
    Column("Last sign-in", "last_login", ("last_login", "username")),
)


def _teacher_slip(request, user, password, *, heading):
    """Render the one-time temporary password; never cached, never stored."""
    response = render(
        request,
        "core/teacher_credential_slip.html",
        {"teacher": user, "password": password, "heading": heading},
    )
    add_never_cache_headers(response)
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    return response


def get_teacher_or_404(pk):
    return get_object_or_404(teacher_accounts.teacher_queryset(), pk=pk)


@administrator_required(PERMISSION)
def teacher_list(request):
    query = request.GET.get("q", "").strip()
    status = parse_choice(request, "status", STATUS_CHOICES)
    teachers = teacher_accounts.teacher_queryset()
    if query:
        teachers = teachers.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(username__icontains=query)
            | Q(email__icontains=query)
        )
    if status:
        teachers = teachers.filter(is_active=(status == "active"))
    table = build_table(request, teachers, TEACHER_COLUMNS, "name")
    return render(
        request,
        "core/teacher_list.html",
        {
            "teachers": table.page,
            "table": table,
            "query": query,
            "status": status,
            "status_choices": STATUS_CHOICES,
        },
    )


@administrator_required(PERMISSION)
def teacher_create(request):
    form = TeacherCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            user, password = teacher_accounts.create_teacher(
                actor=request.user, **form.cleaned_data
            )
        except ValidationError as error:
            form.add_error("username", error)
        else:
            return _teacher_slip(request, user, password, heading="Teacher account created")
    return render(request, "core/teacher_form.html", {"form": form})


@administrator_required(PERMISSION)
def teacher_detail(request, pk):
    teacher = get_teacher_or_404(pk)
    return render(request, "core/teacher_detail.html", {
        "teacher": teacher,
        "subject_assignments": teacher.assessment_assignments.select_related(
            "offering__academic_year", "offering__class_grade", "offering__subject", "section"
        ),
        "class_assignments": teacher.class_teacher_assignments.select_related(
            "academic_year", "section__class_grade"
        ),
        "events": SecurityEvent.objects.filter(subject_user=teacher).select_related("actor")[:10],
    })


@administrator_required(PERMISSION)
def teacher_reset_password(request, pk):
    teacher = get_teacher_or_404(pk)
    if request.method == "POST":
        try:
            password = teacher_accounts.reset_teacher_password(user=teacher, actor=request.user)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
            return redirect("core:teacher-detail", pk=teacher.pk)
        return _teacher_slip(request, teacher, password, heading="Password reset")
    return render(request, "core/teacher_reset_confirm.html", {"teacher": teacher})


@administrator_required(PERMISSION)
def teacher_username(request, pk):
    teacher = get_teacher_or_404(pk)
    form = TeacherUsernameForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            teacher_accounts.change_teacher_username(
                user=teacher, new_username=form.cleaned_data["username"], actor=request.user
            )
        except ValidationError as error:
            form.add_error("username", error)
        else:
            messages.success(request, "Username changed.")
            return redirect("core:teacher-detail", pk=teacher.pk)
    return render(request, "core/teacher_username_form.html", {"teacher": teacher, "form": form})


@administrator_required(PERMISSION)
def teacher_deactivate(request, pk):
    teacher = get_teacher_or_404(pk)
    form = TeacherDeactivateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            teacher_accounts.deactivate_teacher(
                user=teacher, reason=form.cleaned_data["reason"], actor=request.user
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Teacher login deactivated. Open sessions have ended.")
            return redirect("core:teacher-detail", pk=teacher.pk)
    return render(request, "core/teacher_deactivate_confirm.html", {
        "teacher": teacher, "form": form,
        "assignment_count": teacher.assignment_count,
    })


@administrator_required(PERMISSION)
def teacher_reactivate(request, pk):
    teacher = get_teacher_or_404(pk)
    if request.method == "POST":
        try:
            teacher_accounts.reactivate_teacher(user=teacher, actor=request.user)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(request, "Teacher login reactivated. The password is unchanged.")
        return redirect("core:teacher-detail", pk=teacher.pk)
    return render(request, "core/teacher_reactivate_confirm.html", {"teacher": teacher})
