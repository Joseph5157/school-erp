"""Guardian Portal views (ADR 0013, ADR 0014). Read-only."""

from django.http import Http404
from django.shortcuts import render
from django.views.decorators.http import require_safe

from core.announcements import visible_announcements
from core.authorization import guardian_required, guardian_visible_grant
from core.documents import report_card as report_card_documents
from core.documents import service
from core.portal import (
    attendance_years,
    portal_children,
    student_profile,
    submitted_attendance,
    visible_publications,
)


def _visible_grant_or_404(request, public_id):
    grant = guardian_visible_grant(request.user, public_id)
    if grant is None:
        raise Http404("No such student.")
    return grant


def _context(request, **extra):
    children = portal_children(request.user)
    grant = extra.get("grant")
    if grant is None:
        grant = next((item["grant"] for item in children if item["visible"]), None)
    return {"children": children, "nav_grant": grant, **extra}


@require_safe
@guardian_required
def home(request):
    return render(request, "portal/home.html",
                  _context(request, notices=visible_announcements(request.user)[:3]))


@require_safe
@guardian_required
def child(request, public_id):
    grant = _visible_grant_or_404(request, public_id)
    student = grant.student_guardian.student
    return render(
        request,
        "portal/child.html",
        _context(request, grant=grant, student=student, profile=student_profile(student)),
    )


@require_safe
@guardian_required
def attendance(request, public_id):
    """Submitted attendance for one Academic Year (ADR 0014, P8)."""
    grant = _visible_grant_or_404(request, public_id)
    student = grant.student_guardian.student
    years = attendance_years(student)
    chosen = years[0] if years else None
    requested = request.GET.get("year", "")
    for year in years:
        if year.start_date.isoformat() == requested:
            chosen = year
    data = submitted_attendance(student, chosen) if chosen else {"days": [], "summary": None}
    return render(
        request,
        "portal/attendance.html",
        _context(request, grant=grant, student=student, years=years, year=chosen, **data),
    )


@require_safe
@guardian_required
def report_cards(request, public_id):
    grant = _visible_grant_or_404(request, public_id)
    student = grant.student_guardian.student
    return render(
        request,
        "portal/report_cards.html",
        _context(request, grant=grant, student=student,
                 publications=visible_publications(student)),
    )


@require_safe
@guardian_required
def report_card(request, public_id, publication_id):
    """One released report card, rendered only from its snapshot."""
    grant = _visible_grant_or_404(request, public_id)
    student = grant.student_guardian.student
    pub = next((p for p in visible_publications(student) if p.public_id == publication_id),
               None)
    if pub is None:
        raise Http404("No such report card.")
    return render(
        request,
        "portal/report_card.html",
        _context(request, grant=grant, student=student, pub=pub, entries=pub.entries.all()),
    )


@require_safe
@guardian_required
def report_card_pdf(request, public_id, publication_id):
    """PDF of one released report card; issued once, then reprinted from its snapshot."""
    grant = _visible_grant_or_404(request, public_id)
    student = grant.student_guardian.student
    pub = next((p for p in visible_publications(student) if p.public_id == publication_id),
               None)
    document = report_card_documents.document_for(pub, actor=request.user) if pub else None
    if document is None:
        raise Http404("No such report card.")
    return service.pdf_response(document, actor=request.user)


@require_safe
@guardian_required
def notices(request):
    return render(request, "portal/notices.html",
                  _context(request, notices=visible_announcements(request.user)))


@require_safe
@guardian_required
def notice(request, notice_id):
    item = next((a for a in visible_announcements(request.user) if a.public_id == notice_id),
                None)
    if item is None:
        raise Http404("No such notice.")
    return render(request, "portal/notice.html", _context(request, notice=item))
