"""Find existing records that may be the person being added (F5).

These only ever produce a warning. Two different children can share a parent's phone
and two different guardians can share a name, so nothing here may stop a save.
"""

import re

from core.models import Applicant, Guardian, Student

PHONE_DIGITS = 10
MIN_PHONE_DIGITS = 7


def phone_key(phone):
    """The local number, so `+91 98765 43210` and `9876543210` compare equal.

    Too few digits to identify anyone gives "", which never matches.
    """
    digits = re.sub(r"[^0-9]", "", phone or "")
    return digits[-PHONE_DIGITS:] if len(digits) >= MIN_PHONE_DIGITS else ""


def name_key(name):
    """Ignores capitals and extra spaces; spelling must still match."""
    return " ".join((name or "").split()).casefold()


def _same_phone(record, details):
    key = phone_key(details.get("phone"))
    return bool(key) and phone_key(record.phone) == key


def _same_email(record, details):
    key = (details.get("email") or "").casefold()
    return bool(key) and record.email.casefold() == key


def _child_reasons(record, details):
    reasons = []
    if (
        details.get("date_of_birth")
        and record.date_of_birth == details["date_of_birth"]
        and name_key(record.full_name) == name_key(details.get("full_name"))
    ):
        reasons.append("Same name and date of birth")
    if _same_phone(record, details):
        reasons.append("Same phone, may be a sibling")
    if _same_email(record, details):
        reasons.append("Same email, may be a sibling")
    return reasons


def _guardian_reasons(record, details):
    reasons = []
    if name_key(record.full_name) == name_key(details.get("full_name")):
        reasons.append("Same name")
    if _same_phone(record, details):
        reasons.append("Same phone")
    if _same_email(record, details):
        reasons.append("Same email")
    return reasons


def _with_reasons(records, details, reasons_for):
    matches = []
    for record in records.order_by("full_name", "pk"):
        record.duplicate_reasons = reasons_for(record, details)
        if record.duplicate_reasons:
            matches.append(record)
    return matches


def matching_applicants(details):
    """Applicants not yet admitted; an admitted child is matched through their Student."""
    return _with_reasons(Applicant.objects.filter(student__isnull=True), details, _child_reasons)


def matching_students(details):
    return _with_reasons(Student.objects.all(), details, _child_reasons)


def matching_guardian_reasons(details):
    """{guardian id: reasons}, so the caller can load only those Guardians in full."""
    matches = _with_reasons(Guardian.objects.all(), details, _guardian_reasons)
    return {guardian.pk: guardian.duplicate_reasons for guardian in matches}
