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
Railway log. An optional Telegram alert to the operator works the same way (see
"Telegram crash alerts").

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

## Telegram crash alerts

An optional, immediate ping to the operator's own Telegram chat when production hits
an **unhandled 500**. It is off until both variables below are set. It adds a third
layer and replaces nothing:

1. **Railway console log**: always on, and the authoritative record with the full
   traceback.
2. **Telegram alert**: optional. It says that something broke and where, and nothing
   more.
3. **Crash email**: optional and unchanged (see above).

This bot is **only** for the operator's crash alerts. It is not a guardian or parent
channel, it never messages anyone else, and the application never reads messages
sent to it, so it accepts no commands. Guardian communication stays on the Portal
and the assisted-WhatsApp queue.

### What it covers

Only unhandled exceptions that Django turns into a 500 page (the `django.request`
logger, status 500 with an exception attached), and only in production
(`DJANGO_DEBUG` off). It does **not** alert on successful requests, validation
errors, 403 or 404 pages, a view that deliberately returns an error, warnings,
security events, parent communications, cron jobs or management commands.

Because the alert is sent by the application, it cannot report what happens
outside or before it:

- the Railway service or platform being down;
- failed builds or deploys;
- crashes before Django's logging starts, for example a settings error at startup;
- a Gunicorn worker killed for running out of memory or time.

Use Railway's own deploy notifications and service monitoring for those.

### Set it up

1. In Telegram, open **@BotFather**, send `/newbot` and follow the prompts. BotFather
   replies with the bot's **token**. Treat it like a password: do not paste it into
   chat, tickets, commits, `.env` files or a terminal whose output is shared.
2. Optional hardening: in BotFather send `/setjoingroups`, pick the bot and choose
   **Disable**, so nobody can add it to a group.
3. From the operator's own Telegram account, open the new bot and send `/start`.
   A bot cannot message someone who has not started it.
4. Find the operator's **chat ID**, a number. For a private chat with a bot, it is
   the operator's numeric Telegram user ID. Either:
   - message **@userinfobot** from the operator's account; it replies with the ID; or
   - on the operator's own device, in a private browser window, open
     `https://api.telegram.org/bot<token>/getUpdates` (with the real token in place
     of `<token>`) after sending `/start`, and copy the number after
     `"chat":{"id":`. Then close the window. The address contains the token, so
     never share it, and never fetch it from a terminal whose output is logged.
5. In the Railway dashboard, open the **web** service, then **Variables**, and add:

   | Variable | Value |
   |---|---|
   | `TELEGRAM_ERROR_BOT_TOKEN` | the token from step 1 |
   | `TELEGRAM_ERROR_CHAT_ID` | the number from step 4 |

   Type the values straight into Railway's variable editor. Railway redeploys the
   service. The cron service does not need them, since it serves no web requests.
6. From the web service's shell, check that it works:

   ```
   python manage.py sendtesttelegram
   ```

   The operator receives a fixed test message that names the instance and nothing
   else. The command prints `Telegram test alert sent.` or a short, generic failure
   message, exits non-zero on failure, and never prints the token, the chat ID or the
   Telegram address. It skips the cooldown, so it can be run repeatedly.

The two variables work as a pair:

- **both unset or blank**: alerts are off (the default);
- **both set**: alerts are on in production;
- **only one set**: the application **refuses to start**. The error names the
  missing variable and never shows either value.

Debug runs (`DJANGO_DEBUG=True`) and `manage.py test` never contact Telegram, even
when both variables are set. In those runs `sendtesttelegram` reports that alerts
are not configured.

### What the alert contains

It is built from the same allow-list as the crash email (Security Gate 4A) and
sent as plain text, with forwarding and saving blocked (`protect_content`) and no
link previews:

```
School ERP error

Instance: st-marys
Time (UTC): 2026-11-07 15:45:00
Level: ERROR
Status: 500
Request: GET /students/<int:pk>/report-card/<int:term_pk>/
Exception: django.db.DatabaseError
Caused by: KeyError

Where (innermost last):
  site-packages/django/core/handlers/base.py:197 in _get_response
  core/views.py:120 in report_card

The full details are in Railway logs.
```

So it carries the instance name, the time (UTC), the level and status, the request
method, the **route pattern** (never the concrete address), the exception types in
the chain, and up to six sanitised `file:line in function` locations. It never
contains the concrete URL or the values in it, query strings, names, usernames,
email addresses or phone numbers, IP addresses or the forwarded-for chain, the user
agent, referer or any other header, cookies, form values, exception messages,
database row details, source lines, local variables, absolute file paths, the bot
token or the chat ID. Messages stay under Telegram's 4,096-character limit. A
too-long alert is shortened and still ends with the Railway line. If an alert cannot
be built, a generic one says so instead. Match an alert to its Railway log entry by
the time and the route.

### Delivery, failures and cooldown

- The alert is sent during the failing request, as one HTTPS request with a
  **3-second timeout**. The page has already failed, so this only delays the error
  page a little. Telegram is never retried. (The timeout does not cover the DNS
  lookup, so in rare network trouble the wait can be longer.)
- If Telegram cannot be reached, refuses the message or answers strangely, the
  error page and the Railway traceback are unaffected. The log gets one extra line:
  `Telegram crash alert delivery failed; see the Railway log.` That line never
  includes the token, the chat ID, the Telegram address, Telegram's answer or the
  error text. The usual causes are a wrong or revoked token, a wrong chat ID, or the
  operator not having sent `/start`. Run `sendtesttelegram` to check.
- **Cooldown:** the first occurrence of an error is sent at once, and the same error
  (same instance, route pattern, exception type and raising location) is not sent
  again for **five minutes**. A different error still alerts. The cooldown is held in
  memory by each Gunicorn worker, so with two workers the same error can produce two
  first alerts, and a restart or redeploy starts fresh. It never uses the database or
  the cache, because either may be what failed. A failed delivery still starts the
  cooldown. Each worker remembers at most 256 recent errors.

### If the token is exposed

1. In @BotFather send `/revoke` (or `/token`), pick the bot and confirm. The old
   token stops working immediately.
2. Replace `TELEGRAM_ERROR_BOT_TOKEN` on the Railway web service with the new token.
   Railway redeploys the service.
3. Run `python manage.py sendtesttelegram` from the service shell.

Until step 2 is done, deliveries fail and the log shows the generic failure line.
Crashes are still in the Railway log.

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
| `TELEGRAM_ERROR_BOT_TOKEN`, `TELEGRAM_ERROR_CHAT_ID` | Optional, web service only | Both set: Telegram crash alerts on (see "Telegram crash alerts"). Both unset: off. Only one set: the application **refuses to start**, naming the missing one. |

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
