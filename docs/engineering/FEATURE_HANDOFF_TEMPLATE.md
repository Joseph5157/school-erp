# Feature handoff template

Copy this into the message or file that hands one task to an implementation agent. Fill in
every section; write "None" with a reason rather than deleting one. Keep it to what this
task needs and link to the spec for the rest. Process: [IMPLEMENTATION_WORKFLOW.md](IMPLEMENTATION_WORKFLOW.md).

````markdown
# <Task ID>: <short name>

## Goal

<One or two sentences: what is true when this task is finished.>

- **Risk tier:** <Low / Medium / High / Critical>

## User roles

<Who uses or is affected: administrator, custom office role, class teacher, subject teacher,
guardian, operator.>

## Baseline

- **Repository:** Joseph5157/school-erp
- **Required baseline:** `origin/main` must contain `<sha>`
- **Worktree:** `../school-erp-<name>`
- **Branch:** `<type>/<name>`

## Source specification

- <path> §<sections>
- ADRs: <numbers>

## Approved decisions

| ID | Decision |
| --- | --- |
| <OD-x1> | <what the product owner chose> |

## In scope

- <item>

## Explicitly out of scope

- <item>

## Affected workflows

- <screen or command, and what changes for the user>

## Permissions

- <who may do what; the server-side check; route inventory entries>

## Schema and migration impact

- <None: `makemigrations --check --dry-run` must stay clean>
- <or: the migration this task includes, whether it is reversible, any data migration>

## Privacy and security risks

- <personal data touched, what must never be stored, logged or sent; threat model link for Critical>

## Test plan

- <test module and the cases: allowed, refused, edge dates, history kept>
- Local: targeted tests + `ruff check .`. CI runs the full suite on the final head.

## Browser acceptance

- <pages to check at 360–390px and desktop; what the product owner should see>

## Rollout and rollback

- **Rollout:** <env vars, cron, management commands, data backfill; or "merge only">
- **Rollback:** <revert the squash commit; migration reversal; data to restore>

## Stop conditions

Stop and report, without guessing, if:

- the code, this handoff, the spec and an ADR disagree;
- a case is not covered and needs a product decision;
- the work needs a migration, dependency, setting or CI change not listed above;
- the work would touch out-of-scope areas or files this task did not create;
- tests fail for reasons outside the task.

## Final report format

1. Base SHA and final head SHA
2. PR number (draft) and branch
3. Changed files, each with one line on why
4. Tests and checks run, with results; anything not run and why
5. Browser checks done, with widths
6. Reviewer findings with verdicts and what was fixed
7. CI status on the final head
8. Migrations: none, or which
9. Open questions and follow-ups
10. Confirmation that the original checkout and unrelated files were not touched, and the PR
    was not merged
````
