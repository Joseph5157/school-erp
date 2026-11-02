# Architecture Decision Records

## Purpose

Architecture Decision Records (ADRs) capture important project decisions and the rationale behind them.

They are meant to preserve the reasoning behind technical and product architecture choices so future contributors can understand why a decision was made and what it means for later work.

## ADR format

A typical ADR should include:
- title
- status
- context
- decision
- consequences
- related requirements or domain decisions

## Use in this project

Important decisions should eventually be recorded as individual ADRs.

Suggested future ADR subjects include:
- applicant and student separation
- academic enrollment history
- guardian as first-class entity
- modular monolith architecture
- technology stack
- authorization approach

Do not create all those ADR files now. ADRs should be added only when the decision is important enough to justify a formal record.

## Source-of-truth relationship

ADRs should not replace approved product requirements or domain documentation. They are the formal record of the architectural and design rationale that supports those accepted decisions.

## Index of ADR files

- [0001 Academic structure and enrollment history](0001-academic-structure-and-enrollment-history.md)
- [0002 Applicant, Student, and Guardian lifecycle](0002-applicant-student-and-guardian-lifecycle.md)
- [0003 Phase 1 status and transition rules](0003-phase-1-status-and-transition-rules.md)
- [0004 Phase 1 authorization foundation](0004-phase-1-authorization-foundation.md)
- [0005 Phase 2 attendance domain model and rules (superseded by 0007)](0005-phase-2-attendance-domain-model.md)
- [0006 Academic Enrollment effective dating](0006-academic-enrollment-effective-dating.md)
- [0007 Corrected Phase 2 attendance model](0007-phase-2-attendance-model.md)
- [0008 Phase 2 school calendar rules](0008-phase-2-school-calendar-rules.md)
- [0009 Phase 4 assessment and results model](0009-phase-4-assessment-and-results-model.md)
- [0010 Phase 4 assessment-scoped teacher authorization](0010-phase-4-assessment-teacher-authorization.md)
- [0011 Phase 5 class teacher and teacher workflow model](0011-phase-5-class-teacher-and-teacher-workflow-model.md)
- [0012 Phase 5 teacher attendance and student access authorization](0012-phase-5-teacher-attendance-and-student-access.md)
- [0013 Phase 6 guardian accounts, access grants, multiple roles and revocation](0013-phase-6-guardian-accounts-and-access-grants.md)
- [0014 Phase 6 guardian-visible information and explicit result publication](0014-phase-6-guardian-visible-information-and-result-publication.md)
- [0015 Phase 7 notifications, guardian consent and delivery modes](0015-phase-7-notifications-consent-and-delivery-modes.md)
- [0016 Phase 7 issued documents and PDF generation](0016-phase-7-issued-documents-and-pdf-generation.md)
- [0017 Phase 7 bulk import through applicant progression](0017-phase-7-bulk-import-through-applicant-progression.md)
- [0018 Effective-dated subject teacher assignments](0018-effective-dated-subject-teacher-assignments.md)
- [0019 Subject name captured at assessment finalization](0019-subject-name-captured-at-finalization.md)
- [0020 School logo storage and document letterhead](0020-school-logo-storage-and-document-letterhead.md)
- [0021 Timetable periods and weekly slots](0021-timetable-periods-and-weekly-slots.md)
- [0022 Display-only subject averages in analytics](0022-analytics-subject-averages.md): accepted exception to ADR 0009 for chart averages.
