# Phase 3 Fees — Research and Implementation Plan

Status: RESEARCHED PLAN / ADR CANDIDATES — not accepted source of truth until Phase 3 Gate 0 is reviewed and frozen.

## 1. Goal

Build a reliable school-fee subledger for a single-school ERP.

Phase 3 must answer, from preserved records rather than mutable Student fields:

- What was this student charged?
- Why and for which Academic Year / enrollment?
- When was each amount due?
- What concessions or adjustments changed the amount payable?
- What money was actually received, when, and by which mode?
- Which obligations did each payment settle?
- What remains outstanding?
- What was reversed or corrected?
- What receipt/evidence was issued?
- What was the position as of a historical date?

Phase 3 is not a general accounting package.

## 2. Research basis

### Frappe Education

Useful separation:
- Fee Category defines fee components.
- Fee Structure is a reusable template.
- Fee Schedule applies a structure to a student group/timeline and due date.
- Student Fees records carry actual student/enrollment/year context.
- Current Fee Structure supports component discounts and annual amounts that can be bifurcated into schedules.

Lesson adopted: configuration must not itself be the student's historical debt.

### ERPNext

Useful settlement model:
- payment is a distinct event;
- one payment can be allocated across multiple invoices/obligations for one party;
- a partial allocation leaves an outstanding amount;
- an advance can remain unallocated and later be reconciled;
- allocation/reconciliation changes which debt a payment settles without pretending a second cash movement occurred;
- reversals/unreconciliation preserve traceability rather than deleting the original event.

Lesson adopted: Payment and PaymentAllocation must be distinct, and settlement state should be derived from valid allocations.

Not adopted: general ledger, chart of accounts, multi-currency, customer/supplier accounting and full ERP accounting machinery.

### Gibbon

Useful billing behavior:
- predefined fees/billing schedules feed invoices;
- pending invoice values may reflect configuration, but issued values are fixed;
- partial payments carry payment-specific details;
- transaction IDs and receipts are operational evidence;
- historical fixes explicitly guard against issued invoice values changing;
- refunded invoices retain printable receipt/history behavior.

Lesson adopted: issuance is the historical freeze boundary.

## 3. Phase 3 scope

### In scope

1. Fee categories.
2. Reusable Academic-Year-aware fee structures.
3. Structure components.
4. Installment/due-date planning.
5. Explicit generation of student fee obligations from a structure/plan.
6. Student-specific adjustments/concessions.
7. Manual payment recording.
8. Payment modes such as CASH, UPI and BANK_TRANSFER, designed as controlled configuration/choices.
9. External reference/transaction reference where applicable.
10. Partial payments.
11. Allocation of one payment across multiple obligations belonging to the same student.
12. Unallocated student credit/advance if accepted at Gate 0.
13. Immutable receipt identifier for accepted payments.
14. Payment reversal/correction with audit history.
15. Student fee ledger.
16. Outstanding-dues reporting.
17. Collection reporting.
18. Due/overdue reporting.
19. Admin-only fee mutations for Phase 3.
20. Authorization and direct-ORM/data-integrity regression tests.

### Explicitly out of scope unless Gate 0 changes it

- online payment gateway;
- automatic bank reconciliation;
- full accounting/general ledger;
- GST/tax engine;
- multi-currency;
- multi-school accounting;
- payroll/expenses;
- automatic late-fee engine;
- recurring billing engine;
- parent online payment;
- family/sibling consolidated account;
- refunds that move money out, unless a minimal refund requirement is explicitly accepted;
- WhatsApp/email payment reminders (Phase 7);
- parent/student fee portal (Phase 6).

## 4. Proposed domain model

Names are candidates; behavior matters more than exact naming.

### FeeCategory

Purpose: stable classification such as Tuition, Transport, Examination.

Candidate fields:
- name
- description
- active
- audit timestamps

Rules:
- category identity should remain available for historical obligation lines;
- a used category should not be casually hard-deleted.

### FeeStructure

Purpose: reusable fee template, not a student debt.

Candidate fields:
- name
- academic_year
- class_grade or other approved applicability
- status: DRAFT / ACTIVE / RETIRED
- effective/configuration metadata
- audit timestamps

### FeeStructureComponent

- fee_structure
- fee_category
- amount
- description/order

A structure total is derived from components.

### FeeInstallmentPlan / FeeStructureInstallment

Purpose: define how an annual/template amount becomes due.

Candidate representation:
- structure/plan
- installment label
- due_date or due-date rule resolved to an explicit date before issuance
- component amounts or percentage/amount distribution

Important: generated student obligations store explicit due dates and amounts. Historical debt must never depend on re-evaluating a mutable scheduling rule.

### FeeObligation

Purpose: an issued student-specific amount due.

Candidate fields:
- student
- academic_enrollment
- academic_year (possibly denormalized only with consistency constraints)
- issue_date
- due_date
- status/lifecycle field only where it represents workflow, not derived settlement
- source fee structure/plan reference
- immutable human-readable obligation/reference number if needed
- created_by
- audit timestamps

Rules:
- student/enrollment/year must agree;
- enrollment must be applicable according to the Gate 0 policy;
- an issued obligation is historically frozen;
- changing a FeeStructure never rewrites an issued obligation.

### FeeObligationLine

Snapshot of what was actually charged:
- obligation
- fee_category
- description snapshot
- original_amount

Original issued lines become immutable after issue.

### FeeAdjustment

Purpose: post-issue concession, waiver or correction without rewriting the original charge.

Candidate fields:
- obligation or obligation line
- type (exact vocabulary frozen in Gate 0)
- amount
- reason
- effective/business date
- created_by
- audit timestamps
- reversal relationship if adjustment itself is reversed

Adjusted payable = original issued amount + signed valid adjustments.

Do not overwrite original_amount.

### Payment

Purpose: evidence of money actually received from/for one student.

Candidate fields:
- student
- payment_date (business date)
- amount_received
- payment_mode
- external_reference nullable depending on mode
- receipt_number
- status: RECORDED / REVERSED (candidate)
- recorded_by
- recorded_at
- reversal metadata/history

Important distinction:
payment_date is when money was received; recorded_at is audit time.

### PaymentAllocation

Purpose: state how received money settles obligations.

Candidate fields:
- payment
- fee_obligation
- allocated_amount
- allocation business/audit metadata as required

Rules:
- payment.student == obligation.student;
- allocation amount > 0;
- total valid allocations cannot exceed valid payment amount;
- total allocations to an obligation cannot exceed its adjusted payable amount;
- allocations must be concurrency-safe;
- reversal/unallocation must preserve audit history.

### Optional StudentCredit / derived unallocated amount

Preferred first design: do not create a separate mutable balance row unless required.

unallocated payment amount =
valid payment amount - sum(valid allocations)

This naturally represents an advance/credit.

Whether Phase 3 accepts overpayments/unallocated advances is an OPEN Gate 0 decision.

## 5. Derived financial state

Avoid editable PAID/PARTIAL/OUTSTANDING flags where the same answer can be derived.

For obligation O:

issued_total = sum(original obligation lines)

adjustment_total = sum(valid signed adjustments)

payable_total = issued_total + adjustment_total

allocated_total = sum(valid allocations from non-reversed payments)

outstanding = payable_total - allocated_total

Derived display state:
- UNPAID if allocated_total = 0 and outstanding > 0
- PARTIALLY_PAID if allocated_total > 0 and outstanding > 0
- PAID if outstanding = 0

OVERDUE is a view/report condition:
outstanding > 0 AND due_date < business/today date.

It should not be a manually editable financial fact.

## 6. Historical freeze boundaries

### Before obligation issue

DRAFT configuration may be edited according to authorization.

### At obligation issue

Snapshot:
- student/enrollment context;
- category/component description needed for history;
- line amounts;
- issue date;
- due date.

After issue:
- no silent line edits;
- no structure change propagates into it;
- concessions/waivers use adjustments;
- mistakes use an explicit correction/cancellation policy frozen by ADR.

### At payment acceptance

Snapshot:
- student;
- payment date;
- amount;
- mode;
- external reference;
- receipt number;
- actor/audit time.

A wrong accepted payment is not hard-deleted or overwritten. Use reversal/correction policy.

## 7. Enrollment and transfer semantics

Fees must use Phase 1 effective-dated AcademicEnrollment.

Candidate rule:
- obligation generation uses an enrollment applicable to the obligation's approved applicability date;
- FeeObligation keeps that historical enrollment reference;
- a later transfer must not rewrite earlier obligations;
- future installment behavior after a transfer is an explicit Gate 0 decision.

OPEN: if a student transfers Section/Class mid-year, determine whether remaining fee plan follows:
A. original annual enrollment/structure,
B. new placement prospectively,
C. explicit admin reassignment.

Do not invent this during implementation.

## 8. Concessions and scholarships

Research shows category/component discounts are common, but our historical model should make student-specific financial effects explicit.

Candidate Phase 3 policy:
- structure-level discounts may help calculate a template;
- once issued, a student's concession is represented in the obligation snapshot or an explicit FeeAdjustment;
- post-issue concession never mutates the original charge.

OPEN:
- fixed amount only vs percentage entry;
- obligation-level vs component-level;
- named concession reason/category;
- approval role/workflow;
- whether scholarships are merely concession types or a separate domain.

Recommended minimal product: fixed monetary adjustments with required reason, optionally linked to a line/category. Percentage can be a UI calculation that resolves to a fixed amount before acceptance.

## 9. Partial payments

Accept as core Phase 3 behavior.

Example:
Tuition obligation = 30,000
Payment 1 = 10,000
Allocation = 10,000
Outstanding = 20,000

A second payment does not edit Payment 1.

A single Payment may allocate to several outstanding obligations for the same Student, subject to total-payment and obligation-balance constraints.

OPEN allocation policy:
- admin manually selects allocations;
- system proposes oldest-due-first but admin confirms;
- fully automatic allocation.

Recommended candidate: system may propose oldest-due-first as UI convenience, but persisted allocations are explicit and reviewed.

## 10. Advance / overpayment

Research supports unallocated payments, but product policy must be frozen.

Candidate safe model:
Payment 10,000
Allocated 7,000
Unallocated 3,000

The 3,000 remains traceable to the same Student and can later be allocated; it is not revenue invented by the allocation process.

OPEN:
- accept advances at all;
- allow accidental overpayment;
- refund or carry forward;
- cross-Academic-Year carry-forward.

Recommended Phase 3 boundary: support unallocated credit for the same Student but defer cross-student/family transfer and complex refunds.

## 11. Payment modes

Candidate initial controlled values:
- CASH
- UPI
- BANK_TRANSFER
- OTHER

OPEN:
- CHEQUE needed?
- CARD needed for manual terminal payments?
- should modes be database-configurable or enum choices?

Rules:
- UPI/bank/cheque-like modes may require external reference according to configured policy;
- CASH should not invent a transaction ID;
- payment mode is evidence/metadata, not a gateway integration.

## 12. Receipt policy

Receipt represents an accepted money-receipt event, not an obligation.

Candidate:
- one immutable receipt number per accepted Payment;
- receipt shows payment amount/date/mode/reference and allocations;
- later reversal does not reuse/delete the original receipt number;
- reversal status is visible when viewing historical receipt;
- reprinting does not generate a new number.

OPEN:
- numbering format;
- per Academic Year reset vs global sequence;
- when number is reserved: draft save or acceptance;
- gap tolerance after failed transaction.

Recommended: allocate receipt number only when Payment is atomically accepted/recorded, with a database uniqueness constraint. Do not promise legally gapless numbering unless the school explicitly requires it.

## 13. Reversal, correction and refund semantics

Separate concepts:

Payment reversal:
The recorded payment itself was wrong/invalid. Preserve original payment and record reversal actor, time, reason. Its allocations cease to count toward settlement according to the accepted reversal design.

Allocation correction:
Money receipt is correct but was applied to wrong obligation. Preserve allocation history; unreconcile/reallocate rather than edit the payment event.

Refund:
Money actually leaves the school and is returned. This is a second money movement, not merely a payment reversal.

Recommended Phase 3:
- implement payment reversal;
- implement audited allocation correction if multiple allocations are supported;
- defer real refund workflow unless required before implementation.

## 14. Authorization

Phase 3 candidate:
- authenticated != fee administrator;
- all fee configuration/issuance/payment/adjustment/reversal mutations require explicit admin permission;
- read permissions are explicit;
- Phase 6 later introduces Guardian/Student read-only visibility;
- no parent payment in Phase 3.

High-risk operations (adjustment, reversal) should record actor and reason.

OPEN: whether school needs a separate CASHIER role in Phase 3. If not, keep admin-only and add scoped finance roles only when required.

## 15. Required reports

### Student Fee Ledger

Chronological explanation of:
- issued obligations;
- adjustments;
- payments;
- allocations;
- reversals;
- running/outstanding position.

### Outstanding Dues

As of a selected date:
- Student;
- obligation;
- due date;
- payable;
- allocated;
- outstanding;
- overdue condition.

### Collection Report

For payment business-date range:
- receipt;
- Student;
- payment date;
- amount;
- mode;
- external reference;
- reversal state.

Use Payment amounts, not allocations, for cash-collected totals, otherwise one payment allocated to multiple obligations can be double-counted.

### Due/Overdue Report

Based on issued obligations, valid adjustments and allocations.

### Daily Collection Summary

Totals by payment mode and business date, excluding reversed payments according to the accepted reporting policy.

Optional later:
- category-wise billed/collected analysis;
- concession report;
- aging buckets.

## 16. Critical invariants

At minimum:

1. Money amounts use Decimal, never float.
2. Positive issued line amounts unless explicit credit semantics are designed.
3. Payment amount > 0.
4. Allocation amount > 0.
5. Allocation Student consistency.
6. Enrollment/year consistency.
7. Total valid payment allocations <= payment amount.
8. Total valid obligation allocations <= adjusted payable.
9. Reversed payment contributes zero to current settlement.
10. Issued obligation snapshot cannot silently change.
11. Receipt number unique.
12. Business date distinct from audit timestamp.
13. Used historical financial rows are protected from casual hard deletion.
14. Multi-row issuance/payment/allocation/reversal operations are atomic.
15. Concurrent payment/allocation attempts cannot over-settle an obligation.

Some cross-row invariants require service-layer transaction/locking plus regression tests rather than only DB CHECK constraints.

## 17. Required edge-case tests

- exact full payment;
- multiple partial payments;
- one payment across multiple obligations;
- payment with unallocated remainder if enabled;
- duplicate receipt/reference policy;
- attempted over-allocation;
- concurrent allocations against same final balance;
- concession before payment;
- concession after partial payment;
- adjustment that would reduce payable below already allocated amount;
- reversed payment restores outstanding;
- wrong allocation corrected without inventing new cash movement;
- FeeStructure edited after obligation issue does not alter obligation;
- transfer after old obligation leaves old historical enrollment intact;
- inactive/completed Student/enrollment payment policy;
- future payment date policy;
- backdated payment recording with later recorded_at;
- unauthorized configuration/payment/reversal;
- direct ORM constraint bypass attempts;
- protected deletion;
- reports exclude/restate reversed events correctly.

## 18. Gate-by-gate implementation plan

### Gate 0 — Freeze Phase 3 decisions

Create accepted Fee ADRs covering:
- configuration vs obligation vs payment/allocation;
- issue freeze boundary;
- enrollment applicability;
- concessions/adjustments;
- advance/overpayment;
- reversal/refund distinction;
- receipt numbering;
- roles;
- explicit exclusions.

Update REQUIREMENTS, DOMAIN_MODEL, ARCHITECTURE/ROADMAP as needed.

No fee implementation before unresolved blocking OPEN items are decided.

Suggested commit:
docs: freeze phase 3 fee decisions

### Gate 1 — Fee configuration foundation

Implement:
- FeeCategory;
- FeeStructure;
- FeeStructureComponent;
- chosen installment-plan representation;
- Academic Year/Class applicability;
- lifecycle and delete protection;
- admin configuration UI.

Tests for totals, duplicate rules, year consistency, permissions and historical protection.

Suggested commit:
feat: add fee configuration foundation

### Gate 2 — Student fee obligations

Implement:
- FeeObligation;
- immutable FeeObligationLine snapshots;
- explicit issue workflow;
- generation from approved structure/installment;
- enrollment/date validation;
- duplicate-generation/idempotency protection.

Do not implement payment yet.

Suggested commit:
feat: add student fee obligations

### Gate 3 — Adjustments and concessions

Implement accepted adjustment model:
- explicit reason;
- actor;
- business/audit dates;
- amount bounds;
- reversal/correction behavior;
- no rewriting issued lines.

Suggested commit:
feat: add fee adjustments

### Gate 4 — Payment foundation

Implement:
- Payment;
- modes;
- payment_date vs recorded_at;
- external reference;
- receipt numbering;
- atomic record workflow;
- reversal metadata foundation.

No online gateway.

Suggested commit:
feat: add manual fee payments

### Gate 5 — Payment allocation and partial settlement

Implement:
- PaymentAllocation;
- partial payments;
- multi-obligation same-Student allocation;
- optional unallocated advance if accepted;
- concurrency/over-allocation protection;
- derived outstanding/status.

Suggested commit:
feat: add fee payment allocation

### Gate 6 — Reversal and correction hardening

Implement:
- payment reversal;
- allocation correction/unreconciliation if accepted;
- immutable audit trail;
- reason/actor/timestamp;
- settlement recalculation.

Refund only if Gate 0 included it.

Suggested commit:
feat: harden fee reversals and corrections

### Gate 7 — Admin fee workflows

Server-rendered UI:
- configure fees;
- issue/generate obligations;
- view Student ledger;
- record payment;
- allocate payment;
- print/view receipt;
- adjust/concede;
- reverse with explicit confirmation/reason.

Suggested commit:
feat: add admin fee workflows

### Gate 8 — Reporting and reconciliation

Implement:
- Student Fee Ledger;
- Outstanding Dues;
- Collection Report;
- Due/Overdue;
- Daily Collection Summary;
- approved concession/category reports.

Test historical/as-of semantics and reversal behavior.

Suggested commit:
feat: add fee reporting and reconciliation

### Gate 9 — Integration hardening

End-to-end scenario:
Academic Year -> enrollment -> fee structure -> installments -> obligation issue -> concession -> partial payment -> receipt -> second payment/allocation -> reports -> reversal -> restored outstanding -> transfer -> historical obligation unchanged.

Hardening:
- transaction safety;
- concurrency;
- permissions;
- direct ORM regression;
- deletion protection;
- N+1/query review;
- migration review;
- full suite;
- Ruff;
- Django checks;
- makemigrations --check;
- git diff --check.

Suggested commit:
test: complete phase 3 fee integration hardening

### Gate 10 — Documentation closeout

- README/ROADMAP/domain docs;
- operational fee workflow docs;
- confirm all accepted ADRs implemented;
- no blocking OPEN decisions;
- full validation;
- annotated phase-3-complete tag.

Suggested commit:
docs: complete phase 3 fees

## 19. Gate 0 decision checklist

These require human/product decisions before Phase 3 coding:

1. Formal Invoice entity, or call the student debt FeeObligation?
2. Exact structure applicability: Class/Grade, enrollment, Student category, manual, or combination?
3. Installment model.
4. Transfer mid-year treatment.
5. Concession capabilities and approval.
6. Accept unallocated advance/overpayment?
7. Cross-year credit carry-forward?
8. Late fees now or deferred?
9. Refund workflow now or deferred?
10. Receipt numbering format/reset policy.
11. Required payment modes and reference rules.
12. Admin-only or separate cashier role?
13. Allow backdated payment business dates?
14. Treatment of payment after Student becomes inactive/completes enrollment.
15. Any statutory/local receipt or fee-report requirement that changes the data model.

## 20. Stop-and-return-to-planning triggers

Stop implementation rather than invent behavior if any requirement appears for:
- GST/tax accounting;
- full double-entry accounting;
- payment gateway;
- family/sibling account;
- sponsor/company payer;
- multi-currency;
- cross-student credit transfer;
- complex refund;
- automatic late-fee interest;
- financial approval chains;
- immutable statutory invoice numbering beyond the frozen receipt policy;
- fee behavior dependent on an unmodeled transport/hostel/service domain.

## 21. Research conclusion

The minimal robust architecture is:

FeeStructure (template)
-> FeeObligation + Lines (issued historical debt)
-> FeeAdjustment (explicit change to amount payable)
-> Payment (money received)
-> PaymentAllocation (what debt that money settles)
-> derived outstanding/settlement state
-> reversal/correction records preserving history

This architecture matches the project's existing preference for effective-dated, historically correct operational records while avoiding the complexity of a general accounting ERP.
