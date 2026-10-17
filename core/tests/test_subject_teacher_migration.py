"""Migrations 0070-0072: backfill baseline and the guarded reverse (ADR 0018)."""

from datetime import date

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

BEFORE = [("core", "0069_studentguardian_permissions_to_group")]
AFTER = [("core", "0072_assessmentteacherassignment_effective_dating")]


class SubjectTeacherDatingMigrationTests(TransactionTestCase):
    def tearDown(self):
        # Clear rows made at the old schema, then leave the database fully migrated.
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        if AFTER[0] not in executor.loader.applied_migrations:
            apps = executor.loader.project_state(BEFORE).apps
            apps.get_model("core", "AssessmentTeacherAssignment").objects.all().delete()
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def _fixture_teardown(self):
        # Approved notification templates are guarded against deletion on SQLite;
        # lift that one guard for the flush, then put it back.
        if connection.vendor != "sqlite":
            return super()._fixture_teardown()
        with connection.cursor() as cursor:
            cursor.execute("DROP TRIGGER IF EXISTS core_nt_no_delete")
        try:
            super()._fixture_teardown()
        finally:
            with connection.cursor() as cursor:
                cursor.execute(
                    "CREATE TRIGGER core_nt_no_delete BEFORE DELETE ON core_notificationtemplate "
                    "BEGIN SELECT RAISE(ABORT, 'Notification templates are never deleted.'); END;"
                )

    def _migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def _seed_old_assignment(self, apps):
        Year = apps.get_model("core", "AcademicYear")
        Grade = apps.get_model("core", "ClassGrade")
        Section = apps.get_model("core", "Section")
        Subject = apps.get_model("core", "Subject")
        Offering = apps.get_model("core", "AcademicSubjectOffering")
        User = apps.get_model("accounts", "User")
        year = Year.objects.create(
            name="Legacy", start_date=date(2026, 6, 1), end_date=date(2027, 3, 31)
        )
        grade = Grade.objects.create(name="Legacy grade")
        section = Section.objects.create(class_grade=grade, name="A")
        offering = Offering.objects.create(
            academic_year=year, class_grade=grade, subject=Subject.objects.create(name="Maths")
        )
        teacher = User.objects.create(username="legacy-teacher")
        apps.get_model("core", "AssessmentTeacherAssignment").objects.create(
            teacher=teacher, offering=offering, section=section
        )
        return year, offering, section, teacher

    def test_backfill_starts_each_row_on_its_year_start_with_no_end(self):
        apps = self._migrate(BEFORE)
        year, *_ = self._seed_old_assignment(apps)
        apps = self._migrate(AFTER)
        row = apps.get_model("core", "AssessmentTeacherAssignment").objects.get()
        self.assertEqual(row.start_date, year.start_date)
        self.assertIsNone(row.end_date)

    def test_reverse_is_clean_without_history(self):
        apps = self._migrate(BEFORE)
        self._seed_old_assignment(apps)
        self._migrate(AFTER)
        apps = self._migrate(BEFORE)
        self.assertEqual(
            apps.get_model("core", "AssessmentTeacherAssignment").objects.count(), 1
        )

    def test_reverse_refuses_to_collapse_handover_history(self):
        apps = self._migrate(BEFORE)
        _, offering, section, teacher = self._seed_old_assignment(apps)
        apps = self._migrate(AFTER)
        Assignment = apps.get_model("core", "AssessmentTeacherAssignment")
        first = Assignment.objects.get()
        first.end_date = date(2026, 8, 31)
        first.save()
        Assignment.objects.create(
            teacher_id=teacher.pk, offering_id=offering.pk, section_id=section.pk,
            start_date=date(2026, 9, 1),
        )
        with self.assertRaisesMessage(RuntimeError, "Cannot reverse"):
            self._migrate(BEFORE)
        self.assertEqual(Assignment.objects.count(), 2)
