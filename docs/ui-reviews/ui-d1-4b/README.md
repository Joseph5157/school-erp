# UI-D1-4B — Attendance Register Detail and Correction: synthetic screenshot evidence

**Local synthetic evidence only.** Captured with Playwright (Chromium) against a throwaway local PostgreSQL database seeded with invented data ("Demo Student One/Two/Three", an over-long Academic Year / Class / Section name, an unbroken 80-character Section name, a three-row correction history with a long multi-line reason). Not production, not staging, no real student data.

- `before-*` — `main` at `288fc0d` templates. `after-*` — this branch.
- Widths: 390, 768, 992, 1024, 1280, 1440 (full-page PNGs). **360px** measured only.
- Document-level horizontal overflow (`scrollWidth - clientWidth`) was **0px** at all seven widths in all ten states, and every page returned 200. (The "after" set was re-checked for non-200 and overflow; the "before" set was filtered for overflow only.)
- Full-page captures render the sticky Save bar and topbar at the capture viewport height (about 900px), so they appear mid-page in tall pages; that is a screenshot artefact, not a layout change.

| State | Page | What it shows |
| --- | --- | --- |
| `draft-partial` | register detail (admin) | Draft roster with the unchanged capture form, Save draft / Save and submit |
| `draft-zero` | register detail (admin) | Draft with no marks saved; unmarked students are not absent |
| `draft-noperm` | register detail (view-only) | Read-only context, "You do not have permission to capture attendance.", no form |
| `draft-empty` | register detail (admin) | "No Students are enrolled in this Section on this date." and no form |
| `submitted-admin` | register detail (admin) | Submitted panel, four columns including Correct |
| `submitted-viewonly` | register detail (view-only) | Three columns, no Correct links |
| `submitted-long` | register detail (admin) | Very long unbroken Section and Student names; the table scrolls inside its own region |
| `correction-history` | correction form | Context panel, unchanged form, three-row history newest first |
| `correction-long` | correction form | Long multi-line note, no history |
| `correction-invalid` | correction form | Server-rendered "This field is required." (client validation disabled for the capture) |

## Measured defect fixed with scoped CSS

At 390px the register detail context line ("Section · weekday, date") clipped a long unbroken Section name. A two-rule block, `.erp-attendance-detail-page .erp-page-header-copy` and `.erp-attendance-detail-page .erp-page-purpose`, placed before the D1-3D1 marker in `static/css/erp.css`, makes it wrap. No other CSS was added.

## Keyboard and zoom

Scripted Chromium on the same synthetic database: Draft, Submitted and Correction pages at 320px, 390px, 1280px, and 200% zoom (390px phone at 195 CSS px; 1280px desktop at 640 CSS px).

| Check | Result |
| --- | --- |
| Tab / Shift+Tab | Tab reaches every content control (header link, roster radios and notes, Save draft / Save and submit, Correct links, table regions, correction fields, Save correction, Cancel); Shift+Tab steps back through them. No keyboard trap. |
| Focus visibility | Every content stop shows a focus ring (outline or the shared box-shadow ring; roster radios show it on their toggle label). None without. |
| Table keyboard scrolling | The Submitted and Correction history regions are focusable and scroll with the arrow keys (e.g. Submitted reaches its far edge, 1011 of 1011 px at 390px; the Correction history scrolled 2400 of 3234 px in the 60 key presses used). At 1280px they fit. |
| Document overflow | 0px at 320, 390, 1280 and 200% desktop. |

## Known limits

- **Pre-existing, outside this gate:** `core/_attendance_capture_table.html` starts with a two-line `{# … #}` comment. Django only treats single-line `{# #}` as a comment, so the text "{# Roster for a DRAFT register. Include inside … #}" renders visibly above the roster on both `main` (`before-draft-*`) and this branch, and the raw `<form id="attendance-capture">` in it adds a stray tag. The partial is shared with Teacher Attendance and forbidden here; fixed afterwards in its own reviewed change: PR #103 (merge `f8f9e47`).
- At 200% zoom on a 390px phone (195 CSS px, below the 320px WCAG reflow width) the shared topbar account menu overflows the document by 43px. Shared layout, out of scope.
- The keyboard check is scripted, not a manual screen-reader or assistive-technology pass.
- Long unbroken Student names widen the Submitted table inside its scroll region rather than wrapping; table-local scrolling is the accepted behaviour for these tables.
- Cross-permission oddities in the plan (Student-detail links for accounts without `view_student`; the correction redirect for accounts without `view_attendanceregister`) are unchanged and not tested beyond the 403 on the correction page for non-correctors.
