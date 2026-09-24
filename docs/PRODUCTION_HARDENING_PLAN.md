# Production Hardening Research Plan

Status: RESEARCH BASELINE — execute after functional phases are stable, while applying critical security practices continuously.

## Goal

Prepare the School ERP for low-maintenance Railway deployment where data integrity, recoverability and predictable operations matter more than architectural novelty.

## Principles

- Keep one Django codebase unless scale proves a split is necessary.
- PostgreSQL is the production database.
- Secrets and environment-specific configuration stay outside source control.
- Every production mutation must preserve domain invariants and authorization.
- Backups are not trusted until restore is tested.
- Deployment success is not the same as ongoing monitoring.

## Gate A — Production settings and security

- DEBUG=False
- production SECRET_KEY from environment
- correct ALLOWED_HOSTS / CSRF trusted origins
- HTTPS/proxy/security-cookie configuration
- secure password-reset/account flows
- static-file strategy
- production WSGI/ASGI server, never runserver
- run Django check --deploy against production settings
- dependency/version review
- admin endpoint and privileged-account review
- object-level authorization regression suite for Student/Guardian/Teacher boundaries

## Gate B — PostgreSQL and migration safety

- Railway PostgreSQL configuration through environment variables
- production-like PostgreSQL test before first deployment
- migration review for locks/destructive operations
- explicit pre-deploy migration procedure
- no SQLite-specific assumptions
- indexes for common roster/report/search queries
- query-count checks for obvious N+1 paths
- transaction boundaries for multi-write workflows

## Gate C — Deployment reliability

- Gunicorn or approved production server
- Railway health endpoint and deployment healthcheck
- health endpoint checks app readiness without exposing sensitive data
- predictable startup command
- migrations separated from ordinary web startup where appropriate
- failed deploy must not replace healthy version
- smoke tests after deployment
- documented rollback procedure

Railway healthchecks protect deployment activation, but they are not continuous monitoring; separate monitoring is required.

## Gate D — Backup and disaster recovery

Use layered protection:
- Railway scheduled volume backups
- point-in-time recovery where plan/cost permits
- portable logical pg_dump backups
- off-platform/off-project copy policy for critical dumps
- documented restore procedure
- scheduled restore drill

Acceptance is a successful restore into a disposable environment followed by integrity/smoke checks. A backup that has never been restored is not considered verified.

## Gate E — Observability and failure handling

- structured application logs
- request/error correlation where useful
- error monitoring/alerting
- uptime monitoring separate from deployment healthcheck
- database/storage monitoring
- failed communication/payment-like integration attempts visible to admins
- no secrets/credentials/student-sensitive data in logs
- retention policy

## Gate F — Performance and capacity

- baseline representative school size before optimization
- measure Student list/profile, attendance roster, fee ledger, result sheet, portal dashboard
- indexes based on measured queries
- pagination for large lists
- select_related/prefetch_related review
- caching only for demonstrated hotspots and never as source of truth
- file/static/media storage capacity plan
- load test critical read paths and representative writes

## Gate G — Data integrity audit

Before production:
- direct ORM/database regression tests for critical constraints
- duplicate/conflict tests
- historical-record delete protection
- effective-date overlap checks
- correction/reversal audit integrity
- financial allocation invariants
- portal object-level authorization
- cross-domain acceptance journey from Applicant through later operational records

## Gate H — Operations runbook

Document:
- deploy
- rollback
- migration
- backup
- restore
- create/disable administrator
- rotate secrets
- investigate errors
- database access
- emergency read-only/maintenance procedure
- dependency update procedure
- yearly rollover procedure
- small-update checklist for returning to the project after a long gap

## Gate I — Final production acceptance

- full automated suite
- Ruff
- Django system checks
- check --deploy
- production-like PostgreSQL run
- backup + restore drill
- security/authorization journey
- deployment smoke test
- representative performance checks
- documentation reviewed by a human
- known risks explicitly recorded

## Deferred until demonstrated need

Do not add Redis, Celery, background workers, Kubernetes, microservices, complex caching or high availability merely because deployment platforms support them. Add asynchronous infrastructure when Phase 7 delivery volume or another measured workflow actually requires it.

## Research sources

- Current Django deployment checklist.
- Railway Django deployment guide.
- Railway healthcheck documentation.
- Railway PostgreSQL and backup/restore documentation.
