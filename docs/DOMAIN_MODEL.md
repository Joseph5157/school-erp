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

Rules:
- Changing class/year must preserve previous enrollment history.
- Enrollment history is auditable and non-destructive.
- A student may have multiple academic enrollments over time, but each enrollment belongs to a specific academic year and class/section context.

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

FROZEN: Attendance is a historical, enrollment-scoped record.

Rules:
- Attendance is recorded against a Student's Academic Enrollment, not against a mutable field on Student.
- Attendance is year-aware: an attendance date must fall within the associated Academic Year.
- A Student cannot be marked for a Class/Grade + Section + Academic Year they are not enrolled in.
- Attendance for a Section on a date is captured through an explicit register, not as ungrouped per-student rows.
- The minimum attendance statuses are PRESENT, ABSENT, LATE, and EXCUSED; the set expands only with an explicit decision.
- Attendance records are not hard-deleted; changes are recorded as explicit corrections that preserve the previous value, the actor, the timestamp, and a reason.

CURRENT: Attendance is administrator-facing in Phase 2. Teacher, Guardian, and Student attendance access is deferred to later phases.

OPEN: Period/slot-level attendance, a formal holiday/non-instructional-day calendar, and attendance-based notifications are later work and are not part of the initial attendance phase.

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
- attendance register for a Class/Grade + Section and date
- per-enrollment attendance status capture
- attendance history
- attendance corrections with preserved history
- attendance reporting over a date range
- administrative authorization for attendance operations

Phase 2 explicitly excludes:
- period/slot-level attendance
- formal holiday/non-instructional-day calendar
- teacher, parent/guardian, or student attendance portals
- attendance-based notifications
- biometric/RFID or device-based capture
- staff/teacher attendance
- dashboards, analytics, and scheduled reports
- timetable integration
