"""CI policy guard (ENG-CI-01).

Pins the parts of `.github/workflows/ci.yml` that make it a merge gate: draft PRs run a fixed
safety-test set, while a PR that is Ready for review and every push to `main` run the complete
suite. Checks only those rules, by reading the workflow's own blocks, so ordinary edits
elsewhere in the file do not break it. Standard library only (no YAML parser in the project).
"""

import re

from django.conf import settings
from django.test import SimpleTestCase

WORKFLOW = settings.BASE_DIR / ".github" / "workflows" / "ci.yml"
FULL_SUITE = "python manage.py test --parallel 4 --durations 20"


def _block(lines, header, indent):
    """Lines under `header` (a key at `indent` spaces) up to the next key at that indent."""
    prefix = " " * indent + header
    for i, line in enumerate(lines):
        if line.rstrip() == prefix or line.startswith(prefix + " "):
            out = []
            for nxt in lines[i + 1 :]:
                stripped = nxt.strip()
                if stripped and not stripped.startswith("#"):
                    if len(nxt) - len(nxt.lstrip()) <= indent:
                        break
                out.append(nxt)
            return out
    return None


def _steps(job_lines):
    """Split a job's `steps:` block into one text block per step."""
    steps_block = _block(job_lines, "steps:", 4) or []
    steps, current = [], None
    for line in steps_block:
        if line.startswith("      - "):
            current = [line]
            steps.append(current)
        elif current is not None:
            current.append(line)
    return ["\n".join(s) for s in steps]


def _step_if(step):
    match = re.search(r"^\s*(?:- )?if:\s*(.+)$", step, re.M)
    return match.group(1).strip() if match else None


class CiPolicyTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.text = WORKFLOW.read_text(encoding="utf-8")
        cls.lines = cls.text.splitlines()
        cls.on = _block(cls.lines, "on:", 0)
        cls.jobs = _block(cls.lines, "jobs:", 0)
        cls.test_job = _block(cls.jobs, "test:", 2)
        cls.lint_job = _block(cls.jobs, "lint:", 2)
        cls.test_steps = _steps(cls.test_job)

    def test_pull_requests_listen_for_ready_for_review(self):
        pr = "\n".join(_block(self.on, "pull_request:", 2))
        types = re.search(r"types:\s*\[([^\]]*)\]", pr)
        self.assertIsNotNone(types, "pull_request must list its activity types")
        listed = {t.strip() for t in types.group(1).split(",")}
        self.assertLessEqual(
            {"opened", "reopened", "synchronize", "ready_for_review", "converted_to_draft"}, listed
        )

    def test_main_pushes_run_without_path_filters(self):
        push = "\n".join(_block(self.on, "push:", 2))
        self.assertRegex(push, r"branches:\s*\[\s*main\s*\]")
        self.assertNotIn("paths", push, "a push to main must always run the whole workflow")

    def test_lint_and_test_jobs_keep_their_check_names(self):
        self.assertIsNotNone(self.lint_job, "the lint job must exist under that id")
        self.assertIsNotNone(self.test_job, "the test job must exist under that id")
        for job in (self.lint_job, self.test_job):
            # A job-level name would rename the check; a job-level if could skip it.
            self.assertFalse([ln for ln in job if re.match(r"^    (name|if):", ln)])
        self.assertIn("ruff check .", "\n".join(self.lint_job))

    def test_test_job_still_waits_for_lint(self):
        self.assertIn("    needs: lint", self.test_job)

    def test_mode_is_draft_only_for_a_draft_pull_request(self):
        modes = re.findall(r"^\s*CI_MODE:\s*(.+)$", "\n".join(self.test_job), re.M)
        self.assertEqual(len(modes), 1, "CI_MODE is set once, at job level, and never overridden")
        expr = modes[0]
        self.assertIn("github.event_name == 'pull_request'", expr)
        self.assertIn("github.event.pull_request.draft", expr)
        self.assertRegex(expr, r"\|\|\s*'full'\s*\}\}$", "anything else must fall back to full")

    def test_full_suite_runs_in_every_mode_except_draft(self):
        full = [s for s in self.test_steps if FULL_SUITE in s]
        self.assertEqual(len(full), 1, "exactly one step runs the complete suite")
        self.assertEqual(_step_if(full[0]), "env.CI_MODE != 'draft'")
        self.assertIn("report_test_stall.sh", full[0], "the stall reporter must stay")

    def test_draft_steps_never_run_the_complete_suite(self):
        draft = [s for s in self.test_steps if _step_if(s) == "env.CI_MODE == 'draft'"]
        self.assertTrue(draft, "draft mode must run its safety tests")
        for step in draft:
            for run in re.findall(r"manage\.py test([^\n]*)", step):
                self.assertIn("$DRAFT_SAFETY_TESTS", run, "draft tests must name their modules")

    def test_checks_run_in_both_modes(self):
        for command in ("python manage.py check", "makemigrations --check --dry-run"):
            steps = [s for s in self.test_steps if command in s]
            self.assertEqual(len(steps), 1, command)
            self.assertIsNone(_step_if(steps[0]), f"{command} must not be conditional")

    def test_draft_safety_set_keeps_route_inventory_and_exists(self):
        body = "\n".join(self.test_job)
        match = re.search(r"DRAFT_SAFETY_TESTS:\s*>-\n((?:\s{8}\S.*\n?)+)", body)
        self.assertIsNotNone(match, "DRAFT_SAFETY_TESTS must be a folded list of modules")
        modules = match.group(1).split()
        self.assertIn("core.tests.test_security_gate4b_route_inventory", modules)
        self.assertIn("core.tests.test_ci_policy", modules)
        for module in modules:
            path = settings.BASE_DIR.joinpath(*module.split(".")).with_suffix(".py")
            self.assertTrue(path.exists(), f"{module} does not exist")

    def test_no_pull_request_target(self):
        self.assertNotIn("pull_request_target", self.text)


# --- Browser tests: the path-aware `js` job (ADR 0028, ENG-JS-01 spec section 9) ----------------

BROWSER_TESTS = 'python -m unittest discover -s browser_tests -p "bt_*.py" -t .'
RUNS = "steps.paths.outputs.run == 'true'"
# Changed paths that must run the browser tests on a pull request, and paths that must not.
RELEVANT = (
    "static/js/erp.js", "static/vendor/htmx/2.0.4/htmx.min.js", "static/css/erp.css",
    "browser_tests/bt_harness.py", "browser_tests/support/page.py", "browser_tests/fixtures/marks.html",
    "requirements.txt", "requirements-browser.txt", "config/settings.py", "manage.py",
    ".github/workflows/ci.yml",
)
IRRELEVANT = (
    "docs/adr/0028-javascript-behaviour-testing.md", "README.md", "core/views.py",
    "core/templates/core/my_attendance.html", "static/img/logo.png", "requirements.txt.bak",
    "dev-requirements.txt", "notes/config/x.txt", "scripts/manage.py",
)
UPLOAD_IF = f"always() && {RUNS} && steps.tests.outcome != 'success'"


class JsJobPolicyTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
        jobs = _block(lines, "jobs:", 0)
        cls.test_job = _block(jobs, "test:", 2)
        cls.js_job = _block(jobs, "js:", 2)
        cls.js_steps = _steps(cls.js_job or [])

    def _step(self, text):
        found = [s for s in self.js_steps if text in s]
        self.assertEqual(len(found), 1, f"exactly one js step contains {text!r}")
        return found[0]

    def test_the_js_job_exists_and_cannot_be_skipped_or_ignored(self):
        self.assertIsNotNone(self.js_job, "the js job must exist under that id")
        self.assertFalse([ln for ln in self.js_job if re.match(r"^    (name|if|needs|continue-on-error):", ln)])
        self.assertNotIn("continue-on-error", "\n".join(self.js_job))

    def test_the_js_job_can_only_read_the_repository(self):
        self.assertEqual([ln.strip() for ln in _block(self.js_job, "permissions:", 4) or []], ["contents: read"])

    def test_the_path_check_fails_closed_against_the_exact_base(self):
        checkout = self._step("actions/checkout@v4")
        self.assertIn("fetch-depth: 0", checkout)
        paths = self._step("id: paths")
        self.assertIsNone(_step_if(paths), "the path check itself always runs")
        self.assertIn("github.event.pull_request.base.sha", paths)
        self.assertIn('git diff --name-only "$BASE_SHA" "$GITHUB_SHA"', paths)
        # Starts at run=true and only a successful diff of a pull request can turn it off, so a
        # push to main, a missing base or a failed diff all run the tests.
        script = paths[paths.index("run: |"):]
        self.assertLess(script.index("run=true"), script.index("run=false"))
        self.assertIn('[ "$EVENT" = "pull_request" ] && [ -n "$BASE_SHA" ]', script)
        self.assertIn("if changed=$(git diff", script)
        self.assertIn('grep -Eq "$relevant" <<< "$changed" || run=false', script)
        self.assertNotIn("| grep", script, "a pipe into grep -q can fail open under pipefail")

    def test_the_relevant_paths_decide_correctly(self):
        # The step's own pattern (a POSIX ERE that Python's re reads the same way) is applied to
        # sample changed paths, so a narrowed or broken pattern fails here.
        found = re.findall(r"relevant='([^']+)'", self._step("id: paths"))
        self.assertEqual(len(found), 1)
        relevant = re.compile(found[0])
        for path in RELEVANT:
            self.assertIsNotNone(relevant.search(path), f"{path} must run the browser tests")
        for path in IRRELEVANT:
            self.assertIsNone(relevant.search(path), f"{path} must not run the browser tests")

    def test_the_test_step_runs_exactly_the_browser_test_command(self):
        test = self._step("id: tests")
        self.assertEqual(re.findall(r"^\s+run:(.*)$", test, re.M), [" " + BROWSER_TESTS])
        self.assertEqual(_step_if(test), RUNS)
        for key in ("continue-on-error", "shell:", "working-directory:"):
            self.assertNotIn(key, test)

    def test_the_test_step_times_out_before_the_job(self):
        step = int(re.search(r"^\s+timeout-minutes:\s*(\d+)\s*$", self._step("id: tests"), re.M).group(1))
        job = int(re.search(r"^    timeout-minutes:\s*(\d+)\s*$", "\n".join(self.js_job), re.M).group(1))
        self.assertLessEqual(step, job - 3, "leave the job time to upload diagnostics after a hung run")

    def test_install_steps_are_gated_only_by_the_path_check(self):
        for text in ("pip install -r requirements-browser.txt", "--only-shell chromium", "install-deps chromium"):
            condition = _step_if(self._step(text))
            self.assertIsNotNone(condition, text)
            self.assertTrue(condition.startswith(RUNS), f"{text}: {condition}")

    def test_diagnostics_upload_whenever_the_tests_did_not_pass_and_are_kept_seven_days(self):
        upload = self._step("actions/upload-artifact@v4")
        self.assertEqual(_step_if(upload), UPLOAD_IF)
        self.assertIn("retention-days: 7", upload)

    def test_the_django_browser_contract_tests_run_in_draft_safety(self):
        body = "\n".join(self.test_job)
        modules = re.search(r"DRAFT_SAFETY_TESTS:\s*>-\n((?:\s{8}\S.*\n?)+)", body).group(1).split()
        self.assertIn("core.tests.test_js_toolchain_boundary", modules)
        self.assertIn("core.tests.test_js_fixture_contract", modules)
