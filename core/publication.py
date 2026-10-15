"""Phase 6 Gate 6: explicit Term publication to guardians (ADR 0014).

- `release_content(student, term)` is what a guardian report card would show
  now: every FINALIZED result in the Term (displayed values only) and the
  Term remark.
- `plan_publication(term, section, include)` is the preview: one row per
  Student whose Term placement is in the Section, either to publish (with
  exact content) or skipped with a reason. Incomplete Students are excluded
  unless explicitly included, then published as partial.
- `confirm_publication(...)` recomputes the plan under locks and writes
  exactly the previewed versions, or nothing (stale token). Confirming twice
  publishes nothing new.
- Corrections mark the current version STALE in the same transaction; the
  portal also re-checks the fingerprint of the released source values.
"""

import hashlib
import json

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.models import SecurityEvent
from core import notification_producers
from core.models import (
    AcademicEnrollment,
    Assessment,
    StudentResult,
    TermPublication,
    TermPublicationEntry,
    TermRemark,
)

FINGERPRINT_SCHEME = 1
Event = SecurityEvent.EventType


def _text(value):
    return None if value is None else str(value)


def entry_values(result):
    """Displayed values of one result — the only result fields ever released."""
    assessment = result.assessment
    pass_fail = result.pass_fail
    return {
        "result_id": result.pk,
        "subject_label": assessment.offering.subject.name,
        "assessment_label": assessment.name,
        "assessment_date": assessment.assessment_date,
        "maximum_marks": assessment.maximum_marks,
        "pass_mark": assessment.pass_mark,
        "status": result.status,
        "score": result.score,
        "percentage": result.percentage,
        "grade_label": assessment.grade_for(result),
        "pass_fail_label": {"PASS": "Pass", "FAIL": "Fail"}.get(pass_fail),
    }


def fingerprint(entries, remark):
    """SHA-256 over the released values (scheme 1); stored values only."""
    canonical = {
        "scheme": FINGERPRINT_SCHEME,
        "entries": sorted(
            ({key: _text(value) for key, value in entry.items()} for entry in entries),
            key=lambda e: int(e["result_id"]),
        ),
        "remark": None if remark is None else {"id": remark["id"], "text": remark["text"]},
    }
    return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()


def _results_queryset():
    return StudentResult.objects.select_related(
        "assessment__offering__subject", "assessment__term"
    )


def release_content(student, term):
    results = (
        _results_queryset()
        .filter(
            academic_enrollment__student=student,
            assessment__term=term,
            assessment__status=Assessment.Status.FINALIZED,
        )
        .order_by("assessment__offering__subject__name", "assessment__assessment_date",
                  "assessment__name", "pk")
    )
    entries = [entry_values(result) for result in results]
    remark = TermRemark.objects.filter(term=term, student=student).first()
    remark = None if remark is None else {"id": remark.pk, "text": remark.remark}
    return {"entries": entries, "remark": remark,
            "fingerprint": fingerprint(entries, remark)}


def live_fingerprint(publication):
    """Fingerprint of the *current* source values of what this version released."""
    entries = [
        entry_values(result)
        for result in _results_queryset().filter(
            pk__in=publication.entries.values("result_id")
        )
    ]
    remark = None
    if publication.remark_id_ref is not None:
        live = TermRemark.objects.filter(pk=publication.remark_id_ref).first()
        remark = {"id": publication.remark_id_ref, "text": live.remark if live else None}
    return fingerprint(entries, remark)


def guardian_visible(publication):
    """Current, PUBLISHED and unchanged since release (ADR 0014)."""
    return (
        publication.status == TermPublication.Status.PUBLISHED
        and live_fingerprint(publication) == publication.fingerprint
    )


def current_publication(student, term):
    return TermPublication.objects.filter(
        student=student, term=term, status__in=TermPublication.CURRENT_STATUSES
    ).first()


# --- preview -----------------------------------------------------------------

PUBLISH, REPUBLISH, INCOMPLETE = "publish", "republish", "incomplete"
SKIP_ALREADY, SKIP_NOTHING, SKIP_AMBIGUOUS = "already", "nothing", "ambiguous"


def _pending_assessments(term, students):
    """{student id: [draft assessments of the Term the Student was on the roster for]}."""
    drafts = list(
        Assessment.objects.filter(term=term, status=Assessment.Status.DRAFT).select_related(
            "offering__subject", "offering"
        )
    )
    if not drafts:
        return {}
    enrollments = {}
    for enrollment in AcademicEnrollment.objects.filter(
        student__in=students, academic_year_id=term.academic_year_id
    ):
        enrollments.setdefault(enrollment.student_id, []).append(enrollment)
    pending = {}
    for student in students:
        for assessment in drafts:
            if any(
                e.section_id == assessment.section_id
                and e.class_grade_id == assessment.offering.class_grade_id
                and e.is_effective_on(assessment.assessment_date)
                for e in enrollments.get(student.pk, [])
            ):
                pending.setdefault(student.pk, []).append(assessment)
    return pending


def plan_publication(term, section, include=()):
    """The preview for one Term and Section. Writes nothing."""
    include = {int(pk) for pk in include}
    students = term.section_rosters([section])[section.pk]
    pending = _pending_assessments(term, students)
    currents = {
        p.student_id: p
        for p in TermPublication.objects.filter(
            term=term, student__in=students, status__in=TermPublication.CURRENT_STATUSES
        )
    }
    rows = []
    for student in students:
        placement = term.enrollment_for(student)
        content = release_content(student, term)
        current = currents.get(student.pk)
        missing = pending.get(student.pk, [])
        row = {"student": student, "placement": placement, "content": content,
               "current": current, "pending": missing, "selected": False}
        if placement is None:
            row["action"] = SKIP_AMBIGUOUS
        elif not content["entries"] and content["remark"] is None:
            row["action"] = SKIP_NOTHING
        elif (current is not None and current.status == TermPublication.Status.PUBLISHED
              and current.fingerprint == content["fingerprint"]
              and current.is_partial == bool(missing)):
            row["action"] = SKIP_ALREADY
        elif missing:
            row["action"] = INCOMPLETE
            row["selected"] = student.pk in include
        else:
            row["action"] = REPUBLISH if current is not None else PUBLISH
            row["selected"] = True
        rows.append(row)
    selected = [row for row in rows if row["selected"]]
    token = hashlib.sha256(
        json.dumps(sorted([row["student"].pk, row["content"]["fingerprint"],
                           len(row["pending"])] for row in selected)).encode()
    ).hexdigest()
    return {"rows": rows, "selected": selected, "token": token}


def confirm_publication(*, term, section, include, token, actor):
    """Publish exactly the previewed selection, or nothing. Returns versions created."""
    if actor is None or not actor.has_perm("core.publish_termpublication"):
        raise ValidationError("Only an administrator can publish Term results.")
    with transaction.atomic():
        students = term.section_rosters([section])[section.pk]
        list(TermPublication.objects.select_for_update().filter(
            term=term, student__in=students))
        plan = plan_publication(term, section, include)
        if plan["token"] != token:
            raise ValidationError(
                "Results changed since the preview, or this preview was already confirmed. "
                "Review the new preview."
            )
        if not plan["selected"]:
            raise ValidationError("Nothing is selected for publication.")
        created = []
        now = timezone.now()
        for row in plan["selected"]:
            created.append(_publish(term, row, actor, now))
        notification_producers.report_card_notices(created)
        return created


def _publish(term, row, actor, now):
    student, current, content = row["student"], row["current"], row["content"]
    if current is not None:
        TermPublication.objects.filter(pk=current.pk).update(
            status=TermPublication.Status.SUPERSEDED, status_changed_at=now,
            status_changed_by=actor, status_reason="Republished",
        )
    last = (
        TermPublication.objects.filter(student=student, term=term)
        .order_by("-version").values_list("version", flat=True).first()
    ) or 0
    placement = row["placement"]
    publication = TermPublication.objects.create(
        student=student, term=term, placement=placement, version=last + 1,
        is_partial=bool(row["pending"]), pending_assessments=len(row["pending"]),
        term_label=term.name, academic_year_label=term.academic_year.name,
        class_grade_label=placement.class_grade.name, section_label=placement.section.name,
        remark_id_ref=content["remark"]["id"] if content["remark"] else None,
        remark_text=content["remark"]["text"] if content["remark"] else None,
        fingerprint=content["fingerprint"], fingerprint_scheme=FINGERPRINT_SCHEME,
        published_by=actor, published_at=now,
    )
    TermPublicationEntry.objects.bulk_create(
        TermPublicationEntry(
            publication=publication, display_order=index,
            **{key: value for key, value in entry.items() if key != "result_id"},
            result_id=entry["result_id"],
        )
        for index, entry in enumerate(content["entries"])
    )
    SecurityEvent.record(Event.TERM_PUBLISHED, actor=actor, student=student, term=term,
                         detail={"version": publication.version,
                                 "partial": publication.is_partial})
    return publication


# --- staleness and withdrawal -------------------------------------------------


def _mark_stale(publications, *, actor, reason):
    for publication in publications:
        TermPublication.objects.filter(
            pk=publication.pk, status=TermPublication.Status.PUBLISHED
        ).update(status=TermPublication.Status.STALE, status_changed_at=timezone.now(),
                 status_changed_by=actor, status_reason=reason[:200])
        SecurityEvent.record(Event.PUBLICATION_STALE, actor=actor,
                             student=publication.student, term=publication.term,
                             detail={"version": publication.version})


def mark_stale_for_result(result, *, actor, reason="A published result was corrected."):
    """Called in the same transaction as a result correction."""
    _mark_stale(
        TermPublication.objects.filter(
            status=TermPublication.Status.PUBLISHED, entries__result=result
        ).select_related("student", "term"),
        actor=actor, reason=reason,
    )


def mark_stale_for_remark(term, student, *, actor,
                          reason="A published Term remark was changed or removed."):
    """Called in the same transaction as a remark change or removal."""
    _mark_stale(
        TermPublication.objects.filter(
            status=TermPublication.Status.PUBLISHED, term=term, student=student,
            remark_id_ref__isnull=False,
        ).select_related("student", "term"),
        actor=actor, reason=reason,
    )


def withdraw(publication, *, actor, reason):
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("A reason is required.")
    with transaction.atomic():
        updated = TermPublication.objects.filter(
            pk=publication.pk, status__in=TermPublication.CURRENT_STATUSES
        ).update(status=TermPublication.Status.WITHDRAWN, status_changed_at=timezone.now(),
                 status_changed_by=actor, status_reason=reason[:200])
        if not updated:
            raise ValidationError("Only a current publication can be withdrawn.")
        SecurityEvent.record(Event.PUBLICATION_WITHDRAWN, actor=actor,
                             student=publication.student, term=publication.term,
                             detail={"version": publication.version})


def stale_publications():
    return TermPublication.objects.filter(status=TermPublication.Status.STALE).select_related(
        "student", "term__academic_year"
    )
