"""Phase 7 Gate 1 views: guardian consent and the ASSIST To send page (ADR 0015)."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from core import notifications
from core.authorization import administrator_required
from core.forms import ContactConsentForm
from core.models import Guardian


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
