"""Fixture contract for the browser tests (ADR 0028, ENG-JS-01 spec section 7.5).

The browser tests run erp.js against hand-written fixture pages and replies in
browser_tests/fixtures/. These tests render the real pages and replies through the views and
check, element by element and in order, that every fixture row, the roster around the rows, the
form and each reply carry the same behaviour-relevant attributes with the same values as the real
ones: hx-*, data-erp-* and data-server-* attributes, ids, input names, types and values (radio
values are what erp.js selects on), checked, hidden and the other attributes in BEHAVIOUR_ATTRS,
and erp-* and is-* classes. Text, labels and Bootstrap classes are not compared. Primary keys
become <pk>, autosave and bulk URLs become <url> and the CSRF token becomes <token>.

There are no exceptions: every marks row keeps the production 15-second timeout. The browser tests
reach the timeout by running it on the page clock (browser_tests/support/page.py).
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


# Attributes erp.js, HTMX or the browser act on. Their values are compared, not just their names.
BEHAVIOUR_ATTRS = {
    "id", "name", "type", "value", "for", "checked", "hidden", "disabled", "inputmode",
    "enterkeyhint", "step", "role", "aria-live", "aria-pressed", "aria-expanded", "aria-controls",
    "data-idle", "data-absolute", "data-status-url", "data-login-url",  # the session box
}
BEHAVIOUR_PREFIXES = ("hx-", "data-erp-", "data-server-")
# data-idle and data-absolute are the seconds left in the session when the page was rendered.
PK_ATTRS = {"id", "name", "for", "aria-controls", "hx-vals", "data-erp-enrollment", "data-idle", "data-absolute"}
URL_ATTRS = {"hx-post", "data-erp-bulk-url", "data-erp-usage-url", "data-status-url", "data-login-url"}


def norm(value):
    return re.sub(r"\d+", "<pk>", value or "")


def behaviour(element):
    """The element's behaviour-relevant attributes with normalised values (empty when it has none).

    Primary keys become <pk>, autosave and bulk URLs become <url>, the CSRF token becomes <token>,
    and hx-headers keeps only its header names. Classes keep only erp-* and is-* tokens. Text and
    other attributes (labels, Bootstrap classes, aria-hidden) are not compared.
    """
    attrs = element.attrs
    out = {}
    for name, value in attrs.items():
        value = value or ""
        if not (name in BEHAVIOUR_ATTRS or name.startswith(BEHAVIOUR_PREFIXES)):
            continue
        if name in URL_ATTRS:
            value = "<url>"
        elif name == "hx-headers":
            value = ",".join(sorted(json.loads(value)))
        elif name == "value" and attrs.get("name") == "csrfmiddlewaretoken":
            value = "<token>"
        elif name in PK_ATTRS:
            value = norm(value)
        out[name] = value
    classes = sorted(c for c in (attrs.get("class") or "").split() if c.startswith(("erp-", "is-")))
    if classes:
        out["class"] = " ".join(classes)
    return out


def signature(elements):
    """Ordered (tag, behaviour) pairs of the elements that carry any behaviour-relevant attribute."""
    return [(el.tag, behaviour(el)) for el in elements if behaviour(el)]


def descendants(element):
    return list(element.walk())[1:]


def rows(tree):
    return [el for el in tree.root.walk() if "data-erp-row" in el.attrs]


def outside_rows(element):
    """The element's descendants that are not inside a row (counts, tabs, hints, action bar)."""
    out = []
    for child in element.children:
        if "data-erp-row" in child.attrs:
            continue
        out.append(child)
        out.extend(outside_rows(child))
    return out


def first(tree, attribute):
    found = [el for el in tree.root.walk() if attribute in el.attrs]
    assert found, attribute
    return found[0]


def page_hooks(tree):
    return {name for el in tree.root.walk() for name in el.attrs if name.startswith("data-erp-")}


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def diff(fixture_sig, real_sig):
    for index, (a, b) in enumerate(zip(fixture_sig, real_sig, strict=False)):
        if a != b:
            return f"first difference at element {index}: fixture {a} != real {b}"
    return f"fixture has {len(fixture_sig)} elements, real has {len(real_sig)}"


class ContractMixin:
    def assert_same(self, fixture_sig, real_sig):
        self.assertEqual(fixture_sig, real_sig, diff(fixture_sig, real_sig))

    def assert_page_matches(self, fixture_html, real_html, roster):
        """Every fixture row, the roster outside the rows, and the form match the real page."""
        fixture_tree, real_tree = Tree(fixture_html), Tree(real_html)
        fixture_rows, real_rows = rows(fixture_tree), rows(real_tree)
        self.assertGreaterEqual(len(real_rows), len(fixture_rows))
        for index, (fixture_row, real_row) in enumerate(zip(fixture_rows, real_rows, strict=False)):
            with self.subTest(row=index):
                self.assert_same(signature([fixture_row] + descendants(fixture_row)),
                                 signature([real_row] + descendants(real_row)))
        with self.subTest(part="roster outside the rows"):
            self.assert_same(signature(outside_rows(first(fixture_tree, roster))),
                             signature(outside_rows(first(real_tree, roster))))
        with self.subTest(part="form"):
            fixture_form, real_form = first(fixture_tree, "hx-headers"), first(real_tree, "hx-headers")
            self.assertEqual((fixture_form.tag, behaviour(fixture_form)), (real_form.tag, behaviour(real_form)))
        missing = page_hooks(fixture_tree) - page_hooks(real_tree)
        self.assertEqual(missing, set(), "the fixture uses hooks the real page no longer has")

    def assert_session_box_matches(self, fixture_html, real_html):
        fixture_box, real_box = first(Tree(fixture_html), "data-erp-session"), first(Tree(real_html), "data-erp-session")
        self.assert_same(signature([fixture_box] + descendants(fixture_box)),
                         signature([real_box] + descendants(real_box)))

    def assert_reply_matches(self, fixture_name, response):
        self.assert_same(signature(descendants(Tree(fixture(f"replies/{fixture_name}")).root)),
                         signature(descendants(Tree(response.content.decode()).root)))


class MarksFixtureContractTests(ContractMixin, AutosaveFixture, TestCase):
    def test_the_marks_page_fixture_matches_the_real_page(self):
        real = self.teacher.get(self.entry_url(self.test1)).content.decode()
        self.assert_page_matches(fixture("marks.html"), real, "data-erp-marks")
        self.assertIn("""hx-request='{"timeout": 15000}'""", real)

    def test_every_fixture_row_keeps_the_production_timeout(self):
        fixture_rows = rows(Tree(fixture("marks.html")))
        self.assertEqual(len(fixture_rows), 3)
        for row in fixture_rows:
            self.assertEqual(json.loads(behaviour(row)["hx-request"]), {"timeout": 15000})

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

    def test_the_forbidden_reply_fixture_matches(self):
        response = self.post_row(self.asha, "MARKED", "12", client=self.client_for(self.iyer))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response["X-ERP-Row-Fragment"], "1")
        self.assert_reply_matches("marks_forbidden.html", response)

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
        self.assert_page_matches(fixture("attendance.html"), real, "data-erp-roster")
        self.assert_session_box_matches(fixture("attendance.html"), real)
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

    def test_the_bulk_present_reply_fixtures_match(self):
        bulk = reverse("core:my-attendance-autosave-present", args=[self.six_a.pk])
        ajax = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}
        saved = self.teacher.post(bulk, {"enrollment": [self.ravi.pk, self.mina.pk]}, **ajax)
        self.assertEqual(saved.status_code, 200)
        expected = json.loads(fixture("replies/attendance_bulk_saved.json"))
        self.assertEqual(set(saved.json()), set(expected))
        # The real ids are database keys: the reply lists exactly the students sent, as the
        # fixture lists exactly the two rows the browser test sends (202 and 203).
        self.assertEqual(set(saved.json()["saved"]), {self.ravi.pk, self.mina.pk})
        self.assertEqual(len(saved.json()["saved"]), len(expected["saved"]))
        signed_out = Client().post(bulk, {"enrollment": [self.ravi.pk]}, **ajax)
        self.assertEqual(signed_out.status_code, 401)
        self.assertEqual(signed_out.json(), json.loads(fixture("replies/signed_out.json")))
