# Definition of done

"Done" is not one state. Report the **exact state** a change has reached, using the names
below. Each state includes everything in the states before it. The process behind these
states is in [IMPLEMENTATION_WORKFLOW.md](IMPLEMENTATION_WORKFLOW.md); higher risk tiers add
gates (section 3 there).

| State | Short test |
| --- | --- |
| 1. Implemented locally | The task works in its worktree and its targeted checks pass. |
| 2. PR verified | Draft PR reviewed, findings settled, CI green on the final head. |
| 3. Merged | The product owner approved, and the exact head was squash-merged. |
| 4. Released to staging | Deployed to staging and checked there. |
| 5. Production-ready | Safe to run for a real school. |
| 6. Closed out | Docs, follow-ups and cleanup finished. |

## 1. Implemented locally

- **Code:** only the approved scope changed, in a fresh worktree from the current
  `origin/main`. No unrelated refactors or formatting. No frozen decision changed.
- **Tests:** new behaviour has tests, including refusals and edge cases. Targeted tests for the
  changed and neighbouring areas pass. `ruff check .` passes.
- **Permissions:** every new or changed path checks access on the server. New routes are in
  `core/tests/route_permissions.json` and the route inventory test passes.
- **Privacy:** no personal data, marks, notes, tokens or file contents in logs, crash reports,
  measurement or outside requests.
- **Migrations:** none, or only those the spec includes. `makemigrations --check --dry-run`
  reports no changes.
- **Browser:** visible changes checked at 360–390px and desktop width.

## 2. PR verified

- Draft PR open with the template filled in, including base and head SHA.
- Independent review done. Each finding checked and given a verdict; chosen fixes pushed.
- **CI:** green on the final head commit (`gh pr checks <N>`). A docs-only PR has no CI run
  (`paths-ignore`), and the PR says so.
- The report states what was **not** tested or checked.

## 3. Merged

- **User acceptance:** the product owner approved this PR for merge explicitly; only then was
  the draft marked ready.
- Merged with `gh pr merge <N> --squash --match-head-commit <head-sha>`.
- `main` contains the squash commit; the PR shows `MERGED`.

## 4. Released to staging

- Staging deployment of that `main` commit finished. Migrations, if any, applied.
- The changed workflow checked on staging by the release operator, and by the product owner
  for High and Critical tiers.
- **Rollback:** the rollback written in the PR is still valid now that the change is live.

## 5. Production-ready

There is no production environment yet. Before the first real school, and for each change
after that:

- **Rollout:** deploy steps, environment variables and cron changes written down and tried on
  staging.
- **Rollback:** tested for Critical changes; written and believable for the rest. Data the
  change writes can be kept or restored.
- **Permissions and privacy:** reviewed against [PERMISSIONS.md](../PERMISSIONS.md) and the
  relevant ADRs; any school approval the ADR needs (for example ADR 0027) is recorded.
- **Operations:** crash reporting and backups cover the change ([OPERATIONS.md](../OPERATIONS.md)).
- Critical tier: threat model and security review closed with no open high findings.

## 6. Closed out

- **Documentation:** spec status or revision updated; README, ADR index and operations docs
  updated where the change affects them.
- Follow-ups and deferred items recorded where the next person will find them.
- **Cleanup:** the task's worktree, local branch and remote branch removed by the safe
  squash-merge steps (IMPLEMENTATION_WORKFLOW.md section 12). Nothing else touched.
