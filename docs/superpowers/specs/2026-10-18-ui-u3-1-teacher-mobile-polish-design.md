# U3.1 Teacher Mobile Polish — Design

**Date:** 2026-10-18
**Roadmap:** `docs/superpowers/plans/2026-10-14-ui-redesign-roadmap.md` (U3.1, between U3 and U4 Guardian portal)
**Rules:** `docs/UI_DESIGN_RULES.md`
**Builds on:** U1 shell, U2 daily screens, U3 marks and students (all on `main` at `146acec`). Component names (`.erp-card`, `.erp-pill`, `.erp-initials`, `.erp-tabbar`, `.erp-progress`, `partials/_empty.html`) are reused.

## Goal

A teacher on a 360px phone gets four primary screens that are calm, scannable and unmistakable: one dominant element per card, one obvious action, honest empty states. This is a **refinement sprint**, not a feature phase.

## Constraints

- Django + Bootstrap, server-rendered. No new framework, npm or build tooling. Little or no new JavaScript.
- **No models, migrations, URL changes, business-rule changes or teacher authorization changes.** Attendance, assessment and result rules are untouched.
- No invented data, totals, ranks, averages or fake progress percentages.
- Works with JS off; 360px and 390px with no page-level horizontal scroll; touch targets at least 44x44.
- Existing U2/U3 tests keep passing.
- Likely files: `templates/base.html`, `templates/partials/_tabbar.html`, `core/navigation.py`, `core/templates/core/my_home.html`, `my_students.html`, `my_assessments.html`, `my_results.html`, `static/css/erp.css`, plus tests and docs.

## Target screens

| Screen | URL name | Page heading (unchanged) | Mobile nav label (new) |
|---|---|---|---|
| My day | `core:my-home` | My day | **Today** |
| My students | `core:my-students` | My students | **Students** |
| My assessments | `core:my-assessments` | My assessments | **Assessments** |
| Results | `core:my-results` | Results | **Results** |

Out of scope: take-attendance, attendance history, marks entry, gradebook, term remarks pages (they keep their U2/U3 design and only inherit shared tokens).

## Decisions

| Topic | Decision |
|---|---|
| Naming | This sprint is **U3.1**. U4 stays the Guardian portal. |
| Top bar | Unchanged: school logo + `School ERP` + account avatar. |
| Bottom nav | `Today · Students · Assessments · Results`, text labels with small restrained icons, never icon-only. Page headings keep `My day`, `My students` etc. |
| Scope of styling | A Teacher-area styling hook (a body/main class) scopes new styles; no global change to every ERP card. |
| Cards | One dominant element per card; purposeful cards only. |
| Radius / depth | Outer 10-12px, inner 6-8px; border and surface first, subtle shadow only where it helps. |
| Merge order | The UI PR is not merged until the pending Logo Gate 1 staging check is finished, so logo verification stays isolated from a large visual change that auto-deploys. |

## Design

### Shell and navigation (Gate T1)

- `TEACHER_TABS` keeps the same four URL names; add a separate short label for the bottom bar (the heading source stays `My day` etc.). Active state computed as today.
- Each item: icon above a one-line text label. All four fit on one line at 360px with no wrapping or truncation; each item at least 44px wide and tall (the bar already uses `--erp-tabbar-h`).
- Active item: accent colour, heavier weight, top indicator, `aria-current="page"`. Inactive items use secondary text colour that meets 4.5:1.
- No hamburger for these four destinations.
- Add the Teacher-area hook on `<body>`/`<main>` when the area is teacher, so the new rules in `erp.css` apply only there.

### My day (Gate T2)

- Date line is preserved with real data.
- **Attendance card per duty:** Section name is the dominant (loud) element; state pill (Not taken / Draft / Submitted / Not a school day) is secondary; one clear action (`Take attendance`, `Continue` or `View`; none when not a school day).
- **Marks to enter:** assessment cards unchanged in data. When none: a deliberate neutral state titled **"No marks waiting"**, with the line "No open assessments are waiting for your marks." and a quiet "My assessments" link, replacing the loose "Nothing waiting." The title is neutral on purpose: the current view only proves that no open assessments are waiting. It cannot tell "all done" from "nothing assigned", so the UI must not claim the teacher completed anything.
- **Term remarks:** compact card per term and Section with honest `written / expected` text and the existing `<progress>`; the whole card is tappable (single link, stretched).
- `Attendance history` becomes a clear secondary navigation action (outline/link button with chevron), not a raw inline link.
- Spacing: 24px between major blocks, 16px inside groups, 8px between related lines. One accent for actions; status colours only for status.

### My students (Gate T3)

- Keep Section grouping, initials avatar and Present/Absent semantics (chips only for class-teacher Sections from a submitted register; draft/missing register keeps the "not submitted yet" line).
- **Student name is the dominant element.** Full row is the tap target (one link, accessible name = student name). The Present/Absent pill is visually non-interactive.
- `Class teacher` pill stays secondary.
- Tighter row height so more students fit, while rows stay at least 44px tall. No horizontal scroll at 360/390px.

### My assessments (Gate T4)

- Assigned-duty cards remain when data exists; Gradebook link and marks-entry links keep their behaviour and targets.
- One obvious action per assessment/duty group.
- Replace "You enter marks for nothing yet - ask an administrator to assign you." with an empty state: **No assessments assigned**, plus one short line on what happens next (an administrator assigns Subjects and Sections).
- **Term remarks** moves from the bullet list to the same compact row/card language as My day.
- No invented totals, ranks or averages.

### Results (Gate T5)

- Current, future and historical duty access is unchanged.
- Replace raw `<ul>` with consistent compact result rows/cards.
- Empty state: **No subject results yet**, with why (nothing finalized/published for the Subjects you teach) and what happens next.
- `Starting soon` and `Past duties` stay distinct sections. Past duties visibly say **Read-only** (badge or label near each group, in addition to the existing explanation text).
- Status labels are not styled as buttons.

### Shared polish and accessibility (Gate T6)

- Radius, text tiers, depth and motion as in `docs/UI_DESIGN_RULES.md` sections 1-3.
- Real `<button>` for actions, `<a>` for navigation; visible focus rings; one primary action per decision area; destructive actions separated.
- Loading, empty and error states stay distinct. No fake progress percentages.
- Motion about 150-250ms ease-out and disabled under `prefers-reduced-motion`.

## Gates

| Gate | Scope | Output |
|---|---|---|
| **T0** | This spec, `docs/UI_DESIGN_RULES.md`, roadmap entry. Docs only. | Review stop |
| T1 | Teacher shell/navigation | Bottom nav, Teacher hook |
| T2 | My day | Template + CSS |
| T3 | My students | Template + CSS |
| T4 | My assessments | Template + CSS |
| T5 | Results | Template + CSS |
| T6 | Shared polish + accessibility | CSS pass, focus/contrast/motion |
| T7 | Tests and visual acceptance | See below |

## Testing and acceptance (Gate T7)

New `core/tests/test_ui_teacher_polish.py` pins:

- Bottom-nav labels (`Today`, `Students`, `Assessments`, `Results`), order, `aria-current` on the active item, text label present for every item.
- Page headings unchanged (`My day`, `My students`, ...).
- Purposeful empty states: "No assessments assigned" and "No subject results yet" appear when there is no data, and the old wording is gone.
- My day neutral "No marks waiting" state, attendance action per state, term-remarks card link.
- Results: `Starting soon`, `Past duties` and a Read-only marker; no tappable status labels.
- Accessibility-critical markup: real buttons vs links, one link per student row, `aria-hidden` on decorative icons/avatars.
- No "Total", "Average", "Rank" text on the four screens.

Plus:

- Existing U2/U3 tests stay green; full suite on PostgreSQL (`--parallel 4`); `ruff check .`; `makemigrations --check` shows no changes.
- Manual screenshots at **360px, 390px and desktop** for the four screens, populated and empty where feasible, with no page-level horizontal scroll.

## Out of scope

Guardian portal (U4); office screens; take-attendance and marks-entry redesign; new JS components; dark mode; any data or permission change.
