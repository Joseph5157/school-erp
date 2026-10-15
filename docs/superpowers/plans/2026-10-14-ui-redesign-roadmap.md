# UI Redesign Roadmap

> Sequence of implementation plans for the School ERP UI/UX redesign. Each plan ships working, tested software on its own. Only **U1** is written in full; each later plan is written (with the writing-plans skill) when the one before it is merged, because it builds on U1's components.

**Spec:** `docs/UI_REFERENCES.md` (34 Mobbin team picks, known problems, design rules) and the illustrated report https://claude.ai/artifact/7zr4DVJGh3fB5ZMbF8xxEQ.

**Starting point:** `origin/main` (Phases 1, 2, 4, 5, 6 complete; 944 tests). The local branch `feat/seed-demo-data` is behind `main`; every UI branch starts from an up-to-date `main`.

## Principles for every plan

- **Server-rendered Django + Bootstrap 5.3.3 stays.** No SPA, no build step, no npm. Our own CSS lives in `static/css/erp.css`; small progressive-enhancement JS in `static/js/erp.js`. Pages must work with JS off.
- **Behaviour does not change.** These plans change templates, CSS and view context only. No model or migration changes, no new permissions. Every existing test keeps passing.
- **Views still enforce access.** Navigation is filtered by permission for tidiness only.
- **Domain rules are visible in the UI:** draft vs submitted, blank ≠ absent, no totals/weighting/ranks on report cards, username (not email) sign-in.
- **Phone-first for teachers and guardians, desktop-first for the office.** Every page usable at 360 px wide without horizontal page scroll.

## Plans

| Plan | Scope | Mobbin picks used | Depends on |
|---|---|---|---|
| **U1 Foundation** (written: `2026-10-14-ui-u1-foundation.md`) | Static/storage fix, design tokens, viewport, office sidebar + phone drawer, teacher and guardian bottom tabs, account menu with role switcher, sign-in and change-password pages, empty-state and toast components | 1.1 Square, 1.2 Shopify, 1.3 ShopBack, 4.1 Cash App (role sheet), 5.11 Sprig, 5.12 Fresha, 5.13 Luma | — |
| **U2 Teacher daily screens** | My day cards with progress; take-attendance screen with count tabs, big Present/Absent buttons, absence-note sheet, sticky submit bar, toast; attendance history | 3.1 Insight Timer, 3.2 Luma, 5.13 Luma | U1 |
| **U3 Teacher marks and students** | Phone marks entry (one row in focus, numeric keypad, next/previous); desktop gradebook grid; my students list with initials avatars; class overview with status chips | 3.3 Yazio, 5.2 Google Classroom, 3.4 Cash App, 5.4 SchoolAI | U1 |
| **U4 Guardian portal** | Child switcher sheet; child overview; attendance month calendar with Present/Absent/Not recorded legend and summary line; report cards as subject blocks on phone and a clean table on larger screens | 4.1 Cash App, 4.2 Insight Timer + MacroFactor, 4.3 Coursera, 5.5 Coursera web | U1 |
| **U5 Office lists and records** | Shared list component (search, filter buttons, count, status pills, paging, cards on phone) for students, guardians, applicants; admissions board; record pages with tabs and details rail; section page with teachers + students; add-people dialog | 2.1 HoneyBook/Sprig/Calendly, 2.2 HoneyBook, 2.3 Calendly, 5.1 Google Classroom, 5.10 Square | U1 |
| **U6 Office academics and results** | Office home (counts + to-do + shortcuts); academic calendar month grid; grading-scale range editor; publish/withdraw confirmation; office attendance register grid | 5.7 HoneyBook, 2.5 Calendly, 5.9 Zoho, 5.8 Sweatpals, 5.3 Fibery | U1, U5 list component |
| **U7 Reports and audit** | Reports hub with categories; report pages with From/To and headline numbers; history timelines for corrections, publications and access reviews | 2.7 Shopify + HoneyBook, 2.8 Basecamp | U1, U5 |
| Later (Phase 7) | Announcements list | 5.14 Mindtrip | Phase 7 models |

Still undecided (resolve when the owning plan is written):
- 2.4 admission/enrolment forms (U5) — only Workable/Gusto flows were shortlisted.
- Role switching (U1) has no pick; U1 reuses the 4.1 Cash App sheet style.

## Definition of done for each plan

1. `python manage.py test` passes (all existing tests plus the plan's new ones).
2. `ruff check .` passes.
3. Manual check with the dev server at 360 px and 1280 px widths for each changed page, as office, teacher, and guardian users from `seed_demo`.
4. `docs/UI_REFERENCES.md` status line updated; PR opened against `main`.
