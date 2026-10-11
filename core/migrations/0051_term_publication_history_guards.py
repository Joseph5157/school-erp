# Phase 6 Gate 6 (ADR 0014): every Term publication version and its snapshot
# is permanent history.
#
# - TermPublication: no DELETE; every column except the status fields is
#   immutable; status only moves PUBLISHED -> STALE/SUPERSEDED/WITHDRAWN and
#   STALE -> SUPERSEDED/WITHDRAWN; nothing changes once SUPERSEDED/WITHDRAWN.
# - TermPublicationEntry: no UPDATE, no DELETE.

from django.db import migrations

DELETE = "Publication history is never deleted."
REWRITE = "A released publication cannot be rewritten."
STATUS = "That publication status change is not allowed."
ENTRY = "Released report-card entries cannot be changed or deleted."

IMMUTABLE = [
    "public_id", "student_id", "term_id", "placement_id", "version", "is_partial",
    "pending_assessments", "term_label", "academic_year_label", "class_grade_label",
    "section_label", "remark_id_ref", "remark_text", "fingerprint", "fingerprint_scheme",
    "published_by_id", "published_at",
]
STATUS_FIELDS = ["status", "status_changed_at", "status_changed_by_id", "status_reason"]
ALLOWED = (
    "(OLD.status = 'PUBLISHED' AND NEW.status IN ('STALE', 'SUPERSEDED', 'WITHDRAWN')) "
    "OR (OLD.status = 'STALE' AND NEW.status IN ('SUPERSEDED', 'WITHDRAWN'))"
)


def _changed(columns, op):
    return " OR ".join(f"NEW.{c} {op} OLD.{c}" for c in columns)


SQLITE = [
    f"CREATE TRIGGER core_tp_no_delete BEFORE DELETE ON core_termpublication "
    f"BEGIN SELECT RAISE(ABORT, '{DELETE}'); END;",
    f"CREATE TRIGGER core_tp_no_rewrite BEFORE UPDATE ON core_termpublication "
    f"WHEN {_changed(IMMUTABLE, 'IS NOT')} BEGIN SELECT RAISE(ABORT, '{REWRITE}'); END;",
    f"CREATE TRIGGER core_tp_status BEFORE UPDATE ON core_termpublication "
    f"WHEN NEW.status <> OLD.status AND NOT ({ALLOWED}) "
    f"BEGIN SELECT RAISE(ABORT, '{STATUS}'); END;",
    f"CREATE TRIGGER core_tp_final BEFORE UPDATE ON core_termpublication "
    f"WHEN OLD.status IN ('SUPERSEDED', 'WITHDRAWN') AND ({_changed(STATUS_FIELDS, 'IS NOT')}) "
    f"BEGIN SELECT RAISE(ABORT, '{STATUS}'); END;",
    f"CREATE TRIGGER core_tpe_no_update BEFORE UPDATE ON core_termpublicationentry "
    f"BEGIN SELECT RAISE(ABORT, '{ENTRY}'); END;",
    f"CREATE TRIGGER core_tpe_no_delete BEFORE DELETE ON core_termpublicationentry "
    f"BEGIN SELECT RAISE(ABORT, '{ENTRY}'); END;",
]
SQLITE_REVERSE = [
    f"DROP TRIGGER IF EXISTS {name};"
    for name in ("core_tp_no_delete", "core_tp_no_rewrite", "core_tp_status", "core_tp_final",
                 "core_tpe_no_update", "core_tpe_no_delete")
]
POSTGRES = [
    f"""
    CREATE OR REPLACE FUNCTION core_tp_guard() RETURNS trigger AS $$
    BEGIN
        IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION USING ERRCODE = 'integrity_constraint_violation', MESSAGE = '{DELETE}';
        END IF;
        IF {_changed(IMMUTABLE, 'IS DISTINCT FROM')} THEN
            RAISE EXCEPTION USING ERRCODE = 'integrity_constraint_violation', MESSAGE = '{REWRITE}';
        END IF;
        IF NEW.status <> OLD.status AND NOT ({ALLOWED}) THEN
            RAISE EXCEPTION USING ERRCODE = 'integrity_constraint_violation', MESSAGE = '{STATUS}';
        END IF;
        IF OLD.status IN ('SUPERSEDED', 'WITHDRAWN')
           AND ({_changed(STATUS_FIELDS, 'IS DISTINCT FROM')}) THEN
            RAISE EXCEPTION USING ERRCODE = 'integrity_constraint_violation', MESSAGE = '{STATUS}';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """,
    "CREATE TRIGGER core_tp_guard BEFORE UPDATE OR DELETE ON core_termpublication "
    "FOR EACH ROW EXECUTE FUNCTION core_tp_guard();",
    f"""
    CREATE OR REPLACE FUNCTION core_tpe_guard() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION USING ERRCODE = 'integrity_constraint_violation', MESSAGE = '{ENTRY}';
    END;
    $$ LANGUAGE plpgsql;
    """,
    "CREATE TRIGGER core_tpe_guard BEFORE UPDATE OR DELETE ON core_termpublicationentry "
    "FOR EACH ROW EXECUTE FUNCTION core_tpe_guard();",
]
POSTGRES_REVERSE = [
    "DROP TRIGGER IF EXISTS core_tp_guard ON core_termpublication;",
    "DROP FUNCTION IF EXISTS core_tp_guard();",
    "DROP TRIGGER IF EXISTS core_tpe_guard ON core_termpublicationentry;",
    "DROP FUNCTION IF EXISTS core_tpe_guard();",
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
    dependencies = [("core", "0050_add_term_publication_permissions_to_group")]

    operations = [migrations.RunPython(forwards, backwards)]
