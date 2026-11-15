"""Daily refresh of the staging demo school: guard and realism helpers."""

import hashlib
import os
from datetime import date

from django.contrib.auth import get_user_model
from django.core.management.base import CommandError

from core.management.commands.seed_demo import DEMO_ADMIN_USERNAME
from core.models import AcademicYear

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
