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
    "root:home": "login required; redirects each login to its own area and shows no data",
    "root:choose-area": "login required; lists only the areas the login itself holds",
    "root:pwa-install": "login required; static install instructions",
    "root:pwa-manifest": "public by design: the web app manifest is fetched before sign-in and holds no school data",
}
# Django-owned routes (admin, stock sign-in/out/password views) are listed with a reason in
# route_inventory.FRAMEWORK_OWNED and flagged `framework_owned`.
SCOPED_BY_OTHER_MEANS = {"teacher_required", "guardian_required", "framework_owned"}

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

    def test_the_root_application_routes_are_covered(self):
        root = {name for name in self.current if name.startswith("root:")}
        self.assertEqual(root, {
            "root:admin", "root:choose-area", "root:home", "root:login", "root:logout",
            "root:password_change", "root:pwa-install", "root:pwa-manifest",
        })
        for name in ("root:admin", "root:login", "root:logout", "root:password_change"):
            self.assertIn("framework_owned", self.current[name]["flags"], name)
        self.assertEqual(self.current["root:home"]["view"], "core_views.home")

    def test_the_inventory_matches_the_live_url_resolver(self):
        """What Django actually routes equals what the source scan found, name for name."""
        from django.urls import URLPattern, URLResolver, get_resolver

        live = set()
        for pattern in get_resolver().url_patterns:
            if isinstance(pattern, URLPattern):
                live.add(f"root:{pattern.name}")
            elif isinstance(pattern, URLResolver) and pattern.namespace == "admin":
                live.add("root:admin")
            elif isinstance(pattern, URLResolver) and pattern.namespace in ("core", "portal"):
                live |= {f"{pattern.namespace}:{p.name}" for p in pattern.url_patterns}
            else:
                self.fail(f"The URL table has a route the inventory does not know: {pattern}")
        self.assertEqual(live, set(self.current))

    def test_unsupported_route_forms_fail_instead_of_being_skipped(self):
        cases = {
            "an imported function": (
                "from core.views import student_list\n"
                "urlpatterns = [path('x/', student_list, name='x')]\n", "not `module.function`"),
            "a class-based view": (
                "from core import views\n"
                "urlpatterns = [path('x/', views.Thing.as_view(), name='x')]\n",
                "a view form the inventory does not read"),
            "an unknown include": (
                "urlpatterns = [path('x/', include('other.urls'))]\n", "does not scan"),
            "a computed include": (
                "urlpatterns = [path('x/', include(some_urls))]\n", "does not scan"),
            "a re_path route": (
                "urlpatterns = [re_path(r'^x/$', views.f, name='x')]\n", "re_path() routes"),
            "a route without a name": (
                "from core import views\n"
                "urlpatterns = [path('x/', views.student_list)]\n", "no literal name="),
            "a view that is not in its module": (
                "from core import views\n"
                "urlpatterns = [path('x/', views.no_such_view_anywhere, name='x')]\n",
                "was not found"),
            "an unknown module alias": (
                "urlpatterns = [path('x/', mystery.view, name='x')]\n", "is not a project module"),
        }
        for label, (source, expected) in cases.items():
            with self.subTest(label):
                with self.assertRaises(route_inventory.InventoryError) as raised:
                    route_inventory.scan_urlconf(source, "test")
                self.assertIn(expected, str(raised.exception))

    def test_a_framework_owned_route_is_allowed_only_from_the_allowlist(self):
        ok = route_inventory.scan_urlconf(
            "urlpatterns = [path('admin/', admin.site.urls)]\n", "test")
        self.assertEqual(ok["test:admin"]["flags"], ["framework_owned"])
        with self.assertRaises(route_inventory.InventoryError):
            route_inventory.scan_urlconf(
                "urlpatterns = [path('other/', other.site.urls, name='other')]\n", "test")

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
