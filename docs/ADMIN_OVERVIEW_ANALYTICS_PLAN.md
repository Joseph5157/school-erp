# Admin Overview analytics (mobile PWA) - plan

Status: **DRAFT for product-owner approval. No code written.**
Reference: the earlier SIMS Discipline Management System admin analytics (trend, comparison bars,
repeat-violator list, heatmap, one shared filter). We port the *ideas*, not the code.

## Scope

- Admin only, on the **existing Overview page** (`/overview/`, `core/templates/core/admin_overview.html`).
- **Phone first and phone only.** Verify at 360 and 390 px. No desktop-specific layout work.
- Teacher dashboard: out of scope for now.
- Online-only PWA: no service-worker caching of analytics data, no offline behaviour.
- No new model, no migration. Read-only aggregates over existing data.

## Data rules (these decide what is allowed to be shown)

From ADR 0007 / the model docstrings:

- Only `AttendanceRegister.status = SUBMITTED` counts. DRAFT is not official; **no register = NOT TAKEN**.
- A missing entry is never ABSENT. Statuses are exactly PRESENT and ABSENT - **no "late"** widget.
- Attendance % = PRESENT / (PRESENT + ABSENT) over submitted entries only.
- Only instructional days (school calendar) have registers; do not render non-days as 0%.
- Marks: `StudentResult` MARKED has a score; ABSENT is never a zero. Only FINALIZED assessments count.
- No fee model exists, so **no fee widgets**.
- Empty and tiny datasets must render an honest "No data yet" state, never a fake 0% or a flat line.

## Widgets by gate

### Gate A - Attendance picture
1. **Today strip** (horizontal scroll tiles): Present, Absent, Registers submitted of expected, Registers not taken.
2. **Attendance trend**: last 14 days (default) as a server-rendered inline SVG area/line chart, with a
   "vs previous 14 days" badge (improving / steady / worsening) and peak/lowest day.
3. **Class comparison**: horizontal bars of attendance % per class for the selected period, lowest first.

### Gate B - Follow-up
4. **Frequent absentees**: cards (not a table) for students under a configurable attendance threshold in the period.
   Shows student name, class, absent days. Links to the existing student detail. Permission-gated like the student list.
5. **Attendance heatmap**: calendar grid, one cell per instructional day, tiered fill, non-days left blank.

### Gate C - Marks and period control
6. **Marks snapshot**: latest term - average per class and a score-band distribution bar (finalized assessments only).
7. **Period filter**: a single sticky chip ("Last 14 days") opening a bottom sheet (14 days / this month / this term /
   custom) plus an optional class selector. Plain GET query params so it works without JS state.

## Technical approach

- New module `core/analytics.py`: one pure function per widget, all taking one `Period` + optional `class_grade` filter.
  Uses ORM aggregation (`Count` with `filter=`, `TruncDate`), no per-row loops, bounded query count per widget.
- `admin_overview` view calls it and passes plain dicts. Templates render partials under `templates/partials/_analytics_*.html`.
- Charts are **inline SVG built from precomputed points in the view layer** - no JS chart library, no new static asset,
  nothing for the PWA to cache. Each chart gets a text alternative (`role="img"` + summary, and a visually-hidden data list).
- Colours and spacing via existing tokens in the stylesheet; tables are not used on phones (card lists), per the
  phone-table CSS rule noted for this project.
- Date handling uses `business_today()`, never `date.today()`.
- Authorisation: same `administrator_required("core.view_school")`; the absentee list additionally requires
  `core.view_student`. Aggregate figures only go to the page for roles allowed to see them.
- Performance: the Overview must not slow down. Budget: analytics adds a small fixed number of queries; assert it with
  `assertNumQueries`-style ceiling tests.

## Testing

- Unit tests per `core/analytics.py` function with fixtures covering: empty school, DRAFT-only registers,
  mix of SUBMITTED/DRAFT, non-instructional days, ABSENT results vs unmarked, class filter, period edges.
- View tests: permission matrix (admin with/without `view_student`, teacher, guardian denied), query-count ceiling.
- Rendering: SVG contains expected points; empty states; no template errors with zero data.
- Manual: screenshots at 360 and 390 px against the seeded demo data, after `collectstatic` and a server restart.

## Delivery

- Branch `feat/admin-overview-analytics` from `origin/main`; one PR per gate (A, B, C).
- Each gate: tests green with `--parallel 4`, screenshots attached, then staging check.
- Not deployed until the product owner approves each gate.

## Decisions (product owner)

1. Default period: **last 14 days** (default assumed; not explicitly answered - change if wrong).
2. Frequent absentee = **a set number of absent days** in the period (not a percentage). Default 3, kept as one named constant.
3. Trend chart is **school-wide only** (no class selector in Gate A).
