# Phase 6 Gate 2 (ADR 0013): access review decisions are immutable history.
# Database triggers refuse UPDATE and DELETE on SQLite and PostgreSQL.

from django.db import migrations

MESSAGE = "Guardian access review decisions are permanent and cannot be changed or deleted."

SQLITE = [
    f"CREATE TRIGGER core_gar_no_update BEFORE UPDATE ON core_guardianaccessreview "
    f"BEGIN SELECT RAISE(ABORT, '{MESSAGE}'); END;",
    f"CREATE TRIGGER core_gar_no_delete BEFORE DELETE ON core_guardianaccessreview "
    f"BEGIN SELECT RAISE(ABORT, '{MESSAGE}'); END;",
]
SQLITE_REVERSE = [
    "DROP TRIGGER IF EXISTS core_gar_no_update;",
    "DROP TRIGGER IF EXISTS core_gar_no_delete;",
]
POSTGRES = [
    f"""
    CREATE OR REPLACE FUNCTION core_gar_guard() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION USING ERRCODE = 'integrity_constraint_violation', MESSAGE = '{MESSAGE}';
    END;
    $$ LANGUAGE plpgsql;
    """,
    "CREATE TRIGGER core_gar_guard BEFORE UPDATE OR DELETE ON core_guardianaccessreview "
    "FOR EACH ROW EXECUTE FUNCTION core_gar_guard();",
]
POSTGRES_REVERSE = [
    "DROP TRIGGER IF EXISTS core_gar_guard ON core_guardianaccessreview;",
    "DROP FUNCTION IF EXISTS core_gar_guard();",
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
    dependencies = [("core", "0046_add_guardian_access_review_permissions_to_group")]

    operations = [migrations.RunPython(forwards, backwards)]
