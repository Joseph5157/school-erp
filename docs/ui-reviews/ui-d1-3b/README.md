# UI-D1-3B synthetic before / after screenshots

Applicant detail and Teacher detail. All people, phones and emails are synthetic.
Disposable local PostgreSQL database (created and dropped for this capture, not the dev DB),
`collectstatic` refreshed, server started fresh (`runserver --noreload`) for each of the two runs.
Full-page Chromium (Playwright) captures, viewport height 900.

- **before** = templates from `461f18a` (applicant_detail.html, teacher_detail.html, swapped in temporarily and restored; working tree clean afterwards).
- **after** = templates at HEAD `9eca086`.

File naming: `{before|after}-{page}-{state}-{user}-{width}.png`.

## Coverage

| Page | State | User | Widths | Sets |
|---|---|---|---|---|
| applicant | PENDING, 2 guardians, Accept/Reject links | admin (School Administrators) | 390, 768, 992, 1024, 1280, 1440 | before + after |
| teacher | active, 2 subject assignments, 1 class-teacher, 3 events | admin | 390, 768, 992, 1024, 1280, 1440 | before + after |
| applicant | PENDING (same record) | limited: `view_applicant` only | 390, 1280 | before + after |
| teacher | active (same record) | limited: `manage_teacher_accounts` only (no `view_sectionclassteacher`, so no workload link) | 390, 1280 | before + after |
| applicant | ACCEPTED, no Student (Progress to Student form) | admin | 390, 1280 | after |
| applicant | ACCEPTED with linked Student | admin | 390, 1280 | after |
| applicant | PENDING but Student exists (inconsistent, reconciliation alert; no guardians) | admin | 390, 1280 | after |
| applicant | REJECTED, no guardians, decision reason | admin | 390, 1280 | after |
| applicant | long name + long guardian name | admin | 390, 1280 | after |
| teacher | inactive (Reactivate) | admin | 390, 1280 | after |
| teacher | long name, must-change-password, no assignments/events | admin | 390, 1280 | after |
| teacher | empty (no assignments, no events) | admin | 390, 1280 | after |

Notes on the fixtures: the inconsistent applicant is built by creating the Student while the applicant was ACCEPTED, then
setting the applicant back to PENDING with a queryset update (the model refuses to create a Student for a non-accepted applicant).
The `admin` user is a non-superuser in the School Administrators group.

## Page-level horizontal overflow (after shots)

Measured in the browser as `document.documentElement.scrollWidth <= window.innerWidth` after load, at every width of every
after shot (32 measurements). Result: **all 32 pass** (scrollWidth equal to innerWidth each time). Every page returned HTTP 200 with
exactly one `<h1>`. The "before" shots were also measured and showed no page-level overflow (16/16).

## Observations (honest notes)

- No double panel spacing seen: panels stack with a single consistent gap, and nested `p-3 p-md-4` padding does not stack with the panel border.
- **Heading-to-table gap is loose** on the two table panels (Guardians, Recent security events). Because the heading block uses `pb-0` and the
  table wrapper adds `mt-3`, the heading sits in a roomy header strip, and at 1280 the space between the heading text and the table header row looks
  about 40-50px (most noticeable in the limited applicant view, where there is no Associate Guardian button). Not a defect that breaks anything,
  but tighter than D1-3A's list panels would be nicer.
- **"Back to Applicants" link** (`btn btn-link`) is inset about 12px from the panel left edge because of button padding, so it does not align with the panels. Applicant page only; the teacher page has no back link.
- Teacher header shows the username as the purpose line and again as the first Account row (carried over, content unchanged).
- Permission-limited views have no sidebar entries (the user has no nav permissions), so the content spans the full width; this is expected.
- On desktop the shared header status pill also appears as the first summary/definition row (duplicated status, unchanged content from before).
- Full-page captures cut off the left navigation at viewport height (900px) because the sidebar is sticky; this is a capture artefact, not a layout bug.
- Long names wrap in the h1 at 390 without clipping or page-level sideways scroll. The long guardian name (one unbreakable hyphenated word) does not wrap at 390: it is cut off at the panel edge and scrolls inside the labelled table region (the second Relationship column is off-screen until scrolled). Expected behaviour for the scroll region, but the clipping gives no visible scroll hint.
- Status is always communicated by text (Pending/Active/etc.), not colour alone.
