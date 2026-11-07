# Operations

How to run and watch a production installation. Each school is its own
installation (one Railway project: app service + PostgreSQL), deployed from
the same `main` branch.

## Crash reporting

Errors are written to the app's console, which Railway shows under the
service's **Logs** tab. Each line looks like:

```
2026-10-28 14:02:11,512 ERROR django.request Internal Server Error: /attendance/
Traceback (most recent call last):
  ...
```

Search Railway logs for `ERROR` to find crashes. Every unhandled crash (a 500
page) can also be emailed to the administrators, but **nothing is emailed until
both `DJANGO_ADMINS` and `EMAIL_HOST` are set**. Until a mail service is chosen
and its credentials are added as Railway variables, crash reporting is the
Railway log only. The email is deliberately short (see "What the email
contains"): it says which crash and where, and you read the full detail in the
Railway log.

### Environment variables

| Variable | Example | Purpose |
|---|---|---|
| `ERP_INSTANCE_NAME` | `st-marys` | Names the installation in email subjects: `[school-erp st-marys] ERROR ...`. Default `local`. |
| `DJANGO_ADMINS` | `ops@example.com,dev@example.com` | Comma-separated addresses that receive crash emails. Empty: no emails, logging only. |
| `EMAIL_HOST` | `smtp.gmail.com` | SMTP server. Empty: no mail is sent. Production discards mail; local development (`DJANGO_DEBUG=True`) prints it to the console. |
| `EMAIL_PORT` | `587` | Default `587`. |
| `EMAIL_HOST_USER` | `alerts@example.com` | SMTP login. |
| `EMAIL_HOST_PASSWORD` | (app password) | SMTP password. For Gmail, use an [app password](https://myaccount.google.com/apppasswords), not the account password. |
| `EMAIL_USE_TLS` | `True` | Default `True`. |
| `SERVER_EMAIL` | `alerts@example.com` | Sender address. Defaults to `EMAIL_HOST_USER`. |
| `DJANGO_LOG_LEVEL` | `INFO` | Console log level. Default `INFO`. |

Outgoing SMTP needs the Railway Pro plan.

### What the email contains

Crash emails go to a mail provider outside the school's installation, so they are
built from an allow-list (`config/error_reporting.py`, Security Gate 4A) and carry
only:

- the instance name, the time (UTC), the level and the status code;
- the request method and the **route pattern** that handled it, for example
  `/students/<int:pk>/edit/`, never the concrete address;
- the **exception types** in the chain (for example `IntegrityError`, caused by
  `KeyError`);
- the traceback locations as `file:line in function`, never as a full path on the
  server: project files are relative to the project, installed packages start
  `site-packages/`, the standard library starts `stdlib/`, and any other file shows
  only `external/<file name>`.

They never contain query-string parameters (search terms), client IP addresses or
other request headers, cookies, form values, the signed-in username, exception
messages (a database error can quote the row it rejected), source lines or the
traceback's local variables. If a report cannot be built the email says so and
nothing else.

The Railway log keeps the full detail, including the exception message and
traceback, because only the person running the service reads it. Match an email to
its log entry by the time and the route.

To check what an email would contain without sending anything, run the tests:
`python manage.py test core.tests.test_security_gate4a_crash_email_privacy` (they
use Django's in-memory mail backend).

### Check it works

After setting the variables, from the Railway service shell:

```
python manage.py sendtestemail --admins
```

## Privileged login linked to a guardian

The guardian workflow only links, resets or renames a login that is not a
superuser or staff, holds no direct permission and belongs to no group other
than Teachers (`core/guardian_accounts.py:is_portal_manageable`). A teacher who
is also a parent is still allowed. Django admin refuses password changes and
username edits for a login with an **active** guardian link
(`accounts/admin.py`), and that protection stays.

If a linked login gains other authority, or an administrator needs to manage a
login that cannot be linked, use this order. Both steps need an administrator
who holds the permission:

1. Revoke the guardian account link: Guardians, open the guardian, Revoke
   account link, give a reason. Revoking is never blocked, is recorded as an
   audit event (account link revoked) and ends every session of that login. It
   does not change the student access grants; revoke those separately if they
   should end too.
2. Manage the login in the Django admin (`/admin/`) as a superuser, or as staff
   who hold the user permissions: change its password or username there. Once
   the link is revoked the admin protection no longer applies.

Do not link the login again until it has only the Teachers group. Use a
separate guardian login instead.

## WhatsApp message queue (ASSIST mode)

In ASSIST mode the ERP prepares messages and office staff send each one by hand
from their own WhatsApp (ADR 0015). The ERP never sends anything.

A prepared message is only a promise made when it was prepared. The guardian's
consent, portal access grant, account link, login or date-based review can change
afterwards, so the queue decides again at each step, from current data:

- **Showing the queue** drops messages that are no longer eligible. No consent
  gives "Skipped — no consent". Lost portal access is dismissed by the system with
  the reason "Guardian no longer has portal access".
- **Send on WhatsApp** is a button that POSTs to the ERP, never a plain link. The
  `wa.me` address is not in the page. The ERP rechecks consent and portal access
  and only then redirects to WhatsApp. If the message is no longer eligible it is
  skipped or dismissed, staff return to the queue, and WhatsApp is not opened.
- **Mark as sent** rechecks once more under a row lock. It is authoritative for
  recording the SENT state: it never records SENT for a message that is no longer
  eligible.

**Limitation.** Nothing here can see or stop what staff do inside WhatsApp. If
consent or access is withdrawn after staff were redirected to WhatsApp but before
they choose Mark as sent, the message may already have been sent by hand while the
queue records it as dismissed or skipped. Mark as sent is therefore not a guarantee
that nothing was sent, only that the ERP will not claim it was sent to someone who
is no longer eligible. Keep that window short: open WhatsApp, send, and choose Mark
as sent straight away.

## Roles and permissions

Which screens a login can use, and which kinds of personal data they show, is described in
[PERMISSIONS.md](PERMISSIONS.md): the permission each class of data needs, what a limited
custom role sees, the deliberate bundles and the recommended registrar, communications,
attendance, results and import roles.

To take an inventory of the custom roles in an installation, run from the service shell:

```
python manage.py role_permission_gaps
```

It is read-only. It lists the custom groups, and the logins with permissions assigned directly,
whose permissions leave a page limited or a file refused, and prints names only (no emails,
passwords or personal data). Running it on a live installation is safe, and it is the way to
check a deployment before relying on a narrow role. A gap it reports is information, not an
error.

## Production settings

Set these on the Railway web service. The cron service references the web
service's variables, so it must receive the same ones.

| Variable | Required | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | Yes | A unique, secret value per installation. The application **refuses to start** if it is missing, blank or begins with `django-insecure-` (the development default in the repository). Generate one with `python -c "import secrets; print(secrets.token_urlsafe(64))"`. Changing it signs every user out. |
| `DJANGO_ALLOWED_HOSTS` | Yes | Comma-separated host names this installation answers to. |
| `DJANGO_HTTPS` | Leave unset, or `True` | In production HTTPS is **on by default**: Secure cookies, the HTTPS redirect and HSTS. An explicit `False` stops startup, so HTTPS cannot be lost silently. Behind Railway it needs `DJANGO_TRUSTED_PROXIES` as well, or the HTTPS redirect loops. |
| `DJANGO_TRUSTED_PROXIES` | Yes, behind Railway | Comma-separated proxy addresses or CIDR ranges whose `X-Forwarded-*` headers are believed. A malformed entry stops startup. Together with `DJANGO_HTTPS` it also enables the proxy HTTPS header. |
| `DJANGO_SOURCE_HASH_KEY` | Recommended | Key for hashing network addresses. If unset it is derived from the secret key, so changing the secret key also changes it. |
| `DJANGO_HSTS_PRELOAD` | Optional | Default and valid value `False`. Set `True` only once the site is ready for the browser preload list. |
| `DJANGO_DEBUG` | Never in production | `True` is for local development only. It is also what lets a development machine start without a secret key. |

On/off variables (`DJANGO_HTTPS`, `DJANGO_HSTS_PRELOAD`, `EMAIL_USE_TLS`) accept
`True`/`False` in any capitalisation, and also `1`/`0`, `yes`/`no`, `on`/`off`.
Any other value stops startup, so a typo can no longer silently switch HTTPS or
mail encryption off. A blank value (for example `EMAIL_USE_TLS=`) counts as unset
and takes the variable's default: HTTPS on in production, mail encryption on, HSTS
preload off. Mail encryption is turned off only by an explicit `False`, `0`, `no`
or `off`.

### Local development, tests and CI

- **Local development:** set `DJANGO_DEBUG=True` before `manage.py` commands such as
  `migrate`, `shell` and `runserver` (see `.env.example`). A debug run may leave the
  secret key unset, stays on plain HTTP and needs no proxy setting. You can still set
  `DJANGO_HTTPS=True` locally to try the HTTPS behaviour.
- **Tests:** `manage.py test` uses plain HTTP by default. An explicit
  `DJANGO_HTTPS=True` enables HTTPS behavior during tests. Tests also use a fast
  password hasher and need no key.
- **CI** (`.github/workflows/ci.yml`): sets `DJANGO_SECRET_KEY` to a placeholder and
  `DJANGO_DEBUG=False`, then runs `manage.py check`, `makemigrations --check --dry-run`
  and `manage.py test`. HTTPS is on by default in the first two, which send no
  requests, so CI needs no HTTPS or proxy variables. Never copy the placeholder key to
  a deployment.

### Check a deployment without exposing secrets

Never print variable values: do not run `railway variables` or `printenv`
without discarding the values.

1. List only the variable **names** on each service:
   `railway variables --service <service> --kv | cut -d= -f1`. `DJANGO_SECRET_KEY`,
   `DJANGO_ALLOWED_HOSTS` and `DJANGO_TRUSTED_PROXIES` must appear on the web and
   cron services. `DJANGO_HTTPS` is optional: when it is absent, HTTPS is on. If it
   does appear, its value must not be `False`.
2. From the service shell, run `python manage.py check --deploy`. It prints no
   secrets and should report no errors. Warning `security.W021` (HSTS preload) is
   expected until `DJANGO_HSTS_PRELOAD` is set.
3. From outside, `curl -sI https://<host>/accounts/login/` should show
   `strict-transport-security`, `x-frame-options: DENY`, `x-content-type-options:
   nosniff` and a `csrftoken` cookie marked `Secure`. `curl -sI http://<host>/...`
   should answer `301` to the `https://` address.

If a deployment fails with "DJANGO_SECRET_KEY must be set", add the variable to
the service and redeploy. The build step runs `collectstatic`, which loads the
settings, so a missing key fails the build and the previous deployment keeps
serving.
