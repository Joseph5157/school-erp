"""Phase 7 Gate 1 views: guardian consent and the ASSIST To send page (ADR 0015)."""

from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core import notifications
from core.authorization import administrator_required
from core.forms import ContactConsentForm
from core.models import Guardian, Notification, School


@administrator_required("core.add_guardiancontactconsent")
@require_POST
def guardian_consent_record(request, pk):
    guardian = get_object_or_404(Guardian, pk=pk)
    form = ContactConsentForm(request.POST)
    if form.is_valid():
        consent = notifications.record_consent(
            guardian=guardian, user=request.user, **form.cleaned_data
        )
        messages.success(request, f"WhatsApp consent recorded: {consent.get_status_display()}.")
    else:
        messages.error(request, "Consent was not recorded. Choose a decision and how it was given.")
    return redirect("core:guardian-detail", pk=pk)


@administrator_required("core.send_notification")
def to_send(request):
    rows = [
        {
            "notification": notification,
            "text": notifications.render(notification),
            "link": notifications.whatsapp_link(notification),
        }
        for notification in notifications.to_send()
    ]
    sent_today = (
        Notification.objects.filter(marked_sent_at__date=timezone.localdate())
        .select_related("guardian", "marked_sent_by")
        .order_by("-marked_sent_at")
    )
    mode = notifications.school_mode()
    return render(request, "core/notifications_to_send.html", {
        "rows": rows,
        "sent_today": sent_today,
        "portal_only": mode == School.NotificationMode.PORTAL_ONLY,
        "portal_address_missing": (
            mode == School.NotificationMode.ASSIST and not settings.PORTAL_BASE_URL
        ),
    })


@administrator_required("core.send_notification")
@require_POST
def notification_mark_sent(request, pk):
    notification = get_object_or_404(Notification, pk=pk)
    try:
        result = notifications.mark_sent(notification, user=request.user)
    except notifications.NotificationError as problem:
        messages.error(request, str(problem))
    else:
        if result.status == Notification.Status.SENT:
            messages.success(request, "Marked as sent.")
        else:
            messages.info(
                request, "The guardian has opted out, so this message is recorded as not sent."
            )
    return redirect("core:notifications-to-send")


@administrator_required("core.send_notification")
@require_POST
def notification_dismiss(request, pk):
    notification = get_object_or_404(Notification, pk=pk)
    try:
        notifications.dismiss(notification, user=request.user, reason=request.POST.get("reason"))
    except notifications.NotificationError as problem:
        messages.error(request, str(problem))
    else:
        messages.info(request, "Message dismissed. It will not be sent.")
    return redirect("core:notifications-to-send")
