# UI-D1-4C-1 — Attendance Reports hub, Daily absent students, Missing attendance: synthetic screenshot evidence

**Local synthetic evidence only.** Captured with Playwright (Chromium) against a throwaway **SQLite** database seeded with invented data ("Demo Student One" to "Five", Grade 6 A and B, and one deliberately long Class/Section name), served by `runserver` with `DJANGO_DEBUG=True`. This is not PostgreSQL, staging or production, and the database was deleted afterwards. The automated tests ran on PostgreSQL (see the PR).

Seed: Section A has Mon 19 Oct submitted (Student One absent, note "Fever"), Tue 20 **Draft** (a saved Absent entry that must not count), Thu 22 submitted; Section B has Mon 19 submitted (Student Four absent, "Family function"); the long Section has a Mon 19 **Draft** with nothing marked. Every other instructional day is **Not taken**. Reports date window: 19 to 23 Oct 2026.

Widths shot: 1440, 1280, 1024, 992, 768, 390 (full-page PNG). Restricted users: 1280 and 390.

| File prefix | URL | What it shows |
| --- | --- | --- |
| `index-*` | `/attendance/reports/` | Hub: three report cards, Registers shortcut in the header, breadcrumbs, active sidebar item |
| `absent-pristine-*` | `/attendance/reports/absent/` | Guidance only, no table, no errors, no default date |
| `absent-results-*` | `?date=2026-10-19` | Two absent students with notes (Draft absence on 20 Oct is not listed) |
| `absent-empty-*` | `?date=2026-10-21` | "No submitted absences on this date." (valid, not an error) |
| `absent-invalid-empty-*`, `absent-invalid-garbage-*` | `?date=`, `?date=not-a-date` | Error summary plus field error, no table, no "no results" claim |
| `missing-pristine-*` | `/attendance/reports/missing/` | Guidance only |
| `missing-results-*`, `missing-section-a-*` | `?start=2026-10-19&end=2026-10-23[&section=1]` | **Draft** (amber badge + Open register) versus **Not taken** (neutral badge, nothing to open); long Section names wrap |
| `missing-inverted-*` | start after end | Non-field error in the summary only |
| `missing-invalid-fields-*` | empty start, unknown Section | Two errors, fields flagged, no table |
| `entry-*` | `demo_entry` (view_school + view_attendanceentry) | Index with **no** Missing card and **no** Registers shortcut; absent results with plain-text Section; Missing is a 403 (`entry-missing-403-*`) |
| `register-*` | `demo_register` (view_school + view_attendanceregister) | Missing page with the register-list header action and no Reports crumb; index is a 403 (`register-index-403-*`) |
| `noschool-*` | `demo_noschool` (view_attendanceentry only, no view_school) | Page renders with **no sidebar and no breadcrumb trail**, so no Overview link at all |

## Measurements (`measurements.json`)

125 page probes (every state above at 360, 390, 768, 992, 1024, 1280, 1440px, plus restricted users).

| Check | Result |
| --- | --- |
| Document horizontal overflow (`scrollWidth - clientWidth`) | **0px** at every width in every state |
| 200% zoom equivalents | 1280 → 640px: 0px. 390 → 195px: **43px**, the pre-existing shared top-bar account menu limit already disclosed in D1-4A; not introduced here |
| H1 count | exactly 1 on every 200 page |
| `aria-describedby` references | every token resolves to an element on the page (0 dangling), including invalid states |
| Phone table fit (390px, Missing results) | tables are `erp-keep`, so State and Absence note stay on screen with no local scroll (region scroll range 0) |
| Summary link | clicking "Start: This field is required." moves focus to `#id_start` |
| Focus ring | focused input shows a 3px solid outline |

Review-driven fixes made during capture: the first capture showed the State and Absence note columns pushed off-screen on phones and "Open register" wrapping beside the Draft badge; the tables now fit, with a small scoped `erp-attendance-report-table` rule.

## Review correction: Missing attendance toolbar on one row

Review asked for Start, End, Section and "Show missing attendance" to fit on one row at 1280 and 1440px. The form gets a scoped `erp-attendance-report-toolbar` modifier (existing `erp-toolbar erp-toolbar--inline` pattern kept) and, from 576px up, its three fields share the row (`flex: 1 1 11rem`, min 11rem, max 17rem) instead of each claiming 18rem. Under 576px the shared full-width stacking rule is untouched. Template change: one class on the `<form>`. All names, required markers, GET parameters, validation and permissions are unchanged. Probes (`toolbar` key in `measurements.json`, rows counted by distinct bottoms of the fields and the button):

| Width | Rows (pristine / results / inverted / invalid) | Field width | Clipped labels / form overflow / page overflow |
| --- | --- | --- | --- |
| 1440 | 1 / 1 / 1 / 1 | 272px | none / 0 / 0 |
| 1280 | 1 / 1 / 1 / 1 | 227px | none / 0 / 0 |
| 1024 | 2 / 2 / 2 / 2 (button wraps) | 215px | none / 0 / 0 |
| 992 | 2 / 2 / 2 / 2 | 205px | none / 0 / 0 |
| 768 | 2 / 2 / 2 / 2 | 223px | none / 0 / 0 |
| 390 and 360 | 4 (fields and button stack) | 324 / 294px | none / 0 / 0 |

Refreshed: all `missing-*` and `register-missing-results-*` PNGs at 390, 768, 992, 1024, 1280 and 1440 (the invalid-form states are `missing-invalid-fields-*` and `missing-inverted-*`). Re-checked on the final head: document overflow 0px at every width in every state (43px only at 195px, the known shared top bar); 0 dangling `aria-describedby`; the summary link moves focus to `#id_start`; focus outline 3px solid; tab order from the error summary goes Section link, Start (day/month/year segments of the native date control), End. Final results: `manage.py check` clean; focused UI modules 102 OK; **full PostgreSQL `--parallel 4`: 2558 tests OK**.

Minor, left as is: in the invalid state the existing toolbar bottom-aligns fields, so a field with an error message below it makes its label sit a little higher than its neighbours.

## Known limits

- SQLite, synthetic data; no staging or production verification.
- No automatic focus move to the first invalid field: that comes only from `FieldAccessibilityMixin`, which these forms do not use (`core/forms.py` is out of scope). The live-region summary with field links is the mitigation. No manual screen-reader pass.
- Very long Section names make tall rows on phones (they wrap), by design rather than scrolling.
- Users without `view_school` get no admin sidebar or breadcrumbs on these pages (existing `user_areas` behaviour).
- Monthly summary and Student history are D1-4C-2 and unchanged.
