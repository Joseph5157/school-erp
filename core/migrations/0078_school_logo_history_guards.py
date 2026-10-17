# ADR 0020: school logo versions are history.
#
# No DELETE and no UPDATE, ever: a document issued with a logo version must be
# able to render that exact image later. Replacing or removing the logo adds a
# new row (a tombstone for removal).

from django.db import migrations

MESSAGE = "School logo versions cannot be changed or deleted."

SQLITE = [
    f"CREATE TRIGGER core_schoollogo_no_delete BEFORE DELETE ON core_schoollogo "
    f"BEGIN SELECT RAISE(ABORT, '{MESSAGE}'); END;",
    f"CREATE TRIGGER core_schoollogo_no_update BEFORE UPDATE ON core_schoollogo "
    f"BEGIN SELECT RAISE(ABORT, '{MESSAGE}'); END;",
]
SQLITE_REVERSE = [
    "DROP TRIGGER IF EXISTS core_schoollogo_no_delete;",
    "DROP TRIGGER IF EXISTS core_schoollogo_no_update;",
]

POSTGRES = [
    f"""
    CREATE OR REPLACE FUNCTION core_schoollogo_guard() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION USING ERRCODE = 'integrity_constraint_violation',
            MESSAGE = '{MESSAGE}';
    END;
    $$ LANGUAGE plpgsql;
    """,
    "CREATE TRIGGER core_schoollogo_guard BEFORE UPDATE OR DELETE ON core_schoollogo "
    "FOR EACH ROW EXECUTE FUNCTION core_schoollogo_guard();",
]
POSTGRES_REVERSE = [
    "DROP TRIGGER IF EXISTS core_schoollogo_guard ON core_schoollogo;",
    "DROP FUNCTION IF EXISTS core_schoollogo_guard();",
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
    dependencies = [("core", "0077_school_logo")]

    operations = [migrations.RunPython(forwards, backwards)]
