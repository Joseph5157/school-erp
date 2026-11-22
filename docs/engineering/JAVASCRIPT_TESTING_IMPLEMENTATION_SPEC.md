# JavaScript Testing Implementation Specification (ENG-JS-01)

| | |
| --- | --- |
| Status | **Approved by the product owner on 2026-11-22**, with the decisions recorded in section 13. The JS1 spike passed every condition in section 7.1 (evidence in ADR 0028). |
| Revision | r4, 2026-11-22 (JS1): the spike passed; plain `unittest` and headless-only Chromium approved; harness behaviour found in JS1 recorded (section 19.3). r3 (with review fixes): OD-JS7 merge-gate rule approved and applied to AGENTS.md, IMPLEMENTATION_WORKFLOW.md, DEFINITION_OF_DONE.md and the PR template in the docs PR. A1 is no longer merged as an expected failure: JS2 records F-JS1 as a confirmed uncovered defect, and JS3 adds the regression test, shows it failing, fixes the bug and leaves it passing. r3 also applies the fixes from the second independent review (section 19.2). r2: product-owner decisions OD-JS1 to OD-JS15 recorded, plus six corrections: the toolchain wording, fixture fidelity, one browser per job, a path-aware CI job, source-string tests as temporary, and ADR acceptance only after the spike. r1 added Option 5 after independent review. r0 recommended `node:test` + jsdom. Section 19 lists both independent reviews and the owner's r2 changes. |
| Baseline | `origin/main` at `d7d309067ea099edf03562167e317d04ccdb428c` (ENG-CI-01, #286) |
| Risk tier | High. The later implementation changes the repository's testing stack and guards marks autosave, attendance autosave, sessions and privacy measurement. |
| ADR | [0028 Behavioural tests for JavaScript](../adr/0028-javascript-behaviour-testing.md), **Accepted** in the JS1 PR with the spike evidence; listed in the ADR index and noted in `ARCHITECTURE.md`. |
| Affects | Nothing yet. This document installs, changes and implements nothing. |

Every statement about code below cites the baseline. "Read from code, not exercised" marks a
conclusion nobody has run. "Inference" marks a claim about a tool's behaviour that the JS1 spike
must confirm. Section 17 separates what exists today, what this spec proposes and what it defers.

## Contents

1. [Purpose and scope](#1-purpose-and-scope)
2. [Rules this spec must keep](#2-rules-this-spec-must-keep)
3. [Current state audit](#3-current-state-audit)
4. [Options compared](#4-options-compared)
5. [Recommended architecture](#5-recommended-architecture)
6. [Production boundary and testability](#6-production-boundary-and-testability)
7. [Test harness design](#7-test-harness-design)
8. [Coverage packages](#8-coverage-packages)
9. [CI design](#9-ci-design)
10. [Dependencies and maintenance](#10-dependencies-and-maintenance)
11. [Existing source-string tests](#11-existing-source-string-tests)
12. [Whole-journey tests (deferred)](#12-whole-journey-tests-deferred)
13. [Product-owner decisions](#13-product-owner-decisions)
14. [PR plan and affected files](#14-pr-plan-and-affected-files)
15. [Acceptance criteria](#15-acceptance-criteria)
16. [Risks](#16-risks)
17. [Current, proposed and deferred](#17-current-proposed-and-deferred)
18. [External sources](#18-external-sources)
19. [Independent review and verdicts](#19-independent-review-and-verdicts)

## 1. Purpose and scope

`static/js/erp.js` (1,745 lines, one classic script) now carries data-integrity logic: per-row
marks autosave with conflict handling (Option B1), attendance autosave and bulk present,
signed-out handling, the session warning and privacy-safe usage measurement (Option B3, ADR 0027).
It changes often: 52 commits on `main` have touched it, 40 of them since 2026-10-22
(`git log origin/main -- static/js/erp.js`).

Today its behaviour is protected by Django tests that read its **source text** and by manual
browser checks (section 3). This spec proposes how to test that behaviour by running it.

**In scope:**

- choice of test tool, DOM or browser environment, and test seam;
- the test-only toolchain boundary;
- the first coverage package;
- CI placement and the merge gate;
- dependency and lockfile policy;
- what happens to the source-string tests;
- when whole-journey tests come in.

**Out of scope:**

- any change to what `erp.js` does;
- bundling, transpiling or generating JavaScript;
- ES-module conversion of `erp.js`, SPA conversion or TypeScript;
- JavaScript linting (ESLint is a separate question);
- coverage percentages as a gate;
- fixing defects the new tests expose (OD-JS11, OD-JS15).

## 2. Rules this spec must keep

| Rule | Source |
| --- | --- |
| No Node/npm **frontend build pipeline**. Server-rendered Django templates, vanilla JavaScript. | [ARCHITECTURE.md](../ARCHITECTURE.md), Approved Technology Stack and Frontend principle (FROZEN) |
| "Testing: Django test framework initially." A new testing stack is a stack change and needs an ADR with problem, why the current architecture cannot solve it, alternatives, costs, benefits and rollback. | ARCHITECTURE.md, Stack change rule (FROZEN) |
| Low maintenance is a major requirement; minimal infrastructure; pip with pinned dependencies. | ARCHITECTURE.md, Engineering principles and stack (FROZEN) |
| No JavaScript build step without an accepted ADR. No dependency or CI change unless the task is about them. | [AGENTS.md](../../AGENTS.md) |
| Every page works without `erp.js`. | `static/js/erp.js:1`, and the no-JS tests (for example `core/tests/test_ui_teacher_marks.py:115`) |
| Never measure, log or send personal data, marks, notes, IDs, URLs or values. | ADR 0027; AGENTS.md, Security and privacy |
| Vendored front-end files stay byte-for-byte. | `static/vendor/README.md`; `.gitattributes` (`static/vendor/** -text`); `core/tests/test_vendored_assets.py` |
| Attendance autosave behaviour was deliberately left unchanged by Option B, including having no request timeout. | Option B spec 4.4; `core/tests/test_marks_autosave.py:469-471` |
| Server rules, permissions and rendered attributes stay in Django tests. | ADRs 0004, 0010, 0012; [PERMISSIONS.md](../PERMISSIONS.md) |

## 3. Current state audit

### 3.1 How `erp.js` reaches the browser

- **Serving.** WhiteNoise serves it directly from `static/` (`config/settings.py:214-223`,
  `CompressedManifestStaticFilesStorage`). There is no build step; `collectstatic` runs in the
  Railway build.
- **Builder.** Railpack, according to the operations notes. No repo file records it: there is no
  `railway.json`, `railpack.json`, `nixpacks.toml`, `Procfile` or `Dockerfile`.
- **Load order.** Loaded with `defer` and last in both shells, after Bootstrap and after the page's
  `extra_js` block (`templates/base.html:64-66`, `templates/portal/base.html:30-31`). Deferred
  scripts run in document order before `DOMContentLoaded`.
- **HTMX.** Version 2.0.4 is vendored (`static/vendor/htmx/2.0.4/htmx.min.js`) and loads only on
  the two autosave pages: `core/templates/core/assessment_marks_entry.html:67` and
  `core/templates/core/my_attendance.html:52`.
- **SortableJS.** Loads only on the two order dialogs (`class_grade_list.html:80`,
  `academic_year_offerings.html:82`).
- **Inline script.** One script in `<head>` applies the stored sidebar state
  (`templates/base.html:12`).
- **Measurement data.** It reaches the script only through `<body>` attributes
  (`data-erp-usage`, `-usage-url`, `-route`, `-area`). They are rendered only when measurement is
  on and the request had no `Sec-GPC: 1` (`templates/base.html:14`, `templates/portal/base.html:13`).
- **Globals.** The script creates two: `erpUsage` (a `var`, `static/js/erp.js:12`) and the
  helper function `usageHeaders` (`:110-113`). The rest is a series of IIFEs plus one
  `htmx:configRequest` listener on `document` (`:107-109`). All the IIFEs run at the top level of
  one classic script, so an uncaught error in any of them stops the rest of the file.
- **Node.** The repository has no package.json, lockfile, `.nvmrc` or `node_modules`. The
  product owner's machine has Node v22.17.0 and npm 11.8.0, but nothing in the repository uses
  them.

### 3.2 Behaviour map

Classification key:

- **C1:** already tested by running it. No `erp.js` behaviour is C1, because nothing in the
  repository runs the script.
- **C2:** protected only by source-string tests.
- **C3:** checked manually in a browser (recorded in specs or reviews).
- **C4:** untested.
- **C5:** suitable for DOM-unit tests (jsdom).
- **C6:** needs a real browser engine. Option 5 provides one without a server; whole journeys
  also need the server.
- **C7:** server behaviour that stays in Django tests.

| # | Behaviour | Lines (`static/js/erp.js`) | Today | Proposed home |
| --- | --- | --- | --- | --- |
| 1 | Usage queue: GPC off-switch, measurement-off no-op, 20-item cap, per-event device state, batching by device state, requeue on network/5xx, drop on 4xx, 30 s flush, flush on hidden | 12-102 | C2 (`test_usage_workflows.py:672-740`) | C5 or C6 |
| 2 | Usage page events: page viewed, teacher home timing, missing-attendance act, `appinstalled`; `X-ERP-Client` header only when on | 105-143 | C2 | C5 or C6 |
| 3 | Server-side validation hand-off (`noValidate`) | 151-153 | C2 | C5 (low priority) |
| 4 | Password show/hide, `aria-pressed`, label word | 156-171 | C2, C3 | C5 or C6 |
| 5 | `enterkeyhint="next"` moves to next field; IME guard | 175-186 | C2 | Handler C5; resulting focus and real keypad C6 |
| 6 | Password rules, strength meter, match line live region (match announced on leaving the field) | 190-276 | C2 (`test_password_page_polish.py`, `test_ui_password_strength.py`), C3 | Rules C5; blur behaviour C6 |
| 7 | Sidebar groups remember open state; storage failures ignored | 280-298 | C2 | C5 or C6 |
| 8 | Offcanvas `aria-expanded` sync | 301-310 | C2 | C6 (Bootstrap transitions) |
| 9 | Desktop sidebar collapse, storage write in `try` | 315-336 | C2 | C5 or C6 |
| 10 | "Complete" announcer | 340-348 | C4 | C5 or C6 |
| 11 | Message auto-hide, waits while hovered or focused; uses `bootstrap.Alert` when present | 352-366 | C2 | C6 (`:hover`; the Bootstrap branch needs the vendored bundle) |
| 12 | Attendance counts, filter tabs, hint | 370-442 | C3 | C5 or C6 |
| 13 | Mark unanswered as present, never overrides | 446-471 | C2 (`test_attendance_bulk_present.py:144-146`) + C7 server | C5 or C6, + C7 |
| 14 | Bulk present request, per-row results, 401 | 526-585 | C2 + C7 | C5 or C6, + C7 |
| 15 | Attendance HTMX autosave: global `responseHandling`, per-row `_seq/_sent/_dirty`, Retry, 401, wait-before-submit | 587-694 | C2 (`test_marks_autosave.py:556-558`), C3 | C6 preferred (real HTMX, change on blur); C5 with real HTMX if the spike allows |
| 16 | Unsaved-changes warning when autosave is off | 698-716 | C4 | Handler C5; prompt C6 |
| 17 | Marks counts, filters, typing selects Marked, Absent clears score | 722-795 | C3 | C5 or C6 |
| 18 | Marks Enter/Next, last-row behaviour | 797-818 | C2 (`test_marks_autosave.py:517-523`) | C6 (blur fires `change`, which saves the row being left) |
| 19 | Marks autosave: local validation, own-row parameters, scoped swap, failure mapping, stale replies, conflict Use/Keep, Retry, fallback, `online`, `beforeunload` | 831-1158 | C2 (`test_marks_autosave.py:494-568`), C3 (Option B spec 10.1 manual list) | C6 preferred; most branches C5 if the spike allows; server C7 |
| 20 | Announcement audience fields | 1162-1183 | C4 | C5 or C6 |
| 21 | Character counters | 1187-1198 | C4 | C5 or C6 |
| 22 | Logo preview checks | 1202-1257 | C2 (`test_ui_uploads_audit19.py`) | Size/type C5 or C6; decode C6 |
| 23 | Subjects-offered hash opens group | 1260-1266 | C4 | C6 (`scrollIntoView` unguarded at `:1264`) |
| 24 | Timetable class picker dialog and search | 1270-1316 | C2 (`test_teacher_timetable_class.py`) | C6 (native `<dialog>`) |
| 25 | Order dialogs, arrows, drag | 1323-1405 | C2 (`test_reorder_dialog.py`) | C6 (modal; drag needs SortableJS) |
| 26 | One-shot submit buttons | 1412-1432 | C2 | C5 or C6 |
| 27 | Child switcher Escape/outside tap | 1437-1452 | C4 | C5 or C6 |
| 28 | Install button (help page) | 1456-1476 | C2 (`test_pwa_gate1.py:228-231`) | Synthetic `beforeinstallprompt`, C5 or C6 |
| 29 | Install bar: phone only, 30-day "Not now", userChoice, shown/dismissed/installed | 1484-1550 | C2 (`test_pwa_gate1.py:280-286`, `test_usage_workflows.py:709-716`) | Script logic C5 or C6. The CSS `@media` hide rule needs CSS (C6). The real install prompt cannot be automated reliably and stays manual. |
| 30 | Dependent selectors | 1558-1605 | C2 (`test_ui_dependent_selects.py`) | C5 or C6 |
| 31 | Credential copy buttons | 1608-1623 | C4 | C6 (clipboard permission) or C5 stubbed |
| 32 | Session warning: schedule, ask, warn, countdown, Stay, signed-out, `erp:signed-out` | 1625-1735 | C2 (`test_session_errors_audit18.py:251-263`) + C7 (`:196-249`) | C5 or C6, + C7 |
| 33 | Timetable date strip centring | 1738-1745 | C4 | C6 (layout) |

Server behaviour that stays in Django (C7) is already tested by running it:

- marks autosave refusals, conflicts, idempotent retry, lock order, reply contents and
  concurrency (`core/tests/test_marks_autosave.py:79-446`, `:570-739`);
- signed-out 401 for HTMX and `X-Requested-With` requests
  (`accounts/middleware.py:68-73`, `:190`; `core/tests/test_session_errors_audit18.py:196-249`);
- measurement store, enums, beacon validation and report (`core/tests/test_usage_*.py`);
- rendered attributes: `hx-*`, base inputs, timeout and the HTMX script loading only when
  needed (`core/tests/test_marks_autosave.py:451-492`).

### 3.3 Source-string tests today

About 60 test methods in 20 files read `erp.js` as text. This is a heuristic count from an AST scan
of `core/tests/test_*.py`, and some of those methods also check templates. The largest groups are
`test_marks_autosave.py` (14), `test_usage_workflows.py` (14), `test_reorder_dialog.py` (5),
`test_password_page_polish.py` (4) and `test_session_errors_audit18.py` (4). They fall into two
kinds, and section 11 treats them differently.

**Behaviour stand-ins** pin the text of an implementation. Examples:

- `var stale = row._sent !== row._seq;` (`test_marks_autosave.py:543-551`);
- `queue = batch.concat(queue)` (`test_usage_workflows.py:672-677`).

Renaming a variable breaks them without a bug. A real bug passes them as long as the line
survives.

**Policy guards** pin an absence or a whole-file rule. Examples:

- no `localStorage`, `setTimeout` or `setInterval` in the marks block
  (`test_marks_autosave.py:532-535`);
- no `serviceWorker` (`test_pwa_gate1.py:170`);
- every `fetch(` sends `X-Requested-With` (`test_session_errors_audit18.py:251-255`);
- usage events built only from enum constants (`test_usage_workflows.py:685-696`).

A behavioural test cannot prove an absence across every path, so policy guards stay useful.

### 3.4 Browser evidence

- Playwright is **not** part of the repository. `requirements.txt` has no Playwright package,
  there is no `package.json`, and no test imports `playwright`, `selenium` or `LiveServerTestCase`.
- Browser checks so far were manual or agent-driven:
  - Playwright MCP screenshots (`docs/ui-reviews/ui-d1-3b/README.md:6`), and plans that save under
    `.playwright-mcp/`, which is untracked;
  - the Option B manual phone list (`OPTION_B_IMPLEMENTATION_SPEC.md`, section 10.1, "Manual").

  Results are recorded per review, not re-run.

### 3.5 Findings from the audit

**F-JS1 (read from code, not exercised; the independent reviewer agrees with the reading): an older
attendance reply can show "✓ Saved" while a newer change is in flight.**

- Attendance rows swap the server's status fragment into the row whatever the request's age
  (`_attendance_capture_table.html:19`, `hx-target="find [data-erp-row-status]"`; fragment at
  `_attendance_autosave_status.html:2`).
- With `hx-sync="this:queue last"`, a second change waits for the first reply. When the older reply
  arrives, its "✓ Saved" replaces the "Saving…" set for the newer change (`erp.js:597-606`).
- `htmx:afterRequest` then announces "Saved {name}." without checking `_sent !== _seq`
  (`erp.js:632-641`). The page line keeps "Saving…" because `_dirty` stays true (`:635`).
- An older reply that **fails** shows "Not saved." with Retry over the newer, still-pending change
  (`:655`).
- Out-of-band counts are correctly held back while other rows are in flight (`:511`, `:626-628`).
  Only the row text and the announcement are affected.
- Attendance has no request timeout. That is deliberate (Option B 4.4;
  `test_marks_autosave.py:469-471`), but it means a hung second request could leave the row saying
  Saved for a long time.
- The marks block handles the stale-reply case (`erp.js:1038-1043`).

Whether the attendance row *should* behave like marks is a product decision (OD-JS15). Fixing it
is outside the testing PR (OD-JS11).

**F-JS2: the attendance block changes an HTMX global.** It assigns
`htmx.config.responseHandling` (`erp.js:588-594`). That is by design (Option B 4.4 kept it), but
every test needs a fresh page, or the setting leaks between tests.

**F-JS3: jsdom gaps (relevant only to the DOM options).**

- **`matchMedia`.** jsdom has none. `erp.js:352` calls it unguarded in the middle of the main IIFE
  (which starts at `:145`). Without a stub, that call throws and stops the rest of `erp.js`. It is
  also called at `:33-37` (only when measurement is on) and at `:1489` (only when the install bar
  exists).
- **Other missing APIs.** jsdom also lacks `scrollIntoView` (`:1264` is unguarded),
  `URL.createObjectURL` (`:1249`) and `navigator.clipboard` (`:1611`, guarded).
- **No CSS or layout.** jsdom has no layout and loads no CSS.
- **Change on blur (inference).** jsdom does not fire `change` when focus leaves a field, so the
  marks "Next moves on, leaving the field saves it" flow cannot run there as it does in a browser.
- **Swallowed errors (inference).** Errors thrown inside event listeners go to jsdom's virtual
  console, not to the test. A DOM harness must turn them into failures.

**F-JS4: two handlers share one key press.** Score inputs carry `enterkeyhint="next"`
(`core/forms.py:926`).

- An Enter on a score first runs the sign-in "Next" helper on the field (`erp.js:175-186`).
- The marks handler on the sheet runs next (`:797-818`). It puts focus back on the last row's score
  (`:812`) and triggers that row's save when the value changed (`:813`).
- On other rows, the save comes from the `change` event the browser fires when focus moves on. That
  is a real-browser behaviour.

**F-JS5: string tests missed a race that review caught.** The "older reply must not show Saved"
rule in marks came from B1 review, not from a test (`test_marks_autosave.py:543-545` comment). Its
current guard checks four lines of text.

## 4. Options compared

Common ground:

- Every option that runs JavaScript needs either Node or a browser engine, so every option except
  Option 4 needs ADR 0028.
- Each one loads the unchanged `erp.js` with hand-written fixture HTML (section 7.5).

**Isolation constraint.** `erp.js` attaches listeners to `document` and `window`, starts a
30-second interval (`:99`) and changes an HTMX global (`:588`). None of these can be removed
afterwards, so isolation needs **a fresh page per test**.

- **In a browser (Option 5):** a new page per test does this naturally.
- **In jsdom (Options 1 and 2):** each test needs a fresh window, and the runner's fake timers
  (`vi.useFakeTimers`, `node:test` `mock.timers`) patch the runner's own global, not that window.
  The harness therefore installs `@sinonjs/fake-timers` on the window (`withGlobal(window)`), which
  is the library Vitest uses internally.

Under this constraint the jsdom harness is the same whichever runner is chosen, and the reviewer
agreed with that reading.

### Option 1: Vitest + jsdom

| Aspect | Assessment |
| --- | --- |
| DOM and events | jsdom through a per-test `JSDOM`. Vitest's own `environment: "jsdom"` gives one window per file, which leaks listeners here (F-JS2), so it does not apply. |
| Fake timers | `vi.useFakeTimers` covers the test global only. `@sinonjs/fake-timers` on the window is needed anyway. |
| Fetch, races | `vi.fn` with deferred promises; a controllable fake XHR is hand-written (Vitest has none). |
| Non-module `erp.js` | Loaded as text, so Vite never transforms it. Test files do go through Vite's transform pipeline. |
| Browser fidelity | jsdom only (F-JS3): no change on blur, no CSS, no dialogs, no `matchMedia`. |
| Size and maintenance | Vitest 5 needs Vite ≥ 6.4 as a peer and Node ≥ 22.12. Vite brings native platform binaries (esbuild, and a Rollup or Rolldown binary). npm's handling of platform optional dependencies in lockfiles (npm/cli#4828) is a known cause of "Cannot find module @rollup/rollup-linux-x64-gnu" when a lockfile made on Windows is installed on Linux CI, which is exactly this repo's setup. Majors arrive about yearly. |
| CI runtime | Estimate: install 15-30 s cached, tests a few seconds plus 2-5 s startup. |
| Strengths | Best assertion diffs, watch mode, GitHub Actions reporter, familiar to JavaScript developers. |
| Architectural fit | Vite is a bundler and dev-server toolchain. As a test runner only it fits ADR 0028's boundary, but it is the dependency most easily read later as "we have Vite, so let's bundle". |

### Option 2: `node:test` + jsdom

| Aspect | Assessment |
| --- | --- |
| Runner dependencies | None. `node:test` and `node:assert` ship with Node. |
| Other dependencies | `jsdom` and `@sinonjs/fake-timers`, both plain JavaScript with no native binaries, so no cross-platform lockfile trap. |
| Harness code | Page loader, fake XHR, fetch stub, `matchMedia` and other stubs, and a virtual console that fails tests on errors. Estimate 250-350 lines. |
| Browser fidelity | jsdom only (F-JS3). Change on blur, focus on hidden elements, CSS, dialogs and Bootstrap branches need workarounds or a later browser layer. |
| Runtime | Fastest: install 10-20 s cached, tests a few seconds. |
| Toolchain | Node and npm in the repo (`tests/js/`), with lockfile, Node version pin and Railpack boundary. |
| Later journeys | Still need a second tool (Playwright) for whole journeys (section 12). |

### Option 3: Playwright against a running Django server

| Aspect | Assessment |
| --- | --- |
| Fidelity | Real browser and real server. |
| Server and data | Django against PostgreSQL with seeded users, classes and assessments for each test (`StaticLiveServerTestCase`). |
| Runtime | Estimate: 60-80 behaviours at 2-5 s each is 3-7 minutes. Too slow for drafts. |
| Verdict | Right for three to five whole journeys (section 12). Wrong as the only layer. |

### Option 4: keep source-string tests and manual checks

- **Cost:** none now.
- **Risk:** string tests confirm that text exists, not that it works. F-JS1 passes every current
  test, and F-JS4's end state is untested. Variable renames break tests without a bug.
- **Coverage gap:** manual phone checks are not repeated on each change, and the file had 40
  commits in a month.
- **What stays hard to catch:** reply ordering, timers (session warning, 30 s flush, 6 s
  auto-hide), queue limits, per-event device labels, focus after Enter, storage exceptions, and
  401 handling in each sheet.

### Option 5: browser fixture tests with Python Playwright (no server)

| Aspect | Assessment |
| --- | --- |
| How | Python Playwright (one pip package, pinned like the rest of the stack) drives headless Chromium. Each test opens a fresh page at `https://erp.test/…`. `page.route` serves the hand-written fixture HTML plus the unchanged `static/js/erp.js` and vendored `htmx.min.js` from disk, and intercepts every other request. No Django server, database or seed data. |
| Races | The route handler holds autosave requests. The test then fulfils them in any order (`route.fulfill`) or never answers. Network failures are made on arrival (`fail_on_arrival`): aborting a request after its handler has returned crashed Chromium 156 in JS1. |
| Time | `page.clock` (installed before the page loads) controls `setTimeout`, `setInterval`, `Date` and `performance.now` for the 30 s flush, 6 s auto-hide and session timers. The XHR timeout is not a JavaScript timer. For the 15 s marks timeout, the fixture uses a short timeout value, recorded as the one documented exception in the fixture contract (section 7.5). |
| Fidelity | Real engine: change on blur, real focus and visibility, `matchMedia` from the viewport (360-390 px and desktop), native `<dialog>`, CSS (fixture can link `erp.css`), real HTMX request, queue and swap order. Errors surface through `page.on("pageerror")`, which fails the test. |
| Gaps | Same as any browser automation: the real install prompt, real keypad "Next", and OS sleep or wake. Display mode `standalone` and Global Privacy Control are set with small init scripts. |
| Runner | Plain `unittest` (no Django, no database) in `browser_tests/`, run with `python -m unittest discover -s browser_tests -p "bt_*.py" -t .`. Django's `SimpleTestCase` fails at teardown once Playwright's event loop is running (found in the spike). The `bt_` prefix keeps the files out of Django's `test*.py` discovery, so the normal suite never needs a browser. |
| Dependencies | `playwright` (pip) plus the Chromium build matched to that package version, downloaded by `python -m playwright install --with-deps chromium`. The Python package ships its own internal driver. The repository has no project-managed Node/npm toolchain, package manifest, build pipeline or production dependency. |
| Production boundary | The package goes in a separate `requirements-browser.txt`, never in `requirements.txt`, which is the file Railway installs. A boundary test enforces this. |
| Runtime | Estimate: one browser launch per job (about 1 s), then about 100-300 ms per test with a fresh context and page, so roughly 10-20 s for the first packages. CI install takes about 60-90 s uncached, and the target with the browser cache is a draft run under 90 s in total (section 9). |
| Later journeys | The same tool covers the deferred whole-journey tests (section 12). The final stack gains one tool instead of two. |
| Weaknesses | A browser download: the headless shell in CI (cached by version); the full local install measured 719 MB. Slower than jsdom. Browser updates arrive with each Playwright version (only when the pin is moved). Windows contributors also install Chromium locally. |

### Summary

| | 1 Vitest + jsdom | 2 node:test + jsdom | 3 Playwright + server | 4 Status quo | 5 Playwright fixtures (pip) |
| --- | --- | --- | --- | --- | --- |
| Catches races and timer bugs | Yes | Yes | Yes, slowly | No | Yes |
| Change on blur, dialogs, CSS, real focus | No | No | Yes | — | Yes |
| Production change | None | None | None | None | None |
| Toolchain the repo manages | Node, npm, lockfile | Node, npm, lockfile | pip package + browser | — | pip package + browser |
| Direct new dependencies | 4 (vitest, vite peer, jsdom, fake-timers) | 2 | 1 + browser | 0 | 1 + browser |
| Native binaries in a lockfile | Yes | No | No lockfile | No | No lockfile |
| Fits draft CI | Yes (< 1 min) | Yes (< 1 min) | No | Yes | Target < 90 s cached, parallel job |
| Covers later whole journeys too | No | No | Yes | No | Yes |
| Needs ADR 0028 | Yes | Yes | Yes | No | Yes |

## 5. Recommended architecture

### 5.1 Recommendation

**Option 5, subject to the JS1 spike; Option 2 as the fallback.** The product owner approved this
on 2026-11-22 (OD-JS1 A).

1. Browser fixture tests with Python Playwright and headless Chromium: one browser process per
   test job, with a fresh browser context and page per test. They load the **exact served files**
   (`static/js/erp.js`, vendored HTMX) unchanged, with no Django server.
2. A test-only pip dependency in `requirements-browser.txt`, outside `requirements.txt`. The
   repository gets no project-managed Node/npm toolchain, package manifest, build pipeline or
   production dependency. There is no build, bundle, transpile or generated asset, and nothing
   under `static/` changes.
3. Django tests keep server rules, permissions, rendered attributes and the policy guards.
4. Later, after its own decision, three to five whole-journey tests with the same tool against a
   live Django server (section 12).
5. Source-string behaviour stand-ins are removed only when an equivalent behavioural test lands
   (section 11).

**Why Option 5 over the expected Vitest + jsdom recommendation:**

- **Fidelity where it matters.** The main marks save trigger is the browser firing `change` when
  focus leaves a score (F-JS3, F-JS4; Option B OD-B2). jsdom does not do that. Dialogs, CSS-driven
  hiding, `matchMedia` and real focus also come free.
- **It answers the stack change rule more directly.** It stays within the current stack (Python,
  pip, `unittest`) and adds one pinned package and a browser. ARCHITECTURE asks why the
  problem cannot be solved within the current architecture. With Option 5 it mostly can.
- **One tool, not two.** The hybrid plan already expects a browser layer later. With Option 5 that
  layer is the same tool, so the repository ends with one new test tool.
- **No project-managed Node toolchain to police.** No `package.json`, lockfile, Node version pin,
  npm optional-dependency trap or Railpack detection question. Playwright's internal driver is a
  detail of the pip package, not a Node stack the repository maintains.

- **Vitest adds the least.** Under the per-test-page constraint its jsdom environment and timers do
  not apply. What remains is ergonomics, bought with a Vite peer and native binaries.

**What these tests are not.** They run the real `erp.js` and real HTMX against representative,
hand-written DOM fixtures. They do not render Django templates, so they are not full-page,
template or visual-regression tests. Template drift is caught by the fixture contract
(section 7.5). Rendering and permissions stay with Django tests.
**When Option 2 is better.** If the spike shows the browser install or runtime breaks the CI budget,
or that holding routes is unreliable, Option 2 is the fallback. Its harness is fully specified in
section 7.3. Option 2 is faster and has no browser download, but gives lower fidelity and still
leaves a second tool for whole journeys.

### 5.2 Who tests what (no duplication)

| Layer | Owns | Does not own |
| --- | --- | --- |
| Django tests | Permissions, refusals, server validation, conflict and idempotency rules, 401 middleware, measurement store and enums, rendered attributes, no-JS form posts, policy guards over `erp.js` text, fixture contract | Client state, reply ordering, focus, timers |
| Browser fixture tests (Option 5) or DOM tests (Option 2) | What `erp.js` does with given HTML and given replies: row states, requests sent and their bodies, focus, timers, queue rules, storage failures, accessibility attributes it sets | Whether the server sends those replies; real devices |
| Whole journeys (later) | That the real server, real HTMX and a real browser agree end to end on a few journeys | Every branch or every rule |

The link between Django and the client layer is the **fixture contract** (section 7.5).

## 6. Production boundary and testability

### 6.1 Seam options

| Option | Production change | Risk | Verdict |
| --- | --- | --- | --- |
| A. Load the classic script unchanged into a controlled page | None | Fixtures can drift from templates (handled by section 7.5) | **Recommended** (both Option 5 and Option 2) |
| B. Expose a test-only hook (for example `window.__erpTest`) | Ships test code to every user | A hook can be called in production | Not needed: behaviour is observable through the DOM and the intercepted requests |
| C. Extract small pure helpers inside the one classic script | Refactor of High-tier code | Low, but unprotected until behavioural tests exist | Defer; optional later |
| D. Split `erp.js` into directly served ES modules | Templates and script order change; module scripts are strict and scoped differently | Highest; globals `erpUsage`/`usageHeaders` and listener order shift | Rejected for this work. Needs its own decision. |

### 6.2 With seam A

- **Production files changed:** none. That covers `erp.js`, templates, settings, `static/vendor/`
  and `requirements.txt`.
- **Script order, `defer`, classic globals, HTMX events:** unchanged. Fixtures use the same
  `<script defer>` order as `templates/base.html:64-66`, so in a browser (Option 5) the engine runs
  them exactly as in production. The jsdom fallback has to reproduce the order itself (section
  7.3).
- **Bootstrap:** fixtures that cover the auto-hide (row 11) or offcanvas (row 8) load the vendored
  Bootstrap bundle, because `erp.js:359-363` takes a different branch without it. Other fixtures
  leave it out.
- **No-JavaScript fallback:** untouched. The no-JS paths stay covered by Django tests (for example
  `test_ui_teacher_marks.py:115`, `test_marks_autosave.py:266`, `:560`).
- **Rollback:** a single revert removes the browser tests, `requirements-browser.txt`, the CI job,
  the policy, boundary and contract tests, and the docs and AGENTS.md lines. Production, Railway
  and the Django suite are unaffected. String tests retired in later PRs come back with that PR's
  revert.

## 7. Test harness design

Proposed only; file names are recommendations.

### 7.1 Spike (first task of JS1, time-boxed to one day)

The spike **passes only if** it shows all of the following (product-owner conditions, 2026-11-22):

1. **Blur and change autosave.** Typing a score and moving focus away fires the real `change`
   event, and the row is saved through HTMX.
2. **Delayed and reordered replies.** HTMX XHR requests and `fetch` requests (bulk present, usage
   flush, session check) can be held, answered later and answered out of order, from the
   synchronous API. Aborting a request produces HTMX's `sendError`.
3. **Controlled time.** `page.clock` controls the 30 s interval, `setTimeout`, `Date` and
   `performance.now` when installed before the page loads. The marks timeout path is reached with
   the fixture's short timeout (section 7.5).
4. **Page-hide flush, GPC and storage.** `erp.js` does not use `navigator.sendBeacon`. Its usage
   flush is a `fetch` with `keepalive: true` sent when the page becomes hidden (`erp.js:79-82`,
   `:96-98`). The spike must show that this request is intercepted on `visibilitychange` to
   hidden. Headless Chromium does not hide pages by itself, so overriding `document.visibilityState`
   and dispatching `visibilitychange` is acceptable. If `page.route` does not see the `keepalive`
   request, `context.route` is an acceptable alternative. It must also show that Global Privacy
   Control can be switched on and that `localStorage` can be read, cleared and made to throw.
   Tests pause the page clock, which also pauses HTMX's own swap and settle timers, so they
   advance the clock explicitly after each reply.
5. **Repeatability.** The spike tests pass 10 consecutive runs on Windows and on the GitHub Linux
   runner.
6. **No real network.** Every request outside `https://erp.test/` is aborted and fails the test,
   and no external request appears in the run.
7. **Speed.** A cached draft run of the job finishes in under 90 seconds.
8. **Diagnostics.** A deliberately failing test saves a Playwright trace and screenshot as a CI
   artifact (section 7.6).
9. **Boundary.** No root `package.json`, no production build change and no Railway change.

If any condition fails, report it to the product owner before doing anything else. The likely
fallback is Option 2 (section 7.3). Switching would change an approved decision, so it is not done
without the owner's word. ADR 0028 stays Proposed until the spike passes. The JS1 PR then records
the spike evidence and moves the ADR to Accepted.

### 7.2 Option 5 harness (`browser_tests/support/`)

- **`FixturePage` context:** opens a new browser context and page per test, with these settings:
  - the viewport from the test (390 × 800 phone, 1280 × 900 desktop);
  - `page.clock.install()` before navigation;
  - small init scripts only where the browser cannot be configured otherwise:
    `navigator.globalPrivacyControl`, `(display-mode: standalone)`, and a throwing `localStorage`
    for the storage-failure cases;
  - a `page.on("pageerror")` hook that collects errors. `tearDown` asserts the list is empty,
    because an exception raised inside the handler would not fail the test in the synchronous API.
- **Router:** serves `https://erp.test/<fixture>` from `browser_tests/fixtures/` and
  `/static/...` byte-for-byte from the repository's `static/` folder. It records every other
  request (method, URL, headers, body) and holds it for the test. The test can answer it,
  or leave it pending.
- **Real network blocked:** any request outside `https://erp.test/` is aborted and fails the test.
- **Browser lifetime:** one browser process per test job. It is started on first use by the
  support module and closed when the run ends. Every test gets a **fresh browser context and
  page**, closed in `tearDown`, so cookies, `localStorage`, `sessionStorage`, permissions and
  init scripts never carry over. The tests run without `--parallel`, so there is one process.

### 7.3 Option 2 harness (fallback, `tests/js/support/`)

- **Window:** a fresh `JSDOM` per test with a VirtualConsole that **fails the test on `jsdomError`
  or any uncaught error**.
- **Before scripts run:** install `@sinonjs/fake-timers` on the window, stub `matchMedia` from the
  test's width, define `globalPrivacyControl` and `userAgent`, install the fake XHR (around 100
  lines, answers in any order, honours `timeout`) and the fetch stub, and add a no-op
  `scrollIntoView`.
- **Load order:** evaluate vendored HTMX and then `erp.js` while `readyState` is still `loading`,
  and wait for jsdom's own `DOMContentLoaded` and `load`. The harness never dispatches them itself,
  so nothing runs twice. The Option 2 spike confirms this.
- **Fidelity limits:** focus assertions only on visible targets. Change on blur is simulated by
  dispatching `change` explicitly; those cases are marked as needing the whole-journey layer for
  real confirmation.
- **Package:** `tests/js/` with its own `package.json`, exact pins, committed lockfile, `.nvmrc`;
  details in section 10.4.

### 7.4 Assertions

Tests assert what a person or the server would see:

- the row status text and classes such as `is-unsaved`;
- `aria-*` values;
- the focused element;
- requests sent and their bodies;
- storage writes.

They never read private properties such as `row._seq`. A test that needs an internal value points
to a missing observable and should be raised in review.

### 7.5 Fixtures and the fixture contract

Fixtures are representative, not the production page. They hold just enough DOM for the
behaviour under test. Passing tests show that `erp.js` and HTMX behave correctly on that DOM, not
that a full Django page renders or looks right.

**Fixtures** are hand-written minimal HTML copied from the real templates' structure:

- an attendance roster with 3 rows;
- a marks sheet with 3 rows and base inputs;
- the session box;
- the install bar;
- the password form.

**Fixture contract test** (Django, proposed `core/tests/test_js_fixture_contract.py`). It renders
the real marks-entry and attendance pages from existing test fixtures. For every `data-erp-*`
attribute and every `hx-*` attribute in the matching fixture, it compares **names and normalised
values**: URLs become `<url>` and primary keys become `<pk>`, so a fixture that changes
`hx-sync="this:queue last"` to `replace` fails.

- **Exception:** the marks timeout value. The fixture's short `hx-request` timeout is listed as
  that one exception, with the production value asserted separately.
- **Other checks:** the hidden base input naming pattern, and the `X-ERP-Row-Fragment` header the
  fixtures send.
- **Server reply fragments.** `erp.js` also reads the replies: the `X-ERP-Row-Fragment` header
  (`erp.js:983`, `:1015`), `[data-erp-conflict]` with `data-server-status` and `data-server-score`
  (`:1045`, `:1115-1118`), the Use mine and Keep theirs controls, and the status fragment's root
  classes. The contract renders `_marks_autosave_status.html` and `_attendance_autosave_status.html`
  (saved, conflict and refused states) through the real views. It compares their marker
  attributes and classes with the hand-written reply fixtures. It also checks that the 401 body
  from `accounts/middleware.py` matches the fixture's.
- **What it does not do:** it reads the committed fixture files. It never writes files or starts a
  browser.

### 7.6 Privacy in fixtures and output

- **Synthetic data only.** Fixture names are obviously synthetic ("Student A", "Student B"), and
  enrollment IDs are small fixed integers. No HTML is captured from staging or a real school.
- **Payload checks.** Usage tests assert the exact key set of each payload (`a, d, e, p, r, x`;
  events `w, s, b, z`) and that values come from the ADR 0027 enums.
- **Canary.** A student name and an enrollment ID in the page (the canary) must never appear in any
  usage request body.
- **Failure diagnostics.** A failing test saves a Playwright trace, a screenshot and a records file
  (page errors, blocked requests, unservable requests, held request paths). CI uploads them as an
  artifact only when the browser test step did not pass, kept for 7 days. They contain only the synthetic
  fixture page and its intercepted requests: no Django page, no session, no staging data. Passing
  tests save nothing. Request bodies may appear in a failure message, and they are always
  synthetic fixture data. Artifacts are visible only to people who can read the repository. The
  later live-server journeys must not reuse this capture unchanged, because it would record
  session cookies and seeded data. They need their own rule.
- **Logging.** No test logs a request body on success.

## 8. Coverage packages

Each case says which layer owns the server half. "C7 exists" means a Django test already covers
it (section 3.2).

### 8.1 JS1 (harness) and JS2 (save-path coverage)

JS1 contains the spike, the harness, the CI job and the harness self-checks listed at the end of
this section. JS2 adds the marks and attendance cases below.

**Marks autosave** (`browser_tests/bt_marks_autosave.py`, JS2)

| Case | Asserts | Server half |
| --- | --- | --- |
| M1 Older reply cannot overwrite a newer edit | Change row (A), change again (B); answer A with 200 "Saved"; row shows "Saving…"; answer B; row shows Saved | C7 exists |
| M2 Row stays "Saving…" while a newer request is active | As M1, plus the page line reads "Saving…" until B is answered | — |
| M3 Lost reply, then Retry, no misleading conflict | A times out (fixture timeout, section 7.5) or is aborted; row shows "Not saved: no connection." with Retry; Retry's request carries the **original** base values | C7 exists: `AutosaveIdempotentRetryTests` (`test_marks_autosave.py:277-354`) |
| M4 Distinct failure states | Network, timeout, 500, 422 fragment, 409 conflict fragment, 403 fragment, 403 without the header (CSRF), 401: each gives its approved text; Retry only for network, timeout and 5xx; `erp:signed-out` only for 401 | C7 exists |
| M5 Retry resends only the affected row with its base | Two failed rows; Retry on one sends one request whose body holds only that row's `enrollment`, `status_`, `score_`, `base_status_`, `base_score_` | — |
| M6 Fallback never submits the whole form | Form submit in JavaScript mode is prevented; only `retry`-state rows are resent to the autosave URL; with rows in flight it waits, then resends | C7 exists for the no-JS post |
| M7 Use mine / Keep theirs | After a 409 fragment: Keep sets base inputs, radio and score to the server value and sends nothing; Use mine sets the base inputs and sends the teacher's value | C7 exists |
| M8 Enter and Next | Typing a score and pressing Enter on a middle row moves focus to the next score, and the row left is saved through the browser's `change`; on the final row focus stays in that score and one request is sent only if the value changed | — |
| M9 Marked without a score sends nothing | Choose Marked with an empty score: no request; row shows "Enter a score or choose Absent."; a later older reply does not hide it | C7 exists (`test_marks_autosave.py:193`) |

**Attendance** (`browser_tests/bt_attendance_autosave.py`, JS2)

| Case | Asserts | Server half |
| --- | --- | --- |
| A1 Latest choice wins (OD-JS15) | The teacher changes a row (A), then changes it again (B) while A is in flight. A's reply, whether success or failure, never replaces B's state: the row stays "Saving…", no "Saved {name}." is announced for A, and the next request sent carries B's value. When B's reply arrives, the row shows B's result. **Not in JS2.** JS2 records F-JS1 in its PR description and in GitHub issue [#289](https://github.com/Joseph5157/school-erp/issues/289) as a confirmed, uncovered defect, with no expected-failure test, so `main` holds no expected failures. JS3 adds this test (section 8.2). | — |
| A2 Mark unanswered as present never overwrites | Rows Absent, unanswered, unanswered: only the two unanswered rows become Present; the Absent row and its note are untouched; one bulk request lists exactly those two enrollments | C7 exists |
| A3 401 never shown as saved | Row save answered 401: "Not saved: you have been signed out.", never Saved; `erp:signed-out` fires; the session box shows its signed-out state; same for bulk present through `fetch` | C7 exists (`test_session_errors_audit18.py:196-249`) |
| A4 Typed values remain after sign-out | An absence note typed before a 401 stays in its field and the chosen radio stays checked | — |
| A5 No-JavaScript behaviour unchanged | Without HTMX on the page the roster shows the unsaved warning and sends no request. The no-JS form post itself stays covered by Django tests | C7 exists |

**Harness self-checks** (`browser_tests/bt_harness.py`, JS1):

- a fresh context and page per test (a `localStorage` value and a listener from one test are
  absent in the next);
- the clock controls the 30 s interval (fixture with `data-erp-usage="1"`);
- the served `erp.js` is byte-identical to the file on disk;
- a deliberately thrown page error fails the test;
- a request outside `https://erp.test/` fails the test.

Expected size: about 5 self-checks in JS1 and about 20 cases in JS2.

### 8.2 JS3: fix for F-JS1

This is a separate PR after JS2, because F-JS1 is an existing product defect (OD-JS11).

- **Target behaviour (OD-JS15).** The latest choice wins in the interface and in the database.
  While an earlier save for a row is in flight, the row stays "Saving…". The older reply is
  ignored for display: no "✓ Saved", no "Not saved.", no announcement. The latest selection is
  sent as soon as the earlier request finishes.
- **Client design.** One in-flight request per attendance row, with at most one pending value,
  which a newer change replaces. `hx-sync="this:queue last"` already gives this request pattern
  (`_attendance_capture_table.html:19`). The fix is in how `erp.js` treats a stale reply's swap and
  `htmx:afterRequest` (`erp.js:621-659`), following the marks pattern (`:1038-1043`, `:1064`).
- **What does not change.** No timeout is added to attendance. That is a separate question, and
  `test_marks_autosave.py:469-471` stays green.
- **Test first, then the fix.** JS3 is built in two commits:
  1. The first commit adds only the A1 regression test (section 8.1). Its `js` job run on the
     draft PR (or a recorded local run) must show A1 **failing** against the old behaviour.
  2. The second commit implements the fix and leaves A1 passing.

  The PR description links both runs as the evidence that the test proves the bug. It is not
  merged until A1 passes. No expected-failure marker is ever used.

### 8.3 JS4: privacy-safe usage measurement (`bt_usage.py`)

| Case | Asserts |
| --- | --- |
| U1 GPC | `globalPrivacyControl` true: nothing queued, nothing sent. Turned on after queueing: the next flush empties the queue without sending (`erp.js:74`) |
| U2 Measurement off | No `data-erp-usage`: no request at any point, including after 30 s and on `visibilitychange` |
| U3 Queue cap | 25 events queued; the sent batch holds the newest 20 |
| U4 Requeue | Network abort and 500: the same events are sent at the next flush moment |
| U5 Refused batches | 400, 401 and 403: events dropped and never resent |
| U6 Device at event time | Event at 390 px, viewport changed to 1280 px, then flush: sent with `d: "phone"` |
| U7 Separate sends per device state | Mixed events go out in separate requests, each with one `d/x/p` set |
| U8 No personal data | Exact key set; canary name and ID absent; route and area only from body attributes |
| U9 Duration buckets | Teacher home and marks `completed` events carry the ADR 0027 buckets at boundary times (4.9, 5, 15, 60, 180, 600, 1800 s) |
| U10 30-second flush | Nothing sent at 29.9 s, one send at 30 s |

JS4 must be merged before any school switches measurement on (OD-JS5).

### 8.4 JS5 (later, not yet scheduled): PWA and common interface

- **Install bar.** Shown only at phone width outside standalone mode. `shown` is counted once per
  page view, and `dismissed` is counted only from "Not now" (`erp.js:1539-1544`). `installed` comes
  only from `appinstalled`. Cancelling the browser's prompt stores the 30-day mark
  (`:1533-1537`) but records no `dismissed` event; the spec pins this existing behaviour, it does
  not change it. With `erp.css` linked, the bar stays hidden at 768 px and wider.
- **Install button on the help page.** Shown on a synthetic `beforeinstallprompt` and hidden after
  use.
- **Password page.** Show/hide keeps `aria-pressed` and the hidden field name. The match line is
  announced on leaving the field. `enterkeyhint="next"` moves focus and respects IME composition.
- **Session warning.** Schedules at idle minus 120 s and asks the server before warning. Then the
  countdown; Stay posts and reschedules. Covers the signed-out state, the login link's
  `next`/`expired` values and the 30 s retry when offline.
- **Sidebar.** A throwing `localStorage` (get and set) never breaks the page, and pinned groups
  ignore storage.
- **Other.** The unsaved-changes warning, one-shot buttons, and message auto-hide with Bootstrap
  loaded.

### 8.5 Not planned

- **Real install prompt, real phone keypad, OS sleep or wake:** stay manual.
- **Timetable strip centring and order-dialog drag:** possible in Option 5, but low value. Left for
  later.

## 9. CI design

Implemented in JS1 (`.github/workflows/ci.yml`, job `js`). The table describes Option 5 as built.
Section 9.1 gives the differences for Option 2.

| Item | Proposal |
| --- | --- |
| Job | New job `js`, beside `lint` and `test`, with no `needs:` either way, so it runs in parallel and adds nothing to the full suite's time. |
| When (path-aware) | Docs-only PRs skip the whole workflow, as today (`paths-ignore`). On other PRs, drafts included, the job checks out with `fetch-depth: 0`. Its first step runs `git diff --name-only "$BASE_SHA" "$GITHUB_SHA"` with `BASE_SHA` set to `github.event.pull_request.base.sha`. The install and test steps run only when a relevant path changed. They always run on pushes to `main`. **The check fails closed:** if the base SHA is missing or the diff cannot be computed, the step sets "run", and the tests run. Relevant paths: `static/js/**`, `static/vendor/**`, `static/css/**`, `browser_tests/**`, `requirements.txt`, `requirements-browser.txt`, `config/**`, `manage.py`, `.github/workflows/**`. Templates and `core/forms.py` are not listed, because the browser tests use hand-written fixtures. Template and form drift is caught by the fixture contract test (section 7.5), which runs in the `test` job, draft safety included. When the steps are skipped, the `js` check still reports success, so whether the job applied is read from its test step. A plain shell step is used, so no third-party path-filter action is added. |
| Setup | The job has `permissions: contents: read`. `actions/setup-python@v5` (3.13, pip cache on `requirements-browser.txt`); `pip install -r requirements-browser.txt` only; restore `~/.cache/ms-playwright` keyed on that file; on a cache miss `python -m playwright install --with-deps --only-shell chromium`, on a hit `python -m playwright install-deps chromium`. |
| Run | `python -m unittest discover -s browser_tests -p "bt_*.py" -t .`. The job installs only `requirements-browser.txt` and the headless shell (`--only-shell`); it needs no Django settings, database or `requirements.txt`. |
| Settings | None: the browser tests do not import Django. The Django fixture-contract and boundary tests run in the `test` job (next row). |
| Draft-safety additions | `core.tests.test_js_toolchain_boundary` and `core.tests.test_js_fixture_contract` join `DRAFT_SAFETY_TESTS` in the `test` job. |
| Failure reporting | A failing test saves a screenshot, a Playwright trace and a records file (page errors, blocked real-network requests, requests the harness could not serve, and the held requests' method and path). The test step has a 5-minute timeout inside the job's 10, so a hung run is stopped while the job can still upload. The upload step runs `if: always()` whenever the test step did not succeed, and keeps the artifact for 7 days (section 7.6). A job killed by its own timeout would upload nothing, which is why the step timeout exists. Each Playwright call also times out after 10 seconds, so a stuck test fails, and saves its diagnostics, long before that. |
| Budget | A cached draft run under 90 seconds wall-clock. An uncached run (new Playwright version) may take longer. Over budget is a bug to fix, not a reason to move the job. |
| Policy guard | Extend `core/tests/test_ci_policy.py` (already in `DRAFT_SAFETY_TESTS`). It checks that the `js` job exists, has no job-level `name`, `if`, `needs` or `continue-on-error`, has only `contents: read`, and that the test step's `run:` line is exactly the command above, with no `continue-on-error`, `shell` or `working-directory`. It checks that the install and test steps are conditioned only on the path check, that the path check fails closed, and applies the relevant-path pattern to sample paths that must and must not run the tests. It also checks the step timeout is at least 3 minutes inside the job's, and the upload condition and retention. |
| Test-content guard | New `core/tests/test_js_toolchain_boundary.py`, added to `DRAFT_SAFETY_TESTS`. It checks that each browser test file listed in this spec, once its PR has merged, exists and defines at least its listed number of test methods. No skip or expected-failure marker in any spelling (`skip`, `skipIf`, `skipUnless`, `skipTest`, `SkipTest`, `expectedFailure`, pytest `skip` or `xfail`, and similar) may appear anywhere in `browser_tests/`, so `main` never holds skipped or expected-failing browser tests. `requirements.txt` must not contain `playwright`, and no `package.json` or `node_modules` may exist at the repository root or under `static/`. |
| Merge gate (OD-JS7, approved) | When the path-aware `js` job applies, a PR is verified only when that job passes on the exact approved head. A skipped `js` job is not required. Pushes to `main` always run it. The docs PR writes this rule into `AGENTS.md` (Verification), `IMPLEMENTATION_WORKFLOW.md` section 11, `DEFINITION_OF_DONE.md` state 2 and the PR template, worded to apply from JS1 onward. A skipped job still reports `js` as passed, so whether it applied is read from the test step's conclusion (`gh run view <run-id> --json jobs`). |
| Required checks | None on `main` today. Unchanged here. |
| Railway | No change. Railpack installs `requirements.txt` only; no browser or Playwright package reaches staging or production (section 10.3). |

### 9.1 If the fallback (Option 2) is needed

The job keeps the name `js` and the same path rules, and uses `actions/setup-node@v4` with `node-version-file: tests/js/.nvmrc`,
an npm cache keyed on `tests/js/package-lock.json`, `npm ci --prefix tests/js --ignore-scripts` and
`npm test --prefix tests/js`. The test script is `node --test` with the spec reporter. Its `junit.xml`
is written outside the repository tree (`$RUNNER_TEMP`) and uploaded only on failure. That upload
step is the one allowed `if:`.

The budget is 2 minutes. The policy and boundary guards are the same, with these additions:

- `.only`, `{ skip }` and `{ todo }` are forbidden;
- the reporter's summary must show at least the expected number of tests.

## 10. Dependencies and maintenance

### 10.1 Option 5

- **New file `requirements-browser.txt`.** It holds one exact pin, `playwright==<version>`, chosen
  in JS1 from releases at least two weeks old. Its own dependencies (`greenlet`, `pyee`) are pinned
  there too, matching the pinned-pip rule.
- **Browser.** Chromium only, at the build that version of Playwright expects. Moving the pin moves
  the browser.
- **Updates.** A deliberate PR at least every three months and on relevant advisories (OD-JS9).
  An update changes `requirements-browser.txt`, which triggers the `js` job and the normal
  `lint` and `test` jobs.
- **Local setup (Windows).** `pip install -r requirements-browser.txt`, then
  `python -m playwright install chromium`. It is documented in `docs/engineering/README.md#commands`.
  Contributors who never touch `erp.js` can skip it; CI runs the job whenever a relevant path
  changes (section 9).
- **Harness code.** About 150-250 lines (page context, router, assertions helpers).

### 10.2 Node version (Option 2 or Vitest only)

- **Release status.** Node 26 has been Active LTS since 2026-10-28 and is supported until
  2029-04-30. Node 24 is in maintenance until 2028-04-30. Node 22, on the owner's machine today
  (v22.17.0), ends on 2027-04-30. The official release schedule is the primary source (section
  18); the dates come from a secondary summary of it.
- **Pinning.** OD-JS8 chooses between three options:
  - Node 26, with the major pinned and `engine-strict`; `npm ci` then refuses Node 22 and 27, so
    the owner would install Node 26;
  - `>=24` without `engine-strict`;
  - an exact patch pin.

### 10.3 Production boundary (Railway)

- **Option 5.** Railpack's Python provider installs `requirements.txt`. The browser dependency lives
  only in `requirements-browser.txt`, which nothing on Railway reads. `browser_tests/` holds no
  served files, and `STATICFILES_DIRS` is `static/` only (`config/settings.py:216`).
- **Option 2.** Railpack detects Node from a `package.json` in the repository root, per its Node
  docs. Keeping the toolchain in `tests/js/` keeps the root free of one. Railpack's order when both
  Python and Node match is not documented, so the spec does not rely on it.
- **Both.** The boundary test (section 9) enforces the rules. After the first merge, the staging
  build log is checked for the Python provider only, no extra install step and an unchanged deploy.

### 10.4 Option 2 package details (fallback)

- **Files.** `tests/js/.nvmrc`, plus `.npmrc` with `save-exact=true`, `ignore-scripts=true` and
  `fund=false`, and `engine-strict` per OD-JS8.
- **`package.json`.** It is `private`, has `devDependencies` only (exact versions of `jsdom` and
  `@sinonjs/fake-timers`), and has no `"type"` field because tests use `.mjs`.
- **Lockfile and install.** `package-lock.json` is committed. `npm ci --ignore-scripts` only.
- **Repository additions.** `.gitignore` gains `node_modules/`. HTMX is never an npm dependency;
  tests load the vendored file.

### 10.5 Security

- **No install-time code from JavaScript packages.** There are none in Option 5, and Option 2 uses
  `--ignore-scripts`.
- **No secrets or database in the job, and no real network.** Every request is intercepted, and any
  other request fails the test.
- **Browser download.** The Chromium build comes from Playwright's own CDN. It is pinned by the
  package version and cached in CI. It never reaches Railway.

## 11. Existing source-string tests

| Kind | Treatment |
| --- | --- |
| Behaviour stand-ins (for example `test_marks_autosave.py:509-551`, the usage flush and device tests in `test_usage_workflows.py:672-703`, `test_pwa_gate1.py:280-286`, `test_session_errors_audit18.py:257-263`) | **Temporary.** Autosave and other behaviour is to be verified by execution. Each stand-in is kept only until the PR that adds equivalent browser coverage. That PR removes it and lists it beside its replacement in the PR description. No removal without a named replacement. |
| Policy guards (marks block has no storage or timers, no `serviceWorker`, every `fetch` sends `X-Requested-With`, events only from enum constants, payload key set, no `abandon` step, HTMX globals untouched by the marks block) | Architectural checks, kept permanently in Django, in the draft-safety set where they already are. Examples are "no global HTMX timeout" and "no `serviceWorker`". They check absences across every path, which a behavioural test cannot. |
| Template and rendered-attribute checks (for example `test_marks_autosave.py:451-492`) | Unchanged: Django's job. |

## 12. Whole-journey tests (deferred)

Not part of this spec's implementation. Recorded so the decision is not lost (OD-JS6).

- **Purpose.** Three to five journeys where the real server, real HTMX and a real browser must
  agree:
  - marks autosave including a two-context conflict;
  - attendance save, `context.setOffline`, then Retry;
  - session expiry reaching the signed-out state (short limits via settings override);
  - a 390 px phone smoke of the teacher home.
- **Tool.** With Option 5 it is the same Python Playwright package in `StaticLiveServerTestCase`
  against PostgreSQL. With Option 2 it is a second tool and needs its own ADR amendment.
- **Where it runs.** Full CI only (Ready and `main`), never draft safety, with its own budget
  (target under 3 minutes for that journey job only).
- **Timing.** Deferred (OD-JS6). Considered only after JS4, and then only a few journeys.

## 13. Product-owner decisions

### 13.0 Product-owner answers (2026-11-22)

| Decision | Answer |
| --- | --- |
| OD-JS1 | A: Python Playwright with fixtures, conditional on the spike (section 7.1) |
| OD-JS2 | A: Chromium only, initially |
| OD-JS3 | A: no production test hooks |
| OD-JS4 | A: ADR 0028 plus a note in `ARCHITECTURE.md`. Both are made in JS1, when the spike has passed and the ADR is accepted |
| OD-JS5 | Marks and attendance first; measurement coverage (JS4) before measurement is enabled |
| OD-JS6 | A: full journeys deferred |
| OD-JS7 | Separate parallel `js` job on relevant code PRs, including drafts (path-aware, section 9). When the job applies, a PR is verified only when it passes on the exact approved head; a skipped job is not required; pushes to `main` always run it. Written into the merge-gate documents by the docs PR |
| OD-JS8 | Deferred unless the fallback is needed |
| OD-JS9 | A: exact pins, reviewed at least quarterly |
| OD-JS10 | A: behaviour source-text tests are replaced only after equivalent browser coverage exists; architectural checks stay |
| OD-JS11 | Feature bugs fixed in separate PRs. A defect found while writing coverage is recorded as a confirmed uncovered defect; its regression test arrives with the fix, shown failing first. No expected-failure tests on `main` (this replaces the "lands marked as pending" wording in option A below) |
| OD-JS12 | A: `browser_tests/` and `requirements-browser.txt` |
| OD-JS13 | A: hand-written minimal fixtures with Django contract checks |
| OD-JS14 | A: the real vendored HTMX |
| OD-JS15 | The latest teacher choice wins. Stale replies never replace newer UI state. One in-flight request per row with one replaceable pending value. No timeout change. Fixed in JS3 (section 8.2) |

The options below are kept as the record of what was considered.

### OD-JS1: Test tool

- A. Browser fixture tests with Python Playwright, no server (Option 5), subject to the spike.
  **Recommended:** highest fidelity for the save paths, no Node in the repository, and the same tool
  serves later whole journeys.
- B. `node:test` + jsdom (Option 2). Fastest, two pure-JavaScript dependencies, lower fidelity, and
  a second tool later. **Recommended fallback** if the spike fails.
- C. Vitest + jsdom (Option 1). Best ergonomics; Vite peer and native binaries.
- D. None (Option 4).

### OD-JS2: Environment

- A. Headless Chromium only for PR 1-3; WebKit and Firefox not run. **Recommended** (follows OD-JS1
  A).
- B. Chromium plus WebKit (closer to iPhone Safari; doubles the browser download and runtime).
- C. jsdom with a fresh window per test (follows OD-JS1 B or C).

### OD-JS3: Production test seam

- A. None: load the unchanged classic script and vendored HTMX. **Recommended.**
- B. Test-only hook in `erp.js`.
- C. Extract pure helpers now.
- D. Split into ES modules. Rejected for this work.

### OD-JS4: Toolchain and the frozen stack

- A. Accept ADR 0028 for a test-only pip dependency and browser, and add a one-line
  cross-reference under "Testing" in `docs/ARCHITECTURE.md` (FROZEN, so the line needs your
  approval). **Recommended.**
- B. Accept ADR 0028 for a test-only Node toolchain in `tests/js/` (if OD-JS1 is B or C), with the
  same cross-reference.
- C. Accept the ADR without touching `ARCHITECTURE.md`, since the ADR outranks it.
- D. Neither: keep Option 4.

### OD-JS5: First coverage package

- A. PR 1 = spike, harness, CI, marks autosave (M1-M9) and attendance (A1-A5). PR 2 = usage
  measurement, **required before any school switches measurement on**. PR 3 = PWA and common
  interface. **Recommended.**
- B. As A, with usage measurement in PR 1.
- C. As A, without the measurement gate.

### OD-JS6: Whole-journey scope and timing

- A. Defer until after PR 2, then decide separately: three to five journeys, Full CI only.
  **Recommended.**
- B. Include them in PR 1.
- C. Never.

### OD-JS7: CI placement, budget and merge gate

- A. A separate parallel job (`browser`, or `js` under Option 2) on drafts and full runs, budgeted
  at 3 minutes (2 under Option 2). Guarded by the policy and boundary tests. Added to the "PR
  verified" rule in `IMPLEMENTATION_WORKFLOW.md`, `DEFINITION_OF_DONE.md` and `AGENTS.md`.
  **Recommended.**
- B. As A, without changing the merge-gate documents (a red job would not formally block "PR
  verified").
- C. Full runs only.

### OD-JS8: Node version (only if OD-JS1 is B or C)

- A. Node 26 with the major pinned and `engine-strict` (the owner installs Node 26).
- B. `>=24`, without `engine-strict`; CI uses Node 26. **Recommended** for less local friction.
- C. Exact patch pin.

### OD-JS9: Dependency updates

- A. Exact pins; a manual update PR at least every three months and on relevant advisories.
  **Recommended:** matches today's pip practice (no Dependabot configured).
- B. As A, plus Dependabot for the new file or folder.
- C. Version ranges.

### OD-JS10: Existing source-string tests

- A. Keep policy guards permanently; remove each behaviour stand-in only with its named
  replacement. **Recommended.**
- B. Keep all string tests permanently.
- C. Remove all once PR 1 lands.

### OD-JS11: Defects the new tests expose

- A. The test lands marked as pending, with an issue link; the fix comes in its own small PR with its
  own review. The testing PR changes no production code. **Recommended.**
- B. Fix in the same PR as the test.
- C. Leave the case out until fixed.

### OD-JS12: Where the toolchain lives

- A. Option 5: `browser_tests/` (top-level package, `bt_*.py`) and `requirements-browser.txt`.
  Option 2: `tests/js/`. Never at the repository root, never under `static/`. **Recommended.**
- B. Browser tests inside `core/tests/` with a `bt_` prefix.
- C. Option 2 only: root `package.json` plus a root `railpack.json` pinning
  `"provider": "python"`.

### OD-JS13: Fixture source

- A. Hand-written fixtures plus a Django contract test comparing names and normalised values.
  **Recommended.**
- B. Fixtures generated from rendered Django pages in CI. That makes the client job depend on the
  database and seed data.
- C. Hand-written fixtures without a contract test.

### OD-JS14: HTMX in the tests

- A. The real vendored HTMX 2.0.4. **Recommended:** this is automatic in Option 5, and the spike
  confirms it for Option 2.
- B. Synthetic `htmx:*` events with hand-built details (Option 2 fallback only).

### OD-JS15: Expected attendance behaviour for F-JS1

- A. Attendance should match marks: an older reply never shows "✓ Saved" or "Not saved." over a
  newer pending change, and the row keeps "Saving…". Fixed per OD-JS11, with no timeout added.
- B. As A, and attendance rows also get the marks 15-second timeout. This changes behaviour Option B
  kept on purpose (`test_marks_autosave.py:469-471`).
- C. Today's behaviour is acceptable. A1 pins it as it is.

No recommendation: this is a product judgement about what a teacher should see. Option A is the
smallest change consistent with the marks sheet.

## 14. PR plan and affected files

PRs are taken one at a time, each merged before the next starts.

| PR | Contents | Files (new unless stated) |
| --- | --- | --- |
| Docs (#287) | This spec (approved) and ADR 0028 (Proposed). The OD-JS7 merge-gate rule. The ADR index is not changed yet | `docs/engineering/JAVASCRIPT_TESTING_IMPLEMENTATION_SPEC.md`, `docs/adr/0028-javascript-behaviour-testing.md`, `AGENTS.md`, `docs/engineering/IMPLEMENTATION_WORKFLOW.md`, `docs/engineering/DEFINITION_OF_DONE.md`, `.github/pull_request_template.md` (edits) |
| JS1 | Spike with its evidence; harness; harness self-checks; path-aware `js` CI job; policy, boundary and fixture-contract tests; commands docs. ADR 0028 moved to Accepted using the spike evidence, the ADR index updated, and the `ARCHITECTURE.md` note added | `browser_tests/support/**`, `browser_tests/fixtures/**`, `browser_tests/bt_harness.py`, `requirements-browser.txt`, `.github/workflows/ci.yml` (edit), `core/tests/test_ci_policy.py` (edit), `core/tests/test_js_toolchain_boundary.py`, `core/tests/test_js_fixture_contract.py`, `docs/engineering/README.md` (edit), `docs/adr/0028-…` (edit), `docs/adr/README.md` (edit), `docs/ARCHITECTURE.md` (edit). The merge-gate documents already carry the `js` rule from the docs PR |
| JS2 | Marks (M1-M9) and attendance (A2-A5) cases. F-JS1 recorded as a confirmed uncovered defect, with an issue and no test; retire the replaced marks and attendance behaviour stand-ins | `browser_tests/bt_marks_autosave.py`, `browser_tests/bt_attendance_autosave.py`, `core/tests/test_marks_autosave.py` and `core/tests/test_attendance_bulk_present.py` (edits, stand-ins only) |
| JS3 | A1 regression test shown failing on the old behaviour, then the F-JS1 fix with A1 passing (section 8.2) | `static/js/erp.js` (attendance block), `browser_tests/bt_attendance_autosave.py` |
| JS4 | Usage measurement cases, before measurement is enabled anywhere; retire usage behaviour stand-ins | `browser_tests/bt_usage.py`, `core/tests/test_usage_workflows.py` (edit) |
| JS5 (later) | PWA and common interface cases; retire their stand-ins | browser test files, `core/tests/test_pwa_gate1.py`, `test_session_errors_audit18.py`, others (edit) |
| Later | A few full Django browser journeys (OD-JS6, separate decision) | — |

Only JS3 changes `static/js/erp.js`. No PR changes templates, settings, `requirements.txt`,
`static/vendor/` or Railway configuration.

If JS1 never lands, for example because the spike fails and the product owner drops the
approach, a follow-up docs PR removes the `js` rule lines from `AGENTS.md`,
`IMPLEMENTATION_WORKFLOW.md`, `DEFINITION_OF_DONE.md` and the PR template.

## 15. Acceptance criteria

**JS1:**

1. Every spike pass condition in section 7.1 is met. The evidence goes in the PR description: run
   counts on Windows and Linux, timings, a link to the failure artifact, and the request log
   showing no external calls.
2. The test command passes locally on Windows and in the `js` job on Linux.
3. The job runs on a draft PR when a relevant path changes and is skipped for an unrelated code
   change. A cached draft run takes under 90 s. A deliberately failing commit fails the run and
   uploads the trace and screenshot. That commit is removed before review.
4. Harness self-checks prove: per-test context isolation, the controlled 30 s interval, a
   byte-identical `erp.js`, page errors failing tests, and real network requests failing tests.
5. `git diff origin/main -- static templates core/templates config requirements.txt` is empty.
6. The boundary, CI policy and fixture contract tests pass in the draft-safety run.
7. ADR 0028 is Accepted with the spike evidence, listed in the ADR index, and noted in
   `ARCHITECTURE.md`.
8. The staging build after merge shows the Python provider only, no extra install step and no
   Playwright package.

**JS2 to JS4:**

- Every listed case exists and passes; none is skipped or marked as an expected failure. A1 is
  absent from JS2. In JS3 it is shown failing on the old behaviour before the fix, then passing.
- Each removed source-string test is listed beside its replacement in the PR description.
- JS3 changes only the attendance block of `erp.js` and its test. `test_marks_autosave.py:469-471`
  stays green.

## 16. Risks

| Risk | Mitigation |
| --- | --- |
| Holding or reordering routes is unreliable in the synchronous API | Spike first; fall back to Option 2 and report |
| Browser install makes the job slow or flaky | Browser cache; Chromium only; budget; fallback to Option 2 |
| jsdom (if chosen) differs from browsers | Assert only what jsdom models; blur and focus cases confirmed later by journeys |
| Fixtures drift from templates | Contract test on names and normalised values, in the draft-safety set |
| Toolchain grows into a build pipeline | ADR 0028 boundary; boundary test; any bundler, transform or generated asset needs a new ADR |
| Dependency churn | One pip package (or two npm packages); quarterly manual updates |
| Contributors without the browser or Node | The Django suite still runs alone; CI runs the client job; commands documented |
| New tests expose live defects mid-PR | OD-JS11 and OD-JS15 keep fixes separate and owner-decided |
| A heavy dependency reaches Railway | Separate requirements file or folder; boundary test; staging build check |

## 17. Current, proposed and deferred

| | Current (baseline `d7d3090`) | Approved (r3), conditional on the spike | Deferred |
| --- | --- | --- | --- |
| Test tools | Django test framework only | Plus Python Playwright browser fixture tests (`node:test` + jsdom only if the spike fails and the owner agrees) | Whole-journey tests |
| JavaScript checks | About 60 source-string test methods; manual browser checks | Behaviour verified by execution; behaviour stand-ins removed as coverage lands; architectural checks kept | Journeys; WebKit |
| Node | Not used by the repository | No project-managed Node/npm toolchain, package manifest, build pipeline or production dependency | — |
| `erp.js` | Classic script, served directly | Unchanged | Optional helper extraction; any module split needs its own decision |
| CI | `lint`, `test` | Plus a path-aware `js` job on relevant PRs, drafts included | Required checks |
| Railway | Python-only Railpack build | Unchanged; verified after first merge | — |
| F-JS1 | Present (read from code) | Recorded as a confirmed uncovered defect in JS2. Regression test shown failing, then fixed, in JS3, so the latest choice wins | Attendance timeout (separate question) |

## 18. External sources

Checked 2026-11-22. Versions must be rechecked when JS1 starts.

- Node.js release schedule (primary):
  [Evolving the Node.js release schedule](https://nodejs.org/en/blog/announcements/evolving-the-nodejs-release-schedule).
  Dates as summarised in the
  [Node.js release and EOL timeline](https://hidekazu-konishi.com/entry/nodejs_release_and_eol_timeline.html).
- Vitest 5 requirements (Vite ≥ 6.4 peer, Node ≥ 22.12):
  [Vitest 5.0 announcement](https://vitest.dev/blog/vitest-5.html),
  [vitest on npm](https://www.npmjs.com/package/vitest).
- npm optional native dependencies in lockfiles: [npm/cli#4828](https://github.com/npm/cli/issues/4828).
- Railpack Node detection from a root `package.json`, and provider pinning:
  [Railpack Node.js](https://railpack.com/languages/node/),
  [Railpack configuration file](https://railpack.com/config/file/),
  [railpack#860](https://github.com/railwayapp/railpack/issues/860).
- jsdom releases and Node floors: [jsdom on npm](https://www.npmjs.com/jsdom),
  [jsdom README](https://raw.githubusercontent.com/jsdom/jsdom/main/README.md).
- `node:test` mock timers status: [node issue 61039](https://github.com/nodejs/node/issues/61039)
  and the Node test runner docs.
- Playwright Python capabilities (`page.route`, `route.fulfill` and `route.abort`,
  `page.clock`, `pageerror`, browser install with `--with-deps`) were first taken from general
  knowledge of the library. The JS1 spike verified them against playwright 1.64.1 (ADR 0028,
  "Spike evidence").

## 19. Independent review and verdicts

An independent reviewer (a separate agent without this document's drafting context) reviewed r0
against the code on 2026-11-22. Each finding was then checked against the code by the author.

| # | Severity | Finding | Verdict | Action in r1 |
| --- | --- | --- | --- | --- |
| 1 | High | Options leave out browser fixture tests with pip Playwright and no server, which need no Node and answer the stack change rule's "why not within the current architecture" | **Confirmed** (omission) | Option 5 added; recommendation changed to Option 5 subject to a spike, Option 2 as fallback; ADR updated |
| 2 | Medium | jsdom reports listener errors to its virtual console, not to the test; F-JS3 misplaced line 352 and understated the effect | **Confirmed** for the code (`:145` starts the main IIFE; a top-level throw stops the rest of the file; other `matchMedia` calls at `:33-37`, `:1489`). jsdom behaviour plausible (inference) | F-JS3 corrected; Option 2 harness fails tests on `jsdomError`; Option 5 fails on `pageerror` |
| 3 | Medium | jsdom does not fire `change` on blur, does not do implicit submission, focuses hidden elements and loads no CSS, so several "DOM-testable" items are not | **Confirmed** for the marks flow's dependence on blur `change` (Option B OD-B2; `erp.js:780`); jsdom details plausible (inference) | Behaviour map reclassified (rows 5, 6, 11, 15, 18, 19, 29); M8 now covers middle rows in a real browser |
| 4 | Medium | CI guard does not catch emptied, skipped or `.only` tests; merge-gate docs not updated; "no `if:`" contradicted by `if: failure()` | **Confirmed** (`IMPLEMENTATION_WORKFLOW.md` section 11 and `AGENTS.md` name only `lint` and `test`) | Test-content guard, method counts, skip/only rules; merge-gate docs in PR 1 (OD-JS7); wording fixed |
| 5 | Medium | F-JS1 reading is right, but the spec decides attendance behaviour itself; the missing timeout is deliberate | **Confirmed** (`test_marks_autosave.py:469-471`; Option B 4.4) | OD-JS15 added with no recommendation; A1 no longer asserts an expected fix |
| 6 | Medium-low | Contract compares names, not values | **Confirmed** | Contract compares normalised values; one documented exception |
| 7 | Low | Harness could fire `DOMContentLoaded` twice | **Plausible** (jsdom only) | Option 2 harness waits for jsdom's own events; part of its spike |
| 8 | Low | `engine-strict` with `>=26 <27` fails on the owner's Node 22; dates from a secondary source | **Confirmed** | OD-JS8 option B (`>=24`, no `engine-strict`) recommended; sources labelled |
| 9 | Low | Without Bootstrap the auto-hide takes another branch | **Confirmed** (`erp.js:359-363`) | Fixtures for rows 8 and 11 load the vendored bundle |
| 10 | Nit | ADR vs spec wording on payload logs; rollback list; "unusable"; `junit.xml` location; flush test line; dependency count; `"type"` redundant; interval self-check fixture | **Confirmed** | All corrected |

### 19.1 r2 changes from the product-owner review (2026-11-22)

| # | Owner correction or decision | Change in r2 |
| --- | --- | --- |
| 1 | Replace "no Node" with "no project-managed Node/npm toolchain, package manifest, build pipeline or production dependency" | Wording changed in sections 4, 5, 17 and the ADR |
| 2 | Fixture tests are not full-page, template or visual-regression tests | Stated in sections 5.1 and 7.5 |
| 3 | One browser process per test job, a fresh context and page per test | Sections 4, 7.2 and the harness self-checks |
| 4 | Path-aware JS job; docs-only PRs need no Chromium | Section 9: path list, shell-step check, policy guard |
| 5 | Behaviour source-string tests are temporary; architectural checks stay | Section 11 and OD-JS10 answer |
| 6 | ADR 0028 stays Proposed until the spike passes; accepted in the harness PR | Header, sections 7.1, 14, 15 and the ADR status |
| 7 | Spike pass conditions | Section 7.1. The `sendBeacon` condition is recorded as the page-hide `keepalive` fetch, because `erp.js` has no `sendBeacon` (only `keepalive: true` at `erp.js:82`) |
| 8 | Diagnostics on failure | Trace and screenshot uploaded on failure, synthetic fixtures only, 7-day retention (sections 7.6 and 9; ADR updated) |
| 9 | Budget: a cached draft run under 90 s | Sections 4 and 9 |
| 10 | OD-JS15: latest choice wins, one in-flight request per row with one replaceable pending value | A1 and new section 8.2 (JS3). Superseded in r3: no expected failure in JS2 |
| 11 | Order: docs PR, then JS1 (spike, harness, CI), JS2 (marks and attendance), JS3 (F-JS1 fix), JS4 (measurement), later journeys | Section 14. PWA and common interface moved to JS5, not yet scheduled |

**OD-JS7 merge gate:** decided in r3, see section 9.

### 19.2 Second independent review (r3 working tree, 2026-11-22)

A separate agent without the drafting context reviewed r3, including the rule-document edits. It
found nothing that contradicts the owner's decisions. Each finding was checked against the code
by the author.

| # | Severity | Finding | Verdict | Action |
| --- | --- | --- | --- | --- |
| 1 | Medium | The fixture contract ignores server reply fragments that `erp.js` reads, so a changed fragment or view leaves the browser tests green | **Confirmed** (`erp.js:983`, `:1015`, `:1045`, `:1115`; `_marks_autosave_status.html`, `_attendance_autosave_status.html` exist) | Section 7.5: contract covers reply fragments and the 401 body |
| 2 | Medium | A broken path check would skip silently and still show green | **Confirmed** (design gap) | Section 9: fails closed; base is `github.event.pull_request.base.sha`; `fetch-depth: 0` |
| 3 | Low | Path list misses `config/**` and `manage.py`; `accounts/templates/` does not exist; templates and forms cannot affect the browser tests | **Confirmed** (`accounts/templates` absent) | Path list corrected; template drift assigned to the contract test |
| 4 | Low | Where the contract test runs was unclear | **Confirmed** | Section 9 names both tests in `DRAFT_SAFETY_TESTS` |
| 5 | Medium | ADR still allowed skips with an issue link | **Confirmed** (ADR line 158) | ADR aligned: no skip or expected-failure markers |
| 6 | Medium | Revision row cited a missing section 19.2 | **Confirmed** | This section added; pointer updated |
| 7 | Low | Leftover r2 wording; "every PR"; "nothing else" | **Confirmed** | Corrected in the ADR and sections 10.1 and 17 |
| 8 | Low | PR template checkbox lacked "from JS1 onward" | **Confirmed** | Qualifier added |
| 9 | Low | "Skipped job" is imprecise; "approved head" before approval; where the run id comes from | **Confirmed** | Wording now says "test step was skipped"; the owner's phrase kept, with "(the final head presented for approval)"; run-id command added |
| 10 | Low | Workflow paragraph read as present tense; no revert plan if JS1 never lands | **Confirmed** | "Applies once JS1 adds the job"; revert line in section 14 |
| 11 | Low | Spike risks: paused clock freezes HTMX timers; visibility needs overriding; `keepalive` may need `context.route`; `pageerror` exceptions do not fail sync tests | **Plausible** (inference about Playwright) | Section 7.1 condition 4 and section 7.2 updated |
| 12 | Low | Diagnostics: limit artifact access; do not reuse capture for live-server journeys | **Plausible** | ADR and section 7.6 rule added |
| 13 | Low | ADR and spec budgets differed for Option 2 | **Confirmed** | ADR states the 2-minute Option 2 budget |
| 14 | Nit | Paragraph inside a bullet list in section 5.1 | **Confirmed** | Moved below the list |
| 15 | Nit | JS1 criterion 5 missed `core/templates` | **Confirmed** | Added |
| 16 | Nit | JS2 file list missed `test_attendance_bulk_present.py` | **Confirmed** | Added |

### 19.3 r4 changes from JS1 (2026-11-22)

| # | Change | Where |
| --- | --- | --- |
| 1 | Spike passed all nine conditions; evidence recorded in ADR 0028, which is now Accepted | Header; ADR 0028 |
| 2 | Plain `unittest` replaces `manage.py test` + `SimpleTestCase` for browser tests (approved) | Sections 4, 5.1, 9 |
| 3 | CI installs only the headless shell (`--only-shell`) and `requirements-browser.txt` (approved) | Section 9 |
| 4 | Measured: proposed job 35 s uncached, 28 s cached; local full Chromium 719 MB | Section 4 |
| 5 | Chromium 156 crashed on replies with a body and no headers, and on aborts sent after the route handler returned. The harness always sends a `Content-Type`, makes network failures on arrival only, and replaces a crashed browser | Section 4 (Races); `browser_tests/support/page.py` |
| 6 | JS1 review fixes: an unservable request is aborted at once and fails the test; subTest failures save diagnostics; service workers blocked; a records file joins the diagnostics; tearDown enforcement, diagnostics and isolation proven by probe tests run in a nested suite; the fixture contract compares every behaviour-relevant attribute and value on every row, the roster and the form; the attendance fixture gains the submit button and done announcer it lacked | Sections 7.2, 7.5, 7.6; `browser_tests/` |
| 7 | CI: `contents: read`; a 5-minute test-step timeout inside the 10-minute job, and an `always()` upload whenever the test step did not pass; the policy test checks the exact command and applies the path pattern to sample paths; the marker ban covers every skip and expected-failure spelling | Section 9 |

### 19.4 JS2 notes (2026-11-22)

| # | Note | Where |
| --- | --- | --- |
| 1 | F-JS1 confirmed in Chromium: after the older reply, the row shows "✓ Saved" and announces "Saved Student A." while the newer change is in flight; an older 500 shows "Not saved." with Retry. The newer request carries the newer value, so no wrong value is saved. Issue #289; no test until JS3 | Section 3.5 |
| 2 | Fixtures gained the session box (attendance) and replies for a 403 row fragment and bulk present (saved and 401), all pinned by the contract test | Section 7.5 |
| 3 | Two equivalent mutants: removing the marks `htmx:timeout` listener (afterRequest with status 0 shows the same words) and the last-row Enter trigger (the sign-in "Next" helper's focus move already fires `change`, F-JS4). The string check for the Enter trigger is kept for that reason | `test_marks_autosave.py` |
