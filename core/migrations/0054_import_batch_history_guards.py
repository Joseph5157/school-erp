# Phase 7 Gate 8 (ADR 0017): import batches and their row results are audit
# history.
#
# - ImportBatch: no DELETE; the upload facts are immutable; status only moves
#   VALIDATED -> COMMITTED/DISCARDED/EXPIRED/FAILED; nothing changes once a
#   batch has left VALIDATED (REJECTED batches are final from creation).
# - ImportRowResult: no UPDATE, no DELETE.

from django.db import migrations

DELETE = "Import history is never deleted."
REWRITE = "Import upload details cannot be rewritten."
STATUS = "That import status change is not allowed."
ROW = "Import row results cannot be changed or deleted."

IMMUTABLE = [
    "uploaded_by_id", "uploaded_at", "file_name", "file_sha256", "academic_year_id",
    "enrollment_start_date", "student_rows", "class_rows", "error_count", "warning_count",
]
ALLOWED = "OLD.status = 'VALIDATED' AND NEW.status IN ('COMMITTED', 'DISCARDED', 'EXPIRED', 'FAILED')"


def _changed(columns, op):
    return " OR ".join(f"NEW.{c} {op} OLD.{c}" for c in columns)


SQLITE = [
    f"CREATE TRIGGER core_ib_no_delete BEFORE DELETE ON core_importbatch "
    f"BEGIN SELECT RAISE(ABORT, '{DELETE}'); END;",
    f"CREATE TRIGGER core_ib_no_rewrite BEFORE UPDATE ON core_importbatch "
    f"WHEN {_changed(IMMUTABLE, 'IS NOT')} BEGIN SELECT RAISE(ABORT, '{REWRITE}'); END;",
    f"CREATE TRIGGER core_ib_status BEFORE UPDATE ON core_importbatch "
    f"WHEN NOT ({ALLOWED}) BEGIN SELECT RAISE(ABORT, '{STATUS}'); END;",
    f"CREATE TRIGGER core_irr_no_update BEFORE UPDATE ON core_importrowresult "
    f"BEGIN SELECT RAISE(ABORT, '{ROW}'); END;",
    f"CREATE TRIGGER core_irr_no_delete BEFORE DELETE ON core_importrowresult "
    f"BEGIN SELECT RAISE(ABORT, '{ROW}'); END;",
]
SQLITE_REVERSE = [
    f"DROP TRIGGER IF EXISTS {name};"
    for name in ("core_ib_no_delete", "core_ib_no_rewrite", "core_ib_status",
                 "core_irr_no_update", "core_irr_no_delete")
]
POSTGRES = [
    f"""
    CREATE OR REPLACE FUNCTION core_ib_guard() RETURNS trigger AS $$
    BEGIN
        IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION USING ERRCODE = 'integrity_constraint_violation', MESSAGE = '{DELETE}';
        END IF;
        IF {_changed(IMMUTABLE, 'IS DISTINCT FROM')} THEN
            RAISE EXCEPTION USING ERRCODE = 'integrity_constraint_violation', MESSAGE = '{REWRITE}';
        END IF;
        IF NOT ({ALLOWED}) THEN
            RAISE EXCEPTION USING ERRCODE = 'integrity_constraint_violation', MESSAGE = '{STATUS}';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """,
    "CREATE TRIGGER core_ib_guard BEFORE UPDATE OR DELETE ON core_importbatch "
    "FOR EACH ROW EXECUTE FUNCTION core_ib_guard();",
    f"""
    CREATE OR REPLACE FUNCTION core_irr_guard() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION USING ERRCODE = 'integrity_constraint_violation', MESSAGE = '{ROW}';
    END;
    $$ LANGUAGE plpgsql;
    """,
    "CREATE TRIGGER core_irr_guard BEFORE UPDATE OR DELETE ON core_importrowresult "
    "FOR EACH ROW EXECUTE FUNCTION core_irr_guard();",
]
POSTGRES_REVERSE = [
    "DROP TRIGGER IF EXISTS core_ib_guard ON core_importbatch;",
    "DROP FUNCTION IF EXISTS core_ib_guard();",
    "DROP TRIGGER IF EXISTS core_irr_guard ON core_importrowresult;",
    "DROP FUNCTION IF EXISTS core_irr_guard();",
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
    dependencies = [("core", "0053_phase7_import_batches")]

    operations = [migrations.RunPython(forwards, backwards)]
