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
