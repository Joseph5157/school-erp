"""Phase 7 Gate 3: announcements (ADR 0015).

Spec: docs/superpowers/specs/2026-10-15-phase7-gate3-announcements-design.md.
Saving publishes; a published notice never changes and is withdrawn, not
deleted. Guardians with portal access to a student in the audience read it in
the portal; preparing WhatsApp messages is a separate administrator step.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core import models as core_models
from core import notification_producers, notifications
from core.models import AcademicEnrollment, Announcement, Student
from core.portal import portal_children

TEMPLATE_KEY = "announcement"
WITHDRAWN_REASON = "Announcement withdrawn"


def publish(*, title, body, audience, class_grade=None, section=None, actor):
    announcement = Announcement(
        title=(title or "").strip(),
        body=(body or "").strip(),
        audience=audience,
        class_grade=class_grade if audience == Announcement.Audience.CLASS else None,
        section=section if audience == Announcement.Audience.SECTION else None,
        published_by=actor,
    )
    announcement.full_clean()
    announcement.save()
    return announcement


def withdraw(announcement, *, actor, reason):
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Give a reason for withdrawing this notice.")
    with transaction.atomic():
        locked = Announcement.objects.select_for_update().get(pk=announcement.pk)
        if locked.is_withdrawn:
            raise ValidationError("This notice has already been withdrawn.")
        locked.withdrawn_at = timezone.now()
        locked.withdrawn_by = actor
        locked.withdrawal_reason = reason[:200]
        locked.save(update_fields=["withdrawn_at", "withdrawn_by", "withdrawal_reason"])
    return locked


def _current_enrollments(on_date):
    """Enrollments effective on the date and inside their academic year (an open-ended
    enrollment does not outlive its year, matching the portal review rule)."""
    return AcademicEnrollment.objects.effective_on(on_date).filter(
        academic_year__end_date__gte=on_date
    )


def _enrollments(announcement, on_date):
    enrollments = _current_enrollments(on_date)
    if announcement.audience == Announcement.Audience.CLASS:
        return enrollments.filter(class_grade_id=announcement.class_grade_id)
    if announcement.audience == Announcement.Audience.SECTION:
        return enrollments.filter(section_id=announcement.section_id)
    return enrollments


def audience_students(announcement, on_date=None):
    """Students in the audience: enrollment effective on the date (default today)."""
    on_date = on_date or core_models.business_today()
    return Student.objects.filter(
        pk__in=_enrollments(announcement, on_date).values("student_id")
    ).order_by("pk")


def recipient_grants(announcement):
    """One portal grant per guardian who can read this notice (lowest grant pk)."""
    student_ids = list(audience_students(announcement).values_list("pk", flat=True))
    chosen = {}
    for grant in notification_producers.portal_grants_for_students(student_ids):
        chosen.setdefault(grant.student_guardian.guardian_id, grant)
    return list(chosen.values())


def audience_counts(announcement):
    guardian_ids = [g.student_guardian.guardian_id for g in recipient_grants(announcement)]
    return {"guardians": len(guardian_ids),
            "opted_in": notifications.opted_in_count(guardian_ids)}


def visible_announcements(user):
    """Live notices whose audience includes one of the user's visible children."""
    students = [item["student"] for item in portal_children(user) if item["visible"]]
    placements = list(
        _current_enrollments(core_models.business_today())
        .filter(student__in=students)
        .values_list("class_grade_id", "section_id")
    )
    if not placements:
        return []
    return list(
        Announcement.objects.filter(withdrawn_at__isnull=True)
        .filter(
            Q(audience=Announcement.Audience.ALL)
            | Q(audience=Announcement.Audience.CLASS,
                class_grade_id__in={grade for grade, _ in placements})
            | Q(audience=Announcement.Audience.SECTION,
                section_id__in={section for _, section in placements})
        )
        .order_by("-published_at", "-pk")
    )
