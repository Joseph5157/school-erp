# Phase 6 Gate 1 (ADR 0013): guardian account links and Student access grants
# are revoked, never deleted or rewritten.
#
# - No DELETE.
# - Who/what a row links, how it was verified and who created it are
#   immutable.
# - A revocation can be recorded once; once set, the revocation columns can
#   never change again (so a revocation cannot be cleared or rewritten).
#
# Triggers never consult the clock.

from django.db import migrations

DELETE = "Guardian access history is never deleted; revoke it instead."
REWRITE = "Guardian access history cannot be rewritten."
REVOKED = "A revocation is final; create a new link or grant instead."

TABLES = {
    "core_guardianaccount": {
        "prefix": "core_ga",
        "immutable": [
            "user_id", "guardian_id", "identity_verified_by_id",
            "identity_verification_method", "identity_verification_note",
            "created_by_id", "created_at",
        ],
    },
    "core_guardianstudentaccess": {
        "prefix": "core_gsa",
        "immutable": ["student_guardian_id", "public_id", "granted_by_id", "granted_at"],
    },
}
REVOCATION = ["revoked_at", "revoked_by_id", "revocation_reason"]


def _changed(columns, vendor):
    op = "IS NOT" if vendor == "sqlite" else "IS DISTINCT FROM"
    return " OR ".join(f"NEW.{c} {op} OLD.{c}" for c in columns)


def _sqlite(table, spec):
    p = spec["prefix"]
    return [
        f"CREATE TRIGGER {p}_no_delete BEFORE DELETE ON {table} "
        f"BEGIN SELECT RAISE(ABORT, '{DELETE}'); END;",
        f"CREATE TRIGGER {p}_no_rewrite BEFORE UPDATE ON {table} "
        f"WHEN {_changed(spec['immutable'], 'sqlite')} "
        f"BEGIN SELECT RAISE(ABORT, '{REWRITE}'); END;",
        f"CREATE TRIGGER {p}_revocation_final BEFORE UPDATE ON {table} "
        f"WHEN OLD.revoked_at IS NOT NULL AND ({_changed(REVOCATION, 'sqlite')}) "
        f"BEGIN SELECT RAISE(ABORT, '{REVOKED}'); END;",
    ]


def _sqlite_reverse(table, spec):
    p = spec["prefix"]
    return [f"DROP TRIGGER IF EXISTS {p}_{name};"
            for name in ("no_delete", "no_rewrite", "revocation_final")]


def _postgres(table, spec):
    p = spec["prefix"]
    return [
        f"""
        CREATE OR REPLACE FUNCTION {p}_guard() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION USING ERRCODE = 'integrity_constraint_violation',
                    MESSAGE = '{DELETE}';
            END IF;
            IF {_changed(spec['immutable'], 'postgresql')} THEN
                RAISE EXCEPTION USING ERRCODE = 'integrity_constraint_violation',
                    MESSAGE = '{REWRITE}';
            END IF;
            IF OLD.revoked_at IS NOT NULL AND ({_changed(REVOCATION, 'postgresql')}) THEN
                RAISE EXCEPTION USING ERRCODE = 'integrity_constraint_violation',
                    MESSAGE = '{REVOKED}';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """,
        f"CREATE TRIGGER {p}_guard BEFORE UPDATE OR DELETE ON {table} "
        f"FOR EACH ROW EXECUTE FUNCTION {p}_guard();",
    ]


def _postgres_reverse(table, spec):
    p = spec["prefix"]
    return [f"DROP TRIGGER IF EXISTS {p}_guard ON {table};", f"DROP FUNCTION IF EXISTS {p}_guard();"]


def forwards(apps, schema_editor):
    pg = schema_editor.connection.vendor == "postgresql"
    for table, spec in TABLES.items():
        for statement in (_postgres if pg else _sqlite)(table, spec):
            schema_editor.execute(statement)


def backwards(apps, schema_editor):
    pg = schema_editor.connection.vendor == "postgresql"
    for table, spec in TABLES.items():
        for statement in (_postgres_reverse if pg else _sqlite_reverse)(table, spec):
            schema_editor.execute(statement)


class Migration(migrations.Migration):
    dependencies = [("core", "0043_add_guardian_account_permissions_to_group")]

    operations = [migrations.RunPython(forwards, backwards)]
