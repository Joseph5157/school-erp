"""Shared pieces for the marks and attendance autosave browser tests (ENG-JS-01 JS2).

Reply headers, request-body parsing, and an init script that counts `erp:signed-out` events. The
tests assert only what a person, a screen reader or the server would see (spec section 7.4).
"""

import re
from urllib.parse import parse_qs

# A marks reply the sheet may swap in (views.assessment_marks_autosave sets the header).
FRAGMENT = {"Content-Type": "text/html; charset=utf-8", "X-ERP-Row-Fragment": "1"}
HTML = {"Content-Type": "text/html; charset=utf-8"}
JSON = {"Content-Type": "application/json"}

COUNT_SIGNED_OUT = (
    "document.addEventListener('erp:signed-out', function () {"
    " window.signedOutEvents = (window.signedOutEvents || 0) + 1; });"
)


def form(held):
    """An urlencoded request body (what HTMX sends) as {name: value}."""
    return {name: values[-1] for name, values in parse_qs(held.body, keep_blank_values=True).items()}


def multipart(held, name):
    """Every value of one field in a multipart body (what fetch sends for FormData)."""
    return re.findall(r'name="' + re.escape(name) + r'"\r\n\r\n([^\r]*)\r\n', held.body)
