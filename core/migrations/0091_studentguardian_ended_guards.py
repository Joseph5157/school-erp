# ADR 0024: an ended Student-Guardian relationship is history.
#
# Once ended_at is set the row can never change or be removed, so an ended
# relationship cannot quietly be brought back, bypassing the access it removed.
# Current relationships are not restricted here.

from django.db import migrations

MESSAGE = "Ended guardian relationships cannot be changed or deleted."

SQLITE = [
    f"CREATE TRIGGER core_studentguardian_ended_no_delete BEFORE DELETE ON core_studentguardian "
    f"WHEN OLD.ended_at IS NOT NULL BEGIN SELECT RAISE(ABORT, '{MESSAGE}'); END;",
    f"CREATE TRIGGER core_studentguardian_ended_no_update BEFORE UPDATE ON core_studentguardian "
    f"WHEN OLD.ended_at IS NOT NULL BEGIN SELECT RAISE(ABORT, '{MESSAGE}'); END;",
]
SQLITE_REVERSE = [
    "DROP TRIGGER IF EXISTS core_studentguardian_ended_no_delete;",
    "DROP TRIGGER IF EXISTS core_studentguardian_ended_no_update;",
]

POSTGRES = [
    f"""
    CREATE OR REPLACE FUNCTION core_studentguardian_ended_guard() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION USING ERRCODE = 'integrity_constraint_violation',
            MESSAGE = '{MESSAGE}';
    END;
    $$ LANGUAGE plpgsql;
    """,
    "CREATE TRIGGER core_studentguardian_ended_guard BEFORE UPDATE OR DELETE "
    "ON core_studentguardian FOR EACH ROW WHEN (OLD.ended_at IS NOT NULL) "
    "EXECUTE FUNCTION core_studentguardian_ended_guard();",
]
POSTGRES_REVERSE = [
    "DROP TRIGGER IF EXISTS core_studentguardian_ended_guard ON core_studentguardian;",
    "DROP FUNCTION IF EXISTS core_studentguardian_ended_guard();",
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
    dependencies = [("core", "0090_studentguardian_end")]

    operations = [migrations.RunPython(forwards, backwards)]
