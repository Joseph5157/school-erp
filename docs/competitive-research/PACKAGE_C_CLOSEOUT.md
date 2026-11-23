# Package C Closeout: Admin Phone Coverage (G-04)

- **Status:** Closeout report (documentation only). It approves no feature, schema or roadmap
  change.
- **Gap:** G-04 Admin phone coverage (ADM-08, MOB-01), ranked first in
  `OPTION_A_B_BENCHMARK_CLOSEOUT.md` §4–5.
- **Specification closed:** `PACKAGE_C_IMPLEMENTATION_SPEC.md` (C0–C7). C8 is optional and not
  started (§4).
- **Source audit:** `PACKAGE_C0_ADMIN_PHONE_AUDIT.md` (findings C0-01 to C0-09, 146 page checks).
  It is kept unchanged as the historical record. Status changes are recorded here.
- **Checked against:** `main` at `226fe23` (23 November 2026).
- **Method:** the existing per-PR evidence (CI, browser measurements, screenshots, Android and
  staging checks, recorded in each PR), plus a staging spot-check of the changed pages (§3).
  The 146-page audit was **not** repeated: the product owner decided that a spot-check of the
  changed pages is enough, because every other page was already rated Works or Usable and no
  shared layout rule changed except the opt-in classes below.

## 1. What Package C delivered

| PR | Merge | Scope | Final head (CI) | Device and staging gates |
| --- | --- | --- | --- | --- |
| C0 #294 | `2a01ad4` | Audit and spec (docs only) | `b988a35` | n/a |
| C1 #295 | `8f29147` | Opt-in stacked phone table (`erp-table--stack`), piloted on Grading scales; Ponytail review pilot | `bde7107` (lint, test, js pass) | Chromium checks |
| C2 #296 | `bba9c24` | Assessments list stacked; three generic stack additions (no 10rem cap, wrap beats `.text-nowrap`, visible "Sort by" strip) | `8197e4b` (lint, test, js pass) | Real Android: Redmi Note 12, Android 14, Chrome (version not supplied), run by the product owner over LAN |
| C3+C4 #297 | `c1f1dd4` | Assessment results, result sheet, term report card, publication detail stacked; Correct link in the row actions | `dcd91a2` (lint, test, js pass) | Real Android PASS (product owner, LAN; device details not supplied); owner staging acceptance PASS |
| C5+C6 #298 | `8107695` | Student record Guardians table, calendar, guardian access reviews, stale publications stacked; 24 × 24 px Edit links (`erp-edit-link`) | `3256906` (lint, test, js pass) | Owner staging acceptance PASS; screenshots in the PR |
| C7 #299 | `226fe23` | Compact phone filters (`erp-toolbar--compact`) on Assessments and Attendance; Teacher assignments grouped by Class/Grade with a jump list | `afa4152` (lint, test, js pass) | Staging check PASS (§3); screenshots in the PR |

`main` CI was green after every merge (`2a01ad4`, `8f29147`, `bba9c24`, `c1f1dd4`, `8107695`,
`226fe23`). Every merge was a squash merge guarded on the exact head that CI tested. No PR changed
a view, form, URL, permission, model or migration; the route inventory and migration checks
passed on each. Each PR had an independent review; the CSS PRs (C1, C5, C7) also had a Ponytail
review-only pass. The C1 Ponytail comparison (spec §5) is recorded in the body of #295.

## 2. Findings: final status

**Fixed** means the High or Medium outcome in the audit is met on `main`. **Remaining** means it
is still open and listed for optional C8. **Deferred** means no work is planned, with the reason.

| Finding | Level | Status | Where and how |
| --- | --- | --- | --- |
| C0-01 Assessment rows can't be told apart | High | **Fixed** | C2: every row shows Section, Date, Term, Max and Pass on phones. C7: the filter form above it is 290 px instead of 466 px. |
| C0-02 Result tables hide marks and Correct | High (result sheet Medium) | **Fixed** | C3+C4: assessment detail (finalized and draft), result sheet, term report card and publication detail show every value; the Correct link sits in each row's actions with a name that includes the assessment and student. Print preview unchanged. |
| C0-03 Row actions off screen | Medium | **Fixed** | C5+C6: Guardians (Change relationship, End), calendar (Edit label, Remove), access reviews (Decision form), stale publications (Review). Hidden table width at 360 px went from 143–465 px to 0. |
| C0-04 Long assignment pages, no jump | Medium (two pages Low) | **Fixed** (Teacher assignments); **Deferred** (Class teachers 3,710 px, Assignment overview 9,899 px) | C7: Teacher assignments grouped by grade with a jump list; 20,553 px → about 3,400 px on the seeded data. Grades holding a "No current teacher" or "Login inactive" card start open. The two Low pages are readable and were not in any PR. |
| C0-05 Filter forms take the first screen | Medium (six pages Low) | **Fixed** (Assessments, Attendance); **Remaining** (six Low pages) | C7: two fields to a row on phones (466 → 290 px; 422 → 246 px). Offerings, Student attendance, Students, Timetable issues, Applicants and Announcements are C8 candidates; the class is opt-in, so they are unchanged. |
| C0-06 Small tap targets | Medium (parts Low) | **Fixed** (pencil links); **Remaining** (radio labels); **Deferred** (in-row text links, Rename/Archive) | C5: admission and roll number Edit links are 24 × 24 px. The radio labels on School create and the student-deactivation access-review step (about 20 px) are C8. In-row text links (21 px) meet the WCAG 2.2 spacing exception; Archive opens a confirmation page. |
| C0-07 Wrapping | Low | **Fixed** (Grading scales); **Remaining** (admin home button) | C1 stacked Grading scales, so the Grade bands column is visible. The three-line "Open Applicants awaiting decision" button is C8. |
| C0-08 Secondary read-only tables cut off | Low | **Remaining** | Teacher detail security events and the Bulk imports list are C8 candidates. |
| C0-09 Student record shortcut strip | Low (to confirm) | **Closed: not a defect** | Confirmed in C5: the strip is a horizontal scroller by design (content 732 px in a 313 px box at 360 px); the cut-off chip shows that it scrolls. |

Result: **no High or Medium finding is open.** What remains is Low (C8) or deferred with a reason.

## 3. Staging spot-check of the changed pages

Staging at `226fe23` (the deployed `main`), signed in by the product owner as an administrator, desktop Chrome
with the window at **414 px**, its narrowest. That is below the 576 px phone breakpoint, so the
phone layouts apply. Each page was measured by script: page overflow (document `scrollWidth`
minus the viewport), hidden width inside each stacked table box, and links or controls past the
right edge. Credentials and data were not changed.

| Page (PR) | Page overflow | Hidden in stacked tables | Off-screen controls | Notes |
| --- | --- | --- | --- | --- |
| Grading scales (C1) | 0 | 0 | 0 | |
| Assessments list (C2, C7) | 0 | 0 | 0 | Filter form 290 px, two fields to a row |
| Assessment detail, finalized (C3) | 0 | 0 | 0 | 10 Correct links, all in the row actions |
| Result sheet (C4) | 0 | 0 | 0 | |
| Term report card (C4) | 0 | 0 × 5 tables | 0 | |
| Publication detail (C4) | 0 | 0 × 2 tables | 0 | |
| Student record (C5) | 0 | 0 | 0 | Guardian actions visible (4 links); both Edit links 24 × 24 px |
| Calendar (C6) | 0 | 0 | 0 | 8 row actions (Edit label, Remove) |
| Guardian access reviews (C6) | 0 | 0 | 0 | Empty on staging; the populated case was checked in #298 |
| Stale publications (C6) | 0 | 0 | 0 | Empty on staging; the populated case was checked in #298 |
| Attendance registers (C7) | 0 | n/a | 0 | Filter form 246 px, two fields to a row |
| Teacher assignments (C7) | 0 | n/a | 0 | 10 grade groups holding 91 cards, 10 jump links, page 3,360 px; the jump to Grade 6 opened that collapsed group |

Not checked on staging:

- **Warning grades starting open:** staging has no warning slots. This was checked in a real
  browser on a throwaway local database (one teacher deactivated: every grade holding a warning
  started open) and is covered by a test.
- **360 px:** the window could not be made narrower than 414 px. The 360 and 390 px measurements
  are in each PR.

## 4. C8: optional follow-up (not started)

C8 is optional Low polish. The product owner decided not to build it now: it would add time
without materially improving a critical workflow. Candidates, from the spec §6 C8 row:

- compact filters (`erp-toolbar--compact`) on the six Low filter pages (C0-05);
- a label tap target of at least 24 px for the radio choices on School create and the
  student-deactivation access-review step (C0-06);
- a shorter label for the admin home "Open Applicants awaiting decision" button (C0-07);
- stacked or trimmed secondary tables on Teacher detail (security events) and Bulk imports (C0-08).

Smaller follow-ups noted in reviews, also optional:

- blank values in a stacked row show a bare label (C3+C4 review; needs a CSS rule);
- the access-review Decision form keeps its 15rem width inside the stacked row, and a viewer
  without the decide permission sees an empty actions strip (C5+C6 review; cosmetic);
- Class teachers and Assignment overview grouping (C0-04, Low; deferred above).

## 5. Known limitations

- **Safari and iPhone: not tested.** No iPhone was available. Unverified there: table semantics
  with `display: block`/`flex` on stacked rows under VoiceOver (C2 review), and whether following a
  jump link opens a collapsed Teacher assignments grade. Chromium and Firefox both open it.
- **Large text and zoom settings: not tested.** Neither the audit nor the PRs checked browser text
  scaling. Stacked rows wrap, so they should grow rather than overflow, but this is not proven. The
  inline-flex 24 px Edit link was not checked at large text sizes.
- **Real Android:** checked for C2 and C3+C4 as the spec requires (§7 item 12); C5–C7 were checked
  in emulated Chromium and on staging only. The Chrome version was not recorded.
- **Landscape:** not tested.
- **Evidence pipeline:** usage measurement is still off by default (OD-B9), so the spec §9.5
  ordering by phone views was not available, and phone task use after Package C is not measured.

## 6. G-04 status

**G-04 Admin phone coverage: Closed.** The gap was "not inventoried": there was no proof that
admin tasks work at phone width. Package C produced the inventory (144 routes at 360, 390 and
1366 px) and fixed every High and Medium finding in it, with CI, browser and staging evidence per
PR. The Low leftovers are listed as optional C8 and do not keep the gap open.

Benchmark rows (the baseline audit stays unchanged; this records the change):

| ID | Capability | Before | Now | Reason |
| --- | --- | --- | --- | --- |
| ADM-08 | Admin mobile task coverage | Partial (P1) | **Implemented** | Inventory done; all High and Medium phone findings fixed (§2). Remaining: optional C8 Low polish; the limitations in §5. |
| MOB-01 | Admin desktop and mobile parity | Partial (P1) | **Implemented** | Same root as ADM-08. |

With G-04 closed, four of the five P1 gaps from the baseline are closed (G-02, G-03, G-04, G-05).
G-06 is the only open P1 gap.

## 7. Recommended next priority

**G-06 Guardian activation and recovery (GUA-01, ANA-05).** It is the last open P1 gap: every
forgotten guardian password is still an office task, and the office cannot see which families
never activated their portal account.

It is not ready to build. As `OPTION_A_B_BENCHMARK_CLOSEOUT.md` §4 notes, it first needs:

1. **a recovery-channel decision.** There is no email or SMS channel today (Phase 7 plan), so
   self-service reset needs a channel or an office-assisted alternative;
2. **identity rules for self-service reset** (what proves a guardian is who they say, and what
   happens for shared phones and siblings);
3. **the privacy and security review** that guardian access changes require (High tier).

Suggested shape: a short docs-only G-06 research and decision step (options, risks, the decisions
the product owner must make), then a spec. One part needs no channel decision and could be
specified first: an office view of guardian accounts that have **never signed in**, built on the
existing guardian and session data. It addresses ANA-05 and makes activation follow-up possible
while recovery is decided.

In parallel (operational, no code): documented school approval to switch usage measurement on
for the pilot deployment (OD-B9), so later mobile decisions can rest on evidence.
