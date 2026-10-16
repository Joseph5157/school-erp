"""Task counts for the office sidebar badges and Overview cards (F21).

Only cheap queues are counted, so this can run on every admin page: each is
a single indexed COUNT (the lockout count is one grouped read over the
15-minute failure window).

Deliberately NOT counted: Access reviews (`core:guardian-access-reviews`).
Its count loads every active guardian grant, which must not run on every
page; it stays an Overview-card-only figure.

The "To send" count is a plain COUNT of PREPARED rows. It must never call
`notifications.to_send()`, which marks rows without consent SKIPPED. So the
count may include messages the To send page will skip for missing consent; the
Overview card says so.

The sidebar and the Overview cards both use the helpers here, so the two
cannot disagree.
"""

from accounts import security
from core import publication
from core.models import Notification


def prepared_notification_count():
    return Notification.objects.filter(status=Notification.Status.PREPARED).count()


def locked_username_count():
    return len(security.locked_usernames())


def stale_publication_count():
    return publication.stale_publications().count()


# (sidebar link URL name, permission as in OFFICE_NAV, count). Looked up late so
# tests can patch the helpers.
_QUEUES = (
    ("core:notifications-to-send", "core.send_notification", lambda: prepared_notification_count()),
    ("core:login-lockouts", "accounts.clear_login_lockout", lambda: locked_username_count()),
    ("core:publications-stale", "core.view_termpublication", lambda: stale_publication_count()),
)


def queue_counts(user):
    """{namespaced url name: count} for the queues this user may open."""
    return {
        url_name: count()
        for url_name, perm, count in _QUEUES
        if user.has_perm(perm)
    }
