"""Phase 6 Guardian Portal read models (ADR 0014).

Portal views never reuse administrative or teacher pages. They build their
own, minimal context from the guardian's active grants.
"""

from core import guardian_access
from core.authorization import guardian_grants


def portal_children(user):
    """[{grant, student, visible}] for the user's active grants, in two queries.

    `visible` is False while a date-based access review is pending (OD-8,
    fail closed): the Student is listed only as under review, with no data.
    """
    grants = list(guardian_grants(user).order_by("student_guardian__student__full_name", "pk"))
    states = guardian_access.pending_map(grants)
    return [
        {
            "grant": grant,
            "student": grant.student_guardian.student,
            "visible": not states[grant.pk][0],
        }
        for grant in grants
    ]
