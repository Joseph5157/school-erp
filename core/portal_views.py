"""Guardian Portal views (ADR 0013, ADR 0014). Read-only."""

from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_safe

from core import reports
from core.announcements import visible_announcements
from core.authorization import guardian_required
from core.documents import report_card as report_card_documents
from core.documents import service
from core.portal import (
    attendance_month,
    attendance_years,
    child_summaries,
    default_nav_grant,
    parse_attendance_month,
    portal_children,
    report_card_groups,
    student_profile,
    submitted_attendance,
    visible_publications,
)

# Notices are listed a page at a time, so an older school's list stays quick on a phone.
NOTICES_PER_PAGE = 20


def _children(request):
    """portal_children for this request, built once and reused by every helper (audit 08, P8-03)."""
    if not hasattr(request, "_portal_children"):
        request._portal_children = portal_children(request.user)
    return request._portal_children


def _visible_grant_or_404(request, public_id):
    """The grant behind a portal identifier, from this request's children list.

    Same rule as authorization.guardian_visible_grant: an active grant of this guardian whose
    access review is not pending (fails closed, OD-8); anything else is a 404.
    """
    for item in _children(request):
        if item["grant"].public_id == public_id and item["visible"]:
            return item["grant"]
    raise Http404("No such student.")


def _context(request, switch_route="portal:child", **extra):
    """Shared portal context.

    `switch_route` is the child-scoped route the switcher keeps the guardian on
    ("same task, different child"); it only ever takes a grant id, so no
    publication or other per-child id is carried across children.
    """
    children = _children(request)
    grant = extra.get("grant")
    if grant is None:
        grant = default_nav_grant(children)
    visible = [item for item in children if item["visible"]]
    return {
        "children": children,
        "nav_grant": grant,
        # Child switcher: visible grants only, and only worth showing for 2+.
        "switcher_children": [
            {**item, "url": reverse(switch_route, args=[item["grant"].public_id])}
            for item in visible
        ] if len(visible) > 1 else [],
        **extra,
    }


@require_safe
@guardian_required
def home(request):
    children = _children(request)
    return render(
        request,
        "portal/home.html",
        _context(
            request,
            children=children,
            notices=list(visible_announcements(request.user, children)[:3]),  # LIMIT 3 in SQL
            summaries=child_summaries(children),
        ),
    )


@require_safe
@guardian_required
def child(request, public_id):
    grant = _visible_grant_or_404(request, public_id)
    student = grant.student_guardian.student
    context = _context(request, grant=grant, student=student, profile=student_profile(student))
    # Same batched, snapshot-based summary the Home cards use (never recomputed).
    own = [item for item in context["children"] if item["grant"].pk == grant.pk]
    summaries = child_summaries(own)
    return render(
        request,
        "portal/child.html",
        {**context, "summary": summaries[0] if summaries else None},
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
    data = submitted_attendance(student, chosen) if chosen else {"summary": None}
    month = None
    if chosen:
        selected = parse_attendance_month(
            chosen, request.GET.get("month", ""), reports.business_today()
        )
        month = attendance_month(student, chosen, *selected)
    return render(
        request,
        "portal/attendance.html",
        _context(request, switch_route="portal:attendance", grant=grant, student=student,
                 years=years, year=chosen, month=month, **data),
    )


@require_safe
@guardian_required
def report_cards(request, public_id):
    grant = _visible_grant_or_404(request, public_id)
    student = grant.student_guardian.student
    return render(
        request,
        "portal/report_cards.html",
        _context(request, switch_route="portal:report-cards", grant=grant, student=student,
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
    entries = list(pub.entries.all())  # frozen snapshot rows, in snapshot display_order
    return render(
        request,
        "portal/report_card.html",
        # A publication belongs to one child: switching lands on the other child's list.
        _context(request, switch_route="portal:report-cards", grant=grant, student=student,
                 pub=pub, entries=entries, groups=report_card_groups(entries)),
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
    page = Paginator(
        visible_announcements(request.user, _children(request)), NOTICES_PER_PAGE
    ).get_page(request.GET.get("page"))
    return render(request, "portal/notices.html",
                  _context(request, notices=list(page.object_list), page=page))


@require_safe
@guardian_required
def notice(request, notice_id):
    # The same audience rule as the list, narrowed to one notice in the database.
    item = visible_announcements(request.user, _children(request)).filter(
        public_id=notice_id
    ).first()
    if item is None:
        raise Http404("No such notice.")
    return render(request, "portal/notice.html", _context(request, notice=item))
