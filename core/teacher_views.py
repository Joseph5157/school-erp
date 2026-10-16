"""Phase 3D office views: teacher logins (audit F09). Administrators only."""

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.utils.cache import add_never_cache_headers

from core import teacher_accounts
from core.authorization import administrator_required
from core.forms import TeacherCreateForm
from core.tables import Column, build_table, parse_choice

PERMISSION = "accounts.manage_teacher_accounts"
STATUS_CHOICES = [("active", "Active"), ("inactive", "Inactive")]

TEACHER_COLUMNS = (
    Column("Name", "name", ("first_name", "last_name", "username")),
    Column("Username", "username", ("username",)),
    Column("Email"),
    Column("Status", "status", ("is_active", "username"), ("-is_active", "username")),
    Column("Assignments", "assignments", ("assignment_count", "username")),
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
            user, password = teacher_accounts.create_teacher(actor=request.user, **form.cleaned_data)
        except ValidationError as error:
            form.add_error("username", error)
        else:
            return _teacher_slip(request, user, password, heading="Teacher account created")
    return render(request, "core/teacher_form.html", {"form": form})
