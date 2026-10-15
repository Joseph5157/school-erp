"""Phase 7 Gate 3 office views: announcements (ADR 0015). Administrators only."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core import announcements, notifications
from core.authorization import administrator_required
from core.forms import AnnouncementForm
from core.models import Announcement, School


def _announcements():
    return Announcement.objects.select_related(
        "class_grade", "section__class_grade", "published_by", "withdrawn_by")


@administrator_required("core.view_announcement")
def announcement_list(request):
    return render(request, "core/announcement_list.html",
                  {"announcements": _announcements()[:100]})


@administrator_required("core.add_announcement")
def announcement_create(request):
    form = AnnouncementForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        notice = announcements.publish(actor=request.user, **form.cleaned_data)
        messages.success(request, "Notice published. Guardians can read it in the portal now.")
        return redirect("core:announcement-detail", pk=notice.pk)
    return render(request, "core/announcement_form.html", {"form": form})


@administrator_required("core.view_announcement")
def announcement_detail(request, pk):
    notice = get_object_or_404(_announcements(), pk=pk)
    return render(request, "core/announcement_detail.html", {
        "notice": notice,
        "counts": announcements.audience_counts(notice),
        "assist": notifications.school_mode() == School.NotificationMode.ASSIST,
    })


@administrator_required("core.send_notification")
@require_POST
def announcement_prepare(request, pk):
    notice = get_object_or_404(Announcement, pk=pk)
    try:
        result = announcements.prepare_messages(notice)
    except ValidationError as problem:
        messages.error(request, problem.messages[0])
    else:
        text = (f"Messages ready on the To send page: {result['prepared']}. "
                f"Not sent (no WhatsApp consent): {result['skipped']}.")
        if result["done"]:
            text += f" Already sent or dismissed: {result['done']}."
        if result["failed"]:
            text += f" Could not prepare: {result['failed']}."
        messages.success(request, text)
    return redirect("core:announcement-detail", pk=pk)


@administrator_required("core.withdraw_announcement")
@require_POST
def announcement_withdraw(request, pk):
    notice = get_object_or_404(Announcement, pk=pk)
    try:
        announcements.withdraw(notice, actor=request.user, reason=request.POST.get("reason"))
    except ValidationError as problem:
        messages.error(request, problem.messages[0])
    else:
        messages.info(request, "Notice withdrawn. Guardians no longer see it.")
    return redirect("core:announcement-detail", pk=pk)
