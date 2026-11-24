from django import forms
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.core.exceptions import ValidationError

from accounts import security
from accounts.models import SecurityEvent
from accounts.usernames import normalize_username

GENERIC_ERROR = (
    "The username or password is incorrect, or sign-in is temporarily unavailable."
)


class ThrottledLoginMixin:
    """Sign-in with database-backed throttling and one generic error (ADR 0013).

    Unknown username, wrong password, inactive login, a login this door does not
    accept (for example a non-staff login at the Django admin) and throttled attempts
    all produce the same message, so nothing reveals whether a username exists.
    Events never contain the attempted text. Every password-checking door uses this
    mixin (Security Gate 1), so they share one throttle and one audit trail.
    """

    error_messages = {"invalid_login": GENERIC_ERROR, "inactive": GENERIC_ERROR}

    def clean(self):
        from django.contrib.auth import get_user_model
        from django.db.models.functions import Lower

        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")
        if username is None or not password:
            return self.cleaned_data
        source = security.source_key(self.request)
        security.purge_expired()
        key = normalize_username(username)
        subject = (
            get_user_model().objects.annotate(_k=Lower("username")).filter(_k=key).first()
        )
        if security.is_throttled(username, source):
            # Read by the sign-in view's usage signal (ADR 0027); never stores the username.
            self.was_throttled = True
            security.record_failure(username, source)
            self._event(SecurityEvent.EventType.LOGIN_THROTTLED, subject, source)
            raise forms.ValidationError(GENERIC_ERROR, code="invalid_login")
        self.user_cache = authenticate(self.request, username=username, password=password)
        if self.user_cache is None:
            security.record_failure(username, source)
            self._event(SecurityEvent.EventType.LOGIN_FAILED, subject, source)
            raise forms.ValidationError(GENERIC_ERROR, code="invalid_login")
        try:
            self.confirm_login_allowed(self.user_cache)
        except forms.ValidationError:
            # A correct password at a door that refuses this login (the admin's staff-only
            # rule) is a failure: it counts toward the throttle and is audited.
            self.user_cache = None
            security.record_failure(username, source)
            self._event(SecurityEvent.EventType.LOGIN_FAILED, subject, source)
            raise forms.ValidationError(GENERIC_ERROR, code="invalid_login") from None
        security.clear_source_failures(username, source)
        self._event(SecurityEvent.EventType.LOGIN_SUCCEEDED, self.user_cache, source)
        security.note_successful_sign_in(self.user_cache)
        return self.cleaned_data

    @staticmethod
    def _event(event_type, subject, source):
        event = SecurityEvent(
            event_type=event_type, event_class=SecurityEvent.class_for(event_type),
            subject_user=subject, source_key=source,
        )
        event.save()


class ThrottledAuthenticationForm(ThrottledLoginMixin, AuthenticationForm):
    """The ERP sign-in form (accounts/login/)."""


class ThrottledAdminAuthenticationForm(ThrottledLoginMixin, AdminAuthenticationForm):
    """The Django admin sign-in form: the same throttle and audit, and still staff-only.

    AdminAuthenticationForm.confirm_login_allowed still refuses non-staff logins; the mixin
    turns that refusal into a counted, audited failure with the generic message.
    """


SAME_PASSWORD_ERROR = "Choose a new password that is different from your current one."


class SamePasswordRefusingChangeForm(PasswordChangeForm):
    """Refuses a 'new' password equal to the current one (ADR 0029 R19).

    Without this, a forced change could be met by re-entering the temporary password, which
    then stays valid and is still printed on the slip.
    """

    def save(self, commit=True):
        """Write only the password. Django's default saves the whole login loaded at the start
        of the request, which could undo an office reset made meanwhile (its new temporary
        password stamp and its ended sessions). G-06 reset spec §5.1, review F2."""
        self.user.set_password(self.cleaned_data["new_password1"])
        if commit:
            self.user.save(update_fields=["password"])
        return self.user

    def clean(self):
        cleaned = super().clean()
        new = cleaned.get("new_password2")
        if new and "new_password2" not in self.errors and self.user.check_password(new):
            self.add_error("new_password2", ValidationError(SAME_PASSWORD_ERROR, code="password_unchanged"))
        return cleaned
