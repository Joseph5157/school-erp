# School ERP

## Project status

This repository contains the documentation foundation and the in-progress
Phase 1 implementation of the School ERP.

Current status:
- documentation foundation established; business and domain decisions are the source of truth
- approved technology stack recorded in `docs/ARCHITECTURE.md` (Django + PostgreSQL)
- Phase 1 implementation underway:
  - custom User model (accounts)
  - school configuration
  - academic year management
  - class/grade and section management

## Documentation

- [docs/PRODUCT.md](docs/PRODUCT.md) — product vision, users, principles, and module strategy
- [docs/DOMAIN_MODEL.md](docs/DOMAIN_MODEL.md) — domain model, lifecycle, enrollment, and historical-data rules
- [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) — Phase 1 scope, out-of-scope items, and acceptance criteria
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — engineering principles, security, architecture guidance, and source-of-truth hierarchy
- [docs/ROADMAP.md](docs/ROADMAP.md) — directional roadmap across future phases
- [docs/ECC_EVALUATION.md](docs/ECC_EVALUATION.md) — ECC experiment goals and evaluation framework
- [docs/adr/README.md](docs/adr/README.md) — ADR purpose and process

## Important note

The approved technology stack is recorded in `docs/ARCHITECTURE.md`. Remaining
Phase 1 modules must follow the documented domain model, requirements, and
ADRs. Out-of-scope modules must not be started.
