"""The one username rule (ADR 0013, Phase 6).

Every path that creates, changes or looks up a username uses
`normalize_username` and compares normalized values: account creation, the
username-change workflow, the authentication backend, the site-administration
user forms and the database constraint on Lower("username").
"""

import re
import unicodedata

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

USERNAME_PATTERN = r"^[a-z0-9._-]{3,30}\Z"
USERNAME_HELP = "3–30 characters: lower-case letters, digits, dot, underscore or hyphen."


def normalize_username(value):
    """Unicode NFKC, surrounding whitespace removed, lower-cased."""
    if value is None:
        return ""
    return unicodedata.normalize("NFKC", str(value)).strip().lower()


class NormalizedUsernameValidator(RegexValidator):
    """Validates the allowed form of a new or changed (normalized) username."""

    regex = USERNAME_PATTERN
    message = "Enter a valid username. " + USERNAME_HELP
    flags = 0


def clean_new_username(value, *, exclude_user=None):
    """Normalize, validate the form and check case-insensitive uniqueness."""
    from django.contrib.auth import get_user_model

    username = normalize_username(value)
    NormalizedUsernameValidator()(username)
    users = get_user_model().objects.filter(username__iexact=username)
    if exclude_user is not None:
        users = users.exclude(pk=exclude_user.pk)
    if users.exists() or not re.fullmatch(USERNAME_PATTERN, username):
        raise ValidationError("That username is not available.")
    return username
