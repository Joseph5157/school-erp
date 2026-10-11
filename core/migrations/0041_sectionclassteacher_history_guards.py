# Phase 5 Gate 8 (ADR 0011 D3): database-level protection of class teacher
# assignment history.
#
# - An assignment is never rewritten: teacher, Section, Academic Year and
#   start date cannot change (a change of class teacher ends the row and
#   starts a new one).
# - An assignment with dependent attendance (registers the teacher submitted
#   for that Section inside its range) cannot be deleted, and cannot be
#   ended before the last such register.
#
# The clock-dependent rule ("rows that have taken effect are ended, never
# deleted") stays in the application layer (SectionClassTeacher.delete and
# its QuerySet), because a database trigger has no school-local business
# date that tests and the application agree on.

from django.db import migrations

REWRITE = "A class teacher assignment cannot be rewritten; end it and start a new one."
DELETE = "This class teacher assignment has dependent attendance; end it instead of deleting it."
CUT = "This teacher submitted attendance for this Section after that end date."


def _dependents(alias, after=None):
    upper = (
        f"COALESCE({alias}.end_date, (SELECT y.end_date FROM core_academicyear y "
        f"WHERE y.id = {alias}.academic_year_id))"
    )
    extra = f" AND r.date > {after}" if after else ""
    return (
        "EXISTS (SELECT 1 FROM core_attendanceregister r "
        f"WHERE r.section_id = {alias}.section_id AND r.submitted_by_id = {alias}.teacher_id "
        f"AND r.date >= {alias}.start_date AND r.date <= {upper}{extra})"
    )


SQLITE = [
    f"""
    CREATE TRIGGER core_sct_no_rewrite BEFORE UPDATE ON core_sectionclassteacher
    WHEN NEW.teacher_id <> OLD.teacher_id OR NEW.section_id <> OLD.section_id
      OR NEW.academic_year_id <> OLD.academic_year_id OR NEW.start_date <> OLD.start_date
    BEGIN SELECT RAISE(ABORT, '{REWRITE}'); END;
    """,
    f"""
    CREATE TRIGGER core_sct_no_cut BEFORE UPDATE ON core_sectionclassteacher
    WHEN NEW.end_date IS NOT NULL AND {_dependents("OLD", after="NEW.end_date")}
    BEGIN SELECT RAISE(ABORT, '{CUT}'); END;
    """,
    f"""
    CREATE TRIGGER core_sct_no_delete BEFORE DELETE ON core_sectionclassteacher
    WHEN {_dependents("OLD")}
    BEGIN SELECT RAISE(ABORT, '{DELETE}'); END;
    """,
]
SQLITE_REVERSE = [
    "DROP TRIGGER IF EXISTS core_sct_no_rewrite;",
    "DROP TRIGGER IF EXISTS core_sct_no_cut;",
    "DROP TRIGGER IF EXISTS core_sct_no_delete;",
]

POSTGRES = [
    f"""
    CREATE OR REPLACE FUNCTION core_sct_guard() RETURNS trigger AS $$
    BEGIN
        IF TG_OP = 'UPDATE' THEN
            IF NEW.teacher_id <> OLD.teacher_id OR NEW.section_id <> OLD.section_id
               OR NEW.academic_year_id <> OLD.academic_year_id
               OR NEW.start_date <> OLD.start_date THEN
                RAISE EXCEPTION USING ERRCODE = 'integrity_constraint_violation',
                    MESSAGE = '{REWRITE}';
            END IF;
            IF NEW.end_date IS NOT NULL AND {_dependents("OLD", after="NEW.end_date")} THEN
                RAISE EXCEPTION USING ERRCODE = 'integrity_constraint_violation',
                    MESSAGE = '{CUT}';
            END IF;
            RETURN NEW;
        END IF;
        IF {_dependents("OLD")} THEN
            RAISE EXCEPTION USING ERRCODE = 'integrity_constraint_violation',
                MESSAGE = '{DELETE}';
        END IF;
        RETURN OLD;
    END;
    $$ LANGUAGE plpgsql;
    """,
    """
    CREATE TRIGGER core_sct_guard BEFORE UPDATE OR DELETE ON core_sectionclassteacher
    FOR EACH ROW EXECUTE FUNCTION core_sct_guard();
    """,
]
POSTGRES_REVERSE = [
    "DROP TRIGGER IF EXISTS core_sct_guard ON core_sectionclassteacher;",
    "DROP FUNCTION IF EXISTS core_sct_guard();",
]


def forwards(apps, schema_editor):
    statements = POSTGRES if schema_editor.connection.vendor == "postgresql" else SQLITE
    for statement in statements:
        schema_editor.execute(statement)


def backwards(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    for statement in POSTGRES_REVERSE if vendor == "postgresql" else SQLITE_REVERSE:
        schema_editor.execute(statement)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0040_add_class_teacher_permissions_to_group"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
