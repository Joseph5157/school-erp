# Engineering workflow

How changes are planned, built, reviewed, merged and released. Agent rules in short:
[AGENTS.md](../../AGENTS.md).

- [IMPLEMENTATION_WORKFLOW.md](IMPLEMENTATION_WORKFLOW.md) — stages from research to closeout,
  roles, risk tiers, guarded merge and safe cleanup
- [DEFINITION_OF_DONE.md](DEFINITION_OF_DONE.md) — the six states a change can reach, and what
  each one requires
- [FEATURE_HANDOFF_TEMPLATE.md](FEATURE_HANDOFF_TEMPLATE.md) — template for handing one task to
  an implementation agent
- [Pull request template](../../.github/pull_request_template.md) — what every PR records

## Commands

Run from the repository root with the project `venv` active. Local `manage.py` runs need
`DJANGO_DEBUG=True` (see `.env.example` and [OPERATIONS.md](../OPERATIONS.md)).

| Purpose | Command |
| --- | --- |
| Lint (CI pins `ruff==0.16.7`) | `ruff check .` |
| Django system check | `python manage.py check` |
| No missing migrations | `python manage.py makemigrations --check --dry-run` |
| Targeted tests | `python manage.py test core.tests.test_<area> --parallel 4 --noinput` |
| CSS text guard tests (after `erp.css` edits) | `python manage.py test --pattern="test_ui*.py" --parallel 4 --noinput` |
| Route permission inventory | `python manage.py test core.tests.test_security_gate4b_route_inventory --noinput` |
| PR checks on the current head | `gh pr checks <N>` |
| Mark an approved draft ready | `gh pr ready <N>` |
| Guarded merge (only after approval) | `gh pr merge <N> --squash --match-head-commit <sha>` |

The full suite runs in CI (`.github/workflows/ci.yml`) on PostgreSQL.

Related: [ARCHITECTURE.md](../ARCHITECTURE.md) (frozen decisions and source-of-truth
hierarchy), [adr/README.md](../adr/README.md) (ADRs), [PERMISSIONS.md](../PERMISSIONS.md),
[OPERATIONS.md](../OPERATIONS.md).
