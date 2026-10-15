# Phase 7 piece C: issued documents are history.
#
# No DELETE and no UPDATE, ever: a reprint renders from the stored payload,
# so the row must stay exactly as it was issued.

from django.db import migrations

MESSAGE = "Issued documents cannot be changed or deleted."

SQLITE = [
    f"CREATE TRIGGER core_issueddoc_no_delete BEFORE DELETE ON core_issueddocument "
    f"BEGIN SELECT RAISE(ABORT, '{MESSAGE}'); END;",
    f"CREATE TRIGGER core_issueddoc_no_update BEFORE UPDATE ON core_issueddocument "
    f"BEGIN SELECT RAISE(ABORT, '{MESSAGE}'); END;",
]
SQLITE_REVERSE = [
    "DROP TRIGGER IF EXISTS core_issueddoc_no_delete;",
    "DROP TRIGGER IF EXISTS core_issueddoc_no_update;",
]

POSTGRES = [
    f"""
    CREATE OR REPLACE FUNCTION core_issueddoc_guard() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION USING ERRCODE = 'integrity_constraint_violation',
            MESSAGE = '{MESSAGE}';
    END;
    $$ LANGUAGE plpgsql;
    """,
    "CREATE TRIGGER core_issueddoc_guard BEFORE UPDATE OR DELETE ON core_issueddocument "
    "FOR EACH ROW EXECUTE FUNCTION core_issueddoc_guard();",
]
POSTGRES_REVERSE = [
    "DROP TRIGGER IF EXISTS core_issueddoc_guard ON core_issueddocument;",
    "DROP FUNCTION IF EXISTS core_issueddoc_guard();",
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
    dependencies = [("core", "0064_issued_documents")]

    operations = [migrations.RunPython(forwards, backwards)]
