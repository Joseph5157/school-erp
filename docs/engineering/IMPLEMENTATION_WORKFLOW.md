# Implementation workflow

How a change goes from an idea to a closed-out release in this repository. It applies to
people and AI agents alike. [AGENTS.md](../../AGENTS.md) holds the short rules; this document
explains them. Accepted ADRs and approved requirements still outrank anything here
([ARCHITECTURE.md](../ARCHITECTURE.md), source-of-truth hierarchy).

## 1. Stages

```text
Research → Specification → Decisions → Plan → Tasks → Isolated implementation →
Targeted verification → Independent review → Final CI → Acceptance →
Guarded merge → Staging release → Closeout
```

Each stage has an output. A stage is not finished until its output exists and, where the
table says so, the product owner has accepted it.

| Section | Stage | Output | Who signs off |
| --- | --- | --- | --- |
| 4 | Research | Findings with evidence (file and line, screenshots, audit IDs) | Planning assistant |
| 5 | Specification | Approved spec under `docs/` | Product owner |
| 6 | Decisions | Numbered decisions in the spec; ADR when the decision is architectural | Product owner |
| 7 | Plan and tasks | Ordered PRs, each with tasks, tests and a done check | Product owner (scope), planning assistant (shape) |
| 8 | Isolated implementation | Commits on a task branch in its own worktree | Implementation agent |
| 9 | Targeted verification | Test, lint and browser results for the changed area | Implementation agent |
| 10 | Independent review | Findings with verdicts | Independent reviewer, then implementation agent |
| 11 | Ready, final CI and acceptance | PR marked Ready; full CI green on the final head; acceptance results reported; owner's merge approval | Implementation agent, CI, product owner |
| 12 | Guarded merge and cleanup | Squash commit on `main`; task worktree and branches removed | Release operator |
| 13 | Staging release | Deployed and checked on staging | Release operator, product owner |
| 14 | Closeout | Docs, spec status and follow-ups updated | Implementation agent |

Small, low-risk changes may compress sections 4–7 into a short handoff
([FEATURE_HANDOFF_TEMPLATE.md](FEATURE_HANDOFF_TEMPLATE.md)). Sections 8–12 are never skipped.

## 2. Roles

| Role | Responsibilities | Must not |
| --- | --- | --- |
| **Product owner** | Owns scope and product decisions. Approves specs, decisions and each merge. Accepts the result in the browser. | Be assumed: silence is not approval. |
| **Planning/review assistant** | Researches, drafts specs and plans, lists decisions as options with a recommendation, reviews reports. | Make product decisions or approve its own spec. |
| **Implementation agent** | Builds one approved task in an isolated worktree, verifies it, opens a draft PR, reports honestly. | Widen scope, change frozen decisions, merge without approval, touch work it did not create. |
| **Independent reviewer** | Reviews the PR diff against the spec and the rules, without the implementer's context. Reports findings with evidence. | Edit the branch. Its findings are claims to verify, not instructions. |
| **CI** | Runs `ruff check .`, `manage.py check`, the migration check and the full test suite on PostgreSQL (`.github/workflows/ci.yml`). | Be treated as optional. A red or missing run on the final head blocks merge. |
| **Release operator** | Runs the guarded merge, deploys to staging, checks it, cleans up, and runs any rollback. | Merge a head other than the reviewed one. |

One person or agent may hold more than one role, except that the independent reviewer must
not be the implementer reviewing its own work in the same context. Today the product owner
is also the release operator, or tells the implementation agent to act as one for a
specific merge.

## 3. Risk tiers

Pick the tier from the most sensitive thing the change touches. When unsure, go one higher.

| Tier | Examples | Extra gates (on top of the lower tiers) |
| --- | --- | --- |
| **Low** | Docs, copy, layout, CSS that changes no behaviour | Spec can be the handoff note. Review of the diff. Browser check for any visible change. |
| **Medium** | Reports, lists, filters, normal admin and teacher workflows, management commands | Written spec or plan. Targeted tests for the new behaviour. Independent review. Full CI on the final head. Staging check. |
| **High** | Attendance, marks and results, publication, guardian access and anything guardians can see, roles and permissions | Approved spec that names the ADRs it relies on. Tests for each permission boundary (allowed, refused, and the edge dates). Route inventory updated. Review focused on authorization and history rules. Owner acceptance on staging before closeout. Rollback written down before merge. |
| **Critical** | Fees and payments, authentication and sessions, password and account recovery, data isolation between schools or roles | Written threat model and accepted ADR **before** code. Security-focused review in addition to the normal one. Migration and data-recovery plan. Staged rollout with a tested rollback. Product owner signs off each stage explicitly. |

Today the product serves one school per installation ([PRODUCT.md](../PRODUCT.md)). Data
isolation still matters inside a school: between roles, between a teacher's assignments and
everything else, and between one guardian's children and another's.

## 4. Research

- Gather evidence from the code (file and line), the docs, audits under `docs/audits/` and
  `docs/competitive-research/`, and screenshots.
- Separate facts from opinions. Mark anything you could not verify.
- Do not start building during research.

## 5. Specification

- Implementation specs live under `docs/` (for example
  `docs/competitive-research/OPTION_B_IMPLEMENTATION_SPEC.md`, `docs/PHASE_*_PLAN.md`,
  `docs/superpowers/specs/`).
- A spec states: status and revision, baseline commit, scope, explicit out-of-scope list, the
  rules it must keep (with their ADR or code source), product-owner decisions, affected files,
  test plan, acceptance criteria and risks. The Option B spec is a good model.
- A spec is approved only when the product owner says so. Record later changes as numbered
  revisions at the top, with the PR that caused them.

## 6. Decisions

- Every open product question becomes a numbered decision (for example `OD-B1`) with options
  and a recommendation. The product owner picks.
- A decision that changes architecture, the data model, authorization or a frozen rule needs an
  ADR ([docs/adr/README.md](../adr/README.md)). Add it to the ADR index.

## 7. Plan and tasks

- Split the spec into PRs that can each be reviewed and merged alone, in dependency order.
  One PR per system boundary where possible (for example: model and migration, then views,
  then UI).
- Each task names its files, its tests and how to tell it is done.
- Work one PR at a time unless the product owner asks otherwise.

## 8. Isolated implementation

1. Fetch and confirm the baseline:
   `git fetch origin && git merge-base --is-ancestor <baseline-sha> origin/main`.
2. Create a fresh worktree and branch from the latest `origin/main`:
   `git worktree add --no-track -b <type>/<name> ../school-erp-<name> origin/main`.
   `--no-track` stops the new branch from tracking `main`, so a bare `git push` cannot reach
   `main`. Push with `git push -u origin <type>/<name>`.
3. Work only in that worktree. Never edit, stage, stash, reset or clean the original checkout,
   and never touch untracked files you did not create.
4. Keep commits focused. Do not reformat or refactor code outside the task.
5. No migration unless the spec includes it. No new dependency, setting or CI change unless
   the task is about it.

## 9. Targeted verification

- Run the tests for the changed area and the areas it touches, plus `ruff check .` and, when
  models change, `python manage.py makemigrations --check --dry-run`. Commands are in
  [README.md](README.md#commands).
- After `static/css/erp.css` edits, run the CSS text guard tests (`--pattern="test_ui*.py"`).
- After adding or changing routes, run `core.tests.test_security_gate4b_route_inventory`.
- Do not run the full suite locally by default; CI runs it once a code PR is Ready for review
  (section 11). Run it locally only when the product owner asks. This replaces the "full local suite" step in older phase
  plans.
- For visible changes, check in a browser at 360–390px and at desktop width. Run
  `collectstatic` and restart the server first so you are not looking at stale CSS.
- Report results as they are, including failures and anything skipped.

## 10. Independent review

- Open the PR as a **draft** with the template filled in. While it is a draft, CI runs the
  quick draft-safety mode (section 11), not the full suite.
- Ask an independent reviewer (a separate agent or person without the implementer's context)
  to check the diff against the spec, the ADRs, permissions, privacy and the tests.
- Verify every finding against the code yourself. Give each one a verdict: confirmed,
  plausible or rejected (with the reason). Record them in the PR.
- Batch the fixes the product owner chooses and push once, then update the head SHA in the PR.

## 11. Ready, final CI and acceptance

### CI modes

`.github/workflows/ci.yml` picks its test mode from the event. The `lint` and `test` checks
keep the same names in both modes; the run title and the job summary say which mode ran.

| Event | Mode | What runs |
| --- | --- | --- |
| PR opened, reopened, pushed to or converted back while it is a **draft** | Draft safety | `ruff check .`, `manage.py check`, the migration check, and a fixed safety-test set (route-permission inventory, permission, privacy, session and deployment guards; about 250 tests) |
| PR marked **Ready for review** (`ready_for_review`) | Full | Lint, system check, migration check and the complete PostgreSQL suite |
| Any push to a PR that is **Ready** | Full | The same complete run again on the new head |
| Push to `main` (every merge, including docs-only) | Full | The same complete run |
| PR that changes only `docs/**` or `*.md` | None | Skipped by `paths-ignore`; the review is the gate |

Anything that is not a draft PR runs the full mode. The safety-test list is in `ci.yml`
(`DRAFT_SAFETY_TESTS`), and `core/tests/test_ci_policy.py` guards these rules. A green
draft-safety run never verifies a PR.

To see which mode ran on a head, read the run title (`CI (full)` or `CI (draft safety)`):
`gh run list --workflow CI --commit <sha> --json displayTitle,event,status,conclusion`.
`gh pr checks <N>` shows only pass or fail for `lint` and `test`, not the mode.

`main` has no branch protection or required checks today. Both modes report checks named
`lint` and `test`, so if `test` were made a required check, a green draft-safety run on the
same head could satisfy it (for example after Ready, before the full run finishes, or after
a PR is moved back to draft). Decide on a full-only gate before adding required checks.

**JavaScript browser tests (`js` job, ADR 0028). Applies once ENG-JS-01 JS1 adds the job; until
then there is no `js` job and nothing here applies.** The job runs in
parallel with `lint` and `test`, drafts included. It is path-aware: its install and test steps run
only when the PR changes a relevant path (JavaScript, vendored scripts, CSS, templates,
`core/forms.py`, browser tests, requirements or CI files). The full list is in `ci.yml` and in
spec `docs/engineering/JAVASCRIPT_TESTING_IMPLEMENTATION_SPEC.md` §9. Pushes to `main` always run
them.

- **The rule.** When the job applies, a PR is verified only when the `js` job passed on the exact
  approved head (the final head presented for approval). A `js` job whose test step was skipped
  because no relevant path changed is not required.
- **Telling whether it applied.** A skipped job still reports `js` as passed, so read the run's
  steps. Take the run id of the head's `CI (full)` run from
  `gh run list --workflow CI --commit <sha> --json databaseId,displayTitle`, then run
  `gh run view <run-id> --json jobs`. The test step shows `success` when the job applied and
  `skipped` when it did not.

### Gates

These are separate steps. Passing one does not grant the next.

1. **Draft.** Implementation and independent review are still in progress. CI runs draft
   safety.
2. **Ready for review.** Implementation and the chosen review fixes are complete, and the head
   is ready for final verification. Mark it with `gh pr ready <N>`, which starts the full suite.
   Ready is **not** merge approval.
3. **PR verified.** The full suite passed on the **final Ready head**, and acceptance results
   (tests, browser checks, review verdicts) are reported to the product owner. Check that
   the latest run for that head is titled `CI (full)` and succeeded (`gh run list --workflow
   CI --commit <sha>`). A run on an older commit, or a draft-safety run, does not count. Any new push undoes this
   state until the full suite passes again on the new head. When the path-aware `js` job applies
   to the PR, it must also have passed on that same head (see above). A skipped `js` job is not
   required.
4. **Merge approved.** The product owner explicitly authorizes merging that exact PR head.
   Approval for one PR, or for an earlier head, does not carry over.
5. **Guarded merge.** Exact-head squash merge (section 12).

## 12. Guarded merge and cleanup

The PR is already Ready and verified (section 11). After the product owner approves, merge
only the exact head that was verified:

```bash
gh pr merge <N> --squash --match-head-commit <head-sha>
```

`--match-head-commit` makes GitHub refuse the merge if anyone pushed after the check.

After a squash merge, the task branch is not an ancestor of `main`, so `git branch -d` refuses
it. Clean up carefully instead:

1. Confirm the merge: `gh pr view <N> --json state,headRefOid,mergeCommit` shows `MERGED` and
   `headRefOid` equals the SHA you merged.
2. Remove the worktree only if nothing in it would be lost. Run
   `git -C <worktree> status --porcelain --ignored`. `git worktree remove` deletes **ignored**
   files too (`.env`, a local database, `venv/`, screenshots), and plain `--porcelain` does not
   list them. If anything other than generated files you made for this task appears, or the
   worktree is locked, stop and report it. Otherwise run `git worktree remove <worktree>`,
   without `--force`.
3. Delete the local branch only if its tip is the merged head:
   `git rev-parse <branch>` equals `headRefOid`, then `git branch -D <branch>`.
4. Delete the remote branch only if it still exists and its tip is the merged head:
   `[ "$(git ls-remote origin refs/heads/<branch> | cut -f1)" = "<head-sha>" ] && git push origin --delete <branch>`.
   If GitHub already deleted it, there is nothing to do.
5. Never clean up by pattern, never touch another task's worktree or branch, and never run
   `git clean`, `git reset --hard` or `git stash` in the original checkout.

## 13. Staging release

- Staging on Railway deploys `main` automatically after each merge, and its pre-deploy step
  runs `migrate`. A merged migration therefore reaches the staging database straight away.
  There is no production environment yet.
- Check the deploy finished, then check the changed workflow on staging at phone and desktop
  widths. Operations notes: [OPERATIONS.md](../OPERATIONS.md).
- If staging shows a problem, roll back by reverting the squash commit in a new PR (and
  reversing any migration as the PR's rollback note describes). Do not hot-fix on the server.

## 14. Closeout

- Update the spec's status or revision, the README or docs the change affects, and the ADR
  index if an ADR was added.
- List follow-ups and deferred items where the next person will find them.
- Confirm cleanup from section 12 is complete.

## 15. Stop conditions

Stop, report and wait for the product owner when:

- the code, the spec and an ADR disagree;
- the spec does not cover a case you must decide;
- the work would need a migration, dependency, setting or CI change the spec does not include;
- the work would touch excluded scope or files you did not create;
- the baseline commit is missing from `origin/main`;
- tests fail for reasons outside the task;
- the task turns out to be a higher risk tier than planned.
