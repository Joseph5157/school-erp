"""The office queue for "Can't sign in?" requests (G-06 sign-in help spec §5, PR 1).

Only the queue's own permissions open it (OD-H2): `accounts.view_signinhelprequest` to list and
`accounts.change_signinhelprequest` to record an outcome, never `core.reset_guardian_password`.
Typed values are shown only as escaped element text (spec §5.2) and never go into a URL, a
message or a log. There is no search box and no "find guardian" link on purpose.
"""

from django import forms
from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST, require_safe

from accounts import sign_in_help
from accounts.models import SignInHelpRequest
from core.authorization import administrator_required
from core.tables import Column, build_table, parse_choice

VIEW_PERM = "accounts.view_signinhelprequest"
CHANGE_PERM = "accounts.change_signinhelprequest"
TABS = (("open", "Open"), ("handled", "Handled"))

OPEN_COLUMNS = (
    Column("Received", "received", ("received_at",)),
    Column("Your name"),
    Column("Child's name"),
    Column("Class and section"),
)
OUTCOME_COLUMN = Column("Outcome", action=True)
HANDLED_COLUMNS = (
    *OPEN_COLUMNS,
    Column("Outcome"),
    Column("Handled by"),
    Column("Handled", "handled", ("handled_at",)),
)


class OutcomeForm(forms.Form):
    outcome = forms.ChoiceField(choices=SignInHelpRequest.Outcome.choices)


@administrator_required(VIEW_PERM)
@require_safe
def sign_in_help_requests(request):
    tab = parse_choice(request, "tab", TABS) or "open"
    can_handle = request.user.has_perm(CHANGE_PERM)
    if tab == "open":
        rows = sign_in_help.open_requests()
        columns = (*OPEN_COLUMNS, OUTCOME_COLUMN) if can_handle else OPEN_COLUMNS
        table = build_table(request, rows, columns, "received")  # oldest first
    else:
        rows = sign_in_help.handled_requests().select_related("handled_by")
        table = build_table(request, rows, HANDLED_COLUMNS, "-handled")  # newest first
    dropped_today, dropped_week = sign_in_help.drop_counts()
    base = reverse("core:sign-in-help-requests")
    return render(request, "core/sign_in_help_requests.html", {
        "table": table,
        "rows": table.page,
        "tab": tab,
        "tabs": [{"label": label, "url": f"{base}?tab={value}", "active": value == tab}
                 for value, label in TABS],
        "can_handle": can_handle,
        "outcomes": SignInHelpRequest.Outcome.choices,
        "dropped_today": dropped_today,
        "dropped_week": dropped_week,
        "expired_waiting": sign_in_help.expired_rows_exist(),
        "retention_days": sign_in_help.RETENTION_DAYS,
    })


@administrator_required(CHANGE_PERM)
@require_POST
def sign_in_help_request_handle(request, pk):
    form = OutcomeForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Choose an outcome.")
        return redirect("core:sign-in-help-requests")
    try:
        sign_in_help.handle(pk, actor=request.user, outcome=form.cleaned_data["outcome"])
    except sign_in_help.AlreadyHandled as already:
        by = already.row.handled_by
        name = (by.get_full_name() or by.get_username()) if by else "someone who has since left"
        messages.info(request, f"Already handled by {name}. Nothing was changed.")
    else:
        messages.success(request, "Outcome saved.")
    return redirect("core:sign-in-help-requests")
