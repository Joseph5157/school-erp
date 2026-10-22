# Guardian Portal UI/UX Re-test — Staging

- **Date:** 2026-10-16
- **Environment under test:** https://school-erp-web-staging.up.railway.app (Railway)
- **Repository:** `C:\Users\sikha\school-erp`, branch `main` @ `75bc4ab`
- **Scope:** Guardian portal only (login → guardian area). Admin/teacher pages were
  touched only where needed to diagnose the guardian report.
- **Baseline for comparison:** previous guardian audit, overall UI/UX **6.2/10**.
- **Nature of this task:** read-only audit and diagnosis. No application code was
  modified. No records were created, edited, published, approved, deactivated or
  deleted. The guardian password was not changed. Nothing was committed or pushed.

---

## 0. How to read this report — evidence classes

Every statement below is tagged with one of these:

| Tag | Meaning |
| --- | --- |
| **[LIVE]** | Confirmed in the deployed staging interface via browser automation. |
| **[SRC]** | Inferred from the repository source (templates/views/CSS) — not observed live. |
| **[SIM]** | Rendered from the **real deployed templates + the real `erp.css`** locally with **synthetic** data (no database rows touched). Used only where a guardian login was unavailable. Clearly not live data. |
| **[TEST]** | Result of the repository's own automated tests. |
| **[N/V]** | Not verifiable safely (needs data changes, a guardian session, real devices, or wall-clock time). |

> **Verification gap (important).** Most guardian-authenticated pages (home, child
> overview, attendance, report cards, notices) could **not** be opened live because
> **no guardian password was available and resetting it is out of scope**. Those
> pages were therefore assessed with **[SRC]** + **[SIM]** evidence and are marked
> **[N/V] live**. This is stated again in the findings that depend on it. Admin
> credentials were supplied by the requester; they were used for read-only
> navigation, were **not** written to any file, report, screenshot, log or commit,
> and the temporary local credential file was deleted after use. **Those
> credentials must still be rotated** (requester confirmed they will).

---

## 1. What changed in the repository (recent, guardian-relevant)

`git status`: clean working tree; only untracked artefacts (`.playwright-mcp/`,
`School_ERP_Admin_UI_UX_Audit.pdf`, `phase1-smoke.sqlite3`). No uncommitted work was
disturbed.

Recent commits (2026-10-16) are the **admin/teacher UI audit** phases 0, 1, 2, 3A–3G
(`4d6c5f5`, `71531e3`, `09635dd`, `98259c7` … `75bc4ab`). Measured against the
guardian UI:

| Area | Last guardian-relevant change | Changed by the recent UI work? |
| --- | --- | --- |
| `templates/portal/*` (all 8 portal templates) | `a26e20d`, **2026-10-15** | **No** — untouched |
| `templates/registration/login.html` | older | No |
| `templates/partials/_account_menu.html` | `37853b2`, 2026-10-15 | No |
| `static/css/erp.css` (**shared — the portal loads it**) | `0b0c69d`, 2026-10-16 | **Yes** |
| `static/js/erp.js` (**shared — the portal loads it**) | `26a79cc`, 2026-10-16 | Yes (portal uses none of its features) |

**Headline:** the recent UI/UX work targets the **admin and teacher** interfaces. The
**guardian portal templates were not edited**. The guardian portal changes only
*indirectly*, through the shared `erp.css`/`erp.js` (responsive foundation, design
tokens, button styles, empty-state component, mobile table scrolling). The
guardian-specific concerns from the baseline therefore had little opportunity to
change — and most are confirmed still open below.

---

## 2. Concise testing summary

- **Login/auth surface is the strongest part.** **[LIVE]** The login page loads
  cleanly (HTTP 200) at 375×812, 320×568, 768×1024 and 1440×900 with **no console
  errors, no failed requests and no horizontal overflow**; labels, keyboard focus
  (visible 3px outline) and the JS show/hide-password control work; empty submit
  shows field errors; bad credentials show a single generic message. Security
  headers are present (HSTS, `X-Frame-Options: DENY`, `nosniff`, Referrer-Policy,
  COOP). A `Content-Security-Policy` header is absent.
- **The reported "guardian error" is most likely the bare 403.** **[LIVE]** An
  authenticated **admin** login opening `/guardian/` (or any non-guardian login)
  receives Django's **unstyled, unbranded `403 Forbidden`** page with no
  navigation, explanation or way back. Anonymous visitors are correctly redirected
  to `/accounts/login/?next=…`. The guardian account itself is **healthy** (below).
- **The guardian account and data are intact.** **[LIVE]** Guardian **Meena Rao →
  login `guardian-login`**, account **active**, no forced password change, grant to
  **Anusha Rao** present and not under review; **0 pending access reviews**, **0
  locked usernames**, **0 published notices**.
- **The authenticated guardian UI could not be opened live** (no guardian
  password; resetting is out of scope). It was reviewed via **[SRC]** and **[SIM]**
  evidence. Several baseline issues persist there: desktop has no primary
  navigation, the home page is not a child-centred dashboard, the report-card
  **Grade** column is still blank when the grade is blank (while Pass/Fail says
  "Pass"), and notices still carry no sender/urgency/read/acknowledgement state.
- **No confirmed live-staging regression was found.** One shared-CSS behaviour
  change affects the portal (mobile report-card table becomes an internal
  scroll container); the pre-change baseline CSS is unknown, so it is listed as a
  *possible* regression, not a confirmed one.
- **New guardian UI/UX score: 6.0/10** (previous 6.2/10) — effectively flat; see §8.

---

## 3. Diagnosis: "for some reason guardian is showing error"

**[LIVE]** Three distinct, safe responses exist:

| Access attempt | Response | Correct? |
| --- | --- | --- |
| Anonymous → `/guardian/` | `302` → `/accounts/login/?next=/guardian/` | Yes |
| **Admin login → `/guardian/`** | **`403 Forbidden`** (bare, unstyled page) | Access correct, **presentation poor** |
| Guardian `guardian-login` → `/guardian/` | expected `200` (**[SRC]/[N/V live]** — no guardian password) | n/a |

**[LIVE]** Admin-side inspection of the guardian record shows nothing broken:

- Guardian **Meena Rao** (`/guardians/1/`), phone on file.
- Portal login **`guardian-login`** — **active**, **no "must change password" badge**,
  no "login inactive" badge; verified by `admin-login` on 2026-10-15.
- Student access: **Anusha Rao — Mother — Granted 2026-10-15**, **not** under review.
- `/guardian-access/reviews/` → *"No pending access reviews."*
- `/sign-in-lockouts/` → *"No usernames are locked."*
- `/announcements/` → *"No notices yet."*
- Django admin user list shows 3 logins (an admin, the guardian, and one more), all active.

**Most likely cause of the observed "error":** the operator opened the guardian
portal with a **non-guardian login (e.g. the admin account)** and hit the bare
**403**, or a guardian login attempt failed on **password** (correctly producing the
generic "*The username or password is incorrect…*" message). The guardian account
and grants are **not** broken. If the guardian's own login shows an error page or a
`500`, it could not be reproduced here without the guardian password — please supply
it (or the exact URL/error text) to close this out; see §7.

**Recommended fix regardless:** replace Django's bare 403 with a branded page that
explains the visitor has no guardian access and offers a route back (Finding
**G-01**).

---

## 4. Previous findings — comparison table (every earlier concern)

| # | Previous concern | Status | Evidence | Notes |
| --- | --- | --- | --- | --- |
| 1 | No obvious Notices link on the guardian home page | **Partially fixed** | [SRC]/[SIM] `portal/home.html`, `portal/base.html` | Mobile tab bar has **Notices**; home shows *Latest notices* **only when notices exist**. With **no notices** (staging: 0) desktop shows **no Notices entry point at all**. |
| 2 | Interface not sufficiently mobile-first | **Partially fixed** | [SIM] 4-viewport render; [SRC] `erp.css` | Mobile tab bar, chips and responsive tables exist; report-card table needs horizontal scroll; desktop has no primary nav. |
| 3 | Home page lacked a useful child-centred dashboard | **Still open** | [SIM] `portal-home-*-1440x900.png`, `…-375x812.png` | Home = child list + latest notices; **no attendance %, no recent result, no urgent action**; large unused space. |
| 4 | Attendance lacked explanation and date/period context | **Partially fixed** | [SIM] `portal-attendance-mobile-375x812.png`; [SRC] `attendance.html` | Summary + "*Only attendance the school has officially recorded is shown.*" + per-day dates + year name. Still **no explicit start–end date range** and no calculation breakdown; only Present/Absent (see G-13). |
| 5 | Report viewing/downloading needed clearer actions and status info | **Partially fixed** | [SIM] `portal-report-cards-*.png`, `portal-report-card-*.png`; [SRC] | **Download PDF** button; partial-term warning; "*Each assessment is shown separately; there are no totals…*". Report-cards **list** is a bare `<ul>` with no dates/status; no print action. |
| 6 | Grade column blank while Pass/Fail showed "Pass" | **Still open** | [SIM]/[SRC] `portal/report_card.html:15` | Confirmed in rendered row: `<td></td><td>Pass</td>`. The earlier **F16** fix (`f96d89f`) patched **admin** templates only, **not** the guardian report card. |
| 7 | Notices lacked unread, urgency, sender and acknowledgement states | **Still open** | [SRC]/[SIM] `portal/notices.html`, `portal/notice.html` | Template shows only **title + date** (+ body on detail). No sender, urgency, read/unread, acknowledgement. |
| 8 | Password recovery and school-support guidance weak/unclear | **Still open** | [LIVE] login page | Login says "*Forgot your password? Ask the school office to reset it.*" — correct but no school contact details. Self-service recovery is **out of scope by design** (Phase 6 P3). Support path itself **[N/V]**. |
| 9 | Multi-child behaviour not previously validated | **Partially fixed / [N/V] live** | [SIM] `portal-home-multi-child-*.png`; [LIVE] staging has 1 child | Child-chip switcher exists and renders for ≥2 children; **live multi-child could not be exercised** (staging's `guardian-login` has one child). |
| 10 | Real-device responsiveness + full WCAG 2.2 AA not validated | **Partially fixed** | [LIVE]/[SIM] 4 viewports + 200% zoom | 4 headless viewports + zoom proxy done; **no real device**, **no full axe/WCAG 2.2 AA** pass (see §9 gaps). |

---

## 5. New findings

Severity: **P0** blocks access / exposes data; **P1** serious usability, accessibility, security or mobile problem; **P2** meaningful friction; **P3** polish.

| ID | Page / workflow | Viewport | Sev | Evidence | User impact | Likely cause | Recommended improvement | Acceptance criteria |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **G-01** | Any guardian URL opened by a non-guardian (e.g. admin) | All | **P1** | [LIVE] `admin-guardian-403-desktop-1440x900.png` — plain "403 Forbidden" | Visitor sees an unstyled dead-end; looks like the app is broken; likely the reported "guardian error" | `guardian_required` raises `PermissionDenied`; DEBUG off ⇒ Django's default 403 page; no custom `403.html` | Add a branded `403.html`: explain "This account has no guardian access", show who is signed in, link to login/switch area | A non-guardian sees a styled page with an explanation and a way back; response stays `403` |
| **G-02** | Desktop guardian shell/navigation | 1440×900 | **P1** | [SIM] `portal-home-populated-desktop-1440x900.png`; [SRC] `portal/base.html:31` | At desktop width there is **no primary nav** (only brand + account menu); reaching Attendance/Results/Notices takes several clicks; no active state | Tab bar is `d-lg-none`; portal has no desktop nav equivalent | Add a desktop header nav (Home · Notices · [child] Overview · Attendance · Report cards) with `aria-current` | Desktop shows persistent primary nav with an active indicator on every page |
| **G-03** | Tab bar consistency | All | **P2** | [SIM] home (2 tabs) vs attendance (5 tabs) vs notices (2 tabs) | Guardians cannot jump from Home/Notices to Attendance/Report cards via tabs; the bar changes shape per page | `base.html` only renders child tabs `{% if grant %}`; `home`, `notices`, `notice` views don't pass `grant` | Resolve the "current child" so the full 5-tab set is stable, or move child tabs to a persistent element | The primary nav set is identical across guardian pages |
| **G-04** | Home → Notices discoverability | 1440×900 | **P2** | [LIVE] `admin-announcements` = "No notices yet"; [SRC] `home.html:17-25` | When there are no notices, the home page shows **no Notices link** at all | "Latest notices" block is `{% if notices %}` only | Always render a Notices entry point (with empty state) | A Notices link is present on Home even with zero notices |
| **G-05** | Report card — Grade vs Pass/Fail | All | **P2** | [SIM] `portal-report-card-mobile-375x812-scrolled.png`; `report_card.html:15` | Blank **Grade** beside **Pass** looks like missing/incorrect data | `{{ e.grade_label\|default:"" }}`; admin F16 fix not applied to portal | Show "Not graded" when blank (match F16), or drop the column | No blank Grade cell without an explanatory label |
| **G-06** | Home heading order / duplicate children | All | **P3** | [SIM] `portal-home-populated-*.png` | Child chips appear **above** the "Your students" H1 and duplicate the list | Chips live in `base.html` before `{% block content %}` | Move chips under the page title, or make the list itself the switcher | Chips sit below the page heading, no duplication |
| **G-07** | Home information hierarchy | All | **P2** | [SIM] home screenshots | Parent-critical info (attendance, next result, urgent notice) is not surfaced first; big empty space on desktop | Home template is a plain list | Child-centred dashboard cards (attendance %, latest report card, urgent notice) | Above-the-fold dashboard summarises each child's status |
| **G-08** | Report-cards list | All | **P2** | [SIM] `portal-report-cards-*.png`; `report_cards.html` | Bare `<ul>`; empty state is a naked `<li>` (inconsistent with `partials/_empty.html`); no publication date/status | Minimal template, not using shared components | Use the shared empty-state component; add published date + status | List shows term, year, published date; empty state matches the design system |
| **G-09** | Report card on mobile | 320 / 375 | **P2** | [SIM] `portal-report-card-mobile-375x812.png` & `…-scrolled.png`; measure `table sw=459 > cw=343`, `canScroll=true` | To read Grade/Pass-Fail the guardian must scroll the table sideways with **no visual affordance**; the subject label scrolls out of view; header not sticky | 7-column table + `erp.css` `@media(max-width:575.98px){ .erp-content table{display:block;overflow-x:auto} }` | Wrap in `.erp-table-scroll`/`.table-responsive` with a hint; consider a stacked card layout per assessment | On ≤375px all 7 fields are reachable and the subject stays identifiable |
| **G-10** | Login validation errors (a11y) | All | **P2** | [LIVE] empty submit renders plain `.text-danger`, no `aria-invalid`/`aria-describedby`/live region | Screen-reader users may not learn the field failed; errors not announced | Template uses plain error text | Add `aria-invalid`, `aria-describedby`, and a `role="alert"`/live region | Field errors are programmatically associated and announced |
| **G-11** | Security headers | All | **P3** | [LIVE] response headers | No CSP; other headers present (HSTS, XFO DENY, nosniff, Referrer-Policy, COOP) | CSP not configured | Add a Content-Security-Policy (allow the jsDelivr CDN or vendor Bootstrap) | CSP present and non-breaking on staging |
| **G-12** | Small tap targets | 320/375 | **P3** | [SIM] "All notices" and child-name links measure ~21px tall | Below the 24px minimum; harder to tap | Inline links styled as text | Increase hit area/padding or use buttons | Interactive targets ≥ 24×24 CSS px |
| **G-13** | Attendance context depth | All | **P2 / [N/V]** | [SIM] `portal-attendance-*.png`; [SRC] `portal.py` | No explicit start–end date range, no calculation breakdown, no late/half-day (model supports only PRESENT/ABSENT) | Data + template limited by ADR 0014 (P8) | Show the covered date range and the % formula; add late/half-day if the model supports it | Attendance header states the period and the calculation |
| **G-14** | Logout affordance | All | **P3** | [LIVE] `account-menu-*.png` | Logout is inside a closed `<details>` menu; no confirmation. Functionally correct (POST + CSRF; verified) | Design choice | Optionally add a confirm step; keep it visible | (Optional) logout confirm; menu discoverable |
| **G-15** | Session expiry | All | **Info** | [SRC] `config/settings.py`, `accounts/middleware.py` | 30-min idle / 8-hr absolute; idle expiry redirects to login with `next`. **[N/V] live** (needs wall-clock) | Configured behaviour | None | (verify with a shortened test config) |
| **G-16** | Intermittent external resource failure | Admin page | **P3** | [LIVE] one occurrence of `net::ERR_NAME_NOT_RESOLVED` on `/guardians/1/`, **not reproduced** | Possible transient CDN/DNS hiccup | Third-party `cdn.jsdelivr.net` Bootstrap CSS/JS | Vendor Bootstrap or add SRI/fallback | No external-load console errors across repeated loads |
| **G-17** | Report card provenance | All | **P3** | [SRC] `portal/report_card.html` | No publication date/version shown | Template omits it | Show published-on date and version | Report card shows publication date |

---

## 6. Newly discovered regressions

**No confirmed live-staging regression was found.**

- **Unconfirmed / attributed (possible regression):** the shared
  `erp.css` introduced by the admin responsive foundation (`63bd963`) makes the
  guardian **report-card table an internal horizontal scroll container**
  (`.erp-main{overflow-x:clip}` + `@media(max-width:575.98px){.erp-content table{…overflow-x:auto}}`).
  This is a real behaviour change for the portal, but the **pre-change portal
  baseline behaviour was not recorded**, so it cannot be proven to be a regression.
  Tracked as **G-09**.
- The bare **403** (G-01) is **Django's default** response, not a new bug.

---

## 7. Viewport-by-viewport responsive assessment

Measured with a headless Chromium. "Overflow" = `documentElement.scrollWidth > clientWidth`.

| Area | 320×568 (small) | 375×812 (mobile) | 768×1024 (tablet) | 1440×900 (desktop) |
| --- | --- | --- | --- | --- |
| Login page | No overflow; single column; labels clear; [LIVE] | No overflow; [LIVE] | No overflow; centered narrow card; [LIVE] | No overflow; [LIVE] |
| Guardian home | No overflow; chips + list; large empty space; [SIM] | No overflow; chips above H1; [SIM] | No overflow; list capped 32rem; [SIM] | No overflow; **no primary nav**; very sparse; [SIM] |
| Child overview | Fits; fields stack; [SIM] | Fits; [SIM] | 2-column `<dl>`; [SIM] | 2-column; lots of empty space; [SIM] |
| Attendance | Table fits (2 cols); [SIM] | Fits; [SIM] | Fits; [SIM] | Fits (max-width 28rem); [SIM] |
| Report cards list | Fits; [SIM] | Fits; [SIM] | Fits; [SIM] | Fits; [SIM] |
| **Report card (7-col table)** | **Scrolls internally (sw 459 vs 288); no affordance**; [SIM] | **Scrolls internally (sw 459 vs 343)**; [SIM] | Fits (736/736); [SIM] | Fits (1136/1136); [SIM] |
| Notices | Empty state good; fits; [SIM] | Fits; tab bar 2 tabs; [SIM] | Fits; [SIM] | Fits; **desktop has no nav**; [SIM] |
| Zoom 200% (login) | — | — | — | No overflow; [LIVE] |

- **Mobile tab bar** shows all 5 tabs on child/attendance/report-card pages, but
  only Home/Notices on home/notices/notice pages (**G-03**).
- **Touch targets:** most ≥ 2.75rem; inline links ("All notices", child names)
  ~21px (**G-12**).
- **Long names/content:** not exercised with pathological strings — **[N/V]**.

---

## 8. Guardian UI/UX score

**New score: 6.0 / 10** (previous **6.2 / 10**).

Gains that lift the floor:
- Login/auth surface is clean, responsive, keyboard-usable and secure-header'd
  (best-functioning part of the portal).
- Shared responsive foundation gives the portal sensible mobile behaviour
  (scrollable report-card table, consistent empty-state component on Notices).
- Cross-page visual language (tokens, buttons, headings) is coherent.

What holds it back (and why it is essentially **flat vs 6.2**):
- The recent UI/UX work **did not touch the guardian portal templates**; the
  headline fixes went to the admin/teacher UI.
- High-visibility baseline gaps **remain live/baseline-open**: graded report card
  (**G-05/#6**), no desktop nav (**G-02**), home not a dashboard (#3), notices
  metadata (#7).
- The reported "guardian error" resolves to an **unbranded 403** (**G-01**).
- Authenticated pages were **not verifiable live**, which caps confidence (not
  the score itself, but the evidence).

A **+1.5–2.0** jump is realistically available in one sprint by fixing G-01, G-02,
G-05, G-07 — see §10.

---

## 9. Test evidence

### 9.1 Pages inspected

- **Live [LIVE]:** `/accounts/login/` (all 4 viewports + empty submit + wrong
  credentials + show/hide + tab order + 200% zoom), `/` (anonymous), `/guardian/`
  (anonymous → 302; admin → 403), `/overview/`, `/guardians/`, `/guardians/1/`,
  `/students/`, `/students/1/`, `/guardian-access/reviews/`, `/sign-in-lockouts/`,
  `/announcements/`, `/admin/accounts/user/` (+ each user change page), logout flow.
- **[SIM] (real templates + real `erp.css`, synthetic data):** portal `home`
  (empty/populated/multi-child), `child`, `attendance` (populated/empty),
  `report_cards` (populated/empty), `report_card`, `notices` (empty/populated),
  `notice`.

### 9.2 Screenshots (filenames; all under `docs/guardian-retest/`)

- **Login:** `login-mobile-375x812.png`, `login-small-mobile-320x568.png`,
  `login-tablet-768x1024.png`, `login-desktop-1440x900.png`,
  `login-empty-submit-desktop-1440x900.png`, `login-error-desktop-1440x900.png`,
  `login-zoom200-desktop.png`.
- **Auth/role [LIVE]:** `admin-guardian-403-desktop-1440x900.png`,
  `admin-landing-desktop-1440x900.png`, `admin-overview-desktop-1440x900.png`,
  `admin-guardian-list-desktop-1440x900.png`,
  `admin-guardian-detail-desktop-1440x900.png`,
  `admin-access-reviews-desktop-1440x900.png`,
  `admin-lockouts-desktop-1440x900.png`,
  `admin-announcements-desktop-1440x900.png`,
  `account-menu-desktop-1440x900.png`, `account-menu-mobile-375x812.png`.
- **Portal [SIM]:** `portal-home-empty-notices-*.png`, `portal-home-populated-*.png`,
  `portal-home-multi-child-*.png`, `portal-child-*.png`, `portal-attendance-*.png`,
  `portal-attendance-empty-*.png`, `portal-report-cards-*.png`,
  `portal-report-cards-empty-*.png`, `portal-report-card-*.png` (+ `…-scrolled.png`
  at 375 and 320), `portal-notices-empty-*.png`, `portal-notices-populated-*.png`,
  `portal-notice-*.png` (`*` = both `mobile-375x812` and `desktop-1440x900`).
- **Rendered HTML [SIM]:** `render/*.html` (12 files, input to the SIM screenshots).
- No credentials, tokens or cookies appear in any screenshot. The signed-in
  username in the top-right account chip of the live admin screenshots and the
  desktop portal renders was **physically redacted** (dark block, top-right) after
  capture.

### 9.3 Automated checks

- **[TEST]** `python manage.py test core.tests.test_phase6_portal_shell
  core.tests.test_phase6_portal_attendance core.tests.test_phase6_student_profile
  core.tests.test_phase6_security core.tests.test_phase6_access_boundary
  core.tests.test_ui_foundation` → **123 tests, OK** (27.5s).
- **[LIVE]** Live header/status capture for `/accounts/login/` (200) and
  `/guardian/` (302/403) and the logout round-trip.
- No `axe`/WCAG tooling was installed (not pre-existing; installing large
  dependencies was out of scope without approval). Contrast checked visually only.

### 9.4 Console / network errors observed

- **[LIVE]** Login page and all admin pages: **no** console errors or failed
  requests, except the intended `HTTP 403 /guardian/` when testing admin access.
- **[LIVE]** One transient `net::ERR_NAME_NOT_RESOLVED` on `/guardians/1/`
  (third-party jsDelivr), **not reproduced** — **G-16**.
- **[SIM]** `ERR_FILE_NOT_FOUND` for `/static/js/erp.js` is an artefact of
  `file://` rendering, **not** a staging issue.

### 9.5 Validation gaps (what was NOT verified and why)

- **[N/V] live** guardian-authenticated pages — no guardian password; reset out of scope.
- **[N/V]** guardian seeing another student's data via a tampered URL — needs a guardian session; **[SRC]** shows `guardian_visible_grant` returns `None` ⇒ **404**, and `guardian_required` ⇒ **403** for non-guardians (role separation is sound in code).
- **[N/V]** guardian → admin page denial live (expected `403`), and CPF/session
  expiry (needs wall-clock), and real-device/iOS-Android behaviour.
- **[N/V]** full WCAG 2.2 AA (no axe run; visual contrast only).

---

## 10. Prioritised remediation backlog

| Priority | ID | Fix | Effort |
| --- | --- | --- | --- |
| 1 | G-01 | Branded, explanatory 403 for guardian access | S |
| 2 | G-02 | Desktop guardian nav + active state | M |
| 3 | G-05 | "Not graded" (or remove) blank Grade column | XS |
| 4 | G-07 | Child-centred home dashboard (attendance %, latest result, urgent notice) | M |
| 5 | G-03 | Stable tab bar across all guardian pages | S |
| 6 | G-04 | Always-present Notices entry point | XS |
| 7 | G-10 | Accessible login validation (aria-invalid/describedby + live region) | S |
| 8 | G-09 | Report-card mobile affordance / stacked layout | M |
| 9 | G-08 | Report-cards list dates/status + shared empty state | S |
| 10 | G-13 | Attendance period + calculation context | S |
| 11 | G-11 | Content-Security-Policy header | S |
| 12 | G-12/G-06/G-14/G-17 | Tap targets, chip order, logout confirm, publication date | S |

---

## 11. Suggested next development sprint (highest value only)

1. **G-01** — Branded 403 page (removes the reported "guardian error" confusion).
2. **G-02** — Desktop primary navigation for the guardian portal.
3. **G-05** — Grade column: "Not graded" when blank (reuse the admin F16 approach).
4. **G-07 (first slice)** — Home dashboard cards: attendance % + latest report card + urgent notice.
5. **G-10** — Accessible login error wiring.

**Definition of done:** each item has an automated test (Django client for the
403/nav/grade/accessibility markup) plus a re-shot screenshot at 375 and 1440; no
new external-load console errors; expected score uplift to **≈7.5/10**.

---

*End of report. Read-only audit — no code, data, commits or credentials were changed
or persisted. Rotate the admin credentials that were shared in chat.*
