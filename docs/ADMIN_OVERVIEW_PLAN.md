# Admin Overview — attention first (plan)

Status: **PLAN, decisions settled 2026-10-25 (all four recommendations accepted); ready to implement.** No code written. Branch `docs/admin-overview-plan` from `origin/main` (`d56b718`, after S1–S3 / PR #126).
Source: Admin Desktop UI/UX audit (24 Oct 2026), items **UI-01** (High) and **UI-12** (Medium).
Out of scope: colours/palette (UI-10), icons, header redesign (UI-11), Teacher/Guardian, mobile/tablet layout, any model/migration/permission/route change. Cards keep their existing data sources (`core/dashboard.py`), so counts and destinations cannot change.

## What is wrong today
- `admin_overview.html` renders the setup checklist first, then the card grid. While setup is incomplete the checklist is ~700px tall, so the first card row starts at y≈717 at 1366×768 (audit) and the page promise "What needs attention today." is answered below the fold.
- Cards are equal-sized. The only difference for a non-zero card is a 4px left border (`.erp-stat-card--attention`); a zero card repeats the same large box with "Nothing waiting." and an Open button.
- Verified on staging (2026-10-25, 1440×900): checklist at 6 of 8 done still shows all 8 rows, including the six completed ones.

## Proposed design (one PR, two commits)

### Commit 1 — UI-01: operations first, setup second
Order on the page becomes: header → **attention cards** → setup.
- While setup is **incomplete**: the checklist card shows only the *incomplete* steps under a one-line summary and the progress bar ("6 of 8 done"). Completed steps fold into a native `<details>` ("Show 6 completed steps"), closed by default, no JS needed.
- When setup is **complete**: unchanged (the one-line "School setup complete" row), now below the cards.
- Brand-new school (0 steps done): checklist stays *above* the cards, because nothing operational exists yet. Rule: `setup_done == 0` → checklist first; otherwise cards first (decision 1).
- View change is limited to passing one flag (`setup_first`). Other context unchanged.

### Commit 2 — UI-12: urgency encoded in the cards
- No new data. A small helper in `core/dashboard.py` splits the existing list into **attention** (`count > 0`) and **clear** (`count == 0`), keeping `_CARDS` order inside each group. Unit-tested.
- **Attention cards**: full card, one fixed slot layout — label · value · summary/age line · action (icon slot reserved; icons are out of scope). The action button is `btn-primary` for the first attention card only and outline for the rest, matching the checklist's "only the next step is filled" rule.
- **Clear cards**: one compact row below, "Nothing waiting: Attendance today · Results to publish · Pending access reviews", each a link to its page. No big zero numbers, no per-card Open button.
- All-clear state: if every visible card is zero, a single calm line "Nothing needs attention today." followed by the compact links.
- Accessibility: attention region is a `<section aria-labelledby>` "Needs attention"; the clear row is a labelled list. Links keep the visually-hidden destination name already used on today's Open buttons.
- CSS: new `.erp-attention-grid` and `.erp-clear-row` in `erp.css`. `.erp-stat-card` stays untouched. Existing tokens only (UI-14 token work is separate).

## Tests
`core/tests/test_ui_admin_phase2.py::test_page_shows_cards_and_empty_copy` currently asserts "Nothing waiting" and must be updated; "Nothing to show for your role" must keep working for users with no card permission. Add:
1. Cards render before the checklist when `setup_done > 0`, after it when `setup_done == 0`.
2. Checklist lists incomplete steps only plus a closed `<details>` for completed ones; step actions and the single `btn-primary` "next" unchanged.
3. Non-zero cards precede zero cards; order within each group follows `_CARDS`.
4. Permission-less users still see no cards; all-clear copy appears only when every visible card is zero.
5. Zero cards render as links in the compact row with accessible names.

## Decisions (settled: option 1 of each accepted)
1. **Checklist position for a brand-new school.** Recommend: checklist first only when no step is done; cards first once any step is done. Alternative: cards always first (simplest, but a fresh school sees a page of zeros above its setup).
2. **Completed setup steps.** Recommend folding into a closed `<details>`. Alternative: remove them entirely (shorter, but admins lose the reassurance of what is done).
3. **Zero cards.** Recommend the compact "Nothing waiting" row with links. Alternative: small cards in a second grid (bigger click targets, more noise).
4. **KPI count.** Audit asks for 4–6 KPIs on top. The six existing cards already fit; recommend no new metrics in this gate (new data sources need their own permission and test review).

## Verification
`manage.py check`, full suite (`--parallel 4`; the known flaky `u4_3a_subject_order` and the one date-dependent test on main are unrelated), `collectstatic` + server restart before screenshots. Screenshots of `/overview/` at 1366×768, 1440×900, 1920×1080 for three states: new school, setup in progress with non-zero cards, setup complete with all clear. Acceptance: at 1366×768 the first attention card is fully visible without scrolling in the in-progress state (audit measured y≈717). Teacher and Guardian home unchanged. Rollback = revert the PR; no migrations.
