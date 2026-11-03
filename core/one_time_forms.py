"""Stop a refresh from repeating a form that issues a password.

The page holds a token, and the session remembers it until the form is used. Repeating the POST
sends a token that is no longer current, so the view refuses it instead of issuing a new password.

This guards against accidents, not attackers: CSRF protection and permissions do that. A POST
with no token is therefore allowed, so a page opened just before a deploy still works. Only the
token is kept in the session, never a password.
"""

import secrets

from django.utils.crypto import constant_time_compare

FIELD = "one_time_token"
_SESSION_KEY = "one_time_forms"


def token_for(request, purpose):
    """The current token for `purpose`, for rendering into the form."""
    tokens = request.session.setdefault(_SESSION_KEY, {})
    if purpose not in tokens:
        tokens[purpose] = secrets.token_urlsafe(16)
        request.session.modified = True
    return tokens[purpose]


def is_repeat(request, purpose):
    """True if this POST repeats a used form. Otherwise uses up the current token."""
    submitted = request.POST.get(FIELD)
    if not submitted:
        return False
    tokens = request.session.get(_SESSION_KEY, {})
    current = tokens.get(purpose)
    if current is None or not constant_time_compare(current, submitted):
        return True
    del tokens[purpose]
    request.session.modified = True
    return False
