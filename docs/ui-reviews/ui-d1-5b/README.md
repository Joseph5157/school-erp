# UI-D1-5B — Assessments, finalization and corrections: synthetic screenshot and accessibility evidence

**Local synthetic evidence only.** Captured with Playwright (Chromium) against a throwaway **SQLite** database seeded with invented data (Academic Year "2026-27", Grade 6 A and B, five Students including one with a deliberately very long name, five assessments in the states below, a teacher, a grading scale), served by `runserver` with `DJANGO_DEBUG=True`. It is not PostgreSQL, staging or production, and the database was deleted afterwards. The automated tests ran on PostgreSQL (see the PR).

Widths: 390, 768, 992, 1024, 1280, 1440 (full-page PNG); invalid forms at 390 and 1440. `measurements.json` holds 121 probes (every state and width, invalid-form focus checks, a keyboard probe, and a 195px / "390 at 200% zoom" probe).

Seeded assessments: **1** Quiz 1 (draft, one marked, one **Absent**, one **Not entered**, so *not ready*); **2** Quiz 2 (draft, every Student entered, *ready to finalize*); **3** Midterm (finalized, one corrected result, one Absent); **4** a planned assessment with a long name and no results (deletable); **5** Sanskrit oral (no teacher assigned).

| File prefix | URL | What it shows |
| --- | --- | --- |
| `list-*` | `/academic-years/4/assessments/` | Header, trail, filter toolbar, table with **Draft / Finalized badges**, right-aligned Max / Pass, em dash for no pass mark |
| `list-filtered-*`, `list-nomatch-*` | `?status=FINALIZED…`, `?status=FINALIZED&term=1` | Valid filter with "Clear filters"; "No assessments match these filters." |
| `list-invalid-*` | `?term=999999&status=NOPE` | Error summary, field errors, **"The filters were not applied; showing all assessments."** and the full list |
| `list-empty-year-*` | next Academic Year | "No assessments have been planned for this Academic Year yet." |
| `detail-notready-*` | `/assessments/1/` | Draft badge, **Not ready** badge with the readiness list, no Finalize button; **Absent** and **Not entered** shown differently |
| `detail-ready-*` | `/assessments/2/` | **Ready to finalize** badge, consequence text, "does not publish anything to guardians", the single Finalize POST |
| `detail-finalized-*` | `/assessments/3/` | Finalized badge, "frozen at finalization", Result sheet, per-row Correct links, **corrected** badge |
| `detail-planned-*` | `/assessments/4/` | Delete panel with consequence text |
| `detail-noteacher-*` | `/assessments/5/` | "No teacher assigned" **badge with text** |
| `form-create-*`, `form-create-invalid-*`, `form-edit-*`, `form-edit-locked-*` | `/academic-years/4/assessments/add/`, `/assessments/{4,1}/edit/` | Form, error summary and field errors, locked notice with disabled fields |
| `correct-*`, `correct-invalid-*` | `/results/6/correct/` | Result being corrected, form, audited history table |
| `viewer-*` | `demo_view` (`view_assessment` only) | No Plan / Results / Edit / Finalize / Delete / Correct controls; no sidebar or trail (no `view_school`) |
| `school-detail-*` | `demo_school` (view, finalize, correct, result view) | Trail, Finalize panel and Correct links shown |

## Measurements

| Check | Result |
| --- | --- |
| Document horizontal overflow | **0px** at 390, 768, 992, 1024, 1280, 1440 in every state and for every user |
| 200% zoom equivalent (390 → 195px) | **43px**: the pre-existing shared top-bar account menu limit already disclosed in D1-4 and D1-5A; not caused by these pages |
| H1 count | exactly 1 on every page |
| `aria-describedby` references | 0 dangling, including both invalid forms |
| Tables on phones | local, labelled, focusable regions: list 434px, roster 384 to 405px, correction history 65px at 390px; Assessment and Status (list) and Student (roster) stay on screen; 0px from 768px up |
| Keyboard | the roster region is `tabindex=0`; ArrowRight scrolled it (0 → 8px on the short seeded roster); focus outline 3px |
| Error summary link | focuses `#id_term` (create) and `#id_reason` (correction) |
| Restricted viewer | no controls, no trail, no sidebar; same data |

## Known limits

- SQLite, synthetic data; no staging or production verification; no manual screen-reader pass.
- No automatic focus to the first invalid field on submit: the forms do not use `FieldAccessibilityMixin` and `core/forms.py` is out of scope. The error summary with field links is the mitigation (recorded D1-5 follow-up).
- Assessment **Delete** (and band Remove) is still an unconfirmed POST. The page now says so; confirmation pages are the recorded launch-readiness follow-up.
- The list table's column order differs from the plan (Assessment and Status first) so the name and state stay visible on phones.
- The "corrected" badge keeps its original lowercase text and the row link keeps the visible text "Correct" (with an accessible name that includes the Student) because existing Phase 4 tests assert both strings.
- Tables scroll locally on phones; 43px top-bar overflow at 195 CSS px is pre-existing.
