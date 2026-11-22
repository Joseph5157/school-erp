# ADR 0028: Behavioural tests for JavaScript

Status: **Proposed**, 2026-11-22. The product owner chose the options below on 2026-11-22. See
[JAVASCRIPT_TESTING_IMPLEMENTATION_SPEC.md](../engineering/JAVASCRIPT_TESTING_IMPLEMENTATION_SPEC.md),
revision r2, section 13.0.

This ADR stays Proposed until the spike in that spec (section 7.1) passes. The harness
implementation PR (JS1) then records the spike evidence here, moves the status to Accepted, adds
the ADR to the [ADR index](README.md) and adds the note to `ARCHITECTURE.md`.

## Problem

`static/js/erp.js` is one classic script of 1,745 lines, served directly with no build step. It
now holds data-integrity logic:

- per-row marks autosave with conflict handling (Option B1);
- attendance autosave and bulk present;
- signed-out reply handling;
- the session warning;
- privacy-safe usage measurement (ADR 0027).

It changes often: 40 of its 52 commits on `main` landed between 2026-10-22 and 2026-11-22.

Nothing in the repository runs this script. About 60 Django test methods read its source text
instead (spec section 3.3). They confirm that particular lines exist, not that the behaviour works:

- Reply ordering, timers, queue limits, focus and storage failures are untested by execution.
- A suspected race in attendance autosave passes every current test. Spec finding F-JS1 describes
  it: an older reply can show "✓ Saved" while a newer change is in flight. This was read from code,
  not exercised, and the independent reviewer agrees with the reading.
- The equivalent marks rule came from code review, and its guard checks four lines of text.
- Manual phone checks are recorded per review and not repeated on each change.

## Constraint

[ARCHITECTURE.md](../ARCHITECTURE.md) is FROZEN. Its stack says "Testing: Django test framework
initially", "JavaScript: Vanilla JavaScript initially" and "pip with pinned dependencies". It
requires low maintenance and minimal infrastructure, and it excludes a "Node/npm frontend build
pipeline".

Its stack change rule requires an ADR that explains why the problem cannot reasonably be solved
within the current architecture. Running a JavaScript test tool is a stack change even with no
build pipeline. AGENTS.md also forbids a JavaScript build step without an accepted ADR.

Django's test client returns HTML but cannot execute it. Running `erp.js` needs a JavaScript engine
with a DOM: either a real browser driven from Python, or Node with a DOM library.

## Options considered

The full comparison is in spec section 4.

1. **Vitest + jsdom.** Good ergonomics. It needs Vite as a peer dependency, which brings native
   binaries and the npm optional-dependency lockfile problem on Windows-to-Linux CI. Its jsdom
   environment and fake timers do not apply to the per-test window this script needs.
2. **`node:test` + jsdom + `@sinonjs/fake-timers`.** Fast, with two plain-JavaScript dependencies,
   but a Node toolchain in the repository. jsdom does not fire `change` on blur, has no CSS or
   dialogs, and swallows listener errors unless the harness catches them. Whole journeys would
   still need a second tool.
3. **Playwright against a running Django server for everything.** Real, but minutes per run, so too
   slow for draft CI. Kept for a few whole journeys later.
4. **Status quo.** No cost; the risks above remain.
5. **Browser fixture tests with Python Playwright, no server.** One pinned pip package and headless
   Chromium. Each test serves hand-written fixture HTML plus the unchanged `erp.js` and vendored
   HTMX through request interception. The test holds, reorders or fails replies and controls time.
   Real change-on-blur, focus, `matchMedia`, dialogs and CSS. The same tool later runs the whole
   journeys.

## Decision (chosen by the product owner; effective when the spike passes)

1. **Option 5, subject to a time-boxed spike in JS1.** Behavioural tests of `erp.js` run in headless
   Chromium through Python Playwright. There is one browser process per test job, with a fresh
   browser context and page per test. They load the **unchanged** served files and run under
   Django's test runner as `SimpleTestCase` classes with no database (OD-JS1, OD-JS2, OD-JS3,
   OD-JS14).
2. The tests run the real JavaScript and HTMX against representative hand-written DOM fixtures.
   They are not full Django-template or visual-regression tests. A Django contract test keeps the
   fixtures in step with the templates (OD-JS13).
3. If the spike fails, the product owner decides what happens next. The prepared fallback is
   **Option 2** (`node:test` + jsdom) under the same boundary rules.
4. Django tests keep server rules, permissions, rendered attributes and architectural checks over
   the script text, such as "no global HTMX timeout". Source-string tests that stand in for
   behaviour are temporary. Each is removed when equivalent browser coverage lands (OD-JS10).
5. Whole-journey tests against a live server are deferred, and are a later, separate decision
   (OD-JS6).

## Production boundary

The test toolchain may only:

- live in `browser_tests/` with its dependency in `requirements-browser.txt` (Option 5), or in
  `tests/js/` with its own `package.json` and lockfile (Option 2); never at the repository root,
  never under `static/`, never in `requirements.txt` (OD-JS12);
- read production files; it never writes, transforms, bundles, transpiles, minifies or generates
  anything that is served;
- run in local development and in GitHub Actions.

It must not:

- change how `erp.js` is served, its script order, `defer`, its classic-script globals or its HTMX
  wiring;
- add a test-only hook to production code;
- put Playwright, a browser, Node, npm or any JavaScript package on Railway: not in the build, the
  pre-deploy step, the start command or the cron service;
- add a Vite dev server, a bundler or a transform step for the Django application.

Any of these needs a new ADR. A Django boundary test in the draft-safety set enforces the location
and requirements rules.

## Dependency and maintenance costs

**Option 5:**

- One exact-pinned pip package (`playwright`, with its pinned dependencies) in
  `requirements-browser.txt`, plus the Chromium build that version expects.
- A browser download in CI, cached by version.
- A manual update PR at least every three months and on relevant advisories (OD-JS9).
- About 150-250 lines of harness code, and hand-written fixtures kept honest by a Django contract
  test that compares attribute names and normalised values (OD-JS13).
- Contributors need the browser only to run these tests locally; the Django suite runs without it.
  The Python package ships its own internal driver. The repository gets no project-managed
  Node/npm toolchain, package manifest, build pipeline or production dependency.

**Option 2 (fallback):**

- Two exact-pinned npm dev dependencies with no native binaries, and a committed lockfile.
- `npm ci --ignore-scripts` only.
- A Node version pin (OD-JS8).
- About 250-350 lines of harness code.

**Both:**

- One more parallel, path-aware CI job (`js`), targeting under 90 seconds for a cached draft run.
- Whether the job joins the documented "PR verified" rule is an open point for the product owner
  (spec section 9).

## Security and privacy

- **No real network in tests.** Every request is intercepted, and any other request fails the
  test. The jobs use no secrets and no database.
- **No install-time code from JavaScript packages.** Option 5 has none, and Option 2 uses
  `--ignore-scripts`.
- **Synthetic fixtures only.** Fixtures use synthetic names and IDs, never HTML from staging or a
  school.
- **Usage payloads.** Measurement tests assert the exact payload keys, and that a canary name and ID
  from the page never appear in any usage request. Running the code this way strengthens the ADR
  0027 allow-list rather than relaxing it.
- **Test output.** No test logs request bodies on success. A failing test saves a Playwright trace
  and screenshot, which CI uploads only when the job fails and keeps for 7 days. They show only the
  synthetic fixture page and its intercepted requests.

## CI and Railway consequences

- CI gains one job, `js`. On pull requests, drafts included, it installs Chromium and runs only
  when JavaScript, vendored scripts, CSS, relevant templates or forms, browser tests, requirements
  or CI configuration change. It always runs on pushes to `main`. Docs-only PRs stay skipped.
- `core/tests/test_ci_policy.py` and a new boundary test, both in the draft-safety set, guard
  against quiet removal or skipping. They check the job's existence and command, the minimum test
  count per file, and that no skip or `.only` appears without an issue link.
- `IMPLEMENTATION_WORKFLOW.md`, `DEFINITION_OF_DONE.md` and `AGENTS.md` change only if the product
  owner confirms the job joins the "PR verified" rule.
- Railway is unchanged. Railpack installs `requirements.txt` only, and under Option 2 no root
  `package.json` exists. The first staging build after the implementation merges is checked for a
  Python-only provider and no extra install step.

## Rollback

Revert the implementation PR or PRs. That removes:

- the browser or JavaScript test folder and its requirements or package files;
- the CI job;
- the policy, boundary and fixture contract tests;
- the `.gitignore` line (Option 2);
- the edits to `docs/engineering/README.md` and to the merge-gate documents.

Retired source-string tests come back with the revert of the PR that removed them. Production,
Railway and the Django suite need no change, because nothing depends on the toolchain.

## When to revisit

- The first PR's spike shows that held routes, the page clock or the vendored HTMX do not behave as
  expected under Option 5 (then Option 2), or under jsdom (then whole journeys only).
- The job regularly exceeds its budget, or the browser download proves unreliable in CI.
- Keeping the pinned package and browser (or Node and jsdom) current costs more than a few hours a
  quarter.
- Someone proposes a bundler, transpiler, TypeScript, an ES-module split of `erp.js` or an SPA
  framework. That is a different decision, needs its own ADR, and must not reuse this one.
- Whole-journey tests are approved, or WebKit coverage becomes necessary for iPhone-specific bugs.
- Required status checks are introduced on `main`.

## Related

- Spec: [JAVASCRIPT_TESTING_IMPLEMENTATION_SPEC.md](../engineering/JAVASCRIPT_TESTING_IMPLEMENTATION_SPEC.md)
- [ADR 0027 Privacy-safe usage measurement](0027-privacy-safe-usage-measurement.md)
- [Option B implementation spec](../competitive-research/OPTION_B_IMPLEMENTATION_SPEC.md),
  sections 4.4, 4.5, 4.7 and 10
- [ARCHITECTURE.md](../ARCHITECTURE.md), Approved Technology Stack and Stack change rule
