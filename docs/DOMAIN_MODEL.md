# Domain model

## Core domain rules

### Applicant and Student are different concepts

FROZEN: Applicant and Student are distinct concepts with separate lifecycle meanings.

The conceptual lifecycle is:

Applicant
→ application/review
→ admission decision
→ enrollment
→ Student
→ academic enrollment
→ active student

Rules:
- An application must not automatically create an active student.
- Rejected applicants must not become students.
- Application history must remain available.
- The system must preserve the distinction between an applicant record and a person after admission.

### Student identity

FROZEN: Student represents the long-lived identity of the person in the school.

Academic-year-specific data should generally not be stored as permanent mutable fields directly on Student.

### Academic Year

FROZEN: Academic years/sessions are explicit domain records.

Historical information must remain associated with the correct academic year.

### Class and Section

FROZEN: Classes/grades and sections are explicit domain concepts.

A student's class/section membership belongs to an academic enrollment rather than permanently overwriting the Student record.

### Academic Enrollment

FROZEN: Academic Enrollment connects:
- Student
- Academic Year
- Class/Grade
- Section
- Enrollment status
- Effective start date and, when completed, effective end date

Rules:
- Changing class/year must preserve previous enrollment history.
- Enrollment history is auditable and non-destructive.
- A student may have multiple academic enrollments over time, but each enrollment belongs to a specific academic year and class/section context.
- Effective enrollment periods for a Student do not overlap. Audit timestamps are not business-effective dates.
- Transfers preserve the former enrollment period and create the later placement.

## Guardians

FROZEN: Guardians are first-class records.

Rules:
- A Student may have multiple Guardians.
- A Guardian may be associated with multiple Students.
- Guardian relationships should support relationship types such as father, mother, guardian, grandparent, or other authorized relationship.

### Siblings

CURRENT: Sibling relationships should preferably be derivable through shared guardians rather than maintained as duplicated data unless later requirements justify explicit relationships.

## Historical data

FROZEN: School records are historical records.

Avoid destructive updates that rewrite history.

This principle later applies to:
- academic enrollment
- attendance
- fees
- payments
- assessments
- important status transitions

Important operational records should normally be archived, deactivated, or corrected rather than hard deleted.

## Fee domain principles

FROZEN: Keep these concepts separate:

Fee Structure
→ Fee Obligation / Schedule
→ Payment

Rules:
- Fee Structure defines what should be charged.
- Fee Obligation / Schedule represents what a student actually owes.
- Payment represents money actually received.
- Initial payments will be recorded manually.

OPEN: Online payment gateways are later work and are not part of the initial phase.

## Assessment principle

FROZEN: Assessment planning and student results are separate concepts.

Detailed grading systems are intentionally undecided until the assessment module is designed.

## Attendance domain principles

FROZEN: Attendance is a historical, daily, enrollment-scoped record governed by
ADR 0006 and ADR 0007. ADR 0005 remains historical evidence only.

Rules:
- Attendance is attached to the AcademicEnrollment effective on the attendance date.
- One Section/date AttendanceRegister has a DRAFT to SUBMITTED lifecycle and its submitted roster must be complete.
- The only statuses are PRESENT and ABSENT; ABSENT may have an optional note.
- The Academic-Year-aware calendar identifies instructional dates, including exceptional instructional days such as working Saturdays.
- Future attendance is prohibited. Missing or unsubmitted attendance is not ABSENT.
- Submitted attendance corrections preserve the previous value, new value, administrator, and timestamp.
- Percentage is PRESENT / (PRESENT + ABSENT) over submitted eligible entries only.

CURRENT: Attendance is administrator-facing in Phase 2. Teacher attendance is deferred to Phase 5; Guardian and Student attendance access is deferred to later phases.

OPEN: Period/slot-level attendance, leave workflows, portals, notifications, and timetable integration are later work and are not part of Phase 2.

## Communication

CURRENT: Potential channels include email, WhatsApp, Telegram, and in-app notifications.

FROZEN: No provider is selected yet. The core ERP must not depend on an external messaging provider to function.

## Domain summary

The system should treat school operations as historical, year-aware, and enrollment-based rather than as a generic account management system. Administrative decisions should be explicit, auditable, and durable.

## Phase 1 domain focus

Phase 1 includes these domain concepts:
- basic school configuration
- academic year management
- class and section management
- applicant management
- guardian records and relationships
- admission decision
- accepted applicant progression into Student
- academic enrollment
- class + section assignment through enrollment
- student status
- student profile
- basic student search/listing
- basic authorization/permissions
- timestamps and historical tracking where required

Phase 1 explicitly excludes:
- attendance
- fees
- payment gateways
- examinations/results
- timetable
- teacher portal
- parent portal
- student portal
- WhatsApp
- Telegram
- automated email
- library
- transport
- HR/payroll
- hostel
- inventory
- mobile applications
- advanced analytics
- AI features

## Phase 2 domain focus

Phase 2 includes these domain concepts:
- effective-dated Academic Enrollment
- minimal Academic-Year-aware calendar
- daily Section/date attendance register and date-effective roster
- DRAFT/SUBMITTED attendance capture and audited corrections
- operational attendance reporting and administrator authorization

Phase 2 explicitly excludes:
- period/slot-level attendance
- teacher, parent/guardian, or student attendance portals
- attendance-based notifications
- biometric/RFID or device-based capture
- staff/teacher attendance
- dashboards, analytics, and scheduled reports
- timetable integration
