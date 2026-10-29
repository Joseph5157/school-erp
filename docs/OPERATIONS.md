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

## Backups

Railway backs up the Postgres volume on a schedule. Each installation needs
this switched on once; a new Railway Postgres service has no backups.

The commands below use the Railway CLI (5.35 or later). Replace the IDs with
the installation's project, environment and **Postgres** service IDs (not the
web service):

```
PG="-p <project-id> -e <environment-id> -s <postgres-service-id>"
```

### Switch on scheduled backups

```
railway postgres $PG pitr schedule set --daily --weekly
railway postgres $PG pitr backup create --name first-manual-<date>
railway postgres $PG pitr schedule list
```

Daily backups are kept for 6 days and weekly backups for 27 days. Manual
backups never expire, so delete old ones (`pitr backup delete <id>`) once
newer backups exist. Backups are billed on the space they add, at volume
rates.

### Check backups exist

```
railway postgres $PG pitr backup list
```

Each row shows the backup ID, when it was taken and its size. The size can
show `-` or `0` for a minute after a backup is taken.

### Restore from a backup

A restore replaces the live database with the backup. **Everything written
after the backup was taken is lost**, so take a manual backup first if the
current data might still be needed.

1. Note a few row counts so you can compare afterwards (Railway web service
   shell, `python manage.py shell`):

   ```python
   from core.models import Student, StudentResult
   print(Student.objects.count(), StudentResult.objects.count())
   ```

2. Find the backup ID with `pitr backup list`, then restore:

   ```
   railway postgres $PG pitr backup restore <backup-id> --yes
   ```

   Railway copies the backup into a new volume, mounts it on the Postgres
   service and redeploys it straight away. Expect about a minute of downtime.

3. Check the counts again and sign in to the site.

The old volume is unmounted, not deleted. If the restore went wrong, it can be
mounted back on the Postgres service from the Railway dashboard. Delete it
once the restored data has been confirmed, as it is still billed.

The daily and weekly schedule carries over to the new volume.

Restore tested on staging on 2026-10-29: row counts matched and a table
created after the backup was gone.

### Not yet set up

- Point-in-time recovery (`railway postgres pitr enable`), which can restore
  to any moment in the last ~4 weeks into a new service. Only covers time after
  it is switched on.
- A copy of the database outside Railway (for example a nightly `pg_dump`).
