# UI-D1-4C-2 — Monthly Class/Section summary and Student attendance history: synthetic screenshot evidence

**Local synthetic evidence only.** Captured with Playwright (Chromium) against a throwaway **SQLite** database seeded with invented data ("Demo Student One" to "Six", Grade 6 A and B, one deliberately long Class/Section name), served by `runserver` with `DJANGO_DEBUG=True`. It is not PostgreSQL, staging or production, and the database was deleted afterwards. The automated tests ran on PostgreSQL (see the PR).

Seed: Section A has Mon 19 Oct submitted (Student One absent, note "Fever"), Tue 20 **Draft** (Student Two saved Absent, which must not count) and Thu 22 submitted (Student Three absent); Section B has Mon 19 submitted (Student Four absent). **Student Six** joins Section B on 20 Oct and has only a **Draft** entry (nothing reportable). Student Five (long Section) has no entries. Reports window: October 2026.

Widths shot: 1440, 1280, 1024, 992, 768, 390 (full-page PNG). Restricted users: 1280 and 390.

| File prefix | URL | What it shows |
| --- | --- | --- |
| `monthly-pristine-*` | `/attendance/reports/monthly/` | Guidance only, no table, no default Section or month |
| `monthly-results-*` | `?section=1&month=2026-10` | Header, three day-count facts, per-Student Present / Absent / Attendance %, Total row, dash legend |
| `monthly-section-b-*` | `?section=2&month=2026-10` | Student Six (Draft only) shows a **dash**, not 0% |
| `monthly-long-dash-*` | `?section=3&month=2026-10` | Long Class/Section name; Student Five with nothing reportable shows a dash |
| `monthly-no-students-*` | `?section=1&month=2026-05` | "No Students enrolled in this Section during this month." |
| `monthly-invalid-empty-*`, `monthly-invalid-month-*` | empty fields; `month=bad` | Error summary plus field errors, fields flagged, no table |
| `history-first-load-*` | `/students/1/attendance/` | **Unfiltered first load**: no filter note, full history and summary |
| `history-filtered-*` | `?start=2026-10-19&end=2026-10-20` | Valid filter: headings carry the applied range, no "not applied" note, Clear filter |
| `history-invalid-inverted-*`, `history-invalid-garbage-*` | start after end; `start=x` | Errors shown, entered values kept, **"The date filter was not applied; showing all recorded attendance."** above both the Summary and the History, headings read "all recorded attendance" |
| `history-draft-only-*` | `/students/6/attendance/` | Draft entry listed, summary 0 / 0 / 0 with a dash and its legend |
| `history-empty-*` | `/students/5/attendance/` | "No attendance recorded." |
| `entry-*` | `demo_entry` (view_school + view_attendanceentry) | Monthly summary; Student history with **no Back to student** and trail `Overview / Attendance` |
| `student-*` | `demo_student` (+ view_student) | Student history with **Back to student** and full trail `Overview / Students / Student / Attendance` |
| `noschool-*` | `demo_noschool` (view_attendanceentry only) | Page renders with no sidebar and no trail (no Overview link at all) |
| `register-*-403-*` | `demo_register` (view_attendanceregister only) | Both pages are 403, as before |

## Measurements (`measurements.json`)

139 page probes (every state at 360, 390, 768, 992, 1024, 1280, 1440px, plus restricted users).

| Check | Result |
| --- | --- |
| Document horizontal overflow (`scrollWidth - clientWidth`) | **0px** at every width in every state |
| 200% zoom equivalents | 1280 → 640px: 0px. 390 → 195px: **43px**, the pre-existing shared top-bar account menu limit already disclosed in D1-4A and D1-4C-1 |
| H1 count | exactly 1 on every 200 page |
| `aria-describedby` references | every token resolves to an element on the page (0 dangling), including the invalid states |
| Toolbar (Section/Month, Start/End) | one row at 768px and wider, stacked at 390 and 360px, no clipped labels, no form overflow |
| Monthly table on phones | `erp-keep`: fits at 390px with no local scroll (0px); at 360px it scrolls 15px inside its labelled region |
| History table on phones | six columns scroll inside the labelled, focusable region (386px range at 390px); ArrowRight scrolls it (178px reached after 40 key presses) |
| Invalid-filter disclosure | "not applied" note appears exactly twice on the two invalid history states and zero times on first load, filtered and Draft-only states |
| Summary link | clicking the error summary's "Start" link moves focus to `#id_start` |
| Focus ring | focused input shows a 3px solid outline |
| Back to student | present only for `demo_admin` and `demo_student` (view_student) |

Review-driven fixes made during capture: the first capture showed the Monthly table 9px wider than its region at 390px, so the three numeric columns use tighter padding on phones; and the keyboard-scroll probe was changed from End (which scrolls vertically) to ArrowRight.

## Known limits

- SQLite, synthetic data; no staging or production verification.
- No automatic focus move to the first invalid field (needs `FieldAccessibilityMixin`; `core/forms.py` is out of scope). The live-region summary with field links is the mitigation. No manual screen-reader pass.
- A saved entry on a Draft register shows its own status label (for example "Absent") in the history next to a **Draft** badge. The explanatory note says why it may not be counted; the per-row "counted" marker is the deferred D7 follow-up.
- At 195 CSS px (390 at 200% zoom) the shared top bar overflows 43px; pre-existing.
- The Monthly table scrolls 15px locally at 360px.
- Student names wrap onto several lines at 390px in the Monthly table, rather than being clipped.
