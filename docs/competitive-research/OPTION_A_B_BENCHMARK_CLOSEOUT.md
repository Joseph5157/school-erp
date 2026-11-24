# Option A/B Benchmark Closeout

- **Status:** Closeout report (documentation only). It approves no feature, schema or roadmap change.
- **Baseline audit:** `CURRENT_STATE_BENCHMARK_AUDIT.md`, the approved planning baseline at `2edeee6` (21 November 2026). It is kept unchanged as the historical record. Status and priority changes are recorded here, not in the baseline.
- **Checked against:** `main` at `b772d5f` (23 November 2026).
- **Specifications closed:** `OPTION_A_IMPLEMENTATION_SPEC.md` (A1–A3) and `OPTION_B_IMPLEMENTATION_SPEC.md` (B1–B3, revision 5).

The method matches the baseline: each status change cites code and tests on `main`. Tests were not run for this report. CI on `main` (green on `b772d5f`) is the authority for pass/fail. No browser or device check was made.

## 1. What Options A and B completed

| Item | PR (merge) | What `main` now does | Evidence | Tests |
| --- | --- | --- | --- | --- |
| A1 | #277 (`4e343b2`) | Every NOT_TAKEN row in Missing attendance says who is responsible (today's class teacher, or the office for past days) and offers the next step the viewer may take: Take register (pre-filled), Open register or Review class teacher. Configuration problems (no class teacher, teacher can't sign in, overlapping years, archived section) are shown as such. | `core/attendance_actions.py`; `core/templates/core/report_missing_attendance.html:44-67` | `test_missing_attendance_actions` |
| A2 | #278 (`6082af7`) | One definition of "absent N school days in a row" (ADR 0026, accepted). The admin gets an "Absent in a row" report, and class teachers get a card on My Day scoped to their own section and assignment dates. | `core/attendance_insights.py`; `core/views.py:1326,5043`; `core/templates/core/my_home.html:38-43`; route `attendance/reports/absent-in-a-row/` | `test_absence_runs`, `test_absence_runs_views` |
| Admin home | #279 (`7260bce`) | Overview became four tabs (Today, Attendance, Academics, Parents). Today's register rows use A1's `resolve_missing`. The Parents tab shows portal engagement in aggregate, and lists sections with students who have no portal parent, linked to a "No parent on the portal" student filter. | `core/home_today.py`, `core/home_academics.py`, `core/home_parents.py:60-98`; `core/views.py:4255` | `test_home_today`, `test_home_attendance`, `test_home_academics`, `test_home_parents`, `test_admin_home_option_a`, `test_ui_admin_home_tabs` |
| A3 | #280 (`a78734c`) | "Results to finish" opens exactly the assessments it counts (`status=DRAFT&due=1&progress=marking`), from one shared query. The Attendance tab links to the Absent in a row report. | `core/assessment_progress.py`; `core/home_academics.py:149-157`; `templates/partials/home/_attendance.html:91` | `test_assessment_progress`, `test_home_academics` |
| B1 | #282 (`19b0b36`) | Each marks row saves itself on change, with Saving, Saved or Not saved and Retry. Conflicting saves from another tab or device are refused with 409 and show the newer value. Background requests from a signed-out session get 401 instead of the sign-in page. Who may enter, finalize, correct or publish is unchanged. | `core/urls.py:250-252` (`assessment-marks-autosave`); `static/js/erp.js` | `test_marks_autosave`; browser tests `bt_marks_autosave` |
| B2 | #283 (`3069665`) | ADR 0027 (accepted). An aggregate-only `UsageCounter` store holds daily counts with no person, record or value, kept 180 days with a daily purge. It is **off by default** (`USAGE_MEASUREMENT_ENABLED=False`, `config/settings.py:129-130`) and honours Global Privacy Control. | `core/usage.py`, `core/usage_views.py` (beacon `/u/`) | `test_usage_measurement`; browser tests `bt_usage` |
| B3 | #284 (`afcec72`) | Named admin, teacher and guardian workflows count starts, completions, save attempts and failures, with bucketed durations. `usage_report` prints weekly aggregates and hides small numbers after every filter and grouping. Spec §9 defines the review triggers for offline, push, login convenience, native apps and admin phone coverage. | `core/usage_evidence.py`; `core/usage.py` | `test_usage_workflows`; browser tests `bt_usage` |

The engineering work that followed (ENG-WORKFLOW-01 #285, ENG-CI-01 #286, ENG-JS-01 #287–#292) changed no product behaviour except one fix: JS3 (#291) stopped an older attendance autosave reply from replacing a newer change (F-JS1, issue #289). ENG-JS-01 added browser tests for the B1 and attendance autosave paths and for the B2/B3 privacy limits.

## 2. Updated benchmark counts

### 2.1 Status changes

| ID | Capability | Baseline | Now | Reason |
| --- | --- | --- | --- | --- |
| ADM-06 | Exception-led attendance administration | Partial | Implemented | A1: every NOT_TAKEN row is actionable or names its configuration problem. Late *registers* (submitted after the school's register cut-off) are now flagged on the admin home Today tab (`core/home_today.py`). A late or conflicting attendance *status* for a student still cannot exist under ADR 0007; that is a governed boundary, not a gap. |
| ANA-01 | Attendance not submitted | Partial | Implemented | A1, and the admin home Today tab uses the same rows. |
| ANA-03 | Incomplete assessment or marks | Partial | Implemented | A3: the admin count opens the matching list. |
| TEA-04 | Consecutive-absence insight | Partial | Implemented | A2: consecutive runs over instructional days, with an admin report and a class-teacher card. Recording a follow-up action was outside Option A's scope (spec §1), and subject teachers are excluded by decision OD-5. A follow-up workflow would need its own decision. |
| ANA-02 | Consecutive or repeated absence | Partial | Implemented | Same root as TEA-04. |
| TEA-07 | Mobile repetitive-task quality | Partial | Implemented | B1 gives marks the attendance save model. B3 can measure task time and failures. No operational measurement data was available to this closeout; deployment enablement was not inspected (see §3.2). |
| ANA-05 | Guardian account inactive | Missing | Partial | The Parents tab shows how many parents signed in this month, and which sections have students with no portal parent. There is still no per-account list of guardians who never signed in. |

**ACA-03** (fast repetitive grade entry) stays **Partial**: autosave and conflict detection are done, but there is no bulk fill. Its priority moves from P1 to Research, because spec §9.6 makes further speed work depend on marks-entry evidence.

**ADM-08 and MOB-01** (admin mobile coverage) stay **Partial, P1**. The new admin home works on phones, and B3 can count admin phone views by route (spec §9.5). There is still no page-by-page inventory, and measurement is off.

**TEA-05** (assessment completeness) stays **Partial, P2**. A3 gave the admin a drill-down, which closes the ANA-03 half. The other half of the baseline gap is untouched: teachers still have no list of their unfinalized or unpublished work.

All other candidate IDs are unchanged.

### 2.2 Status counts

| Status | Baseline | Now | Change |
| --- | --- | --- | --- |
| Implemented | 10 | 16 | +6 |
| Partial | 21 | 16 | −5 |
| Missing | 15 | 14 | −1 |
| Divergent | 1 | 1 | 0 |
| Deferred | 21 | 21 | 0 |
| UI-only, Backend-only, Not applicable, Unknown | 0 | 0 | 0 |
| **Total** | **68** | **68** | |

### 2.3 Priority counts

| Priority | Baseline | Now | Change |
| --- | --- | --- | --- |
| P0 | 0 | 0 | 0 |
| P1 | 9 | 3 | −6 (ADM-06, TEA-04, TEA-07, ANA-01, ANA-02 to P3; ACA-03 to Research) |
| P2 | 14 | 13 | −1 (ANA-03 to P3) |
| P3 | 14 | 20 | +6 (16 of them "preserve" for Implemented rows) |
| Research | 18 | 19 | +1 (ACA-03) |
| Deferred | 13 | 13 | 0 |
| **Total** | **68** | **68** | |

The three remaining P1 candidate rows are ADM-08 and MOB-01 under G-04, and GUA-01 under G-06. That is why there are three P1 rows but only two open P1 gap groups.

### 2.4 Gap register

| Gap | Baseline | Now | Note |
| --- | --- | --- | --- |
| G-02 Exception lists stop short of the action | P1 | **Closed** | A1, A3. A teacher-side list of unfinalized work (TEA-05) remains, at P2. |
| G-03 Absence insight count-based, admin-only | P1 | **Closed** | A2, ADR 0026 |
| G-05 Marks entry lacks the attendance save model | P1 | **Closed** | B1. Bulk fill waits for §9.6 evidence. |
| G-04 Admin phone coverage not inventoried | P1 | **Open, P1** | Measurement exists but is off. No inventory yet. |
| G-06 Guardian activation, recovery and engagement invisible | P1 | **Open, P1 (narrowed)** | Aggregate engagement is now visible. Recovery is still office-only, and there is no list of guardians who never signed in. |
| G-01 No parent-to-school channel | Research | Unchanged | No decision |
| G-07 to G-13 | P2 / Research / P3 | Unchanged | G-13 still applies: `docs/ROADMAP.md:122` still says PDF report cards are excluded, and the demo refresh still posts "Fee Payment Reminder" (`core/demo_refresh.py:295`). |

Three of the five P1 gaps are closed. No P0 defect was found.

## 3. What remains missing or partial

### 3.1 Still missing or partial (unchanged since the baseline)

- **Parent-to-school channel (G-01):** no requests, leave, grievances, service requests or request status (GUA-04 to GUA-08, COM-01 to COM-03, COM-07, ANA-07).
- **Guardian recovery (GUA-01):** office reset only (`core/urls.py:412-414`). There is no self-service reset route.
- **Guardian engagement detail (ANA-05, ANA-06):** aggregate only. There is no per-account inactivity list and no read tracking.
- **Updates inbox (GUA-03, MOB-05):** portal notices only. Absence and report-card alerts are not kept in the portal.
- **Exports (ADM-05):** the import-issues CSV is still the only in-app CSV export. The operator-only `usage_report --format csv` command is not an export for school users.
- **Student 360 (ADM-02):** still no portal access, consent or issued documents on the profile.
- **Global search (ADM-01, ADM-03):** per-list search only.
- **Guardian-layout preview (ACA-07):** still an office table.
- **Teacher list of unfinished work (TEA-05):** teachers see open drafts on My Day, but no list of unfinalized or unpublished work.
- **Result statuses (ACA-04):** still divergent from the candidate. ADR 0009 governs.
- **Documentation drift and demo fee text (G-13):** see §2.4.

### 3.2 Built but not yet producing evidence

B2 and B3 are complete, but measurement is off by default. Under OD-B9 it may be switched on for a deployment only after documented school approval, and this report did not check whether any deployment has it on. Until it runs:

- none of the spec §9 review triggers (offline write, push, login convenience, native apps, admin phone coverage) can fire or be ruled out;
- the research questions on phone task use, save failures and marks-entry time (baseline §13) remain open, even though the instruments now exist.

Two baseline research questions are answered by approved decisions:

- who acts on a NOT_TAKEN register (Option A OD-1);
- how consecutive absence counts school days and corrections (ADR 0026).

### 3.3 Governed and still deferred

These are unchanged and are not gaps:

- year rollover (ADM-07);
- rubrics, lesson plans and homework (ACA-05, ACA-09, TEA-06);
- push, offline, background sync and native apps (MOB-06 to MOB-10);
- fees (FIN-G0 to G6, GUA-10, ANA-09; issue #274).

## 4. High-priority gaps still open

| Rank | Gap | Why it stays high | Blocking decision or input |
| --- | --- | --- | --- |
| 1 | **G-04 Admin phone coverage** (ADM-08, MOB-01) | Admins are expected to work fully on phones. Apart from the new home, admin pages are converted one by one and nothing proves coverage. | None to start a static inventory. Measurement (spec §9.5) would rank the conversion work once approved. |
| 2 | **G-06 Guardian activation and recovery** (GUA-01, ANA-05) | Every forgotten guardian password is still an office task, and the office cannot see which families never activated. | Identity rules for self-service reset. There is no email or SMS channel (Phase 7 plan), so recovery needs a channel decision first. |
| 3 | **Turning the evidence pipeline on** (operational, not a gap ID) | Mobile decisions (MOB-04, MOB-06 to MOB-10) and ACA-03 speed work are evidence-gated. No operational measurement data was available to this closeout; deployment enablement was not inspected. | Documented school approval under OD-B9, then the variable set per deployment. |

G-01 remains the largest benchmark gap by count. It is still a research item with no product decision, so it is not ranked as build work.

## 5. Recommended next product package

**Package C: Admin phone coverage (G-04).**

- **Outcome:** an inventory of every admin route at phone width, with each classified as works, usable or broken. Then one PR at a time converts the broken pages that matter most.
- **Why this package:**
  - It is the only open P1 gap that needs no new policy, identity or schema decision.
  - It reuses the existing phone patterns (`.erp-keep`, phone cards, offcanvas menu) and the route inventory in `core/tests/route_permissions.json`.
  - It matches the product's mobile-first direction.
- **Shape:**
  1. **Docs-only inventory and spec.** Every admin route from the route inventory, checked at 360 px and 390 px, with the task it serves and its status. Phone UI tests already cover some routes; the spec says which.
  2. **Conversion PRs**, ordered by inventory severity. Once measurement is on, order them by phone views (spec §9.5).
- **In parallel (operational, no code):** obtain documented school approval to switch measurement on for the pilot deployment, so the §9 triggers and the conversion order can rest on evidence.
- **Out of scope:** new permissions, schema changes, offline or PWA changes, and fees.
- **Why not G-06 first:** it is equally P1 but needs a recovery-channel and identity decision before any spec. A short research step on G-06 can run alongside Package C without code.

## 6. Status update (24 November 2026)

Sections 1–5 are kept as written on 23 November. This section records what changed since, checked
against `main` at `0240bc2` plus this PR. It approves no feature, schema or roadmap change.

### 6.1 Gap register changes

| Gap | §2.4 said | Now | Evidence |
| --- | --- | --- | --- |
| G-04 Admin phone coverage | Open, P1 | **Closed** | `PACKAGE_C_CLOSEOUT.md` §6 (inventory of 144 routes; every High and Medium finding fixed; optional C8 Low polish left). |
| G-06 Guardian activation and recovery | Open, P1 (narrowed) | **Open, narrowed to self-service recovery** | Never-signed-in list (#303, `G06_NEVER_SIGNED_IN_SPEC.md`) answers ANA-05. Office reset improved under ADR 0029 option A (#306–#310, `G06_OFFICE_RESET_SPEC.md`): identity method recorded, contact changes audited, named reset staff, temporary passwords expire (switched on in staging 24 November). Self-service recovery for guardians stays deferred by ADR 0029. On 24 November the product owner kept guardians on office reset. |
| G-13 Documentation drift and demo fee text | P3, unchanged | **Closed by this PR** | `docs/ROADMAP.md` now says Term report card PDFs came in Phase 7; the demo refresh notice pool has no fee text, pinned by `test_demo_refresh.test_pool_titles_unique_and_no_fee_text`. |

Four of the five baseline P1 gaps are closed (G-02, G-03, G-04, G-05). G-06 stays open only for
guardian self-service recovery, which ADR 0029 defers. Whether to close it on that decision is a
product owner choice.

Benchmark rows (the baseline audit stays unchanged):

| ID | Capability | Before | Now | Reason |
| --- | --- | --- | --- | --- |
| ANA-05 | Guardian account inactive | Missing (P2) | **Implemented** | Office list of guardians who never signed in or still use a temporary password, with an Expired mark and a Reset password link for reset staff. |
| GUA-01 | Activation and recovery | Partial (P1) | **Partial (improved)** | Office reset with identity method, audit and expiry; no self-service recovery (ADR 0029). |

### 6.2 Known follow-ups (not gaps)

- G-06 staging acceptance items still open in `G06_OFFICE_RESET_SPEC.md` §11 (contact edit, reset
  staff added, one reset on staging; PR 3 backup note), waiting on the product owner.
- Temporary-password expiry is not switched on in production (no production environment yet).
- **Staff password recovery by email** (teachers and school administrators; not superusers, not
  guardians) is a product owner requirement before the first real school. It needs an email
  provider decision, an ADR 0013 amendment for staff and a threat model before any code.

### 6.3 Recommended next

1. **Staff email recovery (decision step).** It is the only item with a stated deadline (before
   the first real school). Shape: provider comparison, ADR (provider and ADR 0013 staff
   amendment), threat model, then a spec. Critical tier.
2. **G-01 research (parent-to-school channel).** Still the largest gap by count and still without
   a product decision. Shape: school front-office interviews and a call-log sample (baseline
   research question), then an options paper. No code.
3. **Turning the evidence pipeline on** (§4 rank 3) remains open and operational.
