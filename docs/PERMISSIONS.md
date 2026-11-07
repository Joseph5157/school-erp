# Permissions

How the office screens decide who may see what (Security Gate 4B). The short version: a page's
own permission opens the page, and each class of personal data on it needs that class's own
view permission.

## How access is decided

- A **route permission** opens a page (for example `core.view_student` opens the student list).
- Some pages also show **another class of data**: the student list shows guardians, the
  guardian list shows children, an assessment page shows marks. That data needs **its own
  permission**, listed below. Without it the section is left out of the page, and any search or
  filter that would reach it is dropped, so a search cannot reveal what the page hides.
- A permission counts whether it is held **directly** by the login or **through a group**.
- Superusers and the shipped **School Administrators** group hold every permission, so nothing
  changes for them. The shipped **Teachers** group holds no model permissions at all (a teacher's
  access comes from their assignments, not from permissions).
- The page itself is not turned into a 403 just because a section is missing. A request fails
  with 403 only when it exists to deliver data the login may not see, for example a document PDF.

Only a **custom role** (a group or direct permissions made in the Django admin, since the
app has no role editor) can be narrower than School Administrators. If you have none, none of
the limits below ever apply to anyone.

## Classes of data and their permissions

| Data | Permission | Where it appears |
|---|---|---|
| Guardian names, contacts, links | `core.view_guardian` | Guardians section on the student and applicant pages; the Guardian column and search on the student list |
| Linked students | `core.view_student` | Children on the guardian list and in its search; the duplicate-guardian warning |
| Linked applicants | `core.view_applicant` | Applicant children on the guardian list and in its search |
| Attendance entries (a student's status, notes, absences) | `core.view_attendanceentry` | Register rows; the student page's monthly card; the student list's absent filter; the Overview's absentee and attention lists; attendance summary documents |
| Marks (scores, grades, percentages, pass/fail, who entered them) | `core.view_studentresult` | Assessment results; publication preview and detail; report cards (page and PDF) |
| Staged import rows (names, dates of birth, admission numbers) | `core.run_import` | The pending-batch preview |
| Students (for choosing one) | `core.view_student` | The student choosers for certificates and report cards; certificates |

The Overview's absentee list also needs `core.view_student`, because it names students, and its
attention list needs students, marks and attendance together.

## What a limited role sees on each screen

| Screen | Holds | Without the extra permission |
|---|---|---|
| Student list | `view_student` | No guardian column or search; no "Absent 3+ days" filter (the parameter is ignored) |
| Student profile | `view_student` | No Guardians section; no monthly attendance card; progress already needed `view_studentresult` |
| Applicant profile | `view_applicant` | No Guardians section |
| Guardian list | `view_guardian` | No children; searching by a child's name finds nothing |
| Add-guardian duplicate warning | `add_guardian` + `view_guardian` | Matches show without their linked children |
| Attendance register | `view_attendanceregister` | Header, state and the marked count only; no student rows, statuses or notes |
| Overview | `view_school` | Absentee list needs `view_student` + `view_attendanceentry`; attention list also needs `view_studentresult` |
| Assessment page | `view_assessment` | Roster names only; no scores, grades, pass/fail or entered-by |
| Publication preview and detail | `view_termpublication` | The workflow and student names; no marks or remark. The confirm token is unchanged, so publishing still publishes exactly the plan |
| Import batch | `view_importbatch` | Status, counts and sanitised problems; staged rows need `run_import` |
| Teacher workload | `view_sectionclassteacher` | Only teacher accounts open (Teachers group, or anyone who holds or held a teaching assignment). Any other login is a 404 |
| Documents | `issue_document` | See below |

### Documents

`issue_document` opens the Documents area. What a document contains decides the rest:

| Document | Also needs |
|---|---|
| Bonafide certificate (choosing a student, opening the PDF) | `view_student` |
| Report card (the chooser, the list, the PDF) | `view_studentresult` (the chooser also needs `view_student`) |
| Attendance summary (preview, issuing, the PDF) | `view_attendanceentry` |

A direct request for a PDF, or for a summary or certificate page, without the needed permission
is a 403, and nothing is issued. The "Recently issued" list only shows documents the login
could open.

## Deliberate bundles

These are intentional, not gaps. Each is pinned by a test so it cannot widen unnoticed.

- **Report-card remark.** The teacher's remark is part of the report card, so `view_studentresult`
  includes it on the term report card page. (On the publication pages the remark is hidden
  together with the marks.)
- **Teacher security events.** `manage_teacher_accounts` includes the limited recent-event view
  on that teacher's page: only events about that teacher, newest ten.
- **Message queue.** `send_notification` shows, for each waiting message: the guardian's full
  name, the kind of message, when it was prepared and the message text. The text carries the
  child's first name, the date and a portal link. It does not show phone numbers, emails, the
  student's full name, admission number or date of birth. The WhatsApp address is never in the
  page: the button POSTs, the server rechecks consent and portal access, and only then redirects.
- **Guardian access reviews.** `view_guardianaccessreview` shows the student's name, the
  guardian's name and the last placement (academic year and class section) for each pending
  review. It shows no contact details, admission number or date of birth.
- **Overview headline counts.** Anyone with `view_school` sees the headline counts on the
  overview cards (how many students, guardians, teachers). Only the links need their own
  permission.
- **Bulk import.** `run_import` is one permission for the whole upload: it may create students,
  guardians, classes and sections through the import, without needing `add_student` and the like.

## Recommended combinations

These are starting points for roles made in the Django admin. They are not enforced; they are
what keeps a role from being surprised by a limited page.

| Role | Permissions |
|---|---|
| **Registrar / front office** | `view_student`, `view_guardian`, `view_applicant`, `view_attendanceentry`, `view_studentresult`, `issue_document` (add `change_student`, `change_guardian` as needed) |
| **Communications operator** | `send_notification`, `view_announcement`, `add_announcement` (add `change_guardian` to fix a missing phone number; `view_guardian` to open the guardian) |
| **Attendance clerk** | `view_attendanceregister`, `add_attendanceregister`, `change_attendanceregister`, `view_attendanceentry`, `add_attendanceentry`, `view_student` |
| **Results clerk** | `view_assessment`, `view_studentresult`, `view_termpublication`, `publish_termpublication`, `view_student` |
| **Import operator** | `view_importbatch`, `run_import` |

A role without a companion is allowed; it just sees the limited page described above.

## Checking a deployment

`python manage.py role_permission_gaps` lists the custom groups, and the logins with permissions
assigned directly, whose permissions leave a page limited or a file refused, with what each
missing permission costs. It is **read-only**: it only reads groups, users and permissions,
never writes, and prints names only (never emails, passwords or personal data). It skips the
shipped School Administrators and Teachers groups and superusers. A gap is information, not an
error: a deliberately limited role is meant to have one.

## The route inventory guard

`core/tests/route_permissions.json` pins the permission each route enforces, and which
other permissions its view checks in its body. If a route's permission changes, a route is
added or removed, or a view stops checking a data permission, `test_security_gate4b_route_inventory`
fails with a diff. After reviewing the change, refresh the pin:

    python core/tests/route_inventory.py --write
