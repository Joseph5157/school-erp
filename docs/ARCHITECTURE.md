# Architecture

## Engineering principles

FROZEN:
- Prefer simple architecture.
- Prefer relational data.
- Prefer explicit schema.
- Prefer migrations.
- Prefer conventional authentication.
- Prefer clear APIs.
- Prefer straightforward testing.
- Prefer predictable deployment.
- Prefer minimal infrastructure.

Avoid premature:
- microservices
- Kubernetes
- message brokers
- distributed architectures
- multiple databases
- unnecessary caches/services

FROZEN: Railway is the intended deployment target. Avoid unnecessary Railway-specific lock-in.

FROZEN: Low maintenance is a major requirement.

## Authorization principle

FROZEN: Authorization must be designed from the beginning.

At minimum, future role modeling should be able to support:
- School/System Administrator
- Teacher
- Staff
- Parent/Guardian
- Student

Phase 1 does not need fully complete functionality for every role, but the system must never assume unrestricted access for all authenticated accounts.

## Application architecture

FROZEN: The initial School ERP will be implemented as a modular monolith.

The application should remain a single deployable system with clear internal domain/module boundaries.

Modules may communicate through explicit application interfaces, but should not be split into independently deployed services without a demonstrated operational need.

Background workers or scheduled jobs may be introduced when genuinely required, but they do not imply a microservice architecture.

## Data architecture

FROZEN: The ERP uses a relational domain model with explicit relationships, constraints, and migrations.

Historical school records must be preserved through appropriate relational modeling rather than overwriting previous academic state.

Database schema changes must be performed through versioned migrations.

Production database changes must not rely on manual schema edits.

Do not choose a database product yet; the approved technology stack is still awaiting explicit recording.

## Implementation readiness

FROZEN: Application scaffolding, dependency installation, and implementation must not begin until:

1. The approved technology stack is recorded.
2. Phase 1 requirements are reviewed.
3. The baseline documentation commit exists.
4. ECC installation occurs after that baseline commit.

Keep the existing `Approved Technology Stack — TODO` section unchanged in meaning.

## Maintenance and operability

FROZEN: The system must remain understandable and maintainable even after long periods without active development.

This means:
- clear domain boundaries
- explicit database model
- straightforward workflows
- explicit status transitions and historical records
- minimal operational complexity

## Source-of-truth hierarchy

FROZEN: The project decision hierarchy is:
1. Accepted ADR
2. Approved requirements/domain documentation
3. Current architecture documentation
4. Implementation and automated tests
5. ECC-generated plans
6. AI suggestions
7. Old exploratory conversations

FROZEN: AI suggestions must never silently override accepted project decisions.

## Approved Technology Stack

FROZEN: The initial School ERP technology stack is:

- Language: Python 3.13.x
- Web framework: Django 5.2 LTS
- Application architecture: Modular monolith
- Database: PostgreSQL 18
- ORM: Django ORM
- Database migrations: Django migrations
- Frontend rendering: Django Templates
- UI framework: Bootstrap 5.3 with small project-specific CSS
- JavaScript: Vanilla JavaScript initially
- Authentication: Django authentication
- User model: Custom User model from the beginning of the project
- Authorization: Django Groups/Permissions plus explicit domain-level authorization checks
- Testing: Django test framework initially
- Linting and formatting: Ruff
- Python environment: `venv`
- Dependency management: `pip` with pinned dependencies
- PostgreSQL driver: psycopg 3
- Production application server: Gunicorn
- Static file serving: WhiteNoise
- Deployment platform: Railway
- Production database: Railway PostgreSQL
- Source control: Git
- Remote repository hosting: GitHub

Explicitly not part of the initial stack:

- React
- Next.js
- Vue
- Angular
- separate SPA frontend
- separate frontend API architecture
- Django REST Framework
- Redis
- Celery
- WebSockets
- microservices
- Kubernetes
- Node/npm frontend build pipeline

These may only be introduced later when a demonstrated project requirement justifies them.

### Stack change rule

FROZEN: The approved stack must not be changed merely because another framework or library is newer, more fashionable, or suggested by an AI agent.

A significant stack change requires an Architecture Decision Record that documents:

1. The concrete problem with the current stack.
2. Why the problem cannot reasonably be solved within the current architecture.
3. The proposed alternative.
4. Migration and maintenance costs.
5. Expected benefits.
6. Risks and rollback implications.

### Frontend principle

FROZEN: The School ERP is server-rendered by default using Django Templates.

Use JavaScript only where it provides clear user value.

Do not gradually turn the application into a single-page application without an explicit architecture decision.

Mobbin, 21st.dev, and similar resources may be used for UI/UX inspiration.

Their underlying React or other framework code does not determine this project's technology stack.

Design references should be adapted into the project's Django Templates, Bootstrap components, custom CSS, and minimal JavaScript.

### Dependency principle

FROZEN: Do not introduce Redis, Celery, Django REST Framework, WebSockets, additional databases, or other infrastructure merely because a library, ECC skill, or AI suggestion recommends them.

Each additional infrastructure component requires a demonstrated application requirement.

### Authentication principle

FROZEN: Create a custom Django User model before the first production migration.

Do not use Student, Teacher, Guardian, or other school domain entities directly as the authentication identity.

Authentication identity and school-domain roles/profiles should remain conceptually separate.

## Architecture decisions and future ADRs

The project should eventually record important project decisions as Architecture Decision Records (ADRs).

Suggested future ADR subjects include:
- applicant and student separation
- academic enrollment history
- guardian as first-class entity
- modular monolith architecture
- technology stack
- authorization approach

Do not create all of these ADR files now. The ADR process should be used when a decision is important enough to merit formal tracking.

## Security posture

FROZEN: Authorization, validation, and role boundaries are foundational design concerns, not afterthoughts.

The system should favor explicit access controls and domain-appropriate visibility over broad implicit permissions.

## Deployment and infrastructure

CURRENT:
- Keep the deployment model simple and predictable.
- Favor a straightforward relational application setup.
- Keep the infrastructure modest and maintainable.

OPEN:
- The exact runtime stack remains pending the approved technology selection.

## Architecture summary

The target architecture is intentionally conservative: a maintainable relational system with explicit schema, migration-based evolution, conventional auth, and a low-complexity operational footprint.
