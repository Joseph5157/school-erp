"""Where a DRAFT assessment stands: marking in progress, or ready to finalize (Option A3).

Spec: docs/competitive-research/OPTION_A_IMPLEMENTATION_SPEC.md, section 6.2 step 5. One home for
the rules, so the admin home Academics tab's "Results to finish" count and the assessment list it
links to cannot drift apart. Read-only; no HTTP.

- The roster is the enrollments in the assessment's academic year, class and section that are
  effective on the assessment date.
- Ready to finalize: a due DRAFT with a roster on which every enrollment has a result (MARKED or
  ABSENT).
- Marking in progress: every other due DRAFT (no roster yet, or someone without a result).

"Due" is always an explicit `today` keyword argument with no default: nothing here calls
`business_today()`, so each caller works the date out once per request and passes the same value
to every query.
"""

from django.db.models import Exists, OuterRef, Q

from core.models import AcademicEnrollment, Assessment, StudentResult


def roster_subquery():
    """Enrollments in an assessment's year, grade and section, effective on its date."""
    return AcademicEnrollment.objects.filter(
        academic_year_id=OuterRef("offering__academic_year_id"),
        class_grade_id=OuterRef("offering__class_grade_id"),
        section_id=OuterRef("section_id"),
        start_date__lte=OuterRef("assessment_date"),
    ).filter(Q(end_date__isnull=True) | Q(end_date__gte=OuterRef("assessment_date")))


def annotate_progress(queryset):
    """Add `has_roster` and `has_unmarked` (a roster enrollment without a result)."""
    unmarked = roster_subquery().exclude(
        Exists(
            StudentResult.objects.filter(
                assessment_id=OuterRef(OuterRef("pk")), academic_enrollment_id=OuterRef("pk")
            )
        )
    )
    return queryset.annotate(has_roster=Exists(roster_subquery()), has_unmarked=Exists(unmarked))


def _due_drafts(queryset, today):
    return annotate_progress(
        queryset.filter(status=Assessment.Status.DRAFT, assessment_date__lte=today)
    )


def marking_in_progress(queryset, *, today):
    """Due DRAFT assessments with no roster yet, or with an enrollment still unmarked."""
    return _due_drafts(queryset, today).filter(Q(has_roster=False) | Q(has_unmarked=True))


def ready_to_finalize(queryset, *, today):
    """Due DRAFT assessments whose whole roster has a result."""
    return _due_drafts(queryset, today).filter(has_roster=True, has_unmarked=False)
