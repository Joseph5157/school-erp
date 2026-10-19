# Post-UI Specialized Building Blocks Plan

**Status:** Deferred until the UI redesign is complete.

**Baseline:** Created after PR #88 on `main`.

## Purpose

Keep a short list of reusable technical building blocks that may reduce repeated infrastructure code across the School ERP **without taking ownership of domain rules**.

The rule for adoption is:

> Add a specialized building block only when it eliminates repeated infrastructure code across multiple modules without taking ownership of our domain rules.

Do not implement any item in this document during the current UI redesign unless a genuine blocker appears and is separately approved.

## Candidate building blocks

### 1. HTMX — continue selectively

**Status:** Already adopted in a narrow way for Teacher attendance draft autosave.

Potential future uses:
- small partial-page updates;
- office list filtering/paging;
- inline status changes;
- Guardian child switching if the UX benefits.

Constraints:
- server-rendered Django remains authoritative;
- every page must retain a functional non-JS fallback where practical;
- do not use HTMX to duplicate domain logic in frontend-only paths;
- no Alpine/React/Vue just because HTMX exists.

### 2. django-filter — evaluate before U5 implementation

**Why:** U5/U6/U7 will contain many office lists and reports with repeated GET-based filtering.

Potential targets:
- Students;
- Guardians;
- Applicants;
- Attendance registers;
- Publications;
- Office reports.

Decision criteria:
- meaningfully reduces repeated filtering/form/query-string code;
- works naturally with the existing authorization-filtered querysets;
- does not hide domain-specific rules.

### 3. django-tables2 — evaluate alongside U5

**Why:** Office-facing screens will need dense, sortable, paginated tabular data.

Potential targets:
- Student/Guardian/Applicant office lists;
- attendance registers;
- publication/history views;
- reports where a desktop table is the correct UI.

Do **not** use it for:
- Teacher phone-first workflows;
- Guardian phone-first cards;
- views where responsive cards/lists are clearer.

### 4. Django-Q2 with PostgreSQL ORM broker — deferred post-project

Tracked separately in GitHub issue #87.

Use only if:
- real automated SMS/email/WhatsApp transport is introduced;
- bulk network sends would otherwise block requests;
- background retries become operationally necessary.

Do not add Redis first by default. Reassess a dedicated broker only if real workload justifies it.

### 5. Object storage adapter / django-storages — production-stage evaluation

Potential future need:
- school logos;
- generated/uploaded documents;
- other durable user files.

Adopt only when Railway/local filesystem durability or scaling makes object storage necessary.

### 6. django-csp / Content Security Policy — production hardening

Evaluate during production security hardening.

Goals:
- explicitly control allowed scripts/styles/assets;
- reduce browser-side injection risk;
- account for current Bootstrap/HTMX delivery strategy before enforcement.

### 7. Existing specialized libraries to keep using

Already appropriate:
- `WeasyPrint` for PDF generation;
- `openpyxl` for spreadsheet/document export workflows;
- `Pillow` for safe image validation/normalization.

## Packages we should not add by default

Avoid these unless a future architecture decision clearly changes:

- `django-simple-history` — existing effective dating, correction history, immutable records and SecurityEvent patterns already cover our audit requirements more deliberately.
- `django-import-export` — imports have project-specific validation, batching, retention and audit behavior.
- `django-axes` — account lockout/security behavior is already implemented deliberately.
- generic object-permission packages such as `django-guardian` — authorization is domain-specific and already explicit.
- Celery + Redis — no current operational need.
- React/Vue/Alpine — do not expand frontend architecture without a concrete requirement.

## Planned review point

Revisit this document **after U4–U7 UI redesign work is complete**.

At that time:
1. Evaluate `django-filter` and `django-tables2` first, because U5/U6/U7 are the most likely places to benefit.
2. Review production hardening needs: object storage and CSP.
3. Revisit GitHub issue #87 for background queues only if automated outbound communication is actually needed.
4. Close or reject any candidate whose benefit is still theoretical.

## Current decision

**No implementation now. Finish the UI redesign first.**
