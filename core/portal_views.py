"""Guardian Portal views (ADR 0013, ADR 0014). Read-only."""

from django.http import Http404
from django.shortcuts import render
from django.views.decorators.http import require_safe

from core.authorization import guardian_required, guardian_visible_grant
from core.portal import portal_children


def _visible_grant_or_404(request, public_id):
    grant = guardian_visible_grant(request.user, public_id)
    if grant is None:
        raise Http404("No such student.")
    return grant


def _context(request, **extra):
    return {"children": portal_children(request.user), **extra}


@require_safe
@guardian_required
def home(request):
    return render(request, "portal/home.html", _context(request))


@require_safe
@guardian_required
def child(request, public_id):
    grant = _visible_grant_or_404(request, public_id)
    return render(
        request,
        "portal/child.html",
        _context(request, grant=grant, student=grant.student_guardian.student),
    )
