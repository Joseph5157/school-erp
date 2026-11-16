"""Daily refresh of the staging demo school: guard and realism helpers."""

import datetime
import hashlib
import os
import re
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import CommandError
from django.db import transaction

from core import announcements
from core.management.commands.seed_demo import DEMO_ADMIN_USERNAME
from core.models import (
    AcademicTerm,
    AcademicYear,
    Announcement,
    Assessment,
    AssessmentTeacherAssignment,
    AttendanceRegister,
    AttendanceStatus,
    Section,
    SectionClassTeacher,
)

DEMO_TEACHER_USERNAME = "srinivas.reddy"
ENV_FLAG = "EVERCLASS_DEMO_SCHOOL"

ABSENCE_NOTES = (
    "Fever",
    "Family function",
    "Doctor's appointment",
    "Cold and cough",
    "Travelling with family",
)


class NotInSeason(Exception):
    """Today falls outside the demo school's academic year."""


class PartialFailure(Exception):
    """Some items in a step failed; the rest were still done and kept."""

    def __init__(self, done: int, errors: list):
        self.done = done
        self.errors = errors
        super().__init__(f"{len(errors)} failed, first: {errors[0]}")


def _try(errors, label, work, *args) -> bool:
    """Run `work(*args)` in its own transaction; on error record it and return False."""
    try:
        with transaction.atomic():
            return bool(work(*args))
    except Exception as exc:  # one bad item must not block the rest
        errors.append(f"{label}: {exc!r}")
        return False


def _finish(done, errors):
    if errors:
        raise PartialFailure(done, errors)
    return done


def check_guard(today: date):
    """Return (demo_admin, academic_year) or refuse to touch this database."""
    if os.environ.get(ENV_FLAG) != "1":
        raise CommandError(f"Refusing to run: set {ENV_FLAG}=1 on the demo environment only.")
    admin = get_user_model().objects.filter(username=DEMO_ADMIN_USERNAME).first()
    if admin is None:
        raise CommandError(f"Refusing to run: user {DEMO_ADMIN_USERNAME} not found.")
    years = list(AcademicYear.objects.all()[:2])
    if len(years) != 1:
        raise CommandError("Refusing to run: expected exactly one academic year.")
    year = years[0]
    if not (year.start_date <= today <= year.end_date):
        raise NotInSeason(f"{today} is outside {year.start_date} to {year.end_date}.")
    return admin, year


def _unit(*parts) -> float:
    """Deterministic float in [0, 1) from the given parts."""
    digest = hashlib.sha256(":".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def _tendency(student_id: int) -> float:
    """Per-student absence rate: ~90% rarely absent, ~10% frequent absentees."""
    if _unit("bucket", student_id) < 0.10:
        return 0.10 + 0.05 * _unit("freq", student_id)
    return 0.02 + 0.03 * _unit("rare", student_id)


def is_absent(student_id: int, section_id: int, day: date) -> bool:
    offset = (_unit("section", section_id) - 0.5) * 0.02  # +/- 0.01
    return _unit("absent", student_id, day.isoformat()) < _tendency(student_id) + offset


def absence_note(student_id: int, day: date) -> str:
    return ABSENCE_NOTES[int(_unit("note", student_id, day.isoformat()) * len(ABSENCE_NOTES))]


# -- attendance ------------------------------------------------------------


def _submitter(section, day, fallback_actor):
    """The Section's class teacher on `day`, else the fallback actor."""
    assignment = (
        SectionClassTeacher.objects.effective_on(day)
        .filter(section=section)
        .select_related("teacher")
        .first()
    )
    return assignment.teacher if assignment is not None else fallback_actor


def _fill_and_submit(register, actor):
    """Capture every not-yet-captured eligible enrollment, then submit."""
    captured = set(register.entries.values_list("academic_enrollment_id", flat=True))
    for enrollment in register.eligible_enrollments():
        if enrollment.pk in captured:
            continue
        student_id = enrollment.student_id
        if is_absent(student_id, register.section_id, register.date):
            register.capture(
                enrollment=enrollment,
                status=AttendanceStatus.ABSENT,
                absence_note=absence_note(student_id, register.date),
            )
        else:
            register.capture(enrollment=enrollment, status=AttendanceStatus.PRESENT)
    register.submit(actor=actor)


def _new_register(year, section, day):
    return AttendanceRegister(
        academic_year=year, class_grade=section.class_grade, section=section, date=day
    )


def _create_and_submit(year, section, day, fallback_actor):
    """Create, fill and submit one register; False if the Section has no roster."""
    register = _new_register(year, section, day)
    if not register.eligible_enrollments().exists():
        return False
    register.full_clean()
    register.save()
    _fill_and_submit(register, _submitter(section, day, fallback_actor))
    return True


def _sections():
    return Section.objects.select_related("class_grade").order_by("class_grade_id", "name")


def finish_old_drafts(year, today, fallback_actor) -> tuple[int, int]:
    """Finish old draft registers; return (finished, skipped)."""
    drafts = AttendanceRegister.objects.filter(
        academic_year=year, status=AttendanceRegister.Status.DRAFT, date__lt=today
    ).select_related("section", "class_grade", "academic_year")
    finished = skipped = 0
    for register in drafts:
        if not register.eligible_enrollments().exists():
            continue  # nobody to mark; submit would refuse, so leave it as it is
        try:
            with transaction.atomic():
                _fill_and_submit(
                    register, _submitter(register.section, register.date, fallback_actor)
                )
        except ValidationError:
            skipped += 1  # leave this draft as it is and keep going
            continue
        finished += 1
    return finished, skipped


def backfill_attendance(year, today, fallback_actor, since: date | None = None) -> int:
    start = max(since or year.start_date, year.start_date)
    created = 0
    errors = []
    day = start
    while day < today:
        if year.is_instructional_day(day):
            existing = set(
                AttendanceRegister.objects.filter(academic_year=year, date=day)
                .values_list("section_id", flat=True)
            )
            for section in _sections():
                if section.pk in existing:
                    continue
                if _try(errors, f"{day} {section}",
                        _create_and_submit, year, section, day, fallback_actor):
                    created += 1
        day += datetime.timedelta(days=1)
    return _finish(created, errors)


def prepare_today(year, today, fallback_actor) -> int:
    if not year.is_instructional_day(today):
        return 0
    demo_teacher_sections = set(
        SectionClassTeacher.objects.effective_on(today)
        .filter(teacher__username=DEMO_TEACHER_USERNAME)
        .values_list("section_id", flat=True)
    )
    existing = set(
        AttendanceRegister.objects.filter(academic_year=year, date=today)
        .values_list("section_id", flat=True)
    )
    created = 0
    errors = []
    for section in _sections():
        if section.pk in demo_teacher_sections or section.pk in existing:
            continue
        if _try(errors, f"{today} {section}",
                _create_and_submit, year, section, today, fallback_actor):
            created += 1
    return _finish(created, errors)


# -- assessments -----------------------------------------------------------

_UNIT_TEST_NAME = re.compile(r"^Unit Test (\d+)$")


def current_term(year, today: date):
    return AcademicTerm.objects.filter(
        academic_year=year, start_date__lte=today, end_date__gte=today
    ).first()


def _latest_weekday(day: date) -> date:
    while day.weekday() >= 5:
        day -= datetime.timedelta(days=1)
    return day


def _open_unit_test(term, assignment, today) -> bool:
    existing = Assessment.objects.filter(
        term=term, offering=assignment.offering, section=assignment.section
    )
    if existing.filter(status=Assessment.Status.DRAFT).exists():
        return False
    numbers = [
        int(m.group(1))
        for name in existing.values_list("name", flat=True)
        if (m := _UNIT_TEST_NAME.match(name))
    ]
    assessment = Assessment(
        term=term,
        offering=assignment.offering,
        section=assignment.section,
        name=f"Unit Test {max(numbers, default=0) + 1}",
        assessment_date=max(_latest_weekday(today), term.start_date),
        maximum_marks=Decimal(25),
        pass_mark=Decimal(9),
    )
    assessment.full_clean()
    assessment.save()
    return True


def ensure_open_assessments(year, today: date) -> int:
    term = current_term(year, today)
    if term is None:
        return 0
    created = 0
    assignments = (
        AssessmentTeacherAssignment.objects.effective_on(today)
        .select_related("teacher", "offering__subject", "offering__class_grade", "section")
        .order_by("offering__class_grade__name", "section__name", "offering__display_order")
    )
    errors = []
    for assignment in assignments:
        if _try(errors, f"{assignment.offering} {assignment.section}",
                _open_unit_test, term, assignment, today):
            created += 1
    return _finish(created, errors)


# -- notices ---------------------------------------------------------------

NOTICE_POOL = [
    ("Parent-Teacher Meeting",
     "A parent-teacher meeting will be held this Saturday from 9 am to 12 noon. "
     "Please meet your child's class teacher to discuss progress."),
    ("Annual Sports Day",
     "Our Annual Sports Day is coming up. Students should report in sports uniform "
     "and carry a water bottle."),
    ("Fee Payment Reminder",
     "This is a reminder that the current instalment of school fees is due. "
     "Please pay at the school office before the due date."),
    ("Holiday Notice",
     "The school will remain closed for the upcoming holiday and will reopen on the "
     "next working day."),
    ("Exam Timetable Released",
     "The timetable for the upcoming examinations has been shared with all classes. "
     "Students should begin their revision."),
    ("Science Fair Registration",
     "Registrations are open for the school Science Fair. Interested students should "
     "give their names to their class teacher."),
    ("Library Week",
     "Library Week begins soon. Students are encouraged to borrow and read books, "
     "and to return old ones on time."),
    ("Uniform Reminder",
     "Students are reminded to come to school in the complete prescribed uniform, "
     "with clean shoes and a school ID card."),
]


def post_notice_if_stale(actor, now: datetime.datetime):
    newest = (
        Announcement.objects.filter(withdrawn_at__isnull=True)
        .order_by("-published_at", "-pk")
        .first()
    )
    if newest is not None and now - newest.published_at <= datetime.timedelta(days=7):
        return None
    titles = [title for title, _ in NOTICE_POOL]
    index = 0
    if newest is not None and newest.title in titles:
        index = (titles.index(newest.title) + 1) % len(NOTICE_POOL)
    title, body = NOTICE_POOL[index]
    return announcements.publish(
        title=title, body=body, audience=Announcement.Audience.ALL, actor=actor
    )
