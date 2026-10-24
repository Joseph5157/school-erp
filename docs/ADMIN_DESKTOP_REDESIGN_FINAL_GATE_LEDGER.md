# Admin Desktop redesign — final gate ledger

**Status (2026-10-24):** the Admin Desktop redesign **implementation is complete** (UI-D0 and UI-D1-1 through UI-D1-6). It is **not yet accepted on Railway staging and not approved for production.** No UI-D1 gate has been deployed. Evidence so far is synthetic SQLite screenshots plus local PostgreSQL test runs.

Every gate was presentation-only: templates, scoped CSS, breadcrumb rules and tests. No gate changed views, forms, models, migrations, services, routes, authorization or JavaScript (the D1-4B roster-comment fix and the U4-3A and D1-4C-1 test fixes are the only other changes, recorded below). Each gate was a separate draft PR, independently reviewed, then merged pinned to the reviewed head.

## Gates

| Gate | PR | Merge | Reviewed head | Full PostgreSQL suite | Evidence |
| --- | --- | --- | --- | --- | --- |
| UI-D0 desktop foundation | #92 | `dd6e9da` | `6f2e651` | see PR | `docs/ui-reviews/ui-d0/` |
| D1-1 teacher assignment history | #93 | `45b0088` | `24cfcf9` | see PR | `docs/ui-reviews/ui-d1/` |
| D1-2A school configuration lists | #94 | `19fd57b` | `f4f4306` | see PR | `ui-d1-2a/` |
| D1-2B class teacher mapping | #95 | `e43d477` | `16d5785` | 2,303 | `ui-d1-2b/` |
| D1-3A people lists | #96 | `1fedaae` | `5c8f0a8` | see PR | `ui-d1-3a/` |
| D1-3B applicant and teacher details | #97 | `12c3e10` | `1fe47a1` | see PR | `ui-d1-3b/` |
| D1-3C Guardian detail and access reviews | #98 | `7cbf201` | `bc08a8d` | see PR | `ui-d1-3c/` |
| D1-3D1 Guardian forms | #99 | `de63dd6` | `f6aa143` | see PR | `ui-d1-3d1/` |
| D1-3D2 Guardian account form | #100 | `d60de53` | `1e44537` | see PR | `ui-d1-3d2/` |
| D1-4A attendance register list | #101 | `fbc8520` | `e325f81` | see PR | `ui-d1-4a/` |
| D1-4B register detail and corrections | #102 | `c443cb4` | `a0ae0c6` | see PR | `ui-d1-4b/` |
| Roster-comment micro-fix | #103 | `f8f9e47` | `3af1566` | see PR | n/a |
| U4-3A flaky-test fix (test only) | #104 | `9aa08e4` | `a394300` | see PR | `test-reviews/u4-3a-subject-order-flaky.md` |
| D1-4C plan (docs) | #105 | `64809e5` | `a25e5a9` | n/a | plan |
| D1-4C-1 attendance reports hub, absentees, missing | #106 | `6ef74be` | `c0d073c` | 2,558 | `ui-d1-4c1/` |
| D1-4C-2 monthly summary and Student history | #107 | `aedfd33` | `00c113c` | 2,593 | `ui-d1-4c2/` |
| D1-5 plan (docs) | #108 | `405fd84` | `25af26a` | n/a | plan |
| D1-5A grading scales | #109 | `fe23608` | `76bea51` | 2,619 | `ui-d1-5a/` |
| D1-4C-1 test hardening (test only) | #110 | `cb1a139` | `dd6144f` | 2,620 | n/a |
| D1-5B assessments and corrections | #111 | `7f052ed` | `44e0343` | 2,660 | `ui-d1-5b/` |
| D1-5C result reports | #112 | `5df0b68` | `a8d8e03` | 2,692 | `ui-d1-5c/` |
| D1-5D Term publication | #113 | `b963a8e` | `7616c01` | 2,739 | `ui-d1-5d/` |
| D1-6 plan (docs) | #114 | `4964972` | `9695556` | n/a | plan |
| D1-6A security operations | #115 | `97a2d79` | `aeb83f2` | 2,763 | `ui-d1-6a/` |
| D1-6B announcements | #117 | `ecd2331` | `f2f0161` | 2,793 | `ui-d1-6b/` |
| D1-6C documents | #119 | `f3135f0` | `bde63d4` | 2,826 | `ui-d1-6c/` |
| D1-6D notification queue | #121 | `75d4dba` | `617fadb` | 2,847 | `ui-d1-6d/` |
| D1-6E bulk imports | #123 | `ffaaeed` | `cc22373` | **2,881** | `ui-d1-6e/` |

Documentation closeout PRs: #116 (D1-6A), #118 (D1-6B), #120 (D1-6C), #122 (D1-6D); the D1-6E closeout and this ledger are in the PR that adds this file. Counts marked "see PR" were reported in that PR and are not restated here. All PRs were merged pinned to the reviewed head; none had required status checks configured.

## What the redesign did not change

Authorization, routes, services, models, migrations, exports, delivery behaviour (the ERP never sends messages itself), the PDF engine, the Guardian Portal and the teacher templates. Message text is displayed exactly and autoescaped. Import commit, publication, document issuance and attendance rules are unchanged and re-proved by page-level tests.

## Deferred-work ledger (L1 to L11, from the D1-6 plan section 13)

| # | Item | Blocks production? |
| --- | --- | --- |
| L1 | Publish-only post-withdrawal redirect to a 403 (`publication_withdraw` redirects to Publication detail, which needs `view_termpublication`) | **Yes, mandatory fix** |
| L2 | Sensitive account screens (credential slips; reset, username, revoke, reactivate, deactivate confirmations) need their own security review and gate | Yes, until reviewed |
| L3 | Real confirmation workflows for Discard import, Dismiss message, Withdraw notice, Clear lockout, assessment Delete, grade-band Remove | Yes (launch readiness) |
| L4 | Residual configuration forms and calendar pages | No, but unfinished UI |
| L5 | Automatic focus to the first invalid field (`FieldAccessibilityMixin`) on assessment, grading, correction, revocation, announcement, document and import forms | No |
| L6 | Import detail pagination, search, sorting; a notification-queue filter | Decide at launch |
| L7 | Subject/Section matrix filter form, per-action breakdown of the publication preview, numeric alignment in `_result_cells.html` | No |
| L8 | Manual screen-reader pass and staging verification; every UI-D1 gate is not deployed | **Yes** |
| L9 | Guardian list search/sort/pagination; shared top-bar overflow at 195 CSS px; sidebar keyboard focus styling | No |
| L10 | Announcement Create, Prepare and Withdraw redirect to Announcement detail even without `view_announcement` | **Yes, review before production** |
| L11 | `run_import` / `view_importbatch` mismatch: upload, commit and discard redirect to pages needing `view_importbatch` | **Yes, mandatory workflow review** |

Also recorded for production-hardening review: `notifications.to_send()` can move a PREPARED message to SKIPPED during a GET when consent was withdrawn (D1-6D); opening a report card PDF creates or reuses its audited issued document on first view (D1-6C, existing behaviour); and the attendance-report `view_attendanceentry` versus `view_attendanceregister` reconciliation (D1-4C).

## Deployment status

| Environment | Status |
| --- | --- |
| Local (PostgreSQL tests, synthetic SQLite screenshots) | All gates verified |
| Railway staging | **Not deployed with the redesign; not accepted** |
| Production | **Not approved** |

Next phase (planning only): `docs/STAGING_ACCEPTANCE_AND_PRODUCTION_READINESS_PLAN.md` (separate planning PR).
