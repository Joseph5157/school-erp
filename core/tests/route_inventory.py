"""Source-level map of every route to the permission its view enforces (Security Gate 4B).

`build_inventory()` reads `core/urls.py` and `core/portal_urls.py` and each view function's
decorators and in-body permission checks with `ast`; it imports no project code and needs no
database. The result is pinned in `route_permissions.json`, so a route whose permission changes,
or a new route, shows up as a failing test and a reviewed diff instead of a silent change.

After a deliberate, reviewed change, refresh the pin with:

    python core/tests/route_inventory.py --write
"""

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INVENTORY_FILE = Path(__file__).with_name("route_permissions.json")
URL_FILES = (("core/urls.py", "core"), ("core/portal_urls.py", "portal"))
DATA_ACCESS = ROOT / "core" / "data_access.py"


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


def build_inventory():
    shared = _string_constants(ast.parse(DATA_ACCESS.read_text(encoding="utf-8"))) \
        if DATA_ACCESS.exists() else {}
    modules = {}

    def module(alias):
        if alias not in modules:
            tree = ast.parse((ROOT / "core" / f"{alias}.py").read_text(encoding="utf-8"))
            modules[alias] = (
                {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)},
                _string_constants(tree),
            )
        return modules[alias]

    inventory = {}
    for relative, namespace in URL_FILES:
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "path"):
                continue
            if len(node.args) < 2 or not isinstance(node.args[1], ast.Attribute):
                continue  # include(...) or something that is not a plain view function
            name = next(
                (k.value.value for k in node.keywords if k.arg == "name"), None
            )
            route = node.args[0].value
            alias, function_name = node.args[1].value.id, node.args[1].attr
            functions, local = module(alias)
            function = functions.get(function_name)
            entry = {"route": route, "view": f"{alias}.{function_name}"}
            if function is None:
                entry.update(perms=["<missing view>"], inner=[], flags=[])
            else:
                perms, flags = _decorators(function, local, shared)
                entry.update(perms=perms, inner=_inner_permissions(function, local, shared),
                             flags=flags)
            inventory[f"{namespace}:{name}"] = entry
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
