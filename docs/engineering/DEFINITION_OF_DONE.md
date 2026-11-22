# Definition of done

"Done" is not one state. Report the **exact state** a change has reached, using the names
below. Each state includes everything in the states before it. The process behind these
states is in [IMPLEMENTATION_WORKFLOW.md](IMPLEMENTATION_WORKFLOW.md); higher risk tiers add
gates (section 3 there).

| State | Short test |
| --- | --- |
| 1. Implemented locally | The task works in its worktree and its targeted checks pass. |
| 2. PR verified | Reviewed, findings settled, marked Ready, full CI green on the final head, acceptance results reported. |
| 3. Merged | The product owner approved that exact head, and it was squash-merged. |
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

- PR open with the template filled in, including base and head SHA. It was a draft while the
  work and the review were in progress.
- Independent review done. Each finding checked and given a verdict; chosen fixes pushed.
- Marked **Ready for review** once implementation and fixes were final. Ready only starts
  full CI; it is not merge approval.
- **CI:** the full suite is green on the final Ready head: the latest run for that head is
  titled `CI (full)` and succeeded (`gh run list --workflow CI --commit <sha>`). A
  draft-safety run does not count. A push
  after that undoes this state until the full suite passes on the new head. A docs-only PR has
  no CI run (`paths-ignore`), and the PR says so.
- **JavaScript browser tests:** when the path-aware `js` job applies to the PR (from ENG-JS-01
  JS1 onward), it passed on the exact approved head. A `js` job whose test step was skipped
  because no relevant path changed is not required.
- Acceptance results (tests, browser checks, review verdicts) are reported to the product
  owner, including what was **not** tested or checked.

## 3. Merged

- **User acceptance:** the product owner explicitly approved merging this exact PR head, after
  the full CI and acceptance results were reported.
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
