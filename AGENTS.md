# Agent instructions

Rules for any AI coding agent working in this repository. They are short on purpose: the
detail lives in the linked documents. Where this file and an accepted decision disagree, the
decision wins (see the source-of-truth hierarchy in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)).

Start with [docs/engineering/README.md](docs/engineering/README.md).

## Project decisions

- The stack, modular monolith and data rules in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
  are **FROZEN**. Do not add a framework, service, database, cache, queue or JavaScript
  build step without an accepted ADR ([docs/adr/README.md](docs/adr/README.md)).
- Work from an **approved specification** (an implementation spec, phase plan or design spec
  under `docs/`) and the ADRs it cites. Do not invent product behaviour.
- **Stop and ask** when the code, the specification and an ADR disagree, when the spec does not
  cover a case you must decide, or when the change would touch something the spec excludes.
  Report what you found; do not pick a side silently.
- The product serves one school per installation ([docs/PRODUCT.md](docs/PRODUCT.md)).
  Multi-school behaviour needs its own ADR.

## Security and privacy

- Enforce permissions **on the server**, in the view or domain code, for every request.
  Hiding a link or button is not access control. Rules: [docs/PERMISSIONS.md](docs/PERMISSIONS.md)
  and the authorization ADRs (0004, 0010, 0012, 0013, 0014, 0018, 0024).
- Every new route goes in `core/tests/route_permissions.json` with its guard.
- Never log, report, measure or send to an outside service: passwords, tokens, student or
  guardian personal data, marks, attendance notes or uploaded file contents. Follow the
  allow-list approach of ADR 0027 and Security Gate 4A.
- Fees, payments and anything that moves money need a written threat model and an accepted
  ADR **before** any code. Fees are deferred (issue #274).
- Records that ADRs protect (enrollments, assignments, guardian links and grants, submitted
  attendance, finalized results; see ADRs 0006, 0011, 0013, 0023, 0024) are ended, revoked or
  corrected with an audit trail, never deleted or rewritten.

## Working safely

- One task, one branch, one **fresh worktree** based on the latest `origin/main`. Before
  starting, confirm the required baseline commit is in `origin/main`.
- Never modify, stage, stash, clean or delete files you did not create for this task. That
  includes the original checkout and its untracked files.
- Database migrations only when the specification says the task includes one. Otherwise,
  `python manage.py makemigrations --check --dry-run` must report no changes.
- Do not change CI, dependencies or settings unless the task is about them.

## Verification

- Locally: run the targeted tests for the changed area and the areas around it, plus
  `ruff check .` ([commands](docs/engineering/README.md#commands)). Do not run the full
  suite locally unless the product owner asks; CI runs it.
- The full CI run must pass on the **final PR head commit** before merge. A new push needs
  a new green run. (CI skips PRs that only change `docs/**` or `*.md`; those need a
  manual review only.)
- Check UI changes in a browser at phone (360–390px) and desktop widths.

## Pull requests and merging

- Open the PR as a **draft** and fill in the PR template. Get an independent review, check
  each finding yourself and report a verdict for each one.
- **Never merge without the product owner's explicit approval** for that PR. Only then mark
  the draft ready.
- Merge only the exact head that was reviewed and tested:
  `gh pr merge <N> --squash --match-head-commit <sha>`.
- Clean up only what this task created, and only after the merge is confirmed. The rules
  for squash merges are in
  [docs/engineering/IMPLEMENTATION_WORKFLOW.md](docs/engineering/IMPLEMENTATION_WORKFLOW.md#12-guarded-merge-and-cleanup).

Done means the states in [docs/engineering/DEFINITION_OF_DONE.md](docs/engineering/DEFINITION_OF_DONE.md),
not "the code runs".
