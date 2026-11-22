<!--
Fill in every section. Write "None" or "N/A" with a reason rather than deleting a section.
The checkboxes are a record for the reviewer and the product owner; they do not enforce
anything. See docs/engineering/IMPLEMENTATION_WORKFLOW.md and DEFINITION_OF_DONE.md.
Docs-only PRs: fill in Problem, Base and head, Scope, Changed files, Review, CI and
Workspace; mark the rest N/A.
-->

## Problem and specification

- **Problem:**
- **Specification:** <!-- path and section, e.g. docs/competitive-research/OPTION_B_IMPLEMENTATION_SPEC.md §4 -->
- **ADRs / decisions relied on:**
- **Risk tier:** <!-- Low / Medium / High / Critical (IMPLEMENTATION_WORKFLOW.md §3) -->

## Base and head

- **Base:** `main` at `<sha>`
- **Head:** `<sha>` <!-- update after every push -->
- [ ] The required baseline commit is an ancestor of the base.

## Scope

**In scope:**

-

**Explicitly excluded:**

-

## Changed files

| File | Why |
| --- | --- |
| | |

- [ ] Only files needed for this scope changed. No unrelated formatting or refactors.

## Permissions, security and privacy

- **Who can reach the changed behaviour:**
- **Server-side checks added or relied on:**
- [ ] Every new or changed route is in `core/tests/route_permissions.json` with its guard.
- [ ] No personal data, marks, notes, tokens or file contents are logged, measured or sent outside.
- [ ] No fees or payment code, or a threat model and accepted ADR are linked above.
- [ ] Impact: none / described here:

## Migrations

- [ ] No migration. `makemigrations --check --dry-run` reports no changes.
- [ ] Migration included and the specification includes it: <!-- names, reversible?, data migration? -->

## Local verification (targeted)

| Command | Result |
| --- | --- |
| `ruff check .` | |
| `python manage.py test ...` | |

- [ ] The full suite was **not** run locally, or the reason it was run is given here:

## Visual and browser checks

- [ ] N/A: no user-facing change.
- [ ] Checked at 360–390px and at desktop width. No horizontal scroll at 360px. Screenshots or notes:

## Independent review

| # | Finding | Verdict (confirmed / plausible / rejected) | Action |
| --- | --- | --- | --- |
| 1 | | | |

- [ ] Each finding was checked against the code, not accepted on trust.

## CI on the final head

- [ ] Kept as a draft while work and review were in progress (draft CI runs safety tests only).
- [ ] Marked Ready for review once implementation and fixes were final. Ready starts the full
      suite; it is not merge approval.
- [ ] Full suite passed on the head SHA above, after the last push: the latest run is titled
      `CI (full)` and succeeded (`gh run list --workflow CI --commit <sha>`).
- [ ] N/A: docs-only PR (`docs/**`, `*.md`), which CI skips.

## Deployment and rollback

- **Deploy notes:** <!-- env vars, cron changes, management commands, data backfills -->
- **Rollback:** <!-- revert the squash commit? migration reversible? data to restore? -->
- **Staging check after merge:**

## Workspace and merge

- [ ] Built in a fresh worktree. The original checkout and its untracked files were not touched.
- [ ] The product owner explicitly approved merging this exact head, after full CI and
      acceptance results were reported.
- [ ] Merge with `gh pr merge <N> --squash --match-head-commit <head-sha>`.
- [ ] After the merge is confirmed: remove only this task's worktree and branches.
