"""Fixture contract for the browser tests (ADR 0028, ENG-JS-01 spec section 7.5).

The browser tests run erp.js against hand-written fixture pages and replies in
browser_tests/fixtures/. These tests render the real pages and replies through the views and
check that the fixtures keep the same structure erp.js depends on: hx-* attributes and their
normalised values, data-erp-* hooks, erp-* classes, input names, and the reply markers. Text is
not compared. Primary keys become <pk> and autosave URLs become <url>.

One documented exception: marks fixture row 103 has a 600 ms request timeout so a browser test can
reach the timeout path in real time; production rows use 15000.
"""

import json
import re
from datetime import date
from html.parser import HTMLParser

from django.conf import settings
from django.test import Client, TestCase
from django.urls import reverse

from core.models import SectionClassTeacher
from core.tests.phase4_fixtures import Phase4Fixture
from core.tests.test_marks_autosave import AutosaveFixture
from core.tests.test_phase5_teacher_attendance import MONDAY, on

FIXTURES = settings.BASE_DIR / "browser_tests" / "fixtures"
VOID = {"input", "br", "img", "meta", "link", "hr"}


class Element:
    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs), parent, []

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()


class Tree(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Element("root", {}, None)
        self.current = self.root
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        element = Element(tag, attrs, self.current)
        self.current.children.append(element)
        if tag not in VOID:
            self.current = element

    def handle_startendtag(self, tag, attrs):
        self.current.children.append(Element(tag, attrs, self.current))

    def handle_endtag(self, tag):
        node = self.current
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:
            self.current = node.parent


def norm(value):
    return re.sub(r"\d+", "<pk>", value or "")


def hook_attrs(element):
    """hx-* and data-erp-* attributes with normalised values."""
    out = {}
    for name, value in element.attrs.items():
        if name == "hx-post":
            out[name] = "<url>"
        elif name.startswith(("hx-", "data-erp-")):
            out[name] = norm(value) if name in ("hx-vals", "data-erp-enrollment") else (value or "")
    return out


def markers(elements):
    """The structure erp.js reads, as a set: tags, hooks, erp-* classes, input kinds and names."""
    found = set()
    for el in elements:
        classes = tuple(sorted(c for c in (el.attrs.get("class") or "").split() if c.startswith("erp-")))
        hooks = tuple(sorted(n for n in el.attrs if n.startswith(("data-erp-", "data-server-"))))
        element_id = el.attrs.get("id") or ""
        found.add((
            el.tag, classes, hooks, "hx-swap-oob" in el.attrs,
            norm(element_id) if element_id.startswith("erp-") else "",
            el.attrs.get("type", "") if el.tag == "input" else "", norm(el.attrs.get("name")),
            el.attrs.get("enterkeyhint", ""), el.attrs.get("inputmode", ""),
        ))
    return found


def rows(tree):
    return [el for el in tree.root.walk() if "data-erp-row" in el.attrs]


def page_hooks(tree):
    return {name for el in tree.root.walk() for name in el.attrs if name.startswith("data-erp-")}


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


class ContractMixin:
    def assert_row_matches(self, fixture_row, real_row):
        self.assertEqual(hook_attrs(fixture_row), hook_attrs(real_row))
        fixture_inner = markers(list(fixture_row.walk())[1:])
        real_inner = markers(list(real_row.walk())[1:])
        self.assertEqual(fixture_inner, real_inner,
                         f"fixture only: {fixture_inner - real_inner}; real only: {real_inner - fixture_inner}")

    def assert_page_matches(self, fixture_html, real_html):
        fixture_tree, real_tree = Tree(fixture_html), Tree(real_html)
        self.assert_row_matches(rows(fixture_tree)[0], rows(real_tree)[0])
        missing = page_hooks(fixture_tree) - page_hooks(real_tree)
        self.assertEqual(missing, set(), "the fixture uses hooks the real page no longer has")

    def assert_reply_matches(self, fixture_name, response):
        fixture_markers = markers(list(Tree(fixture(f"replies/{fixture_name}")).root.walk())[1:])
        real_markers = markers(list(Tree(response.content.decode()).root.walk())[1:])
        self.assertEqual(fixture_markers, real_markers,
                         f"fixture only: {fixture_markers - real_markers}; real only: {real_markers - fixture_markers}")


class MarksFixtureContractTests(ContractMixin, AutosaveFixture, TestCase):
    def test_the_marks_page_fixture_matches_the_real_page(self):
        real = self.teacher.get(self.entry_url(self.test1)).content.decode()
        self.assert_page_matches(fixture("marks.html"), real)
        self.assertIn("""hx-request='{"timeout": 15000}'""", real)

    def test_the_only_fixture_exception_is_row_103s_short_timeout(self):
        first, _, third = rows(Tree(fixture("marks.html")))
        a, b = hook_attrs(first), hook_attrs(third)
        self.assertEqual({k for k in a if a[k] != b[k]}, {"hx-request"})
        self.assertEqual(json.loads(a["hx-request"]), {"timeout": 15000})
        self.assertEqual(json.loads(b["hx-request"]), {"timeout": 600})

    def test_the_saved_reply_fixture_matches(self):
        response = self.post_row(self.asha, "MARKED", "12")
        self.assertEqual(response["X-ERP-Row-Fragment"], "1")
        self.assert_reply_matches("marks_saved.html", response)

    def test_the_conflict_reply_fixture_matches(self):
        self.post_row(self.asha, "MARKED", "12")
        response = self.post_row(self.asha, "MARKED", "13")  # stale (empty) base: conflict
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response["X-ERP-Row-Fragment"], "1")
        self.assert_reply_matches("marks_conflict.html", response)

    def test_the_refused_reply_fixture_matches(self):
        response = self.post_row(self.bina, "MARKED", "99")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response["X-ERP-Row-Fragment"], "1")
        self.assert_reply_matches("marks_refused.html", response)


class AttendanceFixtureContractTests(ContractMixin, Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        for patch in on(MONDAY):
            patch.start()
            self.addCleanup(patch.stop)
        SectionClassTeacher.assign(teacher=self.rao, academic_year=self.year, section=self.six_a,
                                   start_date=date(2026, 6, 1))
        _, self.asha = self.make_student("Asha")
        _, self.ravi = self.make_student("Ravi")
        _, self.mina = self.make_student("Mina")
        self.teacher = self.client_class()
        self.teacher.login(username="rao", password="pass-12345")
        self.url = reverse("core:my-attendance", args=[self.six_a.pk])
        self.teacher.post(self.url, {"action": "open"})
        self.autosave = reverse("core:my-attendance-autosave", args=[self.six_a.pk])

    def test_the_attendance_page_fixture_matches_the_real_page(self):
        real = self.teacher.get(self.url).content.decode()
        self.assert_page_matches(fixture("attendance.html"), real)
        self.assertIn("data-erp-bulk-url=", real)

    def test_the_saved_reply_fixture_matches(self):
        pk = self.asha.pk
        response = self.teacher.post(self.autosave, {"enrollment": pk, f"status_{pk}": "ABSENT", f"note_{pk}": ""},
                                     HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assert_reply_matches("attendance_saved.html", response)

    def test_the_signed_out_reply_fixture_matches(self):
        response = Client().post(self.autosave, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 401)
        expected = json.loads(fixture("replies/signed_out.json"))
        self.assertEqual(set(response.json()), set(expected))
        self.assertEqual(response.json()["error"], expected["error"])
