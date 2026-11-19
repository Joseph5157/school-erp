"""Admin home Parents tab data. Read-only; no HTTP here.

Portal rules: a student is "on the portal" when they have a grant that is active, not pending a
date review, and whose guardian has an active login (`portal_grants_for_students`). A parent
counts only with an active, unrevoked login. Everything is computed in a fixed number of queries.
"""
import datetime

from django.urls import reverse
from django.utils import timezone

from core import guardian_access
from core.models import AcademicEnrollment, Announcement, GuardianAccount
from core.notification_producers import portal_grants_for_students

NOTICE_LIMIT = 5


def _percent(part, whole):
    return round(part * 100 / whole) if whole else None


def _placements(today):
    """One current placement per student: {student_id: (section_id, class, section, order)}.

    Same rule as the announcements audience: effective today and inside the academic year. A
    student with two effective placements counts once, under the latest (start_date, then pk).
    """
    rows = (
        AcademicEnrollment.objects.effective_on(today)
        .filter(academic_year__end_date__gte=today)
        .values_list(
            "student_id", "section_id", "start_date", "pk",
            "section__name", "class_grade__name", "class_grade__display_order",
        )
    )
    latest = {}
    for student_id, section_id, start, pk, section, class_name, order in rows:
        key = (start, pk)
        if student_id not in latest or key > latest[student_id][0]:
            latest[student_id] = (key, section_id, section, class_name, order)
    return {sid: row[1:] for sid, row in latest.items()}


def portal_student_ids(student_ids, today):
    """The students among `student_ids` with at least one usable portal grant on `today`."""
    return {
        grant.student_guardian.student_id
        for grant in portal_grants_for_students(list(student_ids), on_date=today)
    }


def engagement(today):
    placements = _placements(today)
    students = len(placements)
    on_portal = len(portal_student_ids(placements, today))
    month_start = timezone.make_aware(datetime.datetime.combine(today.replace(day=1), datetime.time.min))
    accounts = GuardianAccount.objects.filter(revoked_at__isnull=True, user__is_active=True)
    parents = accounts.values("guardian_id").distinct().count()
    active = (
        accounts.filter(user__last_login__gte=month_start).values("guardian_id").distinct().count()
    )
    return {
        "students": students,
        "students_on_portal": on_portal,
        "students_pct": _percent(on_portal, students),
        "parents": parents,
        "parents_active": active,
        "parents_pct": _percent(active, parents),
    }


def missing_accounts(today, *, invite_links):
    """Sections with students lacking a portal parent, most missing first."""
    placements = _placements(today)
    on_portal = portal_student_ids(placements, today)
    sections = {}
    for student_id, (section_id, section, class_name, order) in placements.items():
        row = sections.setdefault(
            section_id,
            {"section_id": section_id, "class_name": class_name, "section_name": section,
             "missing": 0, "students": 0, "_order": order},
        )
        row["students"] += 1
        row["missing"] += student_id not in on_portal
    rows = [row for row in sections.values() if row["missing"]]
    rows.sort(key=lambda r: (-r["missing"], r["_order"], r["class_name"], r["section_name"]))
    base = reverse("core:student-list")
    for row in rows:
        del row["_order"]
        row["url"] = f"{base}?section={row['section_id']}&chip=no_portal" if invite_links else None
    return rows


def access_reviews(today, *, with_names, decide_links):
    pending = guardian_access.pending_reviews(today)
    list_url = reverse("core:guardian-access-reviews")
    rows = None
    if with_names:
        rows = [
            {
                "student_name": row["grant"].student_guardian.student.full_name,
                "guardian_name": row["grant"].student_guardian.guardian.full_name,
                "url": reverse("core:guardian-access-review-decide", args=[row["grant"].pk])
                if decide_links else list_url,
            }
            for row in pending
        ]
    return {"count": len(pending), "url": list_url, "rows": rows}


def sent_notices(limit=NOTICE_LIMIT):
    notices = Announcement.objects.select_related("class_grade", "section__class_grade").order_by(
        "-published_at", "-pk"
    )[:limit]
    return [
        {
            "title": notice.title,
            "audience": notice.audience_label(),
            "published_on": timezone.localdate(notice.published_at),
            "withdrawn": notice.is_withdrawn,
            "url": reverse("core:announcement-detail", args=[notice.pk]),
        }
        for notice in notices
    ]
