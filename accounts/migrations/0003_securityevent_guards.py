# Phase 6 Gate 1 (ADR 0013, OD-7): security events are append-only.
#
# - No UPDATE.
# - DELETE only for ROUTINE events older than 365 days (the authorized
#   retention purge). HISTORY events are never deleted. Both databases store
#   UTC; the 365-day margin makes the comparison insensitive to timezones.

from django.db import migrations

UPDATE = "Security events are append-only."
DELETE = "Only routine security events older than 365 days may be purged."

SQLITE = [
    f"CREATE TRIGGER acc_se_no_update BEFORE UPDATE ON accounts_securityevent "
    f"BEGIN SELECT RAISE(ABORT, '{UPDATE}'); END;",
    f"CREATE TRIGGER acc_se_retention BEFORE DELETE ON accounts_securityevent "
    f"WHEN OLD.event_class <> 'ROUTINE' OR OLD.occurred_at >= datetime('now', '-365 days') "
    f"BEGIN SELECT RAISE(ABORT, '{DELETE}'); END;",
]
SQLITE_REVERSE = [
    "DROP TRIGGER IF EXISTS acc_se_no_update;",
    "DROP TRIGGER IF EXISTS acc_se_retention;",
]
POSTGRES = [
    f"""
    CREATE OR REPLACE FUNCTION acc_se_guard() RETURNS trigger AS $$
    BEGIN
        IF TG_OP = 'UPDATE' THEN
            RAISE EXCEPTION USING ERRCODE = 'integrity_constraint_violation',
                MESSAGE = '{UPDATE}';
        END IF;
        IF OLD.event_class <> 'ROUTINE' OR OLD.occurred_at >= now() - interval '365 days' THEN
            RAISE EXCEPTION USING ERRCODE = 'integrity_constraint_violation',
                MESSAGE = '{DELETE}';
        END IF;
        RETURN OLD;
    END;
    $$ LANGUAGE plpgsql;
    """,
    "CREATE TRIGGER acc_se_guard BEFORE UPDATE OR DELETE ON accounts_securityevent "
    "FOR EACH ROW EXECUTE FUNCTION acc_se_guard();",
]
POSTGRES_REVERSE = [
    "DROP TRIGGER IF EXISTS acc_se_guard ON accounts_securityevent;",
    "DROP FUNCTION IF EXISTS acc_se_guard();",
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
    dependencies = [("accounts", "0002_phase6_user_security")]

    operations = [migrations.RunPython(forwards, backwards)]
