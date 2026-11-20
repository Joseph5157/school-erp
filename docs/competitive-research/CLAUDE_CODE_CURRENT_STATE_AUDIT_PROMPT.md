# Claude Code Prompt for Current-State ERP Benchmark Audit

Copy the prompt below into Claude Code after pulling the audit branch.

---

You are acting as a senior Django product, architecture, security, authorization, and UX auditor.

## Objective

Audit the current `Joseph5157/school-erp` codebase against:

`docs/competitive-research/ERP_BENCHMARK_ADOPTION_AND_CODEBASE_AUDIT_PLAN.md`

The plan consolidates selected patterns from PowerSchool, Toddle, and Edunext. These patterns are audit candidates, not approved requirements.

The purpose of this task is to determine what the present project actually implements before the product owner decides the next move.

## Non-negotiable scope

- This is an evidence-gathering and comparison task.
- Do not implement or fix any feature.
- Do not modify application code, templates, static assets, tests, migrations, dependencies, configuration, CI, fixtures, or deployment files.
- Do not create or change database records.
- Do not deploy anything.
- Do not commit, push, merge, create a PR, edit issues, or change branches after recording the initial baseline.
- Do not start Phase 3 Fees or add fee placeholders.
- Do not reinterpret competitor behaviour as an approved requirement.
- Preserve existing uncommitted user work. Never reset, checkout, clean, stash, or overwrite it.

You may create or replace only these audit outputs:

1. `docs/competitive-research/CURRENT_STATE_BENCHMARK_AUDIT.md`
2. `docs/competitive-research/CURRENT_STATE_EVIDENCE_INDEX.md`

If either output already exists, read it first and preserve any clearly identified user-authored decisions. Do not modify any other file.

## Step 1 — Establish the baseline

Run read-only checks and report:

- `git status --short`
- current branch
- full HEAD SHA
- configured remote URL
- whether local HEAD matches the intended pulled audit branch
- Python and Django versions from the repository environment or declared dependencies
- PostgreSQL assumptions and test configuration

If the working tree contains unrelated changes, continue read-only and list them. Do not touch them.

Read every applicable `AGENTS.md` or repository instruction before proceeding.

## Step 2 — Read the governing project material

At minimum, read:

- `docs/competitive-research/ERP_BENCHMARK_ADOPTION_AND_CODEBASE_AUDIT_PLAN.md`
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
- all ADRs that govern a candidate capability

Also read GitHub issue #274 if network access is available. If it is unavailable, use the FIN-G0–G6 summary in the audit plan and clearly state the limitation.

Treat repository plans as intended behaviour, not proof of implementation.

## Step 3 — Inspect the implementation

Use `rg` and targeted file reads. Inspect, as relevant:

- Django apps, models, migrations, constraints, and PostgreSQL triggers;
- domain services and model methods;
- centralized authorization and permission checks;
- forms, views, URLs, templates, and static resources;
- Teacher and Guardian shells;
- Admin desktop and responsive/mobile behaviour;
- communication outbox, consent, idempotency, and send-time rechecks;
- PWA manifest, icons, service-worker registration, offline storage, background sync, and push code;
- reports, exports, dashboards, and operational exception queries;
- tests, fixtures, and management commands.

Inspect enough call sites to distinguish a reusable domain capability from a one-page special case.

Do not claim authorization is correct because a link is hidden. Verify server-side enforcement.

Do not claim a feature exists because it appears in documentation, navigation, a model name, a template label, or an unused function.

## Step 4 — Evaluate every candidate ID

Evaluate every ADM, ACA, TEA, GUA, COM, MOB, ANA, and FIN candidate in the audit plan.

Use exactly one status:

- Implemented
- Partial
- UI-only
- Backend-only
- Missing
- Divergent
- Deferred
- Not applicable
- Unknown

For each row provide:

- candidate ID and name;
- current status;
- concise current behaviour;
- exact evidence using repository-relative `path:line` references;
- relevant test path and test name, or “no confirming test found”;
- roles and authorization boundary;
- desktop/mobile exposure where relevant;
- risk or user impact;
- dependencies;
- priority: P0, P1, P2, P3, Research, or Deferred;
- recommendation: preserve, improve, research, defer, reject, or resolve conflict.

When evidence is incomplete, use Unknown and state the exact missing evidence. Do not guess.

## Step 5 — Trace the critical journeys

Trace these end to end from URL to authorization, domain operation, persistence, rendering, and tests:

### Administrator

1. Find a student and inspect the permitted record.
2. Complete a representative bulk or repeated task.
3. Review missing attendance or another operational exception.
4. Perform representative work at a phone viewport based on templates and CSS.

### Teacher

1. Sign-in landing and Today home.
2. Take and submit attendance.
3. Enter or review assessment results.
4. View a permitted student.
5. Complete the same common tasks under mobile layout constraints.

### Guardian

1. Account activation or forced password change.
2. Select a child.
3. View attendance.
4. View published assessment or report-card information.
5. View an announcement or document.
6. Determine whether two-way communication, structured requests, leave, and request status exist.

### Communication

1. Consent recording.
2. Notification preparation.
3. Authorization and consent recheck immediately before send or mark-sent.
4. Deduplication, correction, dismissal, and history.

### Fees

Search for models, migrations, routes, templates, navigation, reminder types, payment code, balance fields, and placeholders. Confirm whether the Phase 3 boundary remains intact. Do not create or propose a schema.

## Step 6 — Mobile and PWA truth check

Explicitly verify whether the repository contains:

- a web manifest and install metadata;
- any service worker file or registration;
- offline fallback;
- browser-side write queue;
- client-side persistent data storage;
- background synchronization;
- Web Push subscription and delivery;
- device-assisted or passkey login;
- responsive Admin coverage;
- mobile-first Teacher and Guardian navigation;
- safe error behaviour when the network is lost during a save.

Separate installability, responsive design, offline behaviour, notifications, and native-app capability. Do not group them under one “PWA supported” label.

## Step 7 — Analytics truth check

Inventory operational queries, reports, summary cards, charts, and exports. For each, determine:

- source of truth;
- role and permission scope;
- whether the result is actionable;
- whether it links back to source records;
- whether tests protect its meaning;
- whether it is a true insight or only a count/chart.

Pay special attention to missing attendance, consecutive absence, incomplete marks, stale publication, inactive Guardian access, pending communication, and integrity holds.

## Step 8 — Produce the reports

Use `docs/competitive-research/CURRENT_STATE_AUDIT_REPORT_TEMPLATE.md` as the minimum structure.

Write:

### `CURRENT_STATE_BENCHMARK_AUDIT.md`

- baseline and limitations;
- executive summary;
- verified strengths;
- product map;
- full capability matrix;
- role/device matrix;
- mobile and PWA findings;
- parent-engagement findings;
- analytics findings;
- Fee boundary verification;
- deduplicated gap register;
- conflicts with current decisions;
- research questions;
- two or three next-move options with dependencies and trade-offs.

### `CURRENT_STATE_EVIDENCE_INDEX.md`

- evidence grouped by candidate ID;
- path and line references;
- relevant tests;
- governing ADRs and plans;
- commands used and their outcomes;
- anything that could not be verified.

## Quality rules

- Lead with current evidence, not competitor marketing.
- Record strengths as carefully as gaps.
- Separate missing implementation from poor discoverability or weak UI.
- Separate a product gap from an intentionally deferred capability.
- Deduplicate findings that share one root cause.
- Do not recommend a native app, offline synchronization, AI, or Fee implementation without the required prior decisions.
- Do not use a numeric product score unless every category, weight, and evidence basis is defined.
- Mark inferences explicitly.
- Do not include secrets, credentials, personal data, or complete environment values in the report.

## Final response

Return:

1. inspected branch and full SHA;
2. working-tree condition before and after;
3. reports created;
4. counts by status and priority;
5. top verified strengths;
6. top verified gaps;
7. conflicts or blockers;
8. recommended decision sequence;
9. confirmation that no application code, schema, migration, dependency, deployment, commit, push, PR, or issue was changed.

Stop after the audit. Wait for explicit product-owner approval before preparing any implementation specification.

---
