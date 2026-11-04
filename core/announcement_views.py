"""Phase 7 Gate 3 office views: announcements (ADR 0015). Administrators only."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.html import format_html

from core import announcements, notifications
from core.authorization import administrator_required
from core.forms import AnnouncementForm, WithdrawalForm
from core.models import Announcement, School
from core.tables import Column, build_table, parse_choice

STATUS_CHOICES = [("live", "Live"), ("withdrawn", "Withdrawn")]

ANNOUNCEMENT_COLUMNS = (
    Column("Published", "published", ("published_at",)),
    Column("Title", "title", ("title",)),
    Column("Audience", "audience", ("audience", "class_grade__name", "section__name")),
    Column("Status", "status", ("withdrawn_at",)),
)


def _announcements():
    return Announcement.objects.select_related(
        "class_grade", "section__class_grade", "published_by", "withdrawn_by")


@administrator_required("core.view_announcement")
def announcement_list(request):
    query = request.GET.get("q", "").strip()
    status = parse_choice(request, "status", STATUS_CHOICES)
    audience = parse_choice(request, "audience", Announcement.Audience.choices)
    notices = _announcements()
    if query:
        notices = notices.filter(Q(title__icontains=query) | Q(body__icontains=query))
    if status:
        notices = notices.filter(withdrawn_at__isnull=(status == "live"))
    if audience:
        notices = notices.filter(audience=audience)
    table = build_table(request, notices, ANNOUNCEMENT_COLUMNS, "-published")
    return render(request, "core/announcement_list.html", {
        "table": table, "query": query, "status": status, "audience": audience,
        "status_choices": STATUS_CHOICES, "audience_choices": Announcement.Audience.choices,
    })


@administrator_required("core.add_announcement")
def announcement_create(request):
    """Form -> preview -> publish. Nothing is stored until `confirm` is posted, and
    confirm re-validates everything the preview carried in hidden fields."""
    if request.method != "POST":
        return render(request, "core/announcement_form.html", {"form": AnnouncementForm()})
    if "edit" in request.POST:
        # Back from the preview: refill the form without showing validation noise.
        form = AnnouncementForm(initial=request.POST.dict())
        return render(request, "core/announcement_form.html", {"form": form})
    form = AnnouncementForm(request.POST)
    if not form.is_valid():
        return render(request, "core/announcement_form.html", {"form": form})
    if "confirm" in request.POST:
        notice = announcements.publish(actor=request.user, **form.cleaned_data)
        messages.success(request, "Notice published. Guardians can read it in the portal now.")
        return redirect("core:announcement-detail", pk=notice.pk)
    data = form.cleaned_data
    audience = data["audience"]
    is_class = audience == Announcement.Audience.CLASS
    is_section = audience == Announcement.Audience.SECTION
    preview = Announcement(
        title=data["title"].strip(), body=data["body"].strip(), audience=audience,
        class_grade=data["class_grade"] if is_class else None,
        section=data["section"] if is_section else None,
    )
    counts = announcements.preview_counts(
        audience=audience, class_grade=data["class_grade"], section=data["section"])
    return render(request, "core/announcement_preview.html", {
        "form": form, "notice": preview, "counts": counts,
    })


@administrator_required("core.view_announcement")
def announcement_detail(request, pk):
    notice = get_object_or_404(_announcements(), pk=pk)
    return render(request, "core/announcement_detail.html", {
        "notice": notice,
        "counts": announcements.audience_counts(notice),
        "assist": notifications.school_mode() == School.NotificationMode.ASSIST,
    })


def _stale_notice(notice, *, preparing):
    """Message for a notice that can no longer take this action, else None."""
    if notice.is_withdrawn:
        return ("This notice has been withdrawn." if preparing
                else "This notice has already been withdrawn.")
    if preparing and notifications.school_mode() != School.NotificationMode.ASSIST:
        return "WhatsApp sending is switched off for this school."
    return None


@administrator_required("core.send_notification")
def announcement_prepare(request, pk):
    notice = get_object_or_404(Announcement, pk=pk)
    stale = _stale_notice(notice, preparing=True)
    if stale:
        messages.error(request, stale)
        return redirect("core:announcement-detail", pk=pk)
    if request.method == "POST":
        try:
            result = announcements.prepare_messages(notice)
        except ValidationError as problem:
            messages.error(request, problem.messages[0])
        else:
            text = (f"Messages ready on the Message queue page: {result['prepared']}. "
                    f"Not sent (no WhatsApp consent): {result['skipped']}.")
            if result["done"]:
                text += f" Already sent or dismissed: {result['done']}."
            if result["failed"]:
                text += f" Could not prepare: {result['failed']}."
            messages.success(request, format_html(
                '{} <a href="{}">Open the Message queue</a>.',
                text, reverse("core:notifications-to-send")))
        return redirect("core:announcement-detail", pk=pk)
    return render(request, "core/announcement_prepare_confirm.html", {
        "notice": notice, "counts": announcements.audience_counts(notice),
    })


@administrator_required("core.withdraw_announcement")
def announcement_withdraw(request, pk):
    notice = get_object_or_404(Announcement, pk=pk)
    stale = _stale_notice(notice, preparing=False)
    if stale:
        messages.error(request, stale)
        return redirect("core:announcement-detail", pk=pk)
    form = WithdrawalForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            announcements.withdraw(notice, actor=request.user, reason=form.cleaned_data["reason"])
        except ValidationError as problem:
            messages.error(request, problem.messages[0])
        else:
            messages.info(request, "Notice withdrawn. Guardians no longer see it.")
        return redirect("core:announcement-detail", pk=pk)
    return render(request, "core/announcement_withdraw_confirm.html", {
        "notice": notice, "form": form,
    })
