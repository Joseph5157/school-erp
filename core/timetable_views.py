"""TDB-4C office views: timetable Period setup (ADR 0021 D2, D9). Administrators only.

Slots, the weekly grid and the reports are later gates; nothing here touches them.
"""

from django.contrib import messages
from django.db.models import Count, ProtectedError
from django.shortcuts import get_object_or_404, redirect, render

from core.authorization import administrator_required
from core.forms import TimetablePeriodForm
from core.models import AcademicYear, TimetablePeriod

PERIOD_IN_USE = "This period is already used by timetable slots and cannot be deleted."


def _periods_page(year):
    return redirect("core:timetable-periods", pk=year.pk)


@administrator_required("core.view_timetableperiod")
def timetable_index(request):
    years = AcademicYear.objects.annotate(period_count=Count("timetable_periods"))
    return render(request, "core/timetable_index.html", {"academic_years": years})


@administrator_required("core.view_timetableperiod")
def timetable_periods(request, pk):
    academic_year = get_object_or_404(AcademicYear, pk=pk)
    periods = academic_year.timetable_periods.order_by("sequence")
    return render(
        request,
        "core/timetable_periods.html",
        {"academic_year": academic_year, "periods": periods},
    )


@administrator_required("core.add_timetableperiod")
def timetable_period_create(request, pk):
    academic_year = get_object_or_404(AcademicYear, pk=pk)
    form = TimetablePeriodForm(request.POST or None, academic_year=academic_year)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Period {form.instance.label} added.")
        return _periods_page(academic_year)
    return render(
        request,
        "core/timetable_period_form.html",
        {"form": form, "academic_year": academic_year, "creating": True},
    )


@administrator_required("core.change_timetableperiod")
def timetable_period_update(request, pk):
    period = get_object_or_404(TimetablePeriod.objects.select_related("academic_year"), pk=pk)
    form = TimetablePeriodForm(request.POST or None, instance=period)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Period {period.label} saved.")
        return _periods_page(period.academic_year)
    return render(
        request,
        "core/timetable_period_form.html",
        {"form": form, "academic_year": period.academic_year, "creating": False},
    )


@administrator_required("core.delete_timetableperiod")
def timetable_period_delete(request, pk):
    period = get_object_or_404(TimetablePeriod.objects.select_related("academic_year"), pk=pk)
    in_use = period.slots.exists()
    if request.method == "POST":
        try:
            if in_use:
                raise ProtectedError(PERIOD_IN_USE, set())
            period.delete()
        except ProtectedError:
            messages.error(request, PERIOD_IN_USE)
        else:
            messages.success(request, f"Period {period.label} deleted.")
        return _periods_page(period.academic_year)
    return render(
        request,
        "core/timetable_period_delete.html",
        {"period": period, "academic_year": period.academic_year, "in_use": in_use,
         "in_use_message": PERIOD_IN_USE},
    )
