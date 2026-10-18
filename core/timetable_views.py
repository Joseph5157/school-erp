"""Office timetable views (ADR 0021 D2-D9). Administrators only.

TDB-4C: Period setup. TDB-4D: the Section weekly grid and the slot workflow, which
calls the TDB-4B lifecycle API (`TimetableSlot.create/change/end/delete`) and adds only
UI-layer rules (nothing in the past). The conflicts report and the Teacher dashboard are
later gates.
"""

import datetime
from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, ProtectedError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core import models
from core.authorization import administrator_required
from core.forms import (
    ScheduleDateForm,
    TimetablePeriodForm,
    TimetableSlotChangeForm,
    TimetableSlotCreateForm,
    TimetableSlotEndForm,
)
from core.models import (
    AcademicYear,
    AssessmentTeacherAssignment,
    Section,
    TimetablePeriod,
    TimetableSlot,
)

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


# --- TDB-4D: Section weekly grid and slot workflow ---------------------------------------


def _grid_url(academic_year, section, on=None):
    url = reverse("core:timetable-grid", args=[academic_year.pk, section.pk])
    return f"{url}?{urlencode({'date': on.isoformat()})}" if on else url


def _return_date(request):
    """The schedule date the user was viewing, if the query string carries a valid one."""
    try:
        return datetime.date.fromisoformat(request.GET.get("date", ""))
    except ValueError:
        return None


def _with_date(url, on):
    return f"{url}?{urlencode({'date': on.isoformat()})}" if on else url


def _default_schedule_date(academic_year, today):
    return today if academic_year.contains(today) else academic_year.start_date


def _add_domain_errors(form, error):
    """Show a TDB-4B ValidationError on the form instead of a server error."""
    if hasattr(error, "error_dict"):
        for field, errors in error.error_dict.items():
            form.add_error(field if field in form.fields else None, errors)
    else:
        form.add_error(None, error)
    form.apply_error_state()


def _teacher_name(user):
    return user.get_full_name() or user.get_username()


def _sections_with_offerings(academic_year):
    return (
        Section.objects.filter(class_grade__subject_offerings__academic_year=academic_year)
        .select_related("class_grade")
        .distinct()
        .order_by("class_grade__name", "name")
    )


@administrator_required("core.view_timetableperiod")
@administrator_required("core.view_timetableslot")
def timetable_sections(request, pk):
    academic_year = get_object_or_404(AcademicYear, pk=pk)
    return render(
        request,
        "core/timetable_sections.html",
        {"academic_year": academic_year, "sections": _sections_with_offerings(academic_year)},
    )


@administrator_required("core.view_timetableperiod")
@administrator_required("core.view_timetableslot")
def timetable_grid(request, pk, section_pk):
    academic_year = get_object_or_404(AcademicYear, pk=pk)
    section = get_object_or_404(Section.objects.select_related("class_grade"), pk=section_pk)
    today = models.business_today()
    schedule_date = _default_schedule_date(academic_year, today)
    if "date" in request.GET:
        date_form = ScheduleDateForm(request.GET, academic_year=academic_year)
        if date_form.is_valid():
            schedule_date = date_form.cleaned_data["date"]
    else:
        date_form = ScheduleDateForm(academic_year=academic_year, initial={"date": schedule_date})

    periods = list(academic_year.timetable_periods.order_by("sequence"))
    slots = {
        (slot.period_id, slot.weekday): slot
        for slot in TimetableSlot.objects.effective_on(schedule_date)
        .filter(section=section, period__academic_year=academic_year)
        .select_related("offering__subject")
    }
    teachers = {
        row.offering_id: _teacher_name(row.teacher)
        for row in AssessmentTeacherAssignment.objects.effective_on(schedule_date)
        .filter(section=section, offering__academic_year=academic_year)
        .select_related("teacher")
    }
    user = request.user
    can_add = user.has_perm("core.add_timetableslot")
    can_change = user.has_perm("core.change_timetableslot")
    can_delete = user.has_perm("core.delete_timetableslot")

    rows = []
    for period in periods:
        cells = []
        for weekday, weekday_name in TimetableSlot.WEEKDAY_CHOICES:
            slot = slots.get((period.pk, weekday))
            saturday_closed = weekday == 5 and not academic_year.saturdays_instructional
            cell = {
                "weekday": weekday, "weekday_name": weekday_name, "slot": slot,
                "saturday_closed": saturday_closed, "teacher": None, "historical": False,
                "can_add": False, "can_change": False, "can_end": False, "can_delete": False,
            }
            if slot is None:
                if can_add and not saturday_closed:
                    cell["can_add"] = True
                    cell["add_url"] = _with_date(
                        reverse("core:timetable-slot-create",
                                args=[academic_year.pk, section.pk, period.pk, weekday]),
                        schedule_date,
                    )
            else:
                cell["teacher"] = teachers.get(slot.offering_id)
                last = slot.end_date or academic_year.end_date
                live = last >= today
                cell["historical"] = not live
                cell["can_change"] = can_change and live
                cell["can_end"] = can_change and live
                cell["can_delete"] = can_delete and slot.start_date > today
                for action in ("change", "end", "delete"):
                    cell[f"{action}_url"] = _with_date(
                        reverse(f"core:timetable-slot-{action}", args=[slot.pk]), schedule_date
                    )
            cells.append(cell)
        rows.append({"period": period, "cells": cells})

    return render(
        request,
        "core/timetable_grid.html",
        {
            "academic_year": academic_year, "section": section, "schedule_date": schedule_date,
            "date_form": date_form, "rows": rows,
            "weekdays": [name for _, name in TimetableSlot.WEEKDAY_CHOICES],
            "periods_url": reverse("core:timetable-periods", args=[academic_year.pk]),
        },
    )


def _slot_for(pk):
    return get_object_or_404(
        TimetableSlot.objects.select_related(
            "period__academic_year", "section__class_grade", "offering__subject"
        ),
        pk=pk,
    )


def _slot_form_page(request, form, slot_cell, academic_year, section, on, **extra):
    return render(
        request,
        "core/timetable_slot_form.html",
        {
            "form": form, "cell_label": slot_cell, "academic_year": academic_year,
            "section": section, "cancel_url": _grid_url(academic_year, section, on), **extra,
        },
    )


@administrator_required("core.add_timetableslot")
def timetable_slot_create(request, pk, section_pk, period_pk, weekday):
    academic_year = get_object_or_404(AcademicYear, pk=pk)
    section = get_object_or_404(Section.objects.select_related("class_grade"), pk=section_pk)
    period = get_object_or_404(TimetablePeriod, pk=period_pk, academic_year=academic_year)
    if weekday not in range(6):
        raise Http404("Unknown weekday.")
    today = models.business_today()
    on = _return_date(request)
    start = max(on or _default_schedule_date(academic_year, today), today)
    options = {"academic_year": academic_year, "section": section, "today": today}
    if request.method == "POST":
        form = TimetableSlotCreateForm(request.POST, **options)
        if form.is_valid():
            offering = form.cleaned_data["offering"]
            try:
                slot = TimetableSlot.create(
                    period=period, weekday=weekday, section=section, offering=offering,
                    start_date=form.cleaned_data["start_date"],
                    end_date=form.cleaned_data["end_date"],
                )
            except ValidationError as error:
                _add_domain_errors(form, error)
            else:
                messages.success(
                    request,
                    f"{offering.subject.name} scheduled for {section}, {period.label} on "
                    f"{slot.get_weekday_display()} from {slot.start_date:%d %b %Y}.",
                )
                return redirect(_grid_url(academic_year, section, on))
    else:
        form = TimetableSlotCreateForm(initial={"start_date": start}, **options)
    day = dict(TimetableSlot.WEEKDAY_CHOICES)[weekday]
    return _slot_form_page(
        request, form, f"{section} · {period.label} · {day}", academic_year, section, on,
        title="Add slot", submit_label="Add slot",
    )


@administrator_required("core.change_timetableslot")
def timetable_slot_change(request, pk):
    slot = _slot_for(pk)
    academic_year, section = slot.period.academic_year, slot.section
    today = models.business_today()
    on = _return_date(request)
    if request.method == "POST":
        form = TimetableSlotChangeForm(request.POST, slot=slot, today=today)
        if form.is_valid():
            try:
                slot.change(
                    effective_from=form.cleaned_data["effective_from"],
                    offering=form.cleaned_data["offering"],
                    end_date=form.cleaned_data["end_date"],
                )
            except ValidationError as error:
                _add_domain_errors(form, error)
            else:
                messages.success(
                    request,
                    f"{slot.period.label} on {slot.get_weekday_display()} changed from "
                    f"{form.cleaned_data['effective_from']:%d %b %Y}.",
                )
                return redirect(_grid_url(academic_year, section, on))
    else:
        form = TimetableSlotChangeForm(slot=slot, today=today)
    return _slot_form_page(
        request, form,
        f"{section} · {slot.period.label} · {slot.get_weekday_display()}",
        academic_year, section, on, title="Change slot", submit_label="Save change",
    )


@administrator_required("core.change_timetableslot")
def timetable_slot_end(request, pk):
    slot = _slot_for(pk)
    academic_year, section = slot.period.academic_year, slot.section
    today = models.business_today()
    on = _return_date(request)
    if request.method == "POST":
        form = TimetableSlotEndForm(request.POST, slot=slot, today=today)
        if form.is_valid():
            try:
                slot.end(form.cleaned_data["end_date"])
            except ValidationError as error:
                _add_domain_errors(form, error)
            else:
                messages.success(
                    request,
                    f"{slot.offering.subject.name} in {slot.period.label} on "
                    f"{slot.get_weekday_display()} now ends on "
                    f"{form.cleaned_data['end_date']:%d %b %Y}.",
                )
                return redirect(_grid_url(academic_year, section, on))
    else:
        form = TimetableSlotEndForm(slot=slot, today=today)
    return _slot_form_page(
        request, form,
        f"{section} · {slot.period.label} · {slot.get_weekday_display()} · "
        f"{slot.offering.subject.name}",
        academic_year, section, on, title="End slot", submit_label="End slot",
    )


@administrator_required("core.delete_timetableslot")
def timetable_slot_delete(request, pk):
    slot = _slot_for(pk)
    academic_year, section = slot.period.academic_year, slot.section
    on = _return_date(request)
    grid_url = _grid_url(academic_year, section, on)
    if request.method == "POST":
        try:
            slot.delete()
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(request, "Slot deleted.")
        return redirect(grid_url)
    return render(
        request,
        "core/timetable_slot_delete.html",
        {
            "slot": slot, "academic_year": academic_year, "section": section,
            "started": slot.has_started, "grid_url": grid_url,
            "end_url": _with_date(reverse("core:timetable-slot-end", args=[slot.pk]), on),
            "can_end": request.user.has_perm("core.change_timetableslot"),
        },
    )
