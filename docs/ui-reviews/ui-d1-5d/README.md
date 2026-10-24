# UI-D1-5D — Term publication: synthetic screenshot and accessibility evidence

**Local synthetic evidence only.** Captured with Playwright (Chromium) against a throwaway **SQLite** database seeded with invented data and driven through the real `plan_publication()` / `confirm_publication()` / `withdraw()` services, so every state below is genuine data, not a mock-up. It is not PostgreSQL, staging or production, and the database was deleted afterwards. The automated tests ran on PostgreSQL (see the PR).

Seed (Academic Year "2026-27", Term 1):

- **Grade 6 - A:** Student One (published v1, unchanged), Student Two (published, then a result was **corrected**, so v1 is **Stale**), Student Four with a deliberately very long name (published v1), Late Joiner (no results, no remark: nothing to publish), Student Three (results added after the first publication: **Will publish**).
- **Grade 6 - B:** Student Six (published v1, corrected, republished: v1 **Superseded**, v2 **Published**) and Student Seven (published, then **Withdrawn** with a reason).
- **Grade 6 - C:** two Students with a draft assessment still pending: **Incomplete**.

Widths: 360, 390, 768, 992, 1024, 1280, 1440 (full-page PNG). `measurements.json` holds 142 probes.

| File prefix | URL | What it shows |
| --- | --- | --- |
| `preview-first-*` | `/terms/1/publication/` | Header, Section picker only, no preview |
| `preview-A-*` | `?section=1` | The state matrix: **Skipped** (Nothing to publish; Already published, version 1), **Will publish**, **Will republish** "(replaces version 1, Stale — needs review)"; summary "2 of 5 Student(s) selected"; every proposed entry and remark visible; confirm button "Confirm and publish 2 report card(s)" |
| `preview-B-*` | `?section=2` | A Student with a Withdrawn version shown as **Will publish**; the republished Student **Skipped** (already published, version 2) |
| `preview-C-incomplete-*`, `preview-C-included-*` | `?section=3`, `…&include=8` | **Incomplete** with the pending assessments and the include checkbox (unchecked, then checked); the button is disabled with "nothing to confirm", then "publish 1 report card(s)" with the hidden `include` |
| `confirm-changed-token-*` | confirm with a tampered token | The existing "Results changed since the preview…" message; nothing is written |
| `stale-list-*` | `/publications/stale/` | Table with the **Stale** badge, reason and a Review link; the sidebar badge shows 1 waiting |
| `detail-published-*`, `detail-current-v2-*` | `/publications/{2,6}/` | Published versions: entries as released, remark, Withdraw / Review and republish with consequence text, all versions |
| `detail-stale-*` | `/publications/3/` | **Stale** badge, "Source results or remark have changed since release", "Guardians do not see this report card…" |
| `detail-superseded-*` | `/publications/5/` | **Superseded** (neutral) as history, no actions, the immutable original values, "(this version)" in the version table |
| `detail-withdrawn-*` | `/publications/4/` | **Withdrawn** with its reason, no actions |
| `withdraw-*`, `withdraw-invalid-*` | `/publications/2/withdraw/` | Consequence text and reason field; blank reason shows the error summary with a link that focuses `#id_reason` |
| `viewer-*` | `demo_view` (`view_termpublication` only) | Preview, stale list and detail with **no** include checkbox, confirm form, Withdraw or Review and republish; `viewer-withdraw-403`, `noperm-preview-403` and `teacher-preview-403` show the unchanged 403 outcomes |

## Measurements

| Check | Result |
| --- | --- |
| Document horizontal overflow | **0px** at 360, 390, 768, 992, 1024, 1280, 1440 in every state and for every user |
| 200% zoom equivalent (390 → 195px) | **43px**: the pre-existing shared top-bar account menu limit already disclosed in earlier D1 gates |
| H1 count / `aria-describedby` | exactly 1 on every page; 0 dangling |
| Tables on phones | local labelled, focusable regions: stale list 422px, detail entries 369 / 346px, versions 264 to 290px at 390px; 0px from 1280px |
| Keyboard | the versions region scrolls with ArrowRight (0 → 15px); focus ring 3px; page overflow 0px |
| Preview rows | 5, 2 and 2 records for Sections A, B and C, in plan order |
| Confirm button | label and disabled state match the selection (2 / 1 / 0 report cards) |

## Known limits

- SQLite, synthetic data; no staging or production verification; no manual screen-reader pass.
- No automatic focus to the first invalid field (`RevocationForm` is out of scope); the error summary links to the field.
- The preview summary shows only `plan.selected|length` of `plan.rows|length`; a breakdown by action needs a new data contract (recorded follow-up).
- The confirmation is a single POST with an explanatory note, exactly as before; no separate confirmation page was added.
- Wide tables scroll locally on phones; 43px top-bar overflow at 195 CSS px is pre-existing.
