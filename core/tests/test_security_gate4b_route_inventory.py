"""Security Gate 4B: the route-permission inventory guard.

Every route's enforced permission is pinned in `route_permissions.json`. A change to a route's
permission, a new route, or a removed one fails here until the pin is refreshed in a reviewed
change (`python core/tests/route_inventory.py --write`). No route may become public by accident.
"""

import json

from django.test import SimpleTestCase

from core.tests import route_inventory

# Routes that are intentionally reachable without a permission decorator, and why.
INTENTIONALLY_UNPERMISSIONED = {
    "core:school-logo": "shown on the sign-in page before anyone is signed in",
    "core:term-remarks": "class teachers write remarks; the view checks change_termremark or the class-teacher scope",
}
SCOPED_BY_OTHER_MEANS = {"teacher_required", "guardian_required"}

# Pages that embed another class of data must declare its permission in the view body.
DECLARED_DATA_PERMISSIONS = {
    "core:student-list": {"core.view_guardian", "core.view_attendanceentry"},
    "core:student-detail": {"core.view_guardian", "core.view_attendanceentry",
                            "core.view_studentresult"},
    "core:applicant-detail": {"core.view_guardian"},
    "core:guardian-list": {"core.view_student", "core.view_applicant"},
    "core:attendance-register-detail": {"core.view_attendanceentry"},
    "core:admin-overview": {"core.view_attendanceentry", "core.view_student"},
    "core:assessment-detail": {"core.view_studentresult"},
    "core:term-publication": {"core.view_studentresult"},
    "core:publication-detail": {"core.view_studentresult"},
    "core:import-detail": {"core.run_import"},
}


class RouteInventoryTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.current = route_inventory.build_inventory()
        cls.pinned = json.loads(route_inventory.INVENTORY_FILE.read_text(encoding="utf-8"))

    def test_the_inventory_covers_the_whole_url_table(self):
        self.assertGreaterEqual(len(self.current), 170)
        self.assertEqual(self.current["core:student-list"]["perms"], ["core.view_student"])
        self.assertEqual(self.current["core:teacher-list"]["perms"],
                         ["accounts.manage_teacher_accounts"])
        self.assertIn("require_POST", self.current["core:import-commit"]["flags"])
        self.assertIn("guardian_required", self.current["portal:home"]["flags"])

    def test_every_route_matches_the_pinned_inventory(self):
        problems = []
        for name in sorted(set(self.current) | set(self.pinned)):
            now, then = self.current.get(name), self.pinned.get(name)
            if then is None:
                problems.append(f"new route {name}: {now['perms']} {now['inner']}")
            elif now is None:
                problems.append(f"route removed: {name}")
            elif now != then:
                problems.append(f"{name} changed:\n    was {then}\n    now {now}")
        self.assertEqual(
            problems, [],
            "Route permissions changed. If this is intended, review the diff and refresh the "
            "pin with: python core/tests/route_inventory.py --write\n" + "\n".join(problems),
        )

    def test_no_route_is_public_by_accident(self):
        for name, entry in self.current.items():
            if entry["perms"] or SCOPED_BY_OTHER_MEANS & set(entry["flags"]):
                continue
            with self.subTest(route=name):
                self.assertIn(name, INTENTIONALLY_UNPERMISSIONED, entry)

    def test_the_gated_pages_declare_the_permissions_of_the_data_they_embed(self):
        for name, expected in DECLARED_DATA_PERMISSIONS.items():
            with self.subTest(route=name):
                self.assertTrue(
                    expected <= set(self.current[name]["inner"]),
                    f"{name} no longer checks {sorted(expected - set(self.current[name]['inner']))}",
                )
