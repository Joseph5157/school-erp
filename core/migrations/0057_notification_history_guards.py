# Phase 7 Gate 1 (ADR 0015): consent, templates and notifications are history.
#
# - GuardianContactConsent: no UPDATE, no DELETE (append-only).
# - NotificationTemplate: no DELETE; key/channel/language/version/body fixed;
#   approved may only go from false to true.
# - Notification: no DELETE; content fixed; status only moves forward along
#   QUEUED -> PREPARED/FAILED/SKIPPED_NO_CONSENT,
#   PREPARED -> SENT/DISMISSED/SKIPPED_NO_CONSENT/FAILED, SENT -> DELIVERED;
#   rows may be touched without a status change only while QUEUED or PREPARED.

from django.db import migrations

CONSENT = "Consent records cannot be changed or deleted."
TEMPLATE = "An approved template cannot be changed; create a new version."
TEMPLATE_DELETE = "Notification templates are never deleted."
NOTIFICATION = "Notifications cannot be deleted or rewritten."
STATUS = "That notification status change is not allowed."

TEMPLATE_FIXED = ["key", "channel", "language", "version", "body"]
NOTIFICATION_FIXED = [
    "guardian_id", "student_id", "type", "template_id", "parameters", "channel_mode",
    "idempotency_key", "created_at",
]
TRANSITION = (
    "(OLD.status = NEW.status AND OLD.status IN ('QUEUED', 'PREPARED'))"
    " OR (OLD.status = 'QUEUED' AND NEW.status IN ('PREPARED', 'FAILED', 'SKIPPED_NO_CONSENT'))"
    " OR (OLD.status = 'PREPARED'"
    " AND NEW.status IN ('SENT', 'DISMISSED', 'SKIPPED_NO_CONSENT', 'FAILED'))"
    " OR (OLD.status = 'SENT' AND NEW.status = 'DELIVERED')"
)
UNAPPROVE = "OLD.approved AND NOT NEW.approved"


def _changed(columns, op):
    return " OR ".join(f"NEW.{c} {op} OLD.{c}" for c in columns)


SQLITE = [
    f"CREATE TRIGGER core_gcc_no_update BEFORE UPDATE ON core_guardiancontactconsent "
    f"BEGIN SELECT RAISE(ABORT, '{CONSENT}'); END;",
    f"CREATE TRIGGER core_gcc_no_delete BEFORE DELETE ON core_guardiancontactconsent "
    f"BEGIN SELECT RAISE(ABORT, '{CONSENT}'); END;",
    f"CREATE TRIGGER core_nt_no_delete BEFORE DELETE ON core_notificationtemplate "
    f"BEGIN SELECT RAISE(ABORT, '{TEMPLATE_DELETE}'); END;",
    f"CREATE TRIGGER core_nt_fixed BEFORE UPDATE ON core_notificationtemplate "
    f"WHEN {_changed(TEMPLATE_FIXED, 'IS NOT')} OR ({UNAPPROVE}) "
    f"BEGIN SELECT RAISE(ABORT, '{TEMPLATE}'); END;",
    f"CREATE TRIGGER core_n_no_delete BEFORE DELETE ON core_notification "
    f"BEGIN SELECT RAISE(ABORT, '{NOTIFICATION}'); END;",
    f"CREATE TRIGGER core_n_fixed BEFORE UPDATE ON core_notification "
    f"WHEN {_changed(NOTIFICATION_FIXED, 'IS NOT')} "
    f"BEGIN SELECT RAISE(ABORT, '{NOTIFICATION}'); END;",
    f"CREATE TRIGGER core_n_status BEFORE UPDATE ON core_notification "
    f"WHEN NOT ({TRANSITION}) BEGIN SELECT RAISE(ABORT, '{STATUS}'); END;",
]
SQLITE_REVERSE = [
    f"DROP TRIGGER IF EXISTS {name};"
    for name in ("core_gcc_no_update", "core_gcc_no_delete", "core_nt_no_delete",
                 "core_nt_fixed", "core_n_no_delete", "core_n_fixed", "core_n_status")
]


def _raise(message):
    return (
        f"RAISE EXCEPTION USING ERRCODE = 'integrity_constraint_violation', "
        f"MESSAGE = '{message}';"
    )


POSTGRES = [
    f"""
    CREATE OR REPLACE FUNCTION core_gcc_guard() RETURNS trigger AS $$
    BEGIN {_raise(CONSENT)} END;
    $$ LANGUAGE plpgsql;
    """,
    "CREATE TRIGGER core_gcc_guard BEFORE UPDATE OR DELETE ON core_guardiancontactconsent "
    "FOR EACH ROW EXECUTE FUNCTION core_gcc_guard();",
    f"""
    CREATE OR REPLACE FUNCTION core_nt_guard() RETURNS trigger AS $$
    BEGIN
        IF TG_OP = 'DELETE' THEN {_raise(TEMPLATE_DELETE)} END IF;
        IF {_changed(TEMPLATE_FIXED, 'IS DISTINCT FROM')} OR ({UNAPPROVE}) THEN
            {_raise(TEMPLATE)}
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """,
    "CREATE TRIGGER core_nt_guard BEFORE UPDATE OR DELETE ON core_notificationtemplate "
    "FOR EACH ROW EXECUTE FUNCTION core_nt_guard();",
    f"""
    CREATE OR REPLACE FUNCTION core_n_guard() RETURNS trigger AS $$
    BEGIN
        IF TG_OP = 'DELETE' THEN {_raise(NOTIFICATION)} END IF;
        IF {_changed(NOTIFICATION_FIXED, 'IS DISTINCT FROM')} THEN {_raise(NOTIFICATION)} END IF;
        IF NOT ({TRANSITION}) THEN {_raise(STATUS)} END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """,
    "CREATE TRIGGER core_n_guard BEFORE UPDATE OR DELETE ON core_notification "
    "FOR EACH ROW EXECUTE FUNCTION core_n_guard();",
]
POSTGRES_REVERSE = [
    "DROP TRIGGER IF EXISTS core_gcc_guard ON core_guardiancontactconsent;",
    "DROP FUNCTION IF EXISTS core_gcc_guard();",
    "DROP TRIGGER IF EXISTS core_nt_guard ON core_notificationtemplate;",
    "DROP FUNCTION IF EXISTS core_nt_guard();",
    "DROP TRIGGER IF EXISTS core_n_guard ON core_notification;",
    "DROP FUNCTION IF EXISTS core_n_guard();",
]


def forwards(apps, schema_editor):
    pg = schema_editor.connection.vendor == "postgresql"
    for statement in POSTGRES if pg else SQLITE:
        schema_editor.execute(statement)


def backwards(apps, schema_editor):
    pg = schema_editor.connection.vendor == "postgresql"
    for statement in POSTGRES_REVERSE if pg else SQLITE_REVERSE:
        schema_editor.execute(statement)


class Migration(migrations.Migration):
    dependencies = [("core", "0056_phase7_notifications")]

    operations = [migrations.RunPython(forwards, backwards)]
