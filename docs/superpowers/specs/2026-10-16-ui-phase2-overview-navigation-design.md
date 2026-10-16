# UI Phase 2: Admin Overview and Section-Aware Navigation — Design

Date: 2026-10-16
Source: `School_ERP_Admin_UI_UX_Audit.pdf` findings F04 (no dashboard) and F05 (deep-page context lost).
Builds on: Phase 0 (PR #54, merged) and Phase 1 (PR #55, responsive foundation).

## Intent

An admin or office user lands on a page that answers "what needs my attention today?" on one screen, down to 320px. From any deep page they can see where they are (breadcrumbs, highlighted sidebar section) and go back to the parent predictably.

Agreed with the user: the first version shows the core four queues only (no recent-activity feed); read-only; no new models or migration; admin/office roles only.

## Non-goals

Recent-activity feed, charts, sortable tables (Phase 3), any new model or migration, changes to teacher (`my-home`) or guardian (`portal:home`) landing pages, changes to `choose-area`.

## Design

### 1. Routing

- New view `admin_overview` at `overview/`, name `core:admin-overview`, gated by `core.view_school` (the permission that defines the admin area).
- `core.authorization.user_areas`: the admin area's landing URL changes from `core:school-detail` to `core:admin-overview`. `home()`, the topbar logo and `choose-area` follow with no other change.
- The no-area fallback in `home()` is unchanged.
- Sidebar: add an "Overview" link at the top of `OFFICE_NAV`, permission `core.view_school`.

### 2. Overview cards

New module `core/dashboard.py`: one small function per queue returning `{key, title, count, summary, url, oldest?}` or `None` when the user lacks the source permission. Each function reuses the queryset the corresponding list page uses (extract a shared helper where the view builds it inline) so the count and the linked list cannot disagree.

| Card | Source | Permission |
|---|---|---|
| Attendance today | sections with an `AttendanceRegister` for today vs. sections without | `core.view_attendanceregister` |
| Applicants awaiting decision | applicants with no admission decision; show oldest waiting time | `core.view_applicant` |
| Results to publish | the stale-publications source | `core.view_termpublication` |
| Pending access reviews | the Guardian access reviews source | `core.view_guardianaccessreview` |

- Rendered through one `partials/_queue_card.html`, styled with the Phase 1 tokens and `_status_badge.html`.
- Empty queue reads "Nothing waiting", not "0".
- Cards the user may not see are omitted entirely.
- A school with no academic year or no sections shows a "Set up your school" empty state with a link to Academic Years / Classes, instead of failing.

### 3. Breadcrumbs and section-aware navigation (F05)

- New `core/breadcrumbs.py`: a map from URL name to `(section_url_name, parent_url_name, label)`. Views do not build trails by hand.
- `partials/_page_header.html` gains an optional `breadcrumbs` list, rendered as `<nav aria-label="Breadcrumb"><ol>…</ol></nav>` with `aria-current="page"` on the last item.
- A context processor supplies `breadcrumbs` and `nav_section` from the resolved URL name, so templates need no per-view change beyond including the header partial.
- `navigation._link`: `active` becomes true when the link's URL name equals the current URL name **or** equals the current page's mapped section. Exact-match behavior is otherwise unchanged.
- Back/Cancel links on deep pages point to the mapped parent rather than browser history.
- Pages covered at minimum (named in the audit plus Phase 0 additions): student detail, student deactivate confirm, applicant detail, applicant decision confirm, attendance register detail, attendance correction, announcement create/detail.

### 4. Error handling and access

- The view enforces `core.view_school`; the sidebar stays display-only, as today.
- Teachers and guardians never reach the view. A multi-role user still chooses via `choose-area`.
- Unmapped URL names get no breadcrumbs and keep exact-match highlighting (safe default).

### 5. Testing

- Per-card tests: count correct, link target, empty-queue copy, hidden when the permission is missing.
- Landing: an admin-only user hitting `/` is redirected to `/overview/`; a multi-role user still reaches `choose-area`; teacher and guardian landings unchanged.
- Navigation: for each mapped deep page the parent sidebar link has `aria-current`/`active`; an unmapped page behaves as before.
- Breadcrumb markup: `<nav aria-label="Breadcrumb">`, `aria-current="page"` on the last item only.
- Authorization: non-admin gets 403/redirect on `/overview/` consistent with other admin views.
- Browser: Playwright pass at 320px and 1440px reusing the Phase 1 viewport sweep; no document overflow.

## Open items to confirm during planning

- Exact inline querysets behind the stale-publications, access-review and applicant-list pages (extract helpers only where needed).
- Whether "awaiting decision" uses the applicant's admission-decision field or a status; follow what the Applicants list filters on.
