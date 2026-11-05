# ADR 0023: record corrections are history.
#
# No DELETE and no UPDATE, ever: the record of who changed a child's details, and
# what the old values were, must not be rewritable.

from django.db import migrations

MESSAGE = "Record corrections cannot be changed or deleted."

SQLITE = [
    f"CREATE TRIGGER core_recordcorrection_no_delete BEFORE DELETE ON core_recordcorrection "
    f"BEGIN SELECT RAISE(ABORT, '{MESSAGE}'); END;",
    f"CREATE TRIGGER core_recordcorrection_no_update BEFORE UPDATE ON core_recordcorrection "
    f"BEGIN SELECT RAISE(ABORT, '{MESSAGE}'); END;",
]
SQLITE_REVERSE = [
    "DROP TRIGGER IF EXISTS core_recordcorrection_no_delete;",
    "DROP TRIGGER IF EXISTS core_recordcorrection_no_update;",
]

POSTGRES = [
    f"""
    CREATE OR REPLACE FUNCTION core_recordcorrection_guard() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION USING ERRCODE = 'integrity_constraint_violation',
            MESSAGE = '{MESSAGE}';
    END;
    $$ LANGUAGE plpgsql;
    """,
    "CREATE TRIGGER core_recordcorrection_guard BEFORE UPDATE OR DELETE ON core_recordcorrection "
    "FOR EACH ROW EXECUTE FUNCTION core_recordcorrection_guard();",
]
POSTGRES_REVERSE = [
    "DROP TRIGGER IF EXISTS core_recordcorrection_guard ON core_recordcorrection;",
    "DROP FUNCTION IF EXISTS core_recordcorrection_guard();",
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
    dependencies = [("core", "0088_recordcorrection")]

    operations = [migrations.RunPython(forwards, backwards)]
