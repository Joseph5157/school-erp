from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.crypto import salted_hmac

from accounts.usernames import USERNAME_HELP, NormalizedUsernameValidator, normalize_username


class User(AbstractUser):
    """Authentication identity only. No school-domain fields belong here.

    Phase 6 (ADR 0013): usernames follow one normalization rule and are unique
    case-insensitively; `must_change_password` forces a change at the next
    request; bumping `session_version` ends every session of this login.
    """

    username_validator = NormalizedUsernameValidator()

    username = models.CharField(
        "username",
        max_length=150,
        unique=True,
        help_text=USERNAME_HELP,
        validators=[username_validator],
        error_messages={"unique": "That username is not available."},
    )
    must_change_password = models.BooleanField(default=False, db_default=False)
    session_version = models.PositiveIntegerField(default=0, db_default=0)

    class Meta(AbstractUser.Meta):
        swappable = "AUTH_USER_MODEL"
        permissions = [
            ("manage_teacher_accounts", "Can create and manage teacher logins"),
        ]
        constraints = [
            models.UniqueConstraint(Lower("username"), name="user_username_ci_unique"),
        ]

    @classmethod
    def normalize_username(cls, username):
        return normalize_username(username)

    def _get_session_auth_hash(self, secret=None):
        """Sessions are bound to the password and to `session_version`."""
        key_salt = "accounts.User.get_session_auth_hash"
        return salted_hmac(
            key_salt,
            f"{self.password}:{self.session_version}",
            secret=secret,
            algorithm="sha256",
        ).hexdigest()

    def end_all_sessions(self):
        """Invalidate every session of this login (ADR 0013)."""
        User.objects.filter(pk=self.pk).update(session_version=models.F("session_version") + 1)
        self.refresh_from_db(fields=["session_version"])


class SecurityEvent(models.Model):
    """Bounded security audit (ADR 0013, OD-7).

    Append-only: database triggers refuse every UPDATE, and refuse DELETE
    unless the event is ROUTINE and older than 365 days. HISTORY events are
    never deleted. Never store passwords, page contents or contact data.
    """

    class EventClass(models.TextChoices):
        ROUTINE = "ROUTINE", "Routine (kept 365 days)"
        HISTORY = "HISTORY", "History (kept permanently)"

    class EventType(models.TextChoices):
        LOGIN_SUCCEEDED = "LOGIN_SUCCEEDED", "Sign-in succeeded"
        LOGIN_FAILED = "LOGIN_FAILED", "Sign-in failed"
        LOGIN_THROTTLED = "LOGIN_THROTTLED", "Sign-in throttled"
        LOCKOUT_CLEARED = "LOCKOUT_CLEARED", "Lockout cleared"
        PASSWORD_CHANGED = "PASSWORD_CHANGED", "Password changed"
        PASSWORD_RESET_BY_ADMIN = "PASSWORD_RESET_BY_ADMIN", "Password reset by administrator"
        ACCOUNT_CREATED = "ACCOUNT_CREATED", "Guardian account created"
        ACCOUNT_LINKED = "ACCOUNT_LINKED", "Existing login linked to guardian"
        ACCOUNT_LINK_REVOKED = "ACCOUNT_LINK_REVOKED", "Guardian account link revoked"
        USERNAME_CHANGED = "USERNAME_CHANGED", "Guardian username changed"
        ACCESS_GRANTED = "ACCESS_GRANTED", "Student access granted"
        ACCESS_REVOKED = "ACCESS_REVOKED", "Student access revoked"
        ACCESS_RETAINED = "ACCESS_RETAINED", "Student access retained after review"
        ACCESS_REVIEW_PENDING = "ACCESS_REVIEW_PENDING", "Student access under review"
        TERM_PUBLISHED = "TERM_PUBLISHED", "Term results published"
        PUBLICATION_STALE = "PUBLICATION_STALE", "Publication became stale"
        PUBLICATION_WITHDRAWN = "PUBLICATION_WITHDRAWN", "Publication withdrawn"
        SECURITY_EVENTS_PURGED = "SECURITY_EVENTS_PURGED", "Routine events purged"
        IMPORT_COMMITTED = "IMPORT_COMMITTED", "Bulk import committed"
        DOCUMENT_ISSUED = "DOCUMENT_ISSUED", "Document issued"
        DOCUMENT_DOWNLOADED = "DOCUMENT_DOWNLOADED", "Document downloaded"
        TEACHER_ACCOUNT_CREATED = "TEACHER_ACCOUNT_CREATED", "Teacher account created"
        TEACHER_PASSWORD_RESET = "TEACHER_PASSWORD_RESET", "Teacher password reset"
        TEACHER_USERNAME_CHANGED = "TEACHER_USERNAME_CHANGED", "Teacher username changed"
        TEACHER_DEACTIVATED = "TEACHER_DEACTIVATED", "Teacher login deactivated"
        TEACHER_REACTIVATED = "TEACHER_REACTIVATED", "Teacher login reactivated"

    ROUTINE_TYPES = frozenset(
        {
            EventType.LOGIN_SUCCEEDED,
            EventType.LOGIN_FAILED,
            EventType.LOGIN_THROTTLED,
            EventType.LOCKOUT_CLEARED,
            EventType.PASSWORD_CHANGED,
            EventType.PASSWORD_RESET_BY_ADMIN,
        }
    )

    event_type = models.CharField(max_length=40, choices=EventType.choices)
    event_class = models.CharField(max_length=10, choices=EventClass.choices)
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
    actor = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    subject_user = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    guardian_id_ref = models.PositiveBigIntegerField(null=True, blank=True)
    student_id_ref = models.PositiveBigIntegerField(null=True, blank=True)
    term_id_ref = models.PositiveBigIntegerField(null=True, blank=True)
    source_key = models.CharField(max_length=64, blank=True)
    detail = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-occurred_at", "-pk"]
        permissions = [
            ("purge_securityevent", "Can purge routine security events older than 365 days"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(event_class__in=["ROUTINE", "HISTORY"]),
                name="securityevent_class_valid",
            ),
        ]

    @classmethod
    def class_for(cls, event_type):
        return (
            cls.EventClass.ROUTINE if event_type in cls.ROUTINE_TYPES else cls.EventClass.HISTORY
        )

    @classmethod
    def record(cls, event_type, *, actor=None, subject_user=None, guardian=None, student=None,
               term=None, detail=None):
        return cls.objects.create(
            event_type=event_type,
            event_class=cls.class_for(event_type),
            actor=actor if getattr(actor, "pk", None) else None,
            subject_user=subject_user,
            guardian_id_ref=getattr(guardian, "pk", None),
            student_id_ref=getattr(student, "pk", None),
            term_id_ref=getattr(term, "pk", None),
            detail=detail or {},
        )

    def __str__(self):
        return f"{self.get_event_type_display()} at {self.occurred_at:%Y-%m-%d %H:%M}"


class LoginFailure(models.Model):
    """Throttling state for failed sign-ins (ADR 0013, plan §8). Operational.

    `username_key` is the normalized attempted username; `source_key` is a
    keyed hash of the client address (never the raw address). Rows older
    than 24 hours are purged on each sign-in attempt; an administrator may
    clear a username's rows to lift a lockout.
    """

    username_key = models.CharField(max_length=150)
    source_key = models.CharField(max_length=64)
    occurred_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["username_key", "source_key", "occurred_at"],
                         name="loginfailure_lookup"),
            models.Index(fields=["occurred_at"], name="loginfailure_age"),
        ]
        permissions = [("clear_login_lockout", "Can clear a sign-in lockout")]
