# UI-D1-5A — Grading scales: synthetic screenshot and accessibility evidence

**Local synthetic evidence only.** Captured with Playwright (Chromium) against a throwaway **SQLite** database seeded with invented data (Academic Year "2026-27", Grades 1 to 8, four scales including one with a deliberately very long name, one with a single non-zero band, and one with no bands), served by `runserver` with `DJANGO_DEBUG=True`. It is not PostgreSQL, staging or production, and the database was deleted afterwards. The automated tests ran on PostgreSQL (see the PR).

Widths: 390, 768, 992, 1024, 1280, 1440 (full-page PNG). `measurements.json` holds 65 probes (every state and width, a keyboard probe, and a 195px / "390 at 200% zoom" probe).

| File prefix | URL | What it shows |
| --- | --- | --- |
| `list-*` | `/academic-years/3/grading-scales/` | Header, trail `Overview / Academic Years / Grading scales`, scales table with status badges (**Complete** / **Needs a band from 0%**), bands as a stacked list, long scale name wrapping |
| `detail-complete-*` | `/grading-scales/1/` | Header with status badge and actions, Grade bands table (From % right-aligned), consequence text, add-band toolbar |
| `detail-incomplete-*` | `/grading-scales/3/` | "Add a band starting at 0%" notice, badge **Needs a band from 0%** |
| `detail-blank-*` | `/grading-scales/4/` | No bands, no Grades ("No bands yet.") |
| `detail-long-*` | `/grading-scales/2/` | Long scale name wraps in header and table |
| `create-*`, `create-invalid-*` | `/academic-years/3/grading-scales/add/` | Form; invalid state with error summary, field error and the "Applies to" fieldset |
| `edit-*` | `/grading-scales/1/edit/` | Pre-filled edit form |
| `viewer-list-*`, `viewer-detail-*` | `demo_view` (`view_gradingscale` only) | No Add / Edit / Remove / Add band controls; no sidebar and no trail (no `view_school`) |
| `school-detail-*` | `demo_school` (`view_school`, `view_gradingscale`, `view_academicyear`) | Trail present; no edit controls |

## Measurements

| Check | Result |
| --- | --- |
| Document horizontal overflow | **0px** at 390, 768, 992, 1024, 1280, 1440 in every state and for every user |
| 200% zoom equivalent (390 → 195px) | **43px**: the pre-existing shared top-bar account menu limit already disclosed in D1-4A, D1-4C-1 and D1-4C-2; not caused by these pages |
| H1 count | exactly 1 on every page |
| `aria-describedby` references | 0 dangling, including the invalid form |
| Scales table on phones | 201px of local horizontal scroll inside the labelled, focusable region at 390px; the Scale and Status columns stay on screen; 0px from 768px up |
| Keyboard | the scales region is `tabindex=0`; ArrowRight scrolled it (0 → 114px after 20 presses); focus outline 3px |
| Error summary link | clicking "Name: This field is required." moves focus to `#id_name` |
| Restricted viewer | no controls, no trail, no sidebar |

## Known limits

- SQLite, synthetic data; no staging or production verification; no manual screen-reader pass.
- No automatic focus to the first invalid field on submit: `GradingScaleForm` does not use `FieldAccessibilityMixin` and `core/forms.py` is out of scope. The live error summary with a link to the field is the mitigation (recorded follow-up in the D1-5 plan).
- Band Remove stays an unconfirmed POST. The page now says so and states what it affects; a real confirmation page is the recorded launch-readiness follow-up.
- Add-band errors still arrive as a flash message after redirect (the view redirects on invalid input); that behaviour is unchanged.
- The scales table has a local horizontal scroll at 390px; its Status column was moved second (the plan listed it last) so the status is visible without scrolling.
- 43px top-bar overflow at 195 CSS px, pre-existing.
