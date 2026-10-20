# Admin Desktop + Academic Year Rollover — Implementation Gates

Status: **UI-D0 ACTIVE, implementation kickoff** (2026-10-20).

Source planning branch: `docs/parked-admin-desktop-rollover` at `52ddd61` (historical planning record, leave unchanged).
Implementation base: `main` at `8dc84af` (2026-10-20).
Implementation branch: `ui/admin-desktop-spike`.

## Why the order matters

The admin desktop shell is a shared visual foundation. Create and review a minimal representative spike first; then extend it page-by-page. Rollover is a new high-impact domain feature and needs its own frozen ADR before code. Do not combine UI-D0 with rollover model/migration changes.

## UI-D0 — Desktop shell visual spike (active)

**Preferred visual reference:** `docs/ADMIN_DESKTOP_TABLER_REFERENCE.md` (Tabler live preview, concrete five-screen pattern mapping and non-adoption guardrails). Read it before making UI-D0 changes; capture before/after screenshots against the reference.

**Outcome:** prove a usable, accessible desktop admin workspace at >=992px while maintaining existing mobile/teacher/guardian behaviour.

1. **Read-only audit before code:** inspect `templates/base.html`, `partials/_sidebar.html`, existing topbar and breadcrumbs, `static/css/erp.css`, `static/js/erp.js`, `core/navigation.py`, `core/context_processors.py`, and representative existing admin screens. Identify existing reusable patterns and any collisions.
2. **Representative screens:** Overview, Students, Academic Year, teacher mapping, Timetable. Propose reusable sidebar, page header, filters, data table, stat card, and status patterns without recreating existing implementation unnecessarily.
3. **Narrow implementation:** template/partial/CSS/JS only as justified. Keep Bootstrap 5.3.3, server-rendered Django, existing tokens and styles, project-owned `erp-*` classes. Tabler is a reference, not a new dependency. Prefer minimal incremental diffs, not a rewrite.
4. **Breakpoints:** desktop workspace from 992px; protect small-screen teacher and guardian portals. For truly desktop-only admin tasks, a plain desktop-required explanation is acceptable, but never a substitute for authorization.
5. **Architecture and security:** no model, migration, service, route, forms, view logic, authorization or data/permission changes. Do not affect Phase 3 Fees, Guardian U4, or publishing semantics. No links to unauthorized destinations; enforce permissions in views as before.
6. **Evidence:** before/after screenshots for 390, 768, 992, 1280 and 1440px where supported, keyboard focus/skip link, nav active state, reduced motion, no horizontal page overflow, and no broken pages/403 shell.
7. **Verification:** focused template/navigation tests, `python manage.py check`, relevant UI tests, plus full suite when available. Report precisely what was run and failures; no deployment or merge.
8. **Stop:** submit a **draft PR** with screenshots, files changed, regressions checked, and proposed final components. Explicit design acceptance required before UI-D1.

### UI-D0 acceptance

- No new backend/database changes.
- Existing office routes continue working with permission-scoped nav.
- Teacher, Guardian, public login, and 403 have no unintended shell regressions.
- Desktop overview/student/year/mapping/timetable examples demonstrate a coherent reusable system.
- Existing project UI rules (`docs/UI_DESIGN_RULES.md`, `docs/UI_REFERENCES.md`) are respected; prioritize current source code over stale prose.
- No automatic broad migration; stop for review.

## UI-D1+ — Page-by-page adoption (not started)

After UI-D0 acceptance, freeze component conventions. Migrate selected admin pages in separate PRs with focused visual and behavioural regression checks. No catch-all restyling.

## Rollover 0 — ADR/decision freeze (queued; no code)

Use `docs/ACADEMIC_YEAR_ROLLOVER_PLAN.md` as source. Freeze terminology, enrollment lifecycle, source/target year eligibility, mapping, HOLD semantics, stale-plan handling, concurrency/locks, guardian access, and acceptance examples for Promote/Repeat/Graduate/Leave/Hold. Require explicit review before domain changes.

## Rollover 1 — Domain foundation (blocked on Rollover 0)

Rollover models and migration, deterministic validation, stale-plan detection, atomic idempotent apply service, lifecycle/guardian integration, PostgreSQL-focused tests. No admin UI yet.

## Rollover 2 — Desktop administrator workflow (blocked on 1 and UI shell rules)

Start/map/review/ready/apply/completion screens. Desktop-first design; preserving permissions, audit trail, and actionable validation.

## Rollover 3 — Cross-phase hardening (blocked on 2)

History, attendance, results/report cards, roll numbers, guardian access, teacher authorization, concurrency, idempotency, PostgreSQL integrity, browser acceptance.

## Gate discipline

One implementation gate at a time. Maintain status and evidence in this document or a linked gate ledger. Never infer academic promotion directly from marks. Never automatically create target ACTIVE enrollment when preparing a batch. Never silently rewrite old enrollment/attendance/results history. Do not merge until review.
