from django.contrib import messages
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render

from core.authorization import administrator_required
from core.forms import AcademicYearForm, SchoolForm
from core.models import AcademicYear, School


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
