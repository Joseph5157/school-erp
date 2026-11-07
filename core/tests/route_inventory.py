"""Source-level map of every route to the permission its view enforces (Security Gate 4B).

`build_inventory()` reads the root URLconf (`config/urls.py`) and the two URLconfs it includes
(`core/urls.py`, `core/portal_urls.py`), then each view function's decorators and in-body
permission checks, with `ast`; it imports no project code and needs no database. The result is
pinned in `route_permissions.json`, so a route whose permission changes, or a new route, shows up
as a failing test and a reviewed diff instead of a silent change.

The scan is strict. A route form it does not understand (an imported function, a class-based
view, an unknown `include()`, `re_path`, a route without a name, a view that is not a plain
function) raises `InventoryError` instead of being skipped, so a new kind of route cannot be
added without changing this tool in a reviewed diff. Routes owned by Django itself (the admin and
the stock login/logout/password views) are listed in `FRAMEWORK_OWNED` with the reason they are
not scanned.

After a deliberate, reviewed change, refresh the pin with:

    python core/tests/route_inventory.py --write
"""

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INVENTORY_FILE = Path(__file__).with_name("route_permissions.json")
# (file, namespace). The root URLconf comes first; it is the only one that may `include()`.
URL_FILES = (
    ("config/urls.py", "root"),
    ("core/urls.py", "core"),
    ("core/portal_urls.py", "portal"),
)
# The only `include()` targets that are understood, because they are scanned above.
KNOWN_INCLUDES = {"core.portal_urls", "core.urls"}
DATA_ACCESS = ROOT / "core" / "data_access.py"

# Routes owned by Django, not scanned for permissions. Each needs a stated reason; adding one is
# a reviewed decision. Keyed by the callable as written in the URLconf.
FRAMEWORK_OWNED = {
    "admin.site.urls": "Django admin: its own login and per-model permissions",
    "auth_views.LoginView.as_view": "Django sign-in view; reachable without a login by design",
    "auth_views.LogoutView.as_view": "Django sign-out view; POST only",
}
# Module-level names that are not a plain function but are known, with the reason.
KNOWN_NON_FUNCTION_VIEWS = {
    "account_views.password_change": "Django PasswordChangeView, which requires a login",
}


class InventoryError(Exception):
    """A route the inventory cannot read. Fix the tool or the route; never skip it."""


def _string_constants(tree):
    found = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
            and isinstance(node.targets[0], ast.Name)
        ):
            found[node.targets[0].id] = node.value.value
    return found


def _resolve(node, local, shared):
    """A permission string from a literal, a module constant or `data_access.NAME`."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return local.get(node.id, f"<{node.id}>")
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        if node.value.id == "data_access":
            return shared.get(node.attr, f"<data_access.{node.attr}>")
    if isinstance(node, (ast.Tuple, ast.List)):
        return "+".join(_resolve(item, local, shared) for item in node.elts)
    return "<dynamic>"


def _decorators(function, local, shared):
    perms, flags = [], []
    for decorator in function.decorator_list:
        if isinstance(decorator, ast.Call):
            name = getattr(decorator.func, "id", getattr(decorator.func, "attr", "?"))
            if name == "administrator_required":
                perms.append(_resolve(decorator.args[0], local, shared))
            else:
                flags.append(name)
        elif isinstance(decorator, ast.Name) and decorator.id != "login_required":
            flags.append(decorator.id)
    return sorted(perms), sorted(set(flags))


def _inner_permissions(function, local, shared):
    found = set()
    for node in ast.walk(function):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") in ("has_perm", "has_perms"):
            if node.args:
                found.add(_resolve(node.args[0], local, shared))
    return sorted(found)


def _project_modules(tree):
    """alias -> source file, for `from core import views as v` style imports of project modules."""
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                path = ROOT.joinpath(*node.module.split("."), f"{alias.name}.py")
                if path.exists():
                    found[alias.asname or alias.name] = path
    return found


def _load_module(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    assigned = {
        t.id for n in tree.body if isinstance(n, ast.Assign)
        for t in n.targets if isinstance(t, ast.Name)
    }
    return functions, assigned, _string_constants(tree)


def _include_target(call):
    if not call.args:
        return "<none>"
    first = call.args[0]
    return first.value if isinstance(first, ast.Constant) else ast.unparse(first)


def scan_urlconf(source, namespace, *, relative="<source>", loader=_load_module, shared=None):
    """The inventory entries of one URLconf's source text. Raises InventoryError on anything odd."""
    shared = shared or {}
    tree = ast.parse(source)
    project = _project_modules(tree)
    cache = {}
    entries = {}
    where = f"{relative}:{namespace}"

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = ast.unparse(node.func)
        if callee in ("re_path", "url"):
            raise InventoryError(f"{where}: {callee}() routes are not supported by the inventory")
        if callee != "path":
            continue
        if len(node.args) < 2:
            raise InventoryError(f"{where}: path() with fewer than two positional arguments")
        route = ast.unparse(node.args[0]).strip("'\"")
        target = node.args[1]

        if isinstance(target, ast.Call) and ast.unparse(target.func) == "include":
            included = _include_target(target)
            if included not in KNOWN_INCLUDES:
                raise InventoryError(
                    f"{where}: route {route!r} includes {included!r}, which the inventory does "
                    "not scan. Add it to URL_FILES and KNOWN_INCLUDES in a reviewed change."
                )
            continue

        name = next((k.value.value for k in node.keywords
                     if k.arg == "name" and isinstance(k.value, ast.Constant)), None)
        callable_text = ast.unparse(target.func if isinstance(target, ast.Call) else target)

        if callable_text in FRAMEWORK_OWNED:
            name = name or route.strip("/").replace("/", "-") or "root"
            entries[f"{namespace}:{name}"] = {
                "route": route, "view": callable_text, "perms": [], "inner": [],
                "flags": ["framework_owned"],
            }
            continue

        if not name:
            raise InventoryError(f"{where}: route {route!r} has no literal name=")
        if isinstance(target, ast.Call):
            raise InventoryError(
                f"{where}: route {route!r} uses {callable_text}(...), a view form the inventory "
                "does not read. Use a function view, or list it in FRAMEWORK_OWNED with a reason."
            )
        if not (isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)):
            raise InventoryError(
                f"{where}: route {route!r} uses {callable_text!r}, which is not "
                "`module.function`. An imported or nested callback is not scanned."
            )
        alias, function_name = target.value.id, target.attr
        if alias not in project:
            raise InventoryError(
                f"{where}: route {route!r} uses {callable_text!r} but {alias!r} is not a "
                "project module imported with `from <package> import <module>`."
            )
        if alias not in cache:
            cache[alias] = loader(project[alias])
        functions, assigned, local = cache[alias]
        function = functions.get(function_name)
        entry = {"route": route, "view": callable_text}
        if function is not None:
            perms, flags = _decorators(function, local, shared)
            entry.update(perms=perms, inner=_inner_permissions(function, local, shared),
                         flags=flags)
        elif callable_text in KNOWN_NON_FUNCTION_VIEWS:
            entry.update(perms=[], inner=[], flags=["framework_owned"])
        else:
            kind = "is not a plain function" if function_name in assigned else "was not found"
            raise InventoryError(
                f"{where}: route {route!r} view {callable_text!r} {kind} in "
                f"{project[alias].relative_to(ROOT)}."
            )
        entries[f"{namespace}:{name}"] = entry
    return entries


def build_inventory():
    shared = _string_constants(ast.parse(DATA_ACCESS.read_text(encoding="utf-8"))) \
        if DATA_ACCESS.exists() else {}
    inventory = {}
    for relative, namespace in URL_FILES:
        source = (ROOT / relative).read_text(encoding="utf-8")
        for key, entry in scan_urlconf(
            source, namespace, relative=relative, shared=shared
        ).items():
            if key in inventory:
                raise InventoryError(f"{key} is defined twice")
            inventory[key] = entry
    return dict(sorted(inventory.items()))


def write_inventory():
    INVENTORY_FILE.write_text(
        json.dumps(build_inventory(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    if "--write" in sys.argv:
        write_inventory()
        print(f"Wrote {INVENTORY_FILE.relative_to(ROOT)} ({len(build_inventory())} routes)")
    else:
        print(json.dumps(build_inventory(), indent=2, sort_keys=True))
