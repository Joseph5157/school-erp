"""Phase 6 Gate 2: guardian access reviews (ADR 0013, OD-8).

A grant needs an explicit administrator decision — RETAINED or REVOKED —
when the Student's placement ends:

- STUDENT_INACTIVE and PLACEMENT_ENDED are blocking steps inside
  `Student.record_status_change` and `Student.enroll`: the change cannot be
  saved until every active grant of that Student is decided.
- NO_CURRENT_ENROLLMENT is date-based: an active grant whose Student has no
  enrollment effective on the business date (within its own Academic Year)
  and no decision for that last placement is *pending*. Pending fails
  closed: the guardian receives no data for that Student until decided.

Nothing is ever inferred: no automatic retain, revoke or grace period.
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from accounts.models import SecurityEvent
from core import models as core_models
from core.models import GuardianAccessReview, GuardianStudentAccess

Trigger = GuardianAccessReview.Trigger
Decision = GuardianAccessReview.Decision
Event = SecurityEvent.EventType


def active_grants_for(student):
    return (
        GuardianStudentAccess.objects.filter(
            student_guardian__student=student, revoked_at__isnull=True
        )
        .select_related("student_guardian__guardian")
        .order_by("pk")
    )


def apply_review_decisions(*, student, trigger, enrollment, decisions, actor, note=""):
    """Record one explicit decision per active grant, inside the caller's transaction.

    `decisions` maps grant pk -> "RETAINED"/"REVOKED" and must cover exactly
    the Student's active grants; anything missing, extra or invalid is
    refused without changes. Returns the reviews created (none if the Student
    has no active grants).
    """
    from core.guardian_accounts import revoke_student_access

    with transaction.atomic():
        grants = list(active_grants_for(student).select_for_update(of=("self",)))
        if not grants:
            return []
        decisions = {int(key): value for key, value in (decisions or {}).items()}
        if set(decisions) != {grant.pk for grant in grants} or any(
            value not in Decision.values for value in decisions.values()
        ):
            raise ValidationError(
                "Every guardian's portal access for this Student must be explicitly "
                "retained or revoked before this change."
            )
        if actor is None or not getattr(actor, "pk", None):
            raise ValidationError("An administrator must record the access review.")
        note = (note or "").strip()[:200]
        reviews = []
        for grant in grants:
            decision = decisions[grant.pk]
            reviews.append(
                GuardianAccessReview.objects.create(
                    grant=grant, trigger=trigger, enrollment=enrollment, decision=decision,
                    decided_by=actor, note=note,
                )
            )
            if decision == Decision.REVOKED:
                revoke_student_access(
                    grant=grant, actor=actor,
                    reason=f"Access review ({Trigger(trigger).label}){': ' + note if note else ''}",
                )
            else:
                SecurityEvent.record(
                    Event.ACCESS_RETAINED, actor=actor, guardian=grant.student_guardian.guardian,
                    student=student, detail={"trigger": trigger},
                )
        return reviews


# --- date-based review (NO_CURRENT_ENROLLMENT, fail closed) ------------------


def _effective_within_year(enrollment, on_date):
    year_end = enrollment.academic_year.end_date
    end = min(enrollment.end_date or year_end, year_end)
    return enrollment.start_date <= on_date <= end


def last_placement(enrollments):
    return max(enrollments, key=lambda e: (e.start_date, e.pk), default=None)


def pending_placement(enrollments, decided, on_date):
    """(is_pending, placement) for one grant given the Student's enrollments.

    `decided` is the set of enrollment ids (None for "no enrollment") with a
    NO_CURRENT_ENROLLMENT decision for this grant.
    """
    if any(_effective_within_year(e, on_date) for e in enrollments):
        return False, None
    placement = last_placement(enrollments)
    key = placement.pk if placement is not None else None
    return key not in decided, placement


def review_state(grant, on_date=None):
    """(is_pending, placement) for one grant (a few queries)."""
    on_date = on_date or core_models.business_today()
    enrollments = list(
        core_models.AcademicEnrollment.objects.filter(
            student_id=grant.student_guardian.student_id
        ).select_related("academic_year")
    )
    decided = set(
        grant.reviews.filter(trigger=Trigger.NO_CURRENT_ENROLLMENT).values_list(
            "enrollment_id", flat=True
        )
    )
    return pending_placement(enrollments, decided, on_date)


def is_review_pending(grant, on_date=None):
    return review_state(grant, on_date)[0]


def pending_map(grants, on_date=None):
    """{grant pk: (is_pending, placement)} for many grants in two queries."""
    on_date = on_date or core_models.business_today()
    grants = list(grants)
    student_ids = {g.student_guardian.student_id for g in grants}
    enrollments = {}
    for enrollment in core_models.AcademicEnrollment.objects.filter(
        student_id__in=student_ids
    ).select_related("academic_year", "class_grade", "section__class_grade"):
        enrollments.setdefault(enrollment.student_id, []).append(enrollment)
    decided = {}
    for grant_id, enrollment_id in GuardianAccessReview.objects.filter(
        grant__in=[g.pk for g in grants], trigger=Trigger.NO_CURRENT_ENROLLMENT
    ).values_list("grant_id", "enrollment_id"):
        decided.setdefault(grant_id, set()).add(enrollment_id)
    return {
        grant.pk: pending_placement(
            enrollments.get(grant.student_guardian.student_id, []),
            decided.get(grant.pk, set()),
            on_date,
        )
        for grant in grants
    }


def pending_reviews(on_date=None):
    """Every active grant whose date-based review is pending, in bulk."""
    on_date = on_date or core_models.business_today()
    grants = list(
        GuardianStudentAccess.objects.filter(revoked_at__isnull=True).select_related(
            "student_guardian__student", "student_guardian__guardian", "granted_by"
        )
    )
    states = pending_map(grants, on_date)
    rows = [
        {"grant": grant, "placement": states[grant.pk][1]}
        for grant in grants
        if states[grant.pk][0]
    ]
    rows.sort(key=lambda row: (row["grant"].student_guardian.student.full_name,
                               row["grant"].pk))
    return rows


def decide_date_review(*, grant, decision, actor, note="", on_date=None):
    """Record the decision for a pending NO_CURRENT_ENROLLMENT review.

    Refused if the review is no longer pending (already decided, the grant
    was revoked, or the Student has a current placement again), so repeating
    the confirmation changes nothing.
    """
    from core.guardian_accounts import revoke_student_access

    if decision not in Decision.values:
        raise ValidationError("Choose retain or revoke.")
    with transaction.atomic():
        grant = GuardianStudentAccess.objects.select_for_update().select_related(
            "student_guardian__student", "student_guardian__guardian"
        ).get(pk=grant.pk)
        if not grant.is_active:
            raise ValidationError("This access has already been revoked.")
        pending, placement = review_state(grant, on_date)
        if not pending:
            raise ValidationError("This access review is no longer pending.")
        note = (note or "").strip()[:200]
        review = GuardianAccessReview.objects.create(
            grant=grant, trigger=Trigger.NO_CURRENT_ENROLLMENT, enrollment=placement,
            decision=decision, decided_by=actor, note=note,
        )
        if decision == Decision.REVOKED:
            revoke_student_access(
                grant=grant, actor=actor,
                reason=f"Access review (no current enrollment){': ' + note if note else ''}",
            )
        else:
            SecurityEvent.record(
                Event.ACCESS_RETAINED, actor=actor, guardian=grant.student_guardian.guardian,
                student=grant.student_guardian.student,
                detail={"trigger": Trigger.NO_CURRENT_ENROLLMENT},
            )
        return review


def record_pending_events(rows, actor=None):
    """Write ACCESS_REVIEW_PENDING once per grant and placement (history)."""
    if not rows:
        return
    seen = {
        (event.detail.get("grant"), event.detail.get("enrollment"))
        for event in SecurityEvent.objects.filter(
            event_type=Event.ACCESS_REVIEW_PENDING,
            student_id_ref__in={row["grant"].student_guardian.student_id for row in rows},
        )
    }
    for row in rows:
        grant, placement = row["grant"], row["placement"]
        key = (grant.pk, placement.pk if placement else None)
        if key not in seen:
            SecurityEvent.record(
                Event.ACCESS_REVIEW_PENDING, actor=actor,
                guardian=grant.student_guardian.guardian,
                student=grant.student_guardian.student,
                detail={"grant": key[0], "enrollment": key[1]},
            )
