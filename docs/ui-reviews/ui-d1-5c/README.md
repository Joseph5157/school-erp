# UI-D1-5C — Result reports: synthetic screenshot and accessibility evidence

**Local synthetic evidence only.** Captured with Playwright (Chromium) against a throwaway **SQLite** database seeded with invented data (Academic Year "2026-27", Grade 6 A and B, two Subjects, five Students in Section A including one with a deliberately very long name and a late joiner, nine finalized assessments including one with a long name and one corrected result, an unfinished draft, a Term remark, two class teachers over the year). It is not PostgreSQL, staging or production, and the database was deleted afterwards. The automated tests ran on PostgreSQL (see the PR).

Widths: 360, 390, 768, 992, 1024, 1280, 1440 (full-page PNG). `measurements.json` holds 152 probes (every state, user and width, a matrix keyboard and sticky-column probe, and a 195px / "390 at 200% zoom" probe).

| File prefix | URL | What it shows |
| --- | --- | --- |
| `sheet-*`, `sheet-draft-*` | `/assessments/1/result-sheet/`, `/assessments/10/result-sheet/` | Result sheet with the Finalized badge, Absent and Not graded, audited-corrections note; a draft shows "not finalized yet" and no table |
| `student-*`, `student-absent-*`, `student-empty-*` | `/students/{1,2,6}/results/` | Student results with Term report card links; Absent shown as Absent; "No finalized results yet." |
| `matrix-first-*` | `/academic-years/4/subject-results/` | Toolbar and guidance only, no table, no default selection |
| `matrix-maths-*`, `matrix-sci-term-*` | `?offering=1&section=1`, `?offering=2&section=1&term=1` | The matrix: labelled scroll region, **sticky Student column**, Absent, a dash for a Student with no result, no totals |
| `matrix-empty-section-*` | `?offering=1&section=2` | "No finalized results for this Subject and Section." |
| `matrix-invalid-*` | `?offering=999999&section=abc` | The **existing** flash message "Choose a Subject, Section and Term from the lists." and the guidance; no invented field errors |
| `matrix-scrolled-*` | matrix after ArrowRight | Student column stays pinned at 360, 390 and 1024px |
| `card-*`, `card-term2-*`, `card-empty-*` | `/students/1/report-card/{1,2}/`, `/students/6/report-card/1/` | Administrator Term report card, other Term, a Student with no results and no remark |
| `card-teacher-*` | `/my/report-cards/1/1/` as `demo_rao` | **Same template** in the teacher shell: "Class report card", My students link, no administrator breadcrumb, no All results link |
| `card-dual-teacher-area-*`, `card-dual-admin-area-*` | the teacher and the administrator route as `demo_dual` (administrator and class teacher) | Chrome follows the area; "All results" shows in both because the user holds `view_studentresult` |
| `viewer-*` | `demo_view` (`view_studentresult` only) | No back links, no trail, no sidebar |
| `school-card-*` | `demo_school` | Trail `Overview / Students / Student / Results / Report card` |

## Measurements

| Check | Result |
| --- | --- |
| Document horizontal overflow | **0px** at 360, 390, 768, 992, 1024, 1280, 1440 in every state and for every user |
| 200% zoom equivalent (390 → 195px) | **43px**: the pre-existing shared top-bar account menu limit already disclosed in D1-4 and D1-5A/B |
| H1 count / `aria-describedby` | exactly 1 on every page; 0 dangling |
| Matrix on phones | local labelled, focusable region: 427px (360), 397px (390), 139px (1024), none at 1280 and up |
| Sticky Student column | verified at 360, 390 and 1024px: after ArrowRight the Student cell's left edge still equals the region's left edge (`position: sticky`) |
| Keyboard | focus ring 3px on the matrix region; ArrowRight scrolls it; page overflow stays 0px |
| Shared report card | administrator route: Term report card + trail; teacher route: Class report card, no trail; dual-role user: each route keeps its own chrome |
| Restricted viewer | links and trail follow permissions (no Student, assessment or sidebar links) |

## Known limits

- SQLite, synthetic data; no staging or production verification; no manual screen-reader pass.
- The matrix filter is three plain selects with real `<label for>` associations. They have no Django form, so invalid input shows only the existing flash message, not per-field errors (a real form is a recorded follow-up).
- `_result_cells.html` is unchanged on purpose (it is also used by the teacher Student detail), so Marks and % are not right-aligned in the four-cell result tables.
- Wide tables scroll locally on phones (sheet 119px, Student results 607px, report-card subject tables 164 to 224px, matrix about 400px at 390px).
- The report card's PDF listing belongs to Documents (D1-6) and is untouched; no results export exists.
- 43px top-bar overflow at 195 CSS px is pre-existing.
