# Future Phases Research and Planning Baseline

Status: RESEARCH BASELINE — not an implementation source of truth until phase-specific ADRs are accepted.

## Purpose

Use the period while Phase 2 Attendance is being implemented to research later School ERP phases without changing application code or prematurely freezing uncertain business rules.

The project should continue the existing source-of-truth order:
1. Accepted ADRs
2. Approved requirements/domain model
3. Architecture
4. Phase implementation plan
5. Existing implementation

For each future phase: research -> resolve OPEN decisions -> ADRs -> requirements/domain updates -> gate-by-gate implementation plan -> implementation -> integration hardening -> completion tag.

## Cross-phase design principles

- Preserve historical operational facts; do not model history as mutable fields on Student.
- Separate reusable configuration/templates from student-specific obligations/records and from transactions/results.
- Make business dates explicit; audit timestamps are not substitutes for effective dates.
- Authorization is part of the domain, not an afterthought.
- Prefer explicit lifecycle states where "missing", "draft", "final", "cancelled", or "reversed" have different meanings.
- Corrections should preserve history rather than silently overwrite accepted historical records.
- Keep the Django monolith and server-rendered UI unless a demonstrated requirement forces more complexity.
- Do not import mature-ERP complexity merely because another system supports it.

---

# Phase 3 — Fees

## Research findings

Frappe Education separates Fee Category, Fee Structure, Fee Schedule, and student Fee/payment records. This is a useful pattern: define what may be charged, define when it is due, instantiate a student obligation, then record settlement separately.

Gibbon billing similarly distinguishes predefined/billing-schedule information from issued invoices; once issued, invoice values become fixed rather than continuing to change with the template. It also supports partial payments and transaction/receipt information.

## Proposed bounded Phase 3 scope

- Fee categories/components (for example tuition, transport, exam)
- Reusable fee structures for an Academic Year / applicable Class or cohort
- Student-specific fee obligations with explicit due dates
- Optional explicit concession/discount adjustment
- Manual payment recording (cash/bank/UPI or configurable modes)
- Partial payments and allocation to obligations
- Receipt/reference recording
- Outstanding balance calculation
- Reversal/correction workflow that preserves history
- Operational reports: student ledger, outstanding dues, collection summary, due-date report
- Administrative authorization

## Proposed domain shape

Configuration:
- FeeCategory
- FeeStructure
- FeeStructureComponent

Student obligation:
- FeeObligation (Student, AcademicEnrollment/AcademicYear context, due date, lifecycle)
- FeeObligationLine (category, original amount)
- explicit adjustment/concession records rather than rewriting original charged amount

Settlement:
- Payment
- PaymentAllocation linking a payment to one or more obligations
- reversal/correction record rather than destructive deletion

Derived values such as outstanding balance should be calculated from accepted obligations, adjustments, allocations and reversals, not maintained as an independently editable Student balance.

## Candidate lifecycle

FeeStructure: DRAFT -> ACTIVE/FINAL
FeeObligation: DRAFT -> ISSUED -> SETTLED (with PARTIALLY_PAID preferably derived)
Payment: RECORDED -> REVERSED

Exact states must be frozen by ADR before implementation.

## OPEN decisions before Phase 3 ADRs

- Is a formal invoice concept needed, or is FeeObligation the school's operational invoice?
- Is fee applicability Class/Grade based, enrollment based, or manually assigned?
- Are concessions percentage, fixed amount, component-specific, or all three?
- Can one payment settle multiple obligations? Research supports this, but product need must be confirmed.
- How are advance/overpayments handled: reject, unapplied credit, or allocate forward?
- Are late fees in Phase 3 or deferred?
- Are refunds in Phase 3 or deferred?
- Receipt numbering policy and whether numbers must be immutable/sequential.
- Whether payment edits are forbidden after acceptance and replaced only by reversal.
- Whether sibling/family consolidated payment is needed.
- Whether accounting/ledger integration is intentionally out of scope.

## Suggested implementation gates

0. Freeze fee ADRs and requirements.
1. Fee categories and structures.
2. Student obligation generation/issuance.
3. Adjustments/concessions.
4. Payment + allocation foundation.
5. Receipt and reversal/correction workflow.
6. Administrative capture UI.
7. Fee reporting and reconciliation.
8. Integration hardening.
9. Documentation closeout and phase-3-complete tag.

Stop and return to planning for accounting-ledger integration, payment gateway, tax/GST behavior, multi-currency, family accounts, or complex refund/credit policy.

---

# Phase 4 — Assessments

## Research findings

Frappe separates Assessment Plan from Assessment Result and associates plans with a student group/course and grading scale. Gibbon additionally demonstrates markbooks, rubrics and reporting cycles. The reusable lesson is to keep assessment definition/planning separate from per-student results and from published reports.

## Proposed bounded Phase 4 scope

- Subjects or assessment areas required by the school's classes
- Assessment definition/plan for Academic Year + Class/Section + subject
- assessment date and maximum marks or grading basis
- per-student result capture against date-valid enrollment
- DRAFT -> FINAL result lifecycle
- audited correction after finalization
- basic grade/percentage calculation only after grading policy is frozen
- student result history
- class/section result sheet
- administrator-facing workflow initially

## OPEN decisions before Phase 4 ADRs

- Does the school primarily use numeric marks, letter grades, both, or configurable scales?
- Pass/fail thresholds: global, subject-specific, assessment-specific, or not calculated?
- Assessment hierarchy: exam -> subjects, or independent assessments grouped into an exam/term?
- Terms/semesters: do we need an AcademicTerm model before assessments?
- Weighting and cumulative totals: Phase 4 or later?
- Absent/not-assessed semantics must not be represented as zero unless explicitly intended.
- Ranking/position: needed or intentionally excluded?
- Teacher result entry: Phase 4 admin-only or deferred to Phase 5?
- Report cards: Phase 4 operational report or Phase 6 publication artifact?
- Rubrics/outcomes: defer unless actual school workflow requires them.

## Suggested implementation gates

0. Freeze assessment/grading ADRs.
1. Subject/assessment structure.
2. Assessment planning.
3. Date-effective result roster and DRAFT capture.
4. Finalization and validation.
5. Audited corrections.
6. Administrative result UI.
7. Result reports/calculations.
8. Integration hardening.
9. Documentation closeout and phase-4-complete tag.

Stop for grading-policy changes, GPA, ranking, complex weighting, rubrics, external exams, or transcript requirements.

---

# Phase 5 — Teacher Workflows

## Research findings

Gibbon's teacher workflow joins class assignment, timetable, lesson planning, attendance, homework and student context. Its timetable is flexible but complex. This project should not introduce a timetable merely to give teachers access to their classes.

## Proposed bounded Phase 5 scope

- Staff/Teacher profile linked to authenticated User
- effective teacher-to-Class/Section and possibly Subject assignment
- teacher authorization scoped to assigned classes
- teacher home/work queue: assigned classes and relevant actions
- take attendance for assigned Section using the Phase 2 attendance domain
- enter assessment results for assigned classes/subjects using Phase 4 domain
- read the minimum student context required for teaching
- optional simple homework/assignment only if separately approved

## OPEN decisions before Phase 5 ADRs

- Is assignment to Section sufficient, or must it be Subject + Section?
- Can multiple teachers share one assignment?
- Effective dating of teacher assignments.
- Whether class teacher/homeroom teacher differs from subject teacher.
- Which student profile fields teachers may see.
- Whether teacher attendance correction requires admin approval or same correction rules.
- Whether teacher can finalize assessment results or only submit for admin finalization.
- Whether homework belongs in Phase 5.
- Timetable remains deferred unless a real workflow proves it necessary.

## Suggested implementation gates

0. Teacher-role and access ADRs.
1. Staff/Teacher identity.
2. Effective teacher assignments.
3. Scoped authorization.
4. Teacher daily workspace.
5. Attendance integration.
6. Assessment integration.
7. Optional approved classroom workflow.
8. Integration/security hardening.
9. Documentation closeout and phase-5-complete tag.

---

# Phase 6 — Parent and Student Experience

## Research findings

Gibbon exposes a student's own profile to the student and a child's profile to linked parents, with permissions controlling the detail visible. Published reports distinguish draft/final state and can use a go-live date. These patterns fit this project's existing Guardian relationships and historical-record rules.

## Proposed bounded Phase 6 scope

- Guardian account linking to existing Guardian records
- Student account linking to existing Student records
- guardian access only to explicitly linked children
- student access only to self
- read-only dashboard/profile
- attendance history/summary from submitted attendance
- fee obligations/payments/receipts appropriate for family visibility
- finalized/published assessment results
- announcements/notices when Phase 7 communication data exists
- secure password/account lifecycle

Do not expose administrative views directly; create role-specific read models/views.

## OPEN decisions before Phase 6 ADRs

- Who provisions guardian/student accounts and how identity is verified?
- Can multiple guardian accounts see the same student? Existing domain suggests yes, but visibility policy must be explicit.
- Are some Guardian relationships denied financial or academic visibility?
- Student minimum age or policy for own login.
- Which fee information is visible to students versus guardians.
- Result publication: immediate on FINAL or separate PUBLISHED/go-live state?
- Attendance notes/correction history visibility.
- Contact-data editing: read-only initially or controlled update requests?
- Downloadable report cards/receipts scope.

## Suggested implementation gates

0. Portal identity/privacy ADRs.
1. Guardian/Student account linking.
2. Object-level authorization.
3. Role-specific dashboard/profile.
4. Attendance visibility.
5. Fees visibility.
6. Assessment publication/visibility.
7. Account-security and privacy hardening.
8. Integration hardening.
9. Documentation closeout and phase-6-complete tag.

---

# Phase 7 — Communication and Operational Reporting

## Research findings

Gibbon Messenger treats message posting and external delivery as related but separate concerns and tracks delivery/reporting. This suggests our core should own the communication record and recipients while provider-specific email/WhatsApp/Telegram delivery stays behind adapters.

## Proposed bounded Phase 7 scope

- Announcement/message record
- explicit recipient targeting (school, Class/Section, selected Students/Guardians/Staff as approved)
- in-app visibility
- delivery attempts separated from message content
- email as the first external channel if approved
- provider-independent delivery status/error recording
- read/acknowledgement only if a concrete need exists
- operational management reports across already-built domains

## OPEN decisions before Phase 7 ADRs

- Primary external channel: email, WhatsApp, Telegram, or staged rollout.
- Transactional alerts vs bulk announcements.
- Guardian/student opt-out and consent policy by message type.
- Whether WhatsApp Business API cost/templating constraints fit the deployment.
- Retry/idempotency policy.
- Attachments.
- Scheduled messages.
- Read receipts.
- Whether communication is one-way only initially.
- Data retention for message/delivery logs.
- Which dashboards are genuinely needed versus exportable reports.

## Suggested implementation gates

0. Communication/privacy/delivery ADRs.
1. In-app announcement model.
2. Recipient resolution and authorization.
3. Delivery abstraction + idempotency.
4. First external provider.
5. Delivery status/failure handling.
6. Role-specific communication UI.
7. Operational reports/dashboard only from proven needs.
8. Integration hardening.
9. Documentation closeout and phase-7-complete tag.

Stop for conversational chat, inbound WhatsApp processing, marketing automation, or multi-provider failover unless separately approved.

---

# Cross-phase dependency order

Phase 2 Attendance
-> Phase 3 Fees (depends on Student + Enrollment, largely independent of Attendance)
-> Phase 4 Assessments (depends on Student + Enrollment; may require AcademicTerm/Subject decisions)
-> Phase 5 Teacher Workflows (consumes Attendance + Assessments)
-> Phase 6 Parent/Student Experience (consumes Attendance + Fees + Assessments)
-> Phase 7 Communication/Reporting (consumes role identities and prior operational domains)
-> Production Hardening

Phase 3 and Phase 4 can be researched in parallel, but implementation should remain sequential unless there is a strong reason otherwise.

## Research sources consulted

- Frappe Education documentation: Fee Category, Fee Structure, Fee Schedule, Fees, Assessment Plan, Academic Year/Term.
- ERPNext documentation: Payment Entry and payment allocation/reconciliation concepts.
- Gibbon documentation: Finance, Planner, Timetabling, Student Profile, Reports/Publishing, Reporting Cycles.
- GibbonEdu/core source: invoice lifecycle/partial-payment behavior, Markbook, Messenger and permission patterns.

These are inspiration and evidence, not source-of-truth requirements for this product.
