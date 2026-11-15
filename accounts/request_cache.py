"""Remember a signed-in person's role lookups for one request.

A portal or staff page asks "is this a teacher? a guardian?" from the view, the navigation and the
header. AccountSecurityMiddleware turns the cache on for `request.user` only, and that object is
loaded fresh for every request, so an answer never outlives the request. Any other user object
(another login being edited, a background job, a test) is never cached and always asks the
database, so revoking someone's access is seen at once.
"""

_KEY = "_erp_request_cache"


def enable(user):
    user.__dict__[_KEY] = {}


def remember(user, key, compute):
    cache = getattr(user, "__dict__", {}).get(_KEY)
    if cache is None:
        return compute()
    if key not in cache:
        cache[key] = compute()
    return cache[key]
