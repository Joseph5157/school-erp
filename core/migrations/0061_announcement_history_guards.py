# Phase 7 Gate 3 (ADR 0015): announcements are history.
#
# No DELETE. Published content never changes. The withdrawal fields may be
# set once (from empty) and never changed or cleared afterwards.

from django.db import migrations

MESSAGE = "Announcements cannot be deleted or rewritten."
FIXED = [
    "public_id", "title", "body", "audience", "class_grade_id", "section_id",
    "published_by_id", "published_at",
]
WITHDRAWAL = ["withdrawn_at", "withdrawn_by_id", "withdrawal_reason"]


def _changed(columns, op):
    return " OR ".join(f"NEW.{c} {op} OLD.{c}" for c in columns)


SQLITE = [
    f"CREATE TRIGGER core_ann_no_delete BEFORE DELETE ON core_announcement "
    f"BEGIN SELECT RAISE(ABORT, '{MESSAGE}'); END;",
    f"CREATE TRIGGER core_ann_fixed BEFORE UPDATE ON core_announcement "
    f"WHEN {_changed(FIXED, 'IS NOT')} "
    f"OR (OLD.withdrawn_at IS NOT NULL AND ({_changed(WITHDRAWAL, 'IS NOT')})) "
    f"BEGIN SELECT RAISE(ABORT, '{MESSAGE}'); END;",
]
SQLITE_REVERSE = [
    "DROP TRIGGER IF EXISTS core_ann_no_delete;",
    "DROP TRIGGER IF EXISTS core_ann_fixed;",
]

POSTGRES = [
    f"""
    CREATE OR REPLACE FUNCTION core_ann_guard() RETURNS trigger AS $$
    BEGIN
        IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION USING ERRCODE = 'integrity_constraint_violation',
                MESSAGE = '{MESSAGE}';
        END IF;
        IF {_changed(FIXED, 'IS DISTINCT FROM')}
           OR (OLD.withdrawn_at IS NOT NULL AND ({_changed(WITHDRAWAL, 'IS DISTINCT FROM')}))
        THEN
            RAISE EXCEPTION USING ERRCODE = 'integrity_constraint_violation',
                MESSAGE = '{MESSAGE}';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """,
    "CREATE TRIGGER core_ann_guard BEFORE UPDATE OR DELETE ON core_announcement "
    "FOR EACH ROW EXECUTE FUNCTION core_ann_guard();",
]
POSTGRES_REVERSE = [
    "DROP TRIGGER IF EXISTS core_ann_guard ON core_announcement;",
    "DROP FUNCTION IF EXISTS core_ann_guard();",
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
    dependencies = [("core", "0060_announcements")]

    operations = [migrations.RunPython(forwards, backwards)]
