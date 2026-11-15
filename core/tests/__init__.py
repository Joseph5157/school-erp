"""Load every app module before any test runs, in every test worker.

Many modules do `from core.models import business_today`. Under `--parallel`, each worker
otherwise imports views, context processors and helpers lazily, on first use. When that first
use happens inside a test that patches `core.models.business_today`, the module keeps the fake
date for the rest of the worker's life, and unrelated later tests see the wrong "today" and
fail only in parallel runs. Importing everything here, while no patch is active, gives every
module the real function. (test_today_read_at_call_time.py covers the two worst offenders.)
"""

import importlib
import pkgutil

import core

for _module in pkgutil.walk_packages(core.__path__, prefix="core."):
    if _module.name.startswith(("core.tests", "core.migrations")):
        continue
    importlib.import_module(_module.name)
