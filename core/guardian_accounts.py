"""Phase 6 Gate 1: guardian account and access-grant workflows (ADR 0013).

Every workflow is atomic, audited with a SecurityEvent, and never guesses:
logins are found only by exact normalized username, grants only for a
recorded StudentGuardian relationship. Links and grants are revoked, never
deleted. Temporary passwords are returned to the caller once, for display on
a printable slip, and are never stored in plain text or logged.
"""

import secrets

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.functions import Lower
from django.utils import timezone

from accounts.models import SecurityEvent
from accounts.usernames import clean_new_username, normalize_username
from core.models import Guardian, GuardianAccount, GuardianStudentAccess, StudentGuardian

TEMPORARY_PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
Event = SecurityEvent.EventType


def generate_temporary_password():
    """Twelve random characters without look-alikes, grouped for reading aloud."""
    raw = "".join(secrets.choice(TEMPORARY_PASSWORD_ALPHABET) for _ in range(12))
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:]}"


def _lock_guardian(guardian):
    return Guardian.objects.select_for_update().get(pk=guardian.pk)


def _require_reason(reason):
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("A reason is required.")
    return reason


def _check_verification(method, note):
    if method not in GuardianAccount.VerificationMethod.values:
        raise ValidationError("Choose how the guardian's identity was verified.")
    note = (note or "").strip()
    if not note:
        raise ValidationError("Describe the identity verification.")
    return note


def active_account(guardian):
    return (
        GuardianAccount.objects.filter(guardian=guardian, revoked_at__isnull=True)
        .select_related("user")
        .first()
    )


def find_login(username):
    """The login whose username equals `username` after normalization, or None."""
    key = normalize_username(username)
    return (
        get_user_model()
        .objects.annotate(_key=Lower("username"))
        .filter(_key=key)
        .first()
    )


def create_guardian_account(*, guardian, username, method, note, actor):
    """Create a new login for a verified guardian. Returns (account, temporary password)."""
    note = _check_verification(method, note)
    username = clean_new_username(username)
    password = generate_temporary_password()
    try:
        with transaction.atomic():
            guardian = _lock_guardian(guardian)
            if active_account(guardian) is not None:
                raise ValidationError("This guardian already has an active portal account.")
            user = get_user_model().objects.create_user(username=username, password=password)
            user.must_change_password = True
            user.save(update_fields=["must_change_password"])
            account = GuardianAccount.objects.create(
                user=user, guardian=guardian, identity_verified_by=actor,
                identity_verification_method=method, identity_verification_note=note,
                created_by=actor,
            )
            SecurityEvent.record(Event.ACCOUNT_CREATED, actor=actor, subject_user=user,
                                 guardian=guardian)
    except IntegrityError as error:
        raise ValidationError("That username is not available.") from error
    return account, password


def link_existing_login(*, guardian, username, method, note, actor):
    """Link an existing login (e.g. a teacher who is also a parent) by exact username."""
    note = _check_verification(method, note)
    user = find_login(username)
    if user is None or not user.is_active:
        raise ValidationError("No active login has exactly that username.")
    try:
        with transaction.atomic():
            guardian = _lock_guardian(guardian)
            if active_account(guardian) is not None:
                raise ValidationError("This guardian already has an active portal account.")
            if GuardianAccount.objects.filter(user=user, revoked_at__isnull=True).exists():
                raise ValidationError("That login is already linked to another guardian.")
            account = GuardianAccount.objects.create(
                user=user, guardian=guardian, identity_verified_by=actor,
                identity_verification_method=method, identity_verification_note=note,
                created_by=actor,
            )
            SecurityEvent.record(Event.ACCOUNT_LINKED, actor=actor, subject_user=user,
                                 guardian=guardian)
    except IntegrityError as error:
        raise ValidationError("That login or guardian is already linked.") from error
    return account


def _lock_account(account):
    account = GuardianAccount.objects.select_for_update().select_related("user").get(
        pk=account.pk
    )
    if not account.is_active:
        raise ValidationError("This guardian account link has been revoked.")
    return account


def revoke_account_link(*, account, actor, reason):
    """Revoke the link immediately and end every session of the login."""
    reason = _require_reason(reason)
    with transaction.atomic():
        account = _lock_account(account)
        account.revoked_at = timezone.now()
        account.revoked_by = actor
        account.revocation_reason = reason
        account.save(update_fields=["revoked_at", "revoked_by", "revocation_reason"])
        account.user.end_all_sessions()
        SecurityEvent.record(Event.ACCOUNT_LINK_REVOKED, actor=actor,
                             subject_user=account.user, guardian=account.guardian)
    return account


def change_guardian_username(*, account, new_username, actor):
    with transaction.atomic():
        account = _lock_account(account)
        user = account.user
        username = clean_new_username(new_username, exclude_user=user)
        try:
            with transaction.atomic():
                get_user_model().objects.filter(pk=user.pk).update(username=username)
        except IntegrityError as error:
            raise ValidationError("That username is not available.") from error
        SecurityEvent.record(Event.USERNAME_CHANGED, actor=actor, subject_user=user,
                             guardian=account.guardian)
    return username


def reset_guardian_password(*, account, actor):
    """New temporary password, forced change, every session ended. Returns the password."""
    password = generate_temporary_password()
    with transaction.atomic():
        account = _lock_account(account)
        user = account.user
        user.set_password(password)
        user.must_change_password = True
        user.save(update_fields=["password", "must_change_password"])
        user.end_all_sessions()
        SecurityEvent.record(Event.PASSWORD_RESET_BY_ADMIN, actor=actor, subject_user=user,
                             guardian=account.guardian)
    return password


def grant_student_access(*, student_guardian, actor):
    """Explicitly grant one guardian–Student relationship (one at a time, OD-6)."""
    try:
        with transaction.atomic():
            student_guardian = StudentGuardian.objects.select_for_update().get(
                pk=student_guardian.pk
            )
            if GuardianStudentAccess.objects.filter(
                student_guardian=student_guardian, revoked_at__isnull=True
            ).exists():
                raise ValidationError("Access is already granted for this relationship.")
            grant = GuardianStudentAccess.objects.create(
                student_guardian=student_guardian, granted_by=actor
            )
            SecurityEvent.record(Event.ACCESS_GRANTED, actor=actor,
                                 guardian=student_guardian.guardian,
                                 student=student_guardian.student)
    except IntegrityError as error:
        raise ValidationError("Access is already granted for this relationship.") from error
    return grant


def revoke_student_access(*, grant, actor, reason):
    reason = _require_reason(reason)
    with transaction.atomic():
        grant = GuardianStudentAccess.objects.select_for_update().select_related(
            "student_guardian__guardian", "student_guardian__student"
        ).get(pk=grant.pk)
        if not grant.is_active:
            raise ValidationError("This access has already been revoked.")
        grant.revoked_at = timezone.now()
        grant.revoked_by = actor
        grant.revocation_reason = reason
        grant.save(update_fields=["revoked_at", "revoked_by", "revocation_reason"])
        SecurityEvent.record(Event.ACCESS_REVOKED, actor=actor,
                             guardian=grant.student_guardian.guardian,
                             student=grant.student_guardian.student)
    return grant
