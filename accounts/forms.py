from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm

from accounts import security
from accounts.models import SecurityEvent
from accounts.usernames import normalize_username

GENERIC_ERROR = (
    "The username or password is incorrect, or sign-in is temporarily unavailable."
)


class ThrottledAuthenticationForm(AuthenticationForm):
    """Sign-in with database-backed throttling and one generic error (ADR 0013).

    Unknown username, wrong password, inactive login and throttled attempts
    all produce the same message, so nothing reveals whether a username
    exists. Events never contain the attempted text.
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
            security.record_failure(username, source)
            self._event(SecurityEvent.EventType.LOGIN_THROTTLED, subject, source)
            raise forms.ValidationError(GENERIC_ERROR, code="invalid_login")
        self.user_cache = authenticate(self.request, username=username, password=password)
        if self.user_cache is None:
            security.record_failure(username, source)
            self._event(SecurityEvent.EventType.LOGIN_FAILED, subject, source)
            raise forms.ValidationError(GENERIC_ERROR, code="invalid_login")
        self.confirm_login_allowed(self.user_cache)
        security.clear_source_failures(username, source)
        self._event(SecurityEvent.EventType.LOGIN_SUCCEEDED, self.user_cache, source)
        return self.cleaned_data

    @staticmethod
    def _event(event_type, subject, source):
        event = SecurityEvent(
            event_type=event_type, event_class=SecurityEvent.class_for(event_type),
            subject_user=subject, source_key=source,
        )
        event.save()
