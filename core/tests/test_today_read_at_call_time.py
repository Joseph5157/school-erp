"""Lazily imported modules must read today's date when called, not copy it at import.

Django loads context processors and some views the first time they are used. If that first
use happens inside a test that patches `core.models.business_today`, a module that did
`from core.models import business_today` keeps the fake date for the rest of that test
worker. Later tests then saw a wrong "current year" and failed only under `--parallel`
(test_ui_year_selector_ui, test_ui_register_cards). These modules call
`core_models.business_today()` instead.
"""

from django.test import SimpleTestCase

import core.context_processors
import core.teacher_views

LAZILY_LOADED = (core.context_processors, core.teacher_views)


class TodayReadAtCallTimeTests(SimpleTestCase):
    def test_lazily_loaded_modules_do_not_copy_business_today(self):
        for module in LAZILY_LOADED:
            with self.subTest(module=module.__name__):
                self.assertFalse(hasattr(module, "business_today"))
