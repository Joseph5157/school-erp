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
page) is also emailed to the administrators.

### Environment variables

| Variable | Example | Purpose |
|---|---|---|
| `ERP_INSTANCE_NAME` | `st-marys` | Names the installation in email subjects: `[school-erp st-marys] ERROR ...`. Default `local`. |
| `DJANGO_ADMINS` | `ops@example.com,dev@example.com` | Comma-separated addresses that receive crash emails. Empty: no emails, logging only. |
| `EMAIL_HOST` | `smtp.gmail.com` | SMTP server. Empty: mail is printed to the console instead of sent. |
| `EMAIL_PORT` | `587` | Default `587`. |
| `EMAIL_HOST_USER` | `alerts@example.com` | SMTP login. |
| `EMAIL_HOST_PASSWORD` | (app password) | SMTP password. For Gmail, use an [app password](https://myaccount.google.com/apppasswords), not the account password. |
| `EMAIL_USE_TLS` | `True` | Default `True`. |
| `SERVER_EMAIL` | `alerts@example.com` | Sender address. Defaults to `EMAIL_HOST_USER`. |
| `DJANGO_LOG_LEVEL` | `INFO` | Console log level. Default `INFO`. |

Outgoing SMTP needs the Railway Pro plan.

### What the email contains

The traceback (files, line numbers, code), the URL, the view and the signed-in
user. Submitted form values, cookies and the traceback's local variables are
replaced with `********************` (`config/error_reporting.py`) so no
student or guardian details are emailed. Query-string parameters (e.g.
`?section=4`) are kept.

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
