# ERP Benchmark Adoption and Codebase Audit Plan

**Status:** Research baseline for comparison only  
**Date:** 20 November 2026  
**Repository:** `Joseph5157/school-erp`  
**Implementation authority:** None. This document does not approve features, schema changes, UI changes, roadmap changes, dependencies, deployments, or releases.

## 1. Purpose

This plan consolidates the useful patterns identified from PowerSchool, Toddle, and Edunext and turns them into a controlled audit framework for the current School ERP codebase.

The immediate goal is to determine, with code and test evidence:

- what the product already implements;
- what is partially implemented;
- what is missing;
- what intentionally remains deferred or out of scope;
- where existing behaviour conflicts with a proposed benchmark pattern;
- which apparent gaps are genuine product gaps rather than documentation, discoverability, or UI problems.

The audit must finish before any new implementation plan is approved.

## 2. Product direction to preserve

The target is not to copy any competitor. The intended product direction is:

> PowerSchool-grade administrative control, Toddle-inspired academic workflow quality, and Edunext-level parent self-service, implemented as a simpler mobile-first Indian School ERP with stronger authorization and financial integrity.

### Supported role surfaces

| Role | Desktop direction | Mobile direction |
| --- | --- | --- |
| Administrator and Superadmin | Full support | Full support |
| Teacher and Faculty | No separately designed desktop product; the same authorized experience may remain accessible | Primary, mobile-first experience |
| Guardian and Parent | No separately designed desktop product; the same authorized experience may remain accessible | Primary, mobile-first experience |
| Future non-admin roles | Decide only when the role is approved | Mobile-first by default |

“Mobile-first” does not mean blocking desktop browsers. It means that no separate desktop-optimized Teacher or Guardian product is required unless future evidence justifies one.

## 3. Existing project boundaries

The audit must respect the current repository documents and ADRs. In particular:

- The custom Django and PostgreSQL modular monolith remains the architecture.
- Teacher and Guardian experiences remain separate from the Admin ERP.
- Existing centralized authorization, effective-dated records, immutable publication history, consent, outbox, and audit conventions must not be bypassed.
- Phase 3 Fees is deferred and not implemented.
- The current PWA gate is online-only and installable. It has no service worker, offline page, client-side storage, background synchronization, or push notifications.
- Phase 5 Teacher Workflows and Phase 6 Guardian Portal are completed baselines, not permission to broaden access.
- Phase 7 Communication, Documents, and Bulk Import has its own approved boundaries. Fee reminders wait for Phase 3.

Primary repository sources include:

- `docs/PRODUCT.md`
- `docs/ROADMAP.md`
- `docs/ARCHITECTURE.md`
- `docs/REQUIREMENTS.md`
- `docs/DOMAIN_MODEL.md`
- `docs/PERMISSIONS.md`
- `docs/PHASE_4_ASSESSMENTS_PLAN.md`
- `docs/PHASE_5_TEACHER_WORKFLOWS_PLAN.md`
- `docs/PHASE_6_GUARDIAN_PORTAL_PLAN.md`
- `docs/PHASE_7_COMMUNICATION_DOCUMENTS_IMPORT_PLAN.md`
- `docs/PWA_GATE_1_PLAN.md`
- `docs/UI_DESIGN_RULES.md`
- applicable ADRs under `docs/adr/`
- GitHub issue [#274](https://github.com/Joseph5157/school-erp/issues/274)

## 4. Benchmark sources and their proper use

### PowerSchool

Use PowerSchool as a reference for administrative and student-information-system discipline:

- role-aware global search;
- Student 360 or consolidated student workspace;
- persistent selected-student context;
- safe bulk operations;
- attendance administration and exceptions;
- configurable reporting and exports;
- historical records and academic-year rollover.

Research note: [PowerSchool 101 Research Review for School ERP](https://chatgpt.com/space/page_c9a2639de2a08191bb62bb44f033f37f)

### Toddle

Use Toddle as a reference for academic and teaching workflow coherence:

- planning to assessment to rubric to gradebook to evidence to reporting;
- fast grade entry and assessment management;
- criteria or rubric assessment where school policy requires it;
- student work or evidence linked to assessment;
- teacher preview of published information;
- reusable curriculum or assessment blueprints;
- granular roles and permissions;
- evidence-backed assistance with explicit human approval.

Do not treat IB-specific workflows, portfolios, AI grading, AI tutors, or mastery calculations as default requirements.

Research note: [Toddle Research Review for School ERP](https://chatgpt.com/space/page_37b48a92314c8191b5ce1c18961e2bf2)

### Edunext

Use Edunext as a reference for Indian-school operations and parent engagement:

- unified guardian updates;
- structured communication categories;
- departmental routing;
- inbox, outbox, replies, and retained history;
- request ownership and status;
- guardian leave applications;
- certificate, grievance, transport, and transfer-certificate requests;
- consecutive-absence reporting;
- mobile management summaries;
- parent-facing fee status, instalments, hosted payment, and receipts as future fee UX references only.

Research note: [Edunext Research Review for School ERP](https://chatgpt.com/space/page_07578b5cdff88191a1360274a1563549)

## 5. Candidate capability register

The entries below are audit candidates, not approved requirements.

### 5.1 Administration and student records

| ID | Candidate capability | Intended value | Initial disposition |
| --- | --- | --- | --- |
| ADM-01 | Role-aware global search | Find students, guardians, staff, and permitted actions quickly | Evaluate |
| ADM-02 | Consolidated Student 360 workspace | Reduce navigation across disconnected screens | Evaluate |
| ADM-03 | Persistent selected-student context | Preserve context across authorized student workflows | Evaluate carefully |
| ADM-04 | Safe bulk actions | Preview, validate, confirm, execute, and summarize bulk work | Strong candidate |
| ADM-05 | Configurable exports | Let authorized users select required report columns | Strong candidate |
| ADM-06 | Exception-led attendance administration | Show missing, conflicting, late, or unusual records | Strong candidate |
| ADM-07 | Controlled year rollover | Preview and reconcile year transition without rewriting history | Future validation |
| ADM-08 | Admin mobile task coverage | Full authorized Admin capability with mobile task prioritization | High-priority audit |

### 5.2 Teaching and assessment

| ID | Candidate capability | Intended value | Initial disposition |
| --- | --- | --- | --- |
| ACA-01 | Connected academic chain | Link planning, assessment, results, evidence, and reports without duplicate truth | Evaluate architecture |
| ACA-02 | Assessment-first gradebook | Organize latest assessments and their subjects coherently | Strong candidate |
| ACA-03 | Fast repetitive grade entry | Keyboard, bulk, filtering, validation, and save-state clarity | High-priority UX audit |
| ACA-04 | Explicit result statuses | Distinguish absent, medical leave, exempted, not applicable, and unrecorded | Strong consistency rule |
| ACA-05 | Rubric or criteria assessment | Support only when a school’s policy requires it | Validate, not default |
| ACA-06 | Evidence attachments | Link selected student work to an assessment | Future validation |
| ACA-07 | Guardian-view preview | Let authorized staff confirm what will be published | Strong candidate |
| ACA-08 | Reusable academic blueprints | Reuse approved structures without copying stale operational data | Future validation |
| ACA-09 | Lesson plan approval and coverage | Optional planning and supervision workflow | Defer pending school research |
| ACA-10 | Portfolio | Curated evidence where a school needs it | Optional, not default |

### 5.3 Teacher daily operations

| ID | Candidate capability | Intended value | Initial disposition |
| --- | --- | --- | --- |
| TEA-01 | Task-first Today home | Show classes, attendance, marks, remarks, and pending work | Compare with current Teacher home |
| TEA-02 | Default-plus-exceptions attendance | Reduce taps while preserving explicit submission | Strong candidate |
| TEA-03 | Submission summary and controlled correction | Make saved state and correction authority unambiguous | Compare with current rules |
| TEA-04 | Consecutive-absence insight | Identify students needing timely intervention | Strong analytics candidate |
| TEA-05 | Assessment completeness | Show missing marks, drafts, or unpublished work | Strong candidate |
| TEA-06 | Assignment and homework workflow | Class or selected-student assignment with controlled attachments | Validate against roadmap |
| TEA-07 | Mobile repetitive-task quality | Optimize tap count, input, error recovery, and continuity | High-priority audit |

### 5.4 Guardian engagement and self-service

| ID | Candidate capability | Intended value | Initial disposition |
| --- | --- | --- | --- |
| GUA-01 | Activation and recovery funnel | Improve successful first use without weakening identity verification | High-priority audit |
| GUA-02 | Consolidated child home | Attendance, latest results, notices, and pending actions | Strong candidate |
| GUA-03 | Unified updates inbox | One place for notices, messages, calendar changes, and requests | Strong candidate |
| GUA-04 | Structured school communication | Choose purpose and route to the authorized team | Strong candidate |
| GUA-05 | Request ownership and status | Submitted, assigned, answered, resolved, and closed history | Strong candidate |
| GUA-06 | Guardian leave application | Connect planned absence to school review and attendance | Validate policy |
| GUA-07 | Grievance workflow | Controlled categories, privacy, ownership, escalation, and resolution | Validate carefully |
| GUA-08 | Certificate and service requests | Reduce reception calls when the back-office workflow exists | Future staged candidate |
| GUA-09 | Downloadable verified documents | Give access to published report cards and approved documents | Compare with Phase 7 |
| GUA-10 | Verified fee visibility | Show only authoritative posted financial state | Deferred to FIN-G4 |

### 5.5 Communication

| ID | Candidate capability | Intended value | Initial disposition |
| --- | --- | --- | --- |
| COM-01 | Typed request routing | Route by purpose rather than personal contact details | Strong candidate |
| COM-02 | Reply policy | Explicit one-way, reply-enabled, or staff-only communication | Evaluate |
| COM-03 | Ownership and configurable service target | Make responsibility and delay visible | Validate operations |
| COM-04 | Immutable or correction-aware history | Prevent silent rewriting of consequential communication | Strong safety rule |
| COM-05 | Consent and audience recheck | Respect consent and authorization at preparation and send time | Preserve existing design |
| COM-06 | Idempotency and deduplication | Prevent duplicate notices or actions | Preserve existing design |
| COM-07 | Escalation and closure | Escalate overdue requests and retain closure reason | Future validation |

### 5.6 Mobile, PWA, and notifications

| ID | Candidate capability | Intended value | Initial disposition |
| --- | --- | --- | --- |
| MOB-01 | Admin desktop and mobile parity | Support the full Admin role across devices | Product direction; audit current reality |
| MOB-02 | Teacher mobile-first workflow | Make daily teacher work fast on a phone | Product direction |
| MOB-03 | Guardian mobile-first workflow | Make parent information and requests phone-friendly | Product direction |
| MOB-04 | Login convenience | Reduce repeated friction without weakening account security | Evaluate passkeys or device-assisted login later |
| MOB-05 | Notification centre | Retain in-product notifications regardless of delivery channel | Strong candidate |
| MOB-06 | Push notifications | Improve timely delivery | Decide only after consent, reliability, and usage research |
| MOB-07 | Offline read resilience | Preserve safe selected reads during temporary loss | Measure before designing |
| MOB-08 | Offline write and synchronization | Allow queued writes with conflict handling | High risk; no decision without workflow evidence |
| MOB-09 | Background synchronization | Complete safe queued work later | Dependent on MOB-08 |
| MOB-10 | Native mobile applications | Device-specific application | Do not decide before PWA measurement |

The audit must not label MOB-06 through MOB-10 as ordinary missing features. They are unresolved product decisions.

### 5.7 Analytics and insights

Analytics should be actionable, attributable, permission-scoped, and linked to source records.

| ID | Candidate insight | Intended action |
| --- | --- | --- |
| ANA-01 | Attendance not submitted | Open the responsible class or period workflow |
| ANA-02 | Consecutive or repeated absence | Review the student and contact the authorized guardian |
| ANA-03 | Incomplete assessment or marks | Open the relevant assessment entry workflow |
| ANA-04 | Unpublished or stale report | Review publication state and source changes |
| ANA-05 | Guardian account inactive | Continue verified onboarding or recovery |
| ANA-06 | Unread or unacknowledged important update | Review audience and follow-up policy |
| ANA-07 | Unanswered or overdue parent request | Open the owned conversation or service request |
| ANA-08 | Authorization or data-integrity hold | Resolve the hold before exposing data |
| ANA-09 | Future fee reconciliation exception | Investigate ledger, cash, bank, or gateway mismatch |

Do not recommend decorative dashboards, rankings, opaque risk scores, or AI predictions without an approved decision and trustworthy source data.

### 5.8 Fee management

Fee management is a high-priority product gap but not an unplanned area. GitHub issue #274 records the protected direction.

| Gate | Scope | Audit treatment |
| --- | --- | --- |
| FIN-G0 | Financial rules and threat model | Next work only when explicitly resumed |
| FIN-G1 | Protected financial ledger | Not implemented; do not create placeholders |
| FIN-G2 | Finance-office workflow | Not implemented |
| FIN-G3 | Reconciliation and audit | Not implemented |
| FIN-G4 | Read-only guardian fees | Blocked by G0-G3 |
| FIN-G5 | Fee reminder queue | Blocked by authoritative ledger and reconciliation |
| FIN-G6 | Online payment and supervised pilot | Final gate after security, recovery, and live validation |

The audit should verify that no accidental fee placeholder, mutable balance, reminder, guardian navigation, or payment stub has entered the codebase. It must not propose implementation details beyond identifying evidence and unresolved FIN-G0 questions.

## 6. Patterns explicitly not approved

The following are not default requirements:

- copying a competitor’s complete module list;
- a separate Toddle-like LMS beside the ERP;
- IB terminology as the product default;
- mandatory portfolios, rubrics, lesson plans, or teacher diaries;
- AI grading, AI tutors, or autonomous academic decisions;
- native apps before real PWA usage is measured;
- offline financial transactions;
- automatic messages without consent and last-moment authorization checks;
- rankings or opaque predictive analytics;
- transport, inventory, library, canteen, event, or digital-learning modules without validated demand;
- an unprioritized mobile mega-menu;
- hard-coded response-time promises;
- uncontrolled public-drive links for student files;
- a microservice architecture solely to add Fees.

## 7. Codebase audit method

### 7.1 Establish the exact baseline

Record:

- branch and full commit SHA;
- working-tree state;
- Python, Django, PostgreSQL, frontend, and test configuration;
- authoritative project documents and ADR status;
- whether the inspected code matches the latest local and remote baseline.

Never hide or overwrite an existing dirty working tree.

### 7.2 Inspect implementation evidence

For every candidate, inspect as applicable:

- models, migrations, constraints, and database triggers;
- services and domain methods;
- authorization helpers and permission checks;
- forms, views, URLs, templates, and static assets;
- background workers, management commands, outbox logic, and integrations;
- tests and fixtures;
- documentation and ADRs;
- responsive behaviour and PWA assets.

Documentation describes intent. Code plus tests establish implementation. Templates alone do not establish authorization or domain correctness.

### 7.3 Classification

Use exactly one current-state status per candidate:

| Status | Definition |
| --- | --- |
| Implemented | End-to-end behaviour exists, is authorized correctly, and has proportionate tests |
| Partial | A meaningful subset exists, but the candidate is incomplete or inconsistent |
| UI-only | A screen or control exists without confirmed domain and authorization support |
| Backend-only | Domain support exists without a usable role workflow |
| Missing | No meaningful implementation evidence exists |
| Divergent | Existing behaviour conflicts with the candidate or a frozen project decision |
| Deferred | Repository decisions explicitly postpone the capability |
| Not applicable | Evidence shows the capability should not apply to this product or role |
| Unknown | Evidence is insufficient; state exactly what must be checked |

### 7.4 Evidence requirements

Every conclusion must include:

- repository path and line reference;
- relevant model, service, view, template, or command name;
- relevant test path and test name where available;
- applicable ADR, roadmap, or phase-plan reference;
- role and authorization boundary;
- mobile and desktop exposure where relevant.

Do not infer a feature from a label, URL, navigation item, model name, or plan document alone.

### 7.5 Gap priority

Priority is an audit recommendation, not implementation approval.

| Priority | Meaning |
| --- | --- |
| P0 | Security, authorization, financial integrity, data loss, or misleading published state |
| P1 | High-frequency daily workflow, parent engagement, mobile usability, or operational reliability |
| P2 | Valuable capability with manageable dependency and lower urgency |
| P3 | Optional, specialized, or demand-dependent capability |
| Research | Needs school interviews, usage data, legal review, or policy decisions first |
| Deferred | Explicitly blocked by an approved roadmap or gate decision |

## 8. Required audit outputs

Claude Code should produce:

1. **Executive summary** — the strongest existing areas, largest verified gaps, and material divergences.
2. **Current product map** — Admin, Teacher, Guardian, communication, PWA, analytics, and Fees.
3. **Capability evidence matrix** — every ID in this plan with status, evidence, tests, roles, risks, dependencies, and recommendation.
4. **Role and device matrix** — Admin desktop/mobile, Teacher mobile-first, and Guardian mobile-first coverage.
5. **Mobile workflow audit** — daily journeys, tap/input friction, continuity, failure states, network loss, and login friction.
6. **Parent-engagement audit** — onboarding, child selection, information, communication, requests, consent, and follow-up.
7. **Analytics audit** — existing actionable insights versus decorative or absent reporting.
8. **Fee boundary verification** — confirm Phase 3 remains absent and issue #274 guardrails have not been contradicted.
9. **Duplicate-free gap register** — one canonical entry per gap, with related candidate IDs grouped.
10. **Conflict register** — competitor ideas that conflict with current ADRs, permissions, or product boundaries.
11. **Research questions** — decisions requiring school interviews or real-device usage measurement.
12. **Next-move options** — two or three staged options with dependencies and trade-offs, without implementation.

## 9. Mobile measurement questions

Before recommending offline synchronization or native applications, identify how the product can measure:

- completion time for attendance, marks entry, student lookup, and announcements;
- taps or input actions per common task;
- failed or abandoned saves;
- network-loss frequency and the workflows affected;
- login and password-recovery friction;
- device and viewport distribution;
- notification delivery, opening, and follow-through;
- Guardian activation and repeat use;
- Admin tasks genuinely performed from phones;
- Teacher tasks that require a larger screen.

Measurement proposals must minimize personal data, avoid recording sensitive field values, and respect consent and retention requirements.

## 10. Acceptance criteria for the audit

The audit is complete only when:

- all candidate IDs have exactly one status;
- every Implemented, Partial, UI-only, Backend-only, or Divergent conclusion has code evidence;
- every Deferred conclusion cites the governing repository decision;
- all gaps are deduplicated;
- existing strengths are recorded, not only missing features;
- no competitor feature is presented as automatically required;
- no application code, schema, migration, dependency, configuration, or deployment is changed;
- no fee implementation is started;
- recommended next moves clearly separate safety work, workflow improvements, research, and deferred items.

## 11. Decision after the audit

After reviewing the evidence report, the product owner can choose among:

- address verified P0 inconsistencies or safety gaps;
- select a narrow P1 mobile or parent-engagement improvement;
- begin a dedicated analytics discovery stage;
- resume FIN-G0 as a separate financial requirements and threat-model project;
- conduct school interviews or real-device measurement before choosing a build direction;
- leave a benchmark idea deferred or reject it.

No choice is made by this document.
