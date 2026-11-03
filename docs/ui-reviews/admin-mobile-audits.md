# Admin on mobile: audits

The 16 audits behind the admin mobile work, received 2026-11-03. The audits are an outside review. Their claims were checked by reading the code on main at c6284df, not by using the pages in a browser.

## Where the audits were wrong or out of date
| Audit claim | What the code shows |
|---|---|
| Refreshing the slip reissues the password | True for resets only (`core/teacher_views.py:105-111`, `core/views.py:2806-2816`). Create rejects the repeat, and the slip is lost. |
| Fixing grade order corrects other pages automatically | No. 17 places set their own order by name. |
| Drawer needs to close on selection | Not needed: links load a new page. |
| Academic Years links need grouping (finding 5) | Covered by 939db39. Finding 3 is not. |
| Announcement list "will not scale" | Worse: it silently stops at 100 (`core/announcement_views.py:22-23`). |

# Appendix: the audits as received
Wording kept; headings, tables and punctuation lightly tidied. Findings not listed in a stage above are Low priority and are picked up with the page they belong to, where they still apply.

---

## Audit 1: Overview

[The paste starts mid-sentence; the text before this was not included.] the information priority.

The dashboard promises "What needs attention today," but the important actions appear near the bottom. Attendance analytics occupy most of the page, while missing registers, pending applicants and publication work are buried.

### Recommended dashboard structure

**1. Page context**
Keep this compact:
- Overview
- Academic year and term
- Current date
- Optional "Last updated" indicator

Do not repeat unnecessary descriptive text.

**2. Priority work queue**
This should be the first content administrators see.

| Priority item | Information shown | Action |
|---|---|---|
| Missing attendance | 15 sections · due today | Review registers |
| Pending applicants | 2 applications · oldest waiting date | Review applicants |
| Results awaiting publication | Student count and assessment | Review results |
| Access or security issues | Reviews and lockouts | Open security queue |

Use one list instead of large individual cards. Show only unresolved items and order them by urgency.

**3. Today's school status**
Use four compact operational metrics:
- Attendance recorded today
- Students present
- Staff present
- Classes completed or registers submitted

These are more useful for daily administration than static counts such as total classes and total teachers.

**4. School snapshot**
Move relatively stable metrics into a smaller secondary section:
- Active students
- Teachers
- Classes
- Guardian portal access

These can use compact tiles with small trend or context labels.

**5. Performance workspace**
Instead of displaying every chart simultaneously, use three tabs:
- Attendance
- Assessments
- Admissions

The Attendance tab can contain:
- Attendance rate with target
- Daily trend
- Classes below target
- Attendance heatmap

The Assessments tab can contain:
- Results published
- Subject averages
- Score distribution
- Students needing attention

This will shorten the page considerably.

**6. Students needing attention**
Change the present large list into a structured table:

| Student | Class | Reason | Period | Action |
|---|---|---|---|---|
| Swathi Patnaik | Grade 6 | Below pass in five subjects | Term 1 | View student |
| Deepika Reddy | Grade 9 | Below pass in two subjects | Term 1 | View student |

Use small reason labels, but do not colour every subject separately.

**7. System status**
Combine "Nothing waiting" and "School setup complete" into one compact checklist:
- School configuration complete
- No publication backlog
- No pending access reviews
- No unsent messages
- No sign-in lockouts

Positive states should remain visually quiet. They should not compete with unresolved work.

### Recommended desktop layout
Use a 12-column layout:
- Main workspace, 8 columns
  - Priority work queue
  - Today's status
  - Performance tabs
  - Students needing attention
- Context rail, 4 columns
  - School snapshot
  - Attendance completion
  - System status
  - Useful shortcuts

This creates a much stronger hierarchy than one long stream of equally weighted cards.

### Recommended mobile layout
The mobile dashboard should not simply stack every desktop card.

Recommended order:
1. Page context
2. Priority work queue
3. Today's status in a 2×2 grid
4. Attendance completion
5. Performance tabs
6. Students needing attention
7. School snapshot
8. System status

Mobile-specific changes:
- Show only one analytical chart at a time.
- Use horizontal progress rows instead of vertical charts.
- Collapse secondary analytics under "View more."
- Keep important actions visible without opening accordions.
- Avoid large gauge and donut cards.
- Allow the navigation drawer to close immediately after selection.
- Consider a sticky Tasks button showing the unresolved count.

### Component improvements

| Current component | Recommended replacement |
|---|---|
| Large 91% semicircle gauge | Compact metric with target progress bar |
| Two 0% circular rings | Progress rows: 0 of 15 submitted |
| Five large snapshot cards | Four compact KPI tiles |
| Separate "Needs attention" areas | One consolidated priority queue |
| All analytics displayed together | Attendance/Assessments/Admissions tabs |
| Vertical class chart on desktop | Horizontal comparison bars |
| Plain student exception list | Structured attention table |
| Multiple success chips | One system-status checklist |
| Long mobile analytics stream | Progressive disclosure with "View more" |

### Visual direction
For the next redesign, I recommend:
- Graphite navigation and typography
- Cobalt for active states, links and analytical data
- Green only for completed or healthy states
- Amber for pending work
- Red only for overdue, failed or security-critical items
- Fewer bordered cards
- More spacing between major sections
- Stronger section headings and quieter secondary text

The strongest redesign direction is: an operational command centre first, analytical dashboard second, and school statistics third. This preserves the existing functionality while making the page much faster to understand and act upon.

---

## Mobile Audit 1: Admin shell and navigation

Verdict: Keep the existing structure. No redesign is required.

The mobile shell is already built sensibly with Bootstrap.

### What is working correctly
- Uses Bootstrap's offcanvas-lg offcanvas-start pattern.
- Sidebar becomes a drawer below the desktop breakpoint.
- Menu button correctly targets the Admin sidebar.
- Drawer includes a clearly labelled close button.
- Navigation is grouped using semantic `<details>` and `<summary>`.
- The current group opens automatically.
- Active page uses `aria-current="page"`.
- Sidebar has the accessible label "School administration."
- Menu touch target increases to approximately 44px on smaller screens.
- School name and academic year are hidden from the crowded mobile header.
- Header remains sticky.
- Account menu provides Change password, Install app and Log out.
- Skip-to-content link and correctly identified `<main>` region are present.
- Navigation labels and destinations are clear.

### Improvements actually needed

**1. Academic-year context disappears on mobile**
The school name and academic year are hidden below the medium breakpoint, but I found no equivalent academic-year indicator inside the mobile navigation drawer.

Recommended minor improvement: Show a compact, read-only line inside the drawer header:

Demo Public School · 2026–27

This maintains important working context without crowding the top bar.

**2. Menu expanded state**
The menu button has an accessible label and controls the correct sidebar, but it does not expose aria-expanded.

Recommended accessibility improvement: Toggle:
- `aria-expanded="false"` when closed
- `aria-expanded="true"` when open

Bootstrap already manages the drawer; this only synchronizes its state for assistive technology.

**3. Verify focus restoration with a real mobile interaction test**
Bootstrap should:
- Move focus into the opened drawer
- Trap focus while it is open
- Close with Escape
- Return focus to the menu button

The implementation appears structurally correct, but these behaviours should be included in mobile acceptance testing.

### Decision

| Area | Result |
|---|---|
| Mobile header | Keep |
| Bootstrap drawer | Keep |
| Navigation grouping | Keep |
| Account menu | Keep |
| Touch sizing | Keep |
| Academic-year context | Minor improvement |
| Menu accessibility state | Minor improvement |
| Full redesign | Not needed |

The shared mobile shell passes the audit with only two small improvements. The next audit should be the existing Admin Overview mobile page, checking whether its current Bootstrap layout should remain or needs targeted corrections.

---

## Mobile Audit: School Setup → Teachers

Verdict: The page is fundamentally sound. No full redesign is needed.

The Bootstrap header, filtering controls and accessibility structure are good. Two targeted improvements are recommended.

### What already works
- "Add teacher" becomes a full-width mobile action.
- Search field occupies the full row.
- Status and Search controls wrap correctly below it.
- Inputs and buttons meet the 44px mobile touch target.
- Active filters display a Clear filters link.
- Search form has proper labels and an accessible search-region name.
- Teacher status includes screen-reader context.
- Table has a caption and correct sortable-column semantics.
- Current sort is exposed using `aria-sort="ascending"`.
- Table is placed inside a labelled, keyboard-focusable horizontal-scroll region.
- Result count appears below the list.
- Teacher names link directly to their profiles.

### Improvement 1: Mobile table is too wide
The page currently keeps this six-column table on mobile:
1. Name
2. Username
3. Email
4. Status
5. Assignments
6. Last sign-in

Bootstrap makes it horizontally scrollable, so it remains functional. However, administrators must repeatedly swipe sideways to compare status, assignments and sign-in activity.

Recommended targeted adjustment: Keep the existing desktop table unchanged. Below 576px, present each teacher as a compact summary:
- Teacher name (profile link)
- Username and email (secondary text)
- Active/inactive status
- Current assignment count
- Last sign-in

This can be implemented as responsive table-row styling or mobile-only record summaries. It does not require changing the workflow.

Priority: Medium

### Improvement 2: Incorrect filtered empty-state message
When a search has no matches, the table says:

No teachers yet.

That is misleading because teachers already exist. The page also displays a second "No results" message below the table, creating duplication.

Required correction: When filters are active and nothing matches, show one message:

No teachers match your search or status filter.

Include one Clear filters action.

Use "No teachers yet" only when the school genuinely has no teacher accounts.

Priority: High

### Optional workflow clarification
The list currently shows:

Assignments (all years)

This is accurate but may not be the most useful daily information. Historical assignments can make counts such as 17 or 18 appear like a teacher's present workload.

Consider showing:
- Current assignments: 2026–27
- Historical assignment count inside the teacher profile

This requires a product decision and is not necessary for the mobile layout fix.

### Final decision

| Area | Result |
|---|---|
| Page header | Keep |
| Add teacher action | Keep |
| Search and status filters | Keep |
| Touch sizes | Keep |
| Sorting and accessibility | Keep |
| Six-column mobile table | Improve |
| Filtered empty state | Fix |
| Assignment count meaning | Optional review |
| Full redesign | Not required |

The next logical page is the Teacher profile, because the list sends users there and we should verify whether account status, assignments, reassignment history and actions work comfortably on mobile.

---

## Mobile Audit: Teacher Profile

Verdict: The profile is functional and mostly mobile-safe. No redesign is required.

The page needs a few targeted presentation improvements, mainly around the long assignment list.

### What already works
- Breadcrumbs wrap on narrow screens.
- Teacher name, username and active status have clear hierarchy.
- Account information uses Bootstrap's responsive definition-list grid.
- On mobile, labels and values stack naturally.
- Buttons meet mobile touch-size requirements.
- Reset password, Change username and Deactivate open separate workflows rather than acting immediately.
- Sections have accessible headings.
- "View full workload" provides an appropriate route to detailed information.
- Security events use a labelled, keyboard-accessible scroll region.
- Status text includes screen-reader context.

### Improvement 1: Assignment list is repetitive and difficult to scan
The profile displays ten lines such as:
- 2026-27: Environmental Science · Grade 1 - A
- 2026-27: Environmental Science · Grade 1 - B
- Repeated through Grade 5

On mobile, repeating the year and subject consumes considerable vertical space.

Recommended targeted change: Group identical year and subject information:

Environmental Science · 2026–27
- Grade 1 — Sections A, B
- Grade 2 — Sections A, B
- Grade 3 — Sections A, B
- Grade 4 — Sections A, B
- Grade 5 — Sections A, B

Keep the Class teacher assignment as a separate block.

This changes only presentation, not assignment rules or data.

Priority: High

### Improvement 2: Separate the destructive action
Reset password, Change username and Deactivate currently sit in the same wrapping button group.

Although Deactivate opens a separate confirmation page, it should remain visually separated from routine account actions on mobile.

Recommended change:
- Keep Reset password and Change username together.
- Place Deactivate on a separate row with additional spacing.
- Retain the existing confirmation screen.

Priority: Medium

### Improvement 3: Allow identifiers to wrap safely
Username and email values currently have normal wrapping behaviour. Longer school email addresses could overflow on narrow phones.

Apply `overflow-wrap: anywhere` to:
- Username
- Email
- Other long account identifiers

Priority: Low but recommended

### Improvement 4: Security-events table
The three-column table remains usable through horizontal scrolling. With only Event, When and By, it is acceptable.

If the security history grows substantially, a stacked mobile event row would be easier to read:
- Event name
- Date and time
- Performed by

This is optional and not presently a blocker.

### Final decision

| Area | Result |
|---|---|
| Profile header | Keep |
| Breadcrumbs | Keep |
| Account information | Keep |
| Account actions | Minor adjustment |
| Assignment presentation | Improve |
| Full workload link | Keep |
| Security-events table | Keep for now |
| Long identifier wrapping | Add |
| Full redesign | Not required |

---

## Mobile Audit: Teacher Full Workload

Verdict: The page is technically mobile-safe, but its information structure needs improvement.

There is no overflow or squeezed desktop table, but the page is difficult to scan and does not clearly explain how administrators can manage assignments.

### What already works
- Content naturally fits narrow screens.
- No horizontal scrolling is required.
- Breadcrumbs wrap correctly.
- Academic year is represented as a proper section heading.
- Class-teacher and subject assignments are separated.
- Effective dates are displayed.
- Semantic headings and lists provide good accessibility.
- Current assignments appear before any future historical years.
- No unnecessary desktop-only controls are forced onto mobile.

### Improvement 1: Page title does not identify the workflow
The visible title is only:

Anitha Chowdary

The user must read the breadcrumb to understand that this is the Workload page.

Recommended correction: Use:

Teacher workload
Anitha Chowdary · anitha.chowdary · Active

This makes the page purpose immediately clear.

Priority: High

### Improvement 2: Assignment information is highly repetitive
Every row repeats:
- Environmental Science
- Start date
- "open"

This creates ten long lines on mobile.

Recommended structure:

2026–27

Class teacher — 1 assignment
- Grade 3 – A
  1 Jun 2026 – Ongoing

Environmental Science — 10 assignments
- Grade 1 — Sections A, B
- Grade 2 — Sections A, B
- Grade 3 — Sections A, B
- Grade 4 — Sections A, B
- Grade 5 — Sections A, B

If sections have different effective dates, show them separately. Only combine entries when their subject and dates genuinely match.

Priority: High

### Improvement 3: "Open" is ambiguous
The date range currently appears as:

1 Jun 2026 – open

"Open" may look like an action rather than an assignment state.

Use one of these:
- 1 Jun 2026 – Ongoing
- Started 1 Jun 2026 · Current
- 1 Jun 2026 – No end date

I recommend Ongoing because it is concise and clear.

Priority: Medium

### Improvement 4: Workflow dead end
The workload page is read-only, but it does not tell administrators where assignments can be changed.

Add a short note or link:

Assignments are managed from Academic Years.

Possible actions:
- Manage subject assignments
- Manage class-teacher assignments

These should link to the existing Academic Year workflows rather than introduce new assignment logic.

Priority: High

### Improvement 5: Add a compact summary
A small summary below the heading would help administrators understand the workload immediately:
- Subject assignments: 10
- Class-teacher assignments: 1
- Current academic year: 2026–27

This is useful but optional.

### Final decision

| Area | Result |
|---|---|
| Mobile responsiveness | Keep |
| Breadcrumbs | Keep |
| Semantic accessibility | Keep |
| Page title | Fix |
| Assignment grouping | Improve |
| Date/status wording | Improve |
| Management pathway | Add |
| Summary counts | Optional |
| Full redesign | Not required |

---

## Teachers: Mobile UI/UX Audit Report

I completed the Teachers workflow review in read-only mode. I inspected the list, profile, and workload on mobile, then reviewed the remaining account-management screens and their validation/confirmation behavior.

Overall verdict: the workflow is structurally sound and does not need a redesign. Bootstrap responsiveness, permissions, confirmation steps, security events, and session handling are generally well implemented. There are four important improvements and several smaller usability refinements.

### Workflow anatomy
[The pasted diagram came through as styling code plus its labels; the arrows between screens were lost. Screens named:]
Teachers list, Add teacher, Teacher profile, One-time credential slip, Full workload, Change username, Reset password, Deactivate login, Reactivate login

### Priority findings

| Priority | Screen | Finding | Recommendation |
|---|---|---|---|
| High | Credential slip | Print slip prints the normal webpage. There is currently no print-specific CSS, so navigation, warnings, and buttons may appear on paper. | Add dedicated print styling that prints only the credential card, school identity, username, temporary password, and first-login instruction. |
| High | Credential slip | Refreshing/resubmitting the page issues a new password and invalidates the printed one. A warning exists, but accidental refresh remains possible. | Introduce a safer one-time credential-result flow that cannot reset the password merely through page refresh. |
| High | Teachers list | The six-column table requires horizontal scrolling on mobile. It works technically but makes scanning teachers slow. | Keep the desktop table; on phones show a compact summary per teacher: name, username, status, current assignments, last sign-in, and a View action. |
| High | Teachers list | Filtered results incorrectly show "No teachers yet", followed by "No results." | Replace both with one message: "No teachers match your search or status filter." Include a Clear filters action. |
| High | Deactivation | The warning uses an all-years assignment count. This can make historical assignments appear like current operational responsibilities. | Show current/ongoing assignments separately and link to workload or assignment management before deactivation. |
| Medium | Credential slip | Mobile users must manually select and copy the username and password from small `<code>` text. | Add explicit Copy username and Copy temporary password controls, with visible "Copied" confirmation. |
| Medium | Teacher profile | Reset password, Change username, and Deactivate appear in the same action group. | Keep the actions, but place Deactivate in a separated "Login access" or danger area. |
| Medium | Workload | The page title is the teacher's name, so the workflow is not immediately identifiable. | Use Teacher workload as the title and show the teacher's name, username, and status underneath. |
| Medium | Workload | Repeated subject assignments produce a long list. | Group by academic year → subject → grades/sections, while preserving separate rows when dates differ. |
| Medium | Workload | "Open" is ambiguous. | Use Ongoing or No end date. |
| Medium | Workload | It is a read-only dead end; users are not told where assignments are managed. | Add: "Assignments are managed from Academic Years," with the relevant existing link. |
| Medium | Forms | Errors are displayed beside fields, but there is no top error summary or automatic focus to the first invalid field. | Add an accessible error summary with links to invalid fields and move focus to it after submission. |
| Low | Change username | The form does not clearly explain what changes for the teacher. | Show current username and state: "The teacher must use the new username at their next sign-in." |
| Low | Deactivation | The reason is a standard single-line input despite allowing 200 characters. | Use a small textarea, approximately three rows. |
| Low | Profile | Long usernames and email addresses may wrap awkwardly on narrow phones. | Apply safe word wrapping to account values. |

### Screens that should largely remain unchanged
- Add Teacher has an appropriate short four-field structure: first name, last name, username, and optional email.
- Required fields and field-level validation are clearly presented.
- Reset Password clearly explains that sessions end immediately and a password change is required at the next sign-in.
- Deactivation has a proper confirmation page and explains its consequences.
- Reactivation clearly states that the existing password remains unchanged.
- One-time passwords are not stored and the response uses strict no-cache headers.
- All account-management routes are permission protected.
- Security events are retained for account creation, password resets, username changes, deactivation, and reactivation.
- Cancel actions return to the expected teacher profile or list.
- Buttons and inputs meet suitable mobile touch-target sizing.

### Recommended implementation order
1. Fix credential-slip printing.
2. Prevent accidental password reissue through refresh/resubmission.
3. Correct the filtered-empty Teachers message.
4. Improve the mobile Teachers list presentation.
5. Clarify current assignments before deactivation.
6. Add credential copy controls.
7. Group profile/workload assignments.
8. Add form error summaries and smaller copy refinements.

No staging data was changed and no teacher accounts, passwords, usernames, or statuses were modified. The Teachers area is fundamentally good; these are targeted improvements rather than a redesign.

---

## School Setup → Academic Years: Initial findings

### High priority

**1. Offer a Subject displays every section in the school**
After selecting a class/grade, the form still displays checkboxes for Grade 1 through Grade 10.

Recommendation: show only sections belonging to the selected grade. On mobile, this will significantly shorten the form and prevent incompatible selections.

**2. Assign a Teacher contains a very long Subject Offering dropdown**
The dropdown contains every grade and subject (more than 60 options), followed by a separate Section dropdown.

Recommended sequence:
1. Grade
2. Subject
3. Section
4. Teacher
5. Start date

Each selection should filter the next field. This is a workflow correction, not a redesign.

**3. Class Teacher and Subject Teacher tables are too dense for mobile**
The tables contain repeated End, Replace, and Reassign actions across many rows.

Recommendation: retain desktop tables, but use compact mobile rows showing:
- Grade and section
- Subject
- Current teacher
- Effective date
- Replace/Reassign action
- End assignment as a secondary action

**4. Calendar exception removal has no visible confirmation workflow**
Removing a calendar exception can affect attendance expectations and reporting.

Recommendation: show a confirmation explaining the date, label, and whether the day will return to its normal weekly status.

### Medium priority

**5. Academic Year landing page has too many links inside one table cell**
Calendar, Terms, Subjects offered, Class teachers, Subject teachers, Assignment overview, Assessments, and Grading are all displayed together.

On mobile, present these as grouped links under:
- Calendar and terms
- Teaching setup
- Assessment setup

**6. Assignment Overview has two very long tables**
Add a compact summary before the tables:
- Sections without class teachers
- Subject-section combinations without teachers
- Active class-teacher assignments
- Active subject-teacher assignments

This makes the "overview" useful instead of being only another full data listing.

**7. Copy Assignments shows an empty control when no source year exists**
Because 2026–27 is currently the only year, the Copy from control appears blank.

Replace it with:

No other academic year is available to copy from.

The page should not display an unusable empty selector.

**8. Terms table actions become crowded**
Each Term has Edit, Publish to guardians, and Remarks.

On mobile, stack these beneath the Term information or use a clearly labelled Actions disclosure. "Publish to guardians" should remain visually more important than Edit and Remarks.

### Low priority

**9.** Use consistent capitalization: Add term, rather than "Add Term," if sentence case is the Admin standard.

**10.** Explain Display order using an example such as: "1 appears before 2."

**11.** On assignment forms, show the operational consequence directly above Assign:

If another teacher is currently assigned, their assignment will end on the previous day.

This message already exists for subject teachers and should be consistently applied wherever replacement occurs.

### Keep unchanged
- Academic Year → Calendar → Terms → Teaching → Assessments is a sensible hierarchy.
- Breadcrumbs correctly preserve context.
- Add Academic Year is short and appropriate for mobile.
- Calendar exception types are clearly described.
- "Check a date" is useful and should remain.
- Subject offerings grouped by grade using expandable sections work well.
- Assignment copying correctly uses a preview-before-confirmation workflow.
- Start dates and effective-dated teacher handovers are clearly represented.

The next area will be Classes/Grades and Sections, including create/edit screens and how they connect to Academic Years.

---

## Classes/Grades and Sections: Mobile Audit

Overall verdict: this area is clean and mobile-friendly. The two-column structure is simple, forms are short, and no redesign is needed. One ordering defect and one workflow gap need attention.

### High priority

**1. Grades are sorted alphabetically, not academically**
Current order:

Grade 1 → Grade 10 → Grade 2 → Grade 3…

This happens because records are ordered by name.

Recommendation: introduce an explicit `display_order` or sequence value. Do not derive it only from the name because schools may use Nursery, LKG, UKG, Grade 1, Intermediate, etc.

Expected order:

Nursery → LKG → UKG → Grade 1 → Grade 2 … Grade 10

**2. There is no correction or retirement workflow**
Administrators can create Classes and Sections, but cannot:
- Rename a class/grade
- Rename a section
- Archive an obsolete class/section
- Correct a spelling mistake

Because these records are referenced historically, ordinary deletion should not be added. The safer workflow is:
- Rename, with an explanation that the name changes wherever this reusable record appears.
- Archive, preventing new use while preserving historical enrollments and assignments.

This is a product workflow gap rather than only a styling issue.

### Medium priority

**3. Add naming guidance**
The Name fields provide no examples. This can result in inconsistent records such as 1, Class 1, and Grade 1.

Suggested help text:
- Class/Grade: "Examples: Nursery, LKG, Grade 1."
- Section: "Examples: A, B, Morning."

**4. Sections do not provide any contextual information**
The Grade detail page only shows section names. Once editing/archiving exists, each row could show:
- Section name
- Active/Archived status
- Rename action
- Archive action

Avoid adding enrollment or teacher counts unless they are needed for an operational decision.

### Low priority

**5.** The one-column Sections table does not really require a scrollable table container. A semantic list would be slightly simpler on mobile, but this is not important enough to change by itself.

**6.** Use consistent sentence case:
- Create class/grade
- Create section
- No classes/grades yet
- No sections yet

### Keep unchanged
- The two-column Classes/Grades table works well on mobile.
- Section counts are useful and easy to scan.
- Tapping the grade name to open its Sections is intuitive.
- Create Class/Grade and Create Section forms are appropriately short.
- Required-field indicators are clear.
- Both forms include an accessible error summary.
- Cancel returns to the correct previous page.
- Create Section clearly displays its parent grade.
- Permission-gated create actions are correctly implemented.
- Duplicate names are protected by database constraints.

Recommended implementation order: fix academic ordering first, then decide whether controlled Rename and Archive workflows should be added.

Next area: School Setup → Subjects, including creation, ordering, use across grades, and mobile list behavior.

---

## Subjects: Mobile UI/UX Audit

Overall verdict: this workflow is well designed. It correctly treats a Subject as a long-lived school-wide record and uses deactivate instead of delete. There are no critical workflow defects and no redesign is needed.

### Medium priority

**1. Four-column table is unnecessarily wide on mobile**
The list contains Name, Code, Status, and Edit and is forced to remain a table.

For mobile, each row could stack as:
- Environmental Science
- EVS · Active
- Edit

Keep the existing desktop table unchanged.

**2. Deactivation consequences need more context**
The Edit page says:

To retire a Subject, untick Active; it then cannot be offered again.

This is good, but administrators may still wonder what happens to current assignments and historical results.

Recommended copy:

Existing offerings, assignments and finalized results remain on record. An inactive subject cannot be added to a new offering.

If the subject is currently offered, also show:

Currently used in 5 active offerings.

**3. Active checkbox is easy to overlook**
Retiring a subject currently means unticking a normal checkbox and pressing Save.

Keep the checkbox, but place a short warning immediately below it when editing an active Subject. A separate destructive-looking button is unnecessary because the operation is reversible.

### Low priority

**4. Active is probably unnecessary on the Add Subject form**
New Subjects will almost always be active. The system could set Active automatically during creation and show status only when editing. This simplifies the mobile form slightly.

**5. Status filtering can wait**
With only eight Subjects, search and filters would add unnecessary complexity. Add an Active/Inactive filter only when the school has enough retired subjects to make the list difficult to scan.

**6. Use consistent sentence case:**
- Add subject
- Edit subject
- No subjects yet

### Important ordering decision
The global Subjects page should remain alphabetical. Do not add a global academic sequence here.

Subject/report-card order varies by class and Academic Year, for example:
1. First language
2. Second language
3. Third language
4. Mathematics
5. Science

That ordering belongs to each Academic Year's Subject Offerings, where the existing display-order workflow already handles it.

### Keep unchanged
- The page clearly explains the difference between Subjects and yearly offerings.
- Subject name and optional short code are appropriate fields.
- Codes are normalized to uppercase.
- Non-empty codes are protected against duplicates.
- Safe renaming is supported.
- Finalized results preserve the original finalized subject name.
- Inactive Subjects remain visible for historical clarity.
- Inactive Subjects cannot be selected for new offerings.
- There is no dangerous delete action.
- Add and Edit forms contain accessible error summaries.
- Status is communicated with text, not colour alone.
- Edit links have subject-specific accessible names.
- Permission-gated Add and Edit actions are correct.

Recommended implementation order: clarify deactivation consequences, then improve the four-column mobile presentation. Everything else can remain as it is.

Next area: School Setup → Timetable, including periods, section timetables, slot creation/editing, conflicts, and deletion workflows.

---

## Timetable: Mobile UI/UX Audit

Overall verdict: the timetable logic and effective-dated workflows are strong. The principal issue is the weekly grid on phones. Desktop should remain unchanged, but mobile needs a day-focused presentation.

### High priority

**1. The weekly timetable grid is too large for mobile**
It contains:
- Period column
- Monday–Saturday columns
- Subject
- Teacher
- Effective date
- Change and End actions
- Add actions for empty cells

The existing horizontal scrolling and sticky Period column make it technically usable, but administrators must repeatedly swipe across a very wide grid.

Mobile recommendation: show one weekday at a time.

Example:

Monday
- Period 1 — Telugu · Lakshmi Devi
- Period 2 — English · Padmaja Naidu
- Period 3 — Mathematics · Srinivas Reddy
- Period 4 — Environmental Science · Anitha Chowdary
- Period 5 — Add slot

Use Monday–Saturday tabs or a weekday selector. Keep the existing weekly matrix on tablets and desktops.

**2. Grade 10 appears between Grade 1 and Grade 2**
The Section Timetables list inherits the alphabetical Class/Grade ordering defect identified earlier.

Fixing Class/Grade `display_order` will correct this page and other downstream lists automatically.

### Medium priority

**3. Delete is displayed for periods that cannot be deleted**
All eight periods show Delete, but used periods open a page saying:

This period is already used by timetable slots and cannot be deleted.

Recommendation:
- Show Delete only for unused periods.
- For used periods, show quiet text such as In use.
- Keep the protected backend rule.

This avoids repeated dead-end navigation.

**4. Timetable Issues sounds more comprehensive than it is**
The report checks:
- Teacher clashes
- Existing slots without teachers

It deliberately does not check:
- Empty timetable cells
- Missing subject hours
- Whether every period is scheduled
- Required weekly subject frequency

Add a scope note:

This report checks teacher clashes and scheduled slots without teachers. It does not assess timetable completeness or required subject hours.

**5. Timetable landing-page actions should stack on phones**
"Set up periods," "Section timetables," and "Timetable issues" should appear as three separate full-width or clearly spaced links under the Academic Year, instead of sharing one action cell.

**6. Section selection can be simplified on phones**
The current Class/Grade, Section, Actions table is acceptable but could display:

Grade 1 – A
Open timetable

This reduces one unnecessary column without changing the workflow.

### Low priority

**7.** The Period list could display the label first and sequence as secondary text on mobile:

Period 1
Sequence 1 · Edit

**8.** If the school later requires printed bell schedules or time-based reminders, Periods will need start and end times. They are intentionally period-only today, so this should not be added during the present UI improvement work.

### Keep unchanged
- Period sequence is explicit and stable.
- Periods belong to an Academic Year, preserving historical structures.
- Used periods are protected from deletion.
- Slot changes preserve history instead of overwriting it.
- Start and end dates are inclusive and clearly explained.
- Past slot records cannot be deleted.
- Future slots may be deleted through a confirmation workflow.
- Teacher identity is correctly derived from the effective subject assignment rather than duplicated in the timetable.
- A slot without a teacher is allowed for advance planning and reported separately.
- Known teacher clashes are blocked when saving.
- The Issues report detects clashes caused later by teacher-assignment changes.
- Schedule date selection is useful and clear.
- Saturday correctly displays "Not a school day" when Saturdays are disabled.
- Empty cells provide contextual Add actions.
- Change and End links have complete accessible names containing subject, period, and weekday.
- The timetable scroll region is labelled and keyboard focusable.
- Error summaries are included on the forms.
- Issues is appropriately read-only.

Recommended implementation order: add the mobile day view, fix Class/Grade ordering, hide unavailable Period delete actions, then clarify the Issues report scope.

Next area: School Setup → School profile/settings, followed by Admissions

---

## School Profile/Settings: Mobile UI/UX Audit

Overall verdict: the school-details form is compact, understandable, and mobile-friendly. The main issue is that Remove logo performs an immediate POST without confirmation. Messaging-channel terminology also needs clarification.

### High priority

**1. Remove logo has no confirmation**
Selecting Remove logo immediately removes the current logo from:
- The Admin header
- Future documents
- Future school-branded screens

The underlying system preserves earlier logo versions, but administrators have no visible restore workflow.

Recommendation: add a confirmation screen:

Remove the current school logo?
The school name will appear as text in the header and on future documents. Previously issued documents will not change.

Actions:
- Remove logo
- Cancel

Keep the existing version-preserving backend behavior.

### Medium priority

**2. "ASSIST" is not understandable to ordinary administrators**
The option currently reads:

WhatsApp, sent by office staff (ASSIST)

Most users will not know what ASSIST means.

Recommended label:

Prepare WhatsApp messages for office staff to send

Help text:

The ERP prepares approved message content. It does not send WhatsApp messages automatically. Office staff review the message and record whether it was sent or skipped.

"Portal only" should similarly explain that guardians see messages after signing into the Guardian Portal.

**3. Explain when school-detail changes take effect**
School name, address, affiliation number, principal name, and logo affect official identity.

Add a note above the form:

Changes appear in the Admin header, future messages and newly issued documents. Previously issued documents keep their original school details.

This prevents administrators from expecting old PDFs to change.

**4. Optional fields are operationally important**
Address, affiliation number, and principal name are optional, but they are used on school documents.

Add help text:
- Address: "Shown on newly issued school documents."
- Affiliation number: "Shown on official letterheads when provided."
- Principal name: "Used on documents that include principal identification."

Do not make Affiliation number universally required because some schools may not have one.

**5. Logo replacement has no preview**
A user can choose the wrong file and replace the current logo immediately.

A small client-side preview would help:
- Selected-image preview
- File name and dimensions
- Replace logo
- Cancel selection

The existing server validation and no-JavaScript fallback should remain.

### Low priority

**6.** Consider changing Edit to Edit school details, making the action more explicit.

**7.** The Logo image field is correctly required for the replacement form, but the required asterisk can look as if every School configuration must have a logo. Add:

A logo is optional. Select a file only when uploading or replacing it.

**8.** Keep the logo uploader visually separate from school identity fields, as it currently is. Do not merge everything into one long form.

### Keep unchanged
- Definition-list presentation is appropriate and stacks cleanly on phones.
- The school name, address, affiliation number, principal and communication mode are easy to scan.
- Address uses a suitable multiline field.
- Guardian-message mode uses radio buttons rather than an ambiguous dropdown.
- The Edit form has an accessible error summary.
- Save and Cancel actions are clear.
- Logo upload accepts only PNG/JPEG within controlled size and dimensions.
- Uploaded logos are normalized and stored at a safe maximum width.
- Previous logo versions are retained rather than overwritten.
- Logo access is permission protected.
- The current logo has useful alternative text.
- Portal address configuration is validated before ASSIST mode can be enabled.
- Only one School record can exist.
- No dangerous School delete action is exposed.

Recommended implementation order: add logo-removal confirmation, clarify guardian messaging modes, explain future-versus-issued-document behavior, then optionally add image preview.

Next area: Admissions → Applicants, including list/filtering, create/edit, accept/reject, progression to Student, guardians, and mobile confirmation states.

---

## Applicants: Mobile UI/UX Audit

Overall verdict: admission decisions are safely confirmed and the Applicant profile is readable. However, there are several important workflow gaps around search, Guardian selection, progression, and post-progression Guardian management.

### High priority

**1. Guardian selector is unusable and unsafe at scale**
The Associate Guardian form loads more than 200 Guardians into one dropdown. Several people have identical names, such as multiple "Anil Patnaik" and "Srinivas Goud" entries, with no information to distinguish them.

This creates a genuine risk of linking the wrong person.

Replace it with a searchable lookup showing:
- Guardian name
- Phone or masked phone
- Email when available
- Existing associated children
- A stable reference when names remain identical

Also:
- Exclude Guardians already associated with the Applicant.
- Provide Create new Guardian when no match exists.
- Do not load every Guardian into a native mobile dropdown.

**2. Progress to Student is an immediate POST without confirmation**
The button directly creates a permanent Student identity and copies the Applicant's Guardian relationships.

Add a confirmation page explaining:

This creates one Student record for Ramya Babu and copies the currently associated Guardians. It does not create an Academic Enrollment; class and section placement are managed separately.

Show the Guardians that will be copied before confirmation.

**3. Guardian management remains active after Student progression**
An accepted Applicant with an existing Student still shows Associate Guardian.

Adding a Guardian to the Applicant after progression does not automatically add that Guardian to the existing Student, creating relationship divergence.

Recommended rules:
- Pending Applicant: manage Guardians on the Applicant.
- Accepted but not progressed: manage Guardians on the Applicant.
- Student already exists: manage Guardians only from the Student record.
- Rejected Applicant: retain existing Guardian history but normally hide Associate Guardian.

**4. No Applicant search despite 114 records**
The list only provides a status filter.

Add search for:
- Name
- Email
- Phone

Search results should show enough secondary information to distinguish duplicate names, while keeping the normal unfiltered list compact.

**5. Applicant details cannot be corrected**
There is no Edit Applicant workflow. A spelling error, wrong date of birth, phone number, or email cannot be corrected after registration.

Recommended policy:
- Allow corrections before Student progression.
- Record who made the correction and when.
- Once progressed, direct demographic corrections through the Student record.
- Do not allow Edit to change admission status; decisions must remain in the dedicated workflow.

**6. No duplicate Applicant warning**
Register Applicant does not check for likely existing records.

Before creation, show a non-blocking warning for possible matches using combinations such as:
- Normalized name + date of birth
- Phone
- Email

Allow continuation when two different children legitimately share similar data, but require the administrator to review possible matches first.

### Medium priority

**7. Incorrect filtered-empty message**
When a status filter returns no records, the template says:

No Applicants yet.

Use:

No applicants match the selected admission status.

Include Clear filters and do not show Register Applicant as if the database were empty.

**8. Guardian relationship mistakes cannot be corrected**
The Applicant profile provides no Edit/Remove/End action for a Guardian relationship.

Before progression, administrators need a controlled way to:
- Correct Father/Mother/Guardian relationship type
- Remove an incorrectly associated Guardian

After progression, preserve Applicant history and manage the active relationship from the Student.

**9. Optional information needs clearer guidance**
Date of birth, email and phone are optional. That may be correct, but the form should explain why they matter:
- Date of birth helps identify duplicate applicants.
- Phone/email help locate the family and distinguish Guardians.
- Missing data can be completed before progression.

Do not make these required without a school policy decision.

### Low priority

**10.** Add a full accessible error summary to Register Applicant and Associate Guardian. They currently show inline field errors and non-field errors but not the stronger shared summary pattern.

**11.** The admission decision timestamp is useful, but displaying the acting administrator would improve accountability if that information is already recorded.

**12.** Use consistent sentence case: "No applicants yet" and "Associate guardian."

### Keep unchanged
- The two-column Applicant list works well on mobile.
- Status filtering, sorting and pagination are correctly preserved.
- Pending, Accepted and Rejected status labels are textual and accessible.
- Applicant details are presented in a readable definition list.
- Accept and Reject use dedicated confirmation screens.
- Acceptance clearly states that progression happens separately.
- Rejection requires a reason.
- Admission decisions are final and double decisions are blocked.
- Rejected Applicants cannot progress to Students.
- One Applicant can create at most one Student.
- Progression is transactional.
- Existing Applicant-Guardian history is preserved after progression.
- Applicant-to-Student mismatch warnings exist for legacy data.
- Guardian tables are simple and mobile-safe.
- Permission gating is correctly applied.
- No destructive Applicant delete action is exposed.

Recommended implementation order: searchable Guardian lookup, progression confirmation, prevent post-progression Applicant Guardian changes, add Applicant search, then add correction and duplicate-review workflows.

Next area: Admissions → Students, including student list/search, profile, enrollment history, identifiers, Guardians, status changes, results, attendance, and mobile action structure.

---

## Students: Mobile UI/UX Audit

Overall: the Students area is structurally strong. The mobile student cards, search, pagination, lifecycle history, and audit explanations should remain. The main weaknesses are workflow safety, record correction, and several desktop-style tables.

### High priority

**1. Guardian selection is impractical**
"Associate Guardian" contains approximately 216 Guardian choices, with duplicate names such as "Anil Patnaik" and no phone/email identifier.

Improve with a searchable selector showing:
- Guardian name
- Phone
- Email or Guardian ID
- Existing relationship warning

**2. Student identity/contact information cannot be corrected**
The profile displays DOB, email and phone, but only the admission number can be edited. After Applicant progression, administrators have no visible workflow for correcting these fields.

Add a permission-controlled Edit student details action with audit history. Do not silently update the original Applicant record.

**3. Recording enrollment hides an important consequence**
"Record Enrollment" looks like a simple addition, but a new active placement can end the current placement and potentially trigger Guardian-access decisions.

Before saving, show a change summary:
- Current: Grade 3 · Section B · effective date
- New: selected grade/section/date
- "Current placement will end on …"
- Guardian portal access requiring review

Rename the action to Change placement when an active enrollment exists.

**4. Reactivation lacks the safeguards used for deactivation**
Deactivation has a confirmation page, mandatory reason and permanent history. Reactivation is a direct POST button without confirmation or reason.

Use the same lifecycle pattern for reactivation: confirmation, reason and recorded actor/date.

### Medium priority
- Guardian relationships cannot be removed. Administrators can only change "Father/Mother/Guardian…" Add an End/remove relationship confirmation with reason and history, especially important for incorrect links.
- Admission-number replacement or clearing lacks sufficient consequence text. Explain where the number appears and require confirmation when clearing an existing identifier.
- Grade ordering remains incorrect: Grade 10 appears between Grade 1 and Grade 2 in Class and Section filters. Use natural numeric ordering everywhere.
- Class and Section filters are independent. After choosing Grade 3, Section still contains every grade. Filter Section choices to the selected Class, or automatically clear an incompatible section.
- Results history is a nine-column table on mobile. Horizontal scrolling technically works, but comparing assessment, subject, marks, grade and pass/fail becomes difficult. Use mobile result cards or grouped rows while retaining the desktop table.
- Enrollment history is seven columns and attendance history is six. On mobile, convert each record to a compact stacked entry. Keep the existing scrollable tables from md upward.
- Status history has the same mobile-table problem. A vertical activity timeline would be clearer on phones and naturally show date, change, reason and actor.

### Low priority
- Keep "Record Enrollment" when no placement exists, but use Change placement when one already exists.
- Place phone and email behind tap-friendly `tel:` and `mailto:` links.
- In results, add quick Term and Subject filters before the full history.
- Clearly label report-card terms with no finalized results, instead of making every term look equally available.

### Keep unchanged
- Purpose-built mobile Student cards instead of shrinking the five-column desktop table.
- Search by student or parent name, email and phone.
- Quick filters: New this month, Not in a class and Absent 3+ days.
- Pagination and the correct filtered-empty message.
- Admission number, placement, Guardians and status visible together.
- Profile jump navigation.
- Effective-dated enrollment history rather than overwriting placement.
- Deactivation confirmation, mandatory reason and status history.
- Attendance explanation distinguishing missing/draft registers from absence.
- Finalized-results-only wording and "Absent is not zero/fail" explanation.
- Showing the Student's historical Section alongside finalized results.
- Clear statement that a Guardian relationship does not automatically grant portal access.

Recommended order: Guardian picker → Student correction workflow → enrollment change summary → safe reactivation → responsive history/results records → natural grade ordering.

Next area: Admissions → Guardians, including Guardian records, associated Students, portal accounts, access grants, credentials and revocation workflows.

---

## Guardians: Mobile UI/UX Audit

Overall: the security model is strong and well explained. The main concerns are mobile table usability, duplicate Guardian creation, and sensitive access actions that need clearer confirmation context.

### High priority

**1. Guardian list is still a desktop table on mobile**
Unlike Students, Guardians has no mobile-card layout. The four-column table contains Guardian, linked children, phone and email, forcing horizontal scrolling.

Add mobile Guardian cards containing:
- Guardian name
- Phone and email
- Linked Student/Applicant names
- Portal-account/access status
- Tap target to open the profile

Keep the existing table from the md breakpoint upward.

**2. No duplicate-Guardian prevention**
There are 216 Guardian records, including identical names such as multiple Anil Patnaik and Anitha Naidu records. "Create Guardian" does not show possible matches.

When name, phone or email is entered, show existing possible matches before saving:
- Guardian name
- Phone/email
- Linked children
- "Open existing Guardian" action
- "Create separate Guardian anyway" when genuinely different

**3. Grant Student access is a direct one-tap POST**
"Grant access" immediately enables sensitive Student information without a confirmation screen.

Add a confirmation showing:
- Guardian name and username
- Student name
- Relationship
- Information that will become visible
- Confirmation button: Grant portal access

**4. Access-revocation page omits the Guardian**
The page says "Revoke portal access to Manasa Varma," but does not say whose access is being revoked. Multiple open tabs or duplicate names could cause a serious mistake.

Show both sides prominently:

Revoke Anil Varma's portal access to Manasa Varma

Include Guardian, username, Student, relationship and required reason.

**5. Credential slip still lacks a controlled print layout**
The one-time Guardian password page uses ordinary page printing. It should print only the credential card, not navigation, account controls or surrounding page content.

Add print-specific CSS, a school heading, generated date and clear offline-delivery instructions. Never automatically print.

### Medium priority
- Password reset confirmation does not identify the Guardian. It only says "Reset password." Show Guardian name and username before ending sessions and generating a new password.
- Account-revocation wording is too generic. The heading and button both say "Revoke." Use Revoke portal account link and show Guardian name, username and the effect on existing Student-access grants.
- Student access remains a four-column table on mobile. Convert each relationship into a stacked access card while preserving the table on desktop.
- WhatsApp consent appears after "Back to Guardians" and is missing from the profile section navigation. Move it before the Back action and add "Messaging consent" to the jump navigation.
- Changing WhatsApp consent uses the vague button label "Record." Use Record consent decision and require a note when reversing an existing decision.
- Clear sign-in lockout remains an unconfirmed action. Add a small confirmation identifying the username and explaining that the event is audited.
- Contact information is not directly actionable. Render phone and email as tap-to-call and tap-to-email links.

### Low priority
- Add portal state to Guardian list/cards: No account, Account only, Access granted, Under review or Login inactive.
- Show the number of linked children on the Guardian card.
- Change "Associated Applicants" to sentence case for consistency.
- Use specific destructive button labels: Revoke Student access and Revoke account link.
- Make account/access history collapsible when it becomes long, while showing recent events first.

### Keep unchanged
- Search by Guardian or Student name, phone and email.
- Pagination at 25 records.
- Clear search and correct no-results messaging.
- Profile jump navigation.
- Separate Guardian relationship, portal account and Student-access concepts.
- Clear warning that creating a Guardian does not grant access.
- Identity-verification method and mandatory note for account creation/linking.
- "Do not enter document numbers" guidance.
- Exact-username explanation when linking an existing login.
- One-time temporary password and mandatory first-login password change.
- Username normalization and audit messaging.
- Required reason and permanent history for revocation.
- Explicit access for each Guardian–Student relationship.
- Account and access event history.
- Access-review queue that makes no automatic decision.
- Sign-in lockout thresholds and automatic-expiry explanation.
- WhatsApp consent history rather than overwriting prior decisions.

Recommended order: confirm access grants → fix revocation context → duplicate detection → mobile Guardian cards → credential print layout → consent placement → lockout confirmation.

Next area: Daily → Attendance, covering registers, taking attendance, drafts/submission, corrections, absence notes and mobile roster usability

---

## Daily → Attendance: Mobile UI/UX Audit

Overall: the actual attendance-capture screen is one of the strongest mobile workflows audited so far. Student rows, large Present/Absent controls, live counts and the sticky action area are appropriate. Improvements are mainly needed around submission safety, register discovery and mobile history tables.

### High priority

**1. "Save and submit" has no confirmation**
Submission makes the register official. Any later change requires an audited, individual correction, but the sticky mobile action bar places Save draft and Save and submit together.

Before final submission, show:
- Section and date
- Present, absent and total counts
- Number of absence notes
- Confirmation that no students remain unmarked
- Confirm and submit attendance

Keep Save draft as the immediate action.

**2. Unsaved attendance can be lost**
The administrator roster requires Save draft or Save and submit. There is no visible autosave or unsaved-change warning if the administrator presses Back, closes the PWA or loses connection.

Add:
- "Unsaved changes" status after the first change
- Navigation warning before leaving
- Preferably periodic local draft preservation or server-side draft saving

**3. The register list is a six-column desktop table on mobile**
Date, academic year, grade, section, status and entries require horizontal scrolling.

Use mobile register cards showing:
- Date
- Grade and Section
- Draft/Submitted state
- Marked count
- Unmarked count
- Open/Review action

Keep the existing table on desktop.

**4. "Entries" does not show completion**
The list's Entries value is only the number of saved entries. It does not show roster size and is not proof that attendance is complete.

Replace the mobile-facing value with:

Marked 4 of 6 · 2 unmarked

For submitted registers:

Submitted · 6 of 6

This directly supports the page's stated purpose of reviewing completion.

### Medium priority
- No Draft/Submitted status filter. Add quick filters: All, Draft requiring completion, Submitted and Today. Administrators should not search through 153 registers to find unfinished work.
- "Mark unanswered as present" needs clearer consequence feedback. Change its label dynamically to Mark 6 unanswered as present and provide a temporary Undo action. It already correctly avoids overwriting existing choices.
- Opening a register uses three partially redundant selectors. Academic Year, Class and Section are independent long dropdowns. Make them dependent: Year → Grade → Section, with natural Grade 1–10 ordering.
- Date selection should show school-day feedback before submission. Immediately indicate Holiday, Weekend, Future date or Valid instructional day after the date is chosen.
- Submitted attendance remains a four-column table on mobile. Use compact Student rows/cards with status, absence note and Correct action.
- Correction history is a six-column mobile table. Present it as chronological audit entries containing date/time, old → new status, note change, reason and administrator.
- Destructive and routine actions look too similar. Visually separate Save draft from Submit attendance in the sticky action bar.
- Draft registers are not visually urgent enough in the list. Use an unmarked-count warning alongside the Draft badge rather than relying on colour alone.

### Low priority
- Default the register-list date filter to an easily accessible Today quick filter without automatically hiding historical registers.
- The daily-absent report could prefill today's date while still requiring the administrator to press Show.
- Add recent selections for frequently used Sections.
- Use "Open or resume register" when an existing register may be returned instead of created.
- Display the absent Student's note directly beneath their status rather than as a visually empty table column.

### Keep unchanged
- Large, phone-friendly Present/Absent controls.
- Student name as the fieldset legend.
- Count tabs for All, Unmarked, Present and Absent.
- Sticky mobile action bar.
- "Mark unanswered as present" never overwrites a marked Student.
- Unmarked Students are explicitly not considered absent.
- Submission is blocked until every Student is marked.
- Clear distinction between Draft and Submitted.
- Roster is calculated from enrollment effective on the selected date.
- Submitted register records who submitted it and when.
- Corrections do not rewrite original history.
- Required correction reason.
- Correction page clearly shows Student, Section, date and current status.
- Absence notes appear only when relevant.
- Missing and draft registers never count as absence.
- Attendance percentages use only submitted, instructional, non-future and enrollment-valid records.
- Clear report separation: daily absences, missing attendance, monthly summary and Student history.
- Pagination and newest-register-first ordering.
- Filter validation and distinct filtered-empty messaging.

Recommended order: submission confirmation → unsaved-change protection → mobile register cards with marked/roster counts → Draft filter → responsive submitted/correction history → dependent register selectors.

Next area: Daily → Announcements, including creation, targeting, preview, publishing, withdrawal, history and mobile readability.

---

## Daily → Announcements: Mobile UI/UX Audit

Overall: the creation workflow is safe and well structured. Preview, audience counts and explicit publishing are excellent. The main risks are withdrawal consequences, long-term list scalability and mobile table presentation.

### High priority

**1. Withdrawal needs a stronger confirmation**
The live detail page contains the withdrawal form directly. Submitting immediately:
- Removes the notice from Guardian portals
- Dismisses prepared WhatsApp messages
- Cannot retract messages already sent
- Requires republishing a new notice to correct mistakes

The page currently mentions only that Guardians stop seeing it.

Add a confirmation step showing the notice title, audience and full consequences. Use Confirm withdrawal rather than the generic "Withdraw."

**2. The announcement list will not scale**
The list currently has no search, status filter, audience filter or pagination. It works with four notices but will become difficult after an academic year of announcements.

Add:
- Search by title/body
- Live / Withdrawn filter
- Whole school / Class / Section filter
- Academic year or date range
- Pagination
- "Showing X–Y of N"

### Medium priority
- The announcement list remains a four-column desktop table on mobile. Use mobile cards containing title, published date, audience and Live/Withdrawn status. Keep the existing table on desktop.
- WhatsApp preparation is a direct POST action. It does not send messages immediately, but it creates queue records. Show a small confirmation containing the opted-in Guardian count and a link to review the queue afterwards.
- Withdrawal copy omits prepared and sent-message behavior. Explain that prepared messages are dismissed, while already-sent messages cannot be recalled.
- No title/body character feedback. Show live counters such as 42/120 and 380/2000, particularly useful when composing on a phone.
- Grade ordering remains lexical. Grade 10 can appear between Grade 1 and Grade 2 in the class/section selectors. Apply natural grade ordering.
- Audience reach figures are current eligibility, not historical delivery. Live notices say "Who can see it," but the count may change when enrollment or access changes. Add the short note: "Current eligibility; this is not a view or delivery count."
- No visible preparation state on the notice. After WhatsApp preparation, show how many messages were prepared, skipped, waiting, dismissed or sent, with a link to the message queue.
- No quick way to duplicate a previous notice. A permission-controlled Use as new notice action would reduce retyping while still forcing preview and publication.

### Low priority
- Add quick filters: Live, Withdrawn, Whole school and My notices.
- Show a word/line preview approximating the Guardian Portal display.
- Offer optional publish-at and display-until dates later; immediate publishing should remain the default.
- Display "No opted-in Guardians" beside the WhatsApp action instead of allowing an apparently useful preparation with zero recipients.
- Add a compact "Published by" line to mobile announcement cards.

### Keep unchanged
- Nothing is saved during the first preview request.
- Clear statement that published notices cannot be edited.
- Audience options: Whole school, one Class or one Section.
- Conditional Class/Section selector behavior.
- Form-level error summary and retained field values.
- Full preview of title, audience and body.
- Portal-access and WhatsApp-opt-in counts before publishing.
- Explicit warning when no Guardian can see the notice.
- Back to edit preserves entered content.
- Separate Publish notice action.
- Double-submission protection on publishing.
- Notices appear in the Guardian Portal immediately after publication.
- WhatsApp preparation remains separate from portal publication.
- Preparing WhatsApp messages does not send them automatically.
- One message per Guardian even when multiple children match.
- Prepared-message creation is idempotent.
- Withdrawal requires a reason and is permanently recorded.
- Withdrawn notices remain visible to administrators as historical records.
- Withdrawn notices clearly state Guardians can no longer see them.
- Long titles and bodies wrap rather than overflowing.
- Permission-controlled create, prepare and withdraw actions.

Recommended order: withdrawal confirmation and consequence copy → search/filter/pagination → mobile announcement cards → WhatsApp preparation status → character counters → natural grade ordering.
