"""Keeps personal data out of crash reports (the admin error email).

Security Gate 4A. The email goes to a third-party mail provider, so it is built from an
allow-list, not from Django's request report with parts masked. It carries only: the
instance name, the time, the level and status, the request method, the *route pattern* (never
the concrete URL), the exception *types* in the chain, and `file:line in function` for each
traceback frame. It never carries query-string terms, client addresses or headers, the
signed-in username, exception messages (a database error can quote the row), source lines
or local variables. The Railway console log keeps the full detail for the operator.

`PrivacyExceptionReporterFilter` still masks form data, cookies and local variables wherever
Django's own reporter is used (for example the technical 500 page).
"""

import os
import sysconfig
import traceback
from dataclasses import dataclass
from pathlib import PurePosixPath

from django.conf import settings
from django.utils import timezone
from django.utils.log import AdminEmailHandler
from django.views.debug import SafeExceptionReporterFilter

_MAX_CHAIN = 6
_MAX_FRAMES = 25


class PrivacyExceptionReporterFilter(SafeExceptionReporterFilter):
    def get_post_parameters(self, request):
        if request is None or not self.is_active(request):
            return super().get_post_parameters(request)
        return {key: self.cleansed_substitute for key in request.POST}

    def get_safe_cookies(self, request):
        if not self.is_active(request):
            return super().get_safe_cookies(request)
        return {key: self.cleansed_substitute for key in request.COOKIES}

    def get_traceback_frame_variables(self, request, tb_frame):
        if not self.is_active(request):
            return super().get_traceback_frame_variables(request, tb_frame)
        return [(name, self.cleansed_substitute) for name in tb_frame.f_locals]


def _type_name(error):
    kind = type(error)
    return kind.__qualname__ if kind.__module__ == "builtins" else f"{kind.__module__}.{kind.__qualname__}"


def _chain(error):
    """The exception and what led to it, outermost first, as (error, how) pairs."""
    chain, how = [], ""
    while error is not None and len(chain) < _MAX_CHAIN and all(error is not e for e, _ in chain):
        chain.append((error, how))
        if error.__cause__ is not None:
            error, how = error.__cause__, "cause"
        elif not error.__suppress_context__ and error.__context__ is not None:
            error, how = error.__context__, "raised while handling"
        else:
            error = None
    return chain


def _route(request):
    """The URL pattern that handled the request, e.g. /students/<int:pk>/edit/ (no ids)."""
    match = getattr(request, "resolver_match", None)
    route = getattr(match, "route", None)
    if not route:
        return "(unresolved)"
    return route if route.startswith("/") else "/" + route


def _compare_parts(path):
    """Path components for comparison, whatever the separator style or platform case rules."""
    return PurePosixPath(os.path.normcase(str(path)).replace("\\", "/")).parts


def _shown_parts(path):
    """The same components with their original spelling, for display."""
    return PurePosixPath(str(path).replace("\\", "/")).parts


def _under(path, root):
    """True when `path` is inside the directory `root`, compared by whole components, so
    /app/school-private/x.py is not inside /app/school."""
    inside, base = _compare_parts(path), _compare_parts(root)
    return len(inside) > len(base) and inside[: len(base)] == base


def _safe_location(filename):
    """A file location that never reveals where the service is installed.

    Project file: relative to the project. Installed package: site-packages/... Standard
    library: stdlib/... Anything else: external/<file name> (the name only, no directories).
    """
    if filename.startswith("<") and "/" not in filename and "\\" not in filename:
        return filename  # pseudo files such as <frozen importlib._bootstrap> or <string>
    shown, compared = _shown_parts(filename), _compare_parts(filename)
    for marker in ("site-packages", "dist-packages"):
        if marker in compared:
            return "site-packages/" + "/".join(shown[compared.index(marker) + 1 :])
    if _under(filename, settings.BASE_DIR):
        return "/".join(shown[len(_compare_parts(settings.BASE_DIR)) :])
    paths = sysconfig.get_paths()
    for root in {paths.get("stdlib"), paths.get("platstdlib")} - {None}:
        if _under(filename, root):
            return "stdlib/" + "/".join(shown[len(_compare_parts(root)) :])
    return "external/" + (shown[-1] if shown else "unknown")


def _frames(tb):
    """Safe `file:line in function` locations for a traceback, innermost last."""
    return [
        f"{_safe_location(frame.filename)}:{frame.lineno} in {frame.name}"
        for frame in traceback.extract_tb(tb)[-_MAX_FRAMES:]
    ]


@dataclass(frozen=True)
class ChainLink:
    kind: str  # exception type name, never its message
    how: str  # "", "cause" or "raised while handling"
    frames: tuple  # safe locations, innermost last


@dataclass(frozen=True)
class CrashFacts:
    """Everything a crash report may say about one log record: the allow-list itself.

    Shared by the crash email and the Telegram alert (config.telegram_alerts), so both
    carry the same, and only the same, fields.
    """

    instance: str
    time: str
    level: str
    status: str
    method: str
    route: str
    kind: str
    chain: tuple  # ChainLink, outermost first


def crash_facts(record):
    request = getattr(record, "request", None)
    chain = _chain(record.exc_info[1] if record.exc_info else None)
    return CrashFacts(
        instance=settings.ERP_INSTANCE_NAME,
        time=f"{timezone.now():%Y-%m-%d %H:%M:%S}",
        level=record.levelname,
        status=str(getattr(record, "status_code", "-")),
        method=getattr(request, "method", None) or "-",
        route=_route(request),
        kind=_type_name(chain[0][0]) if chain else "no exception",
        chain=tuple(
            ChainLink(_type_name(error), how, tuple(_frames(error.__traceback__)))
            for error, how in chain
        ),
    )


def build_report(record):
    """(subject, body) for one log record, from the allow-list described above."""
    facts = crash_facts(record)
    lines = [
        f"Instance: {facts.instance}",
        f"Time (UTC): {facts.time}",
        f"Level: {facts.level}",
        f"Status: {facts.status}",
        f"Request: {facts.method} {facts.route}",
        f"Exception: {facts.kind}",
        "",
        "Exception chain (outermost first). Messages, query strings, client details and",
        "variables are left out on purpose; the service's Railway logs have the full detail.",
    ]
    if not facts.chain:
        lines.append("  (no exception was attached to this log record)")
    for number, link in enumerate(facts.chain, 1):
        lines.append(f"  {number}. {link.kind}" + (f" ({link.how})" if link.how else ""))
        lines.extend(f"    {frame}" for frame in link.frames)
    return f"{facts.level}: {facts.kind} at {facts.route}", "\n".join(lines) + "\n"


class PrivacyAdminEmailHandler(AdminEmailHandler):
    """Emails the allow-list report to ADMINS; never Django's full request report."""

    def emit(self, record):
        if not settings.ADMINS:
            return
        try:
            subject, body = build_report(record)
        except Exception:
            subject = f"{record.levelname}: crash"
            body = (
                "A crash was logged, but its report could not be built. "
                "The service's Railway logs have the details.\n"
            )
        self.send_mail(self.format_subject(subject), body, fail_silently=True)
