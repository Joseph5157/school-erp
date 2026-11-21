# Current-State ERP Benchmark Audit

**Audit status:** Approved planning baseline
**Repository:** `Joseph5157/school-erp`
**Branch:** `docs/erp-benchmark-codebase-audit`
**HEAD:** `2edeee60d08f097080a02660453b121ee5721b3c` (matches `origin/docs/erp-benchmark-codebase-audit`; `origin/main` `febc57f` is an ancestor)
**Audit date:** 21 November 2026
**Auditor:** Claude Code
**Benchmark plan:** `docs/competitive-research/ERP_BENCHMARK_ADOPTION_AND_CODEBASE_AUDIT_PLAN.md`
**Evidence index:** `docs/competitive-research/CURRENT_STATE_EVIDENCE_INDEX.md`

This report records what the code at the HEAD above does. Competitor patterns are audit candidates only. Nothing here approves a feature, schema, roadmap or UI change.

## 1. Scope and limitations

- **Working-tree condition:** 38 untracked paths before the audit (screenshots, PDFs, patch file, `docs/audits/`, `docs/guardian-retest/`, GTM folders, plan/spec drafts, `phase1-smoke.sqlite3` and others). No tracked file was modified. All were left untouched. The audit added only the two output files.
- **Environment:** Python 3.13.15 locally (`.venv`); `pyproject.toml` targets py313; Django 5.2.17 and psycopg 3.3.5 (`requirements.txt`). PostgreSQL is the approved database (`config/settings.py:90-106`); without `DB_NAME` settings fall back to SQLite for local bootstrap only (`config/settings.py:107-112`). CI runs the suite on PostgreSQL 16 (`.github/workflows/ci.yml:32-42,81`) with `makemigrations --check`. Test runs use a fast hasher (`config/settings.py:229-232`).
- **Repository instructions:** No `AGENTS.md` or `CLAUDE.md` exists in the repository. No implementation was done.
- **Sources unavailable:** None blocking. GitHub issue #274 was read through `gh` (OPEN, "[DEFERRED] Fee Management — Financial Integrity & Threat Model (FIN-G0–G6)").
- **Not inspected:** Unmerged branches. In particular the admin-home redesign collects on `feature/admin-home` (PRs #270–#273) and is **not** in this HEAD; admin home findings describe `main` only. Untracked user documents under `docs/audits/` were not used as evidence.
- **Tests not run, and why:** This is a read-only evidence audit. Test names are cited from source, and CI on PostgreSQL is the authority for pass/fail. No claim in this report depends on a test result observed during the audit.
- **No browser or device check:** Mobile findings come from templates, CSS and UI tests, not real devices. PWA Gate 2 (device acceptance) has not run (`docs/PWA_GATE_1_PLAN.md:4`).
- **Inferences** are marked "(inference)" where they appear.

## 2. Executive summary

### Strongest verified areas

1. **Server-side authorization is centralized and pinned.** Every admin route uses `administrator_required(perm)` (`core/authorization.py:14-26`); teacher routes use assignment-scoped helpers (`core/authorization.py:65-337`); guardian routes use `guardian_required` plus per-grant lookups (`core/authorization.py:360-416`). All 191 routes are listed with their guard in `core/tests/route_permissions.json`, and `test_security_gate4b_route_inventory` fails if any route's guard changes. Data-class permissions (guardians, attendance entries, marks) are checked inside pages, so a filter or search cannot reveal hidden data (`core/views.py:4003-4030`, `docs/PERMISSIONS.md`).
2. **Communication safety is built in, not bolted on.** Messages are prepared only with current consent. A unique idempotency key prevents duplicates (`core/notifications.py:64-100`, `core/models.py:4011`). Consent and portal access are checked again under a row lock both before the WhatsApp link is handed out and when "mark sent" is pressed (`core/notifications.py:207-275`). Notification and consent history is protected by database triggers (`core/migrations/0057_notification_history_guards.py`).
3. **Records keep their history.** Attendance corrections, result corrections, record corrections, immutable issued documents, publication snapshots that go STALE after a correction, and announcement withdrawal with a reason (`core/models.py:1793, 3411, 1200, 4146, 3682`; `core/publication.py:376-428`).
4. **Teacher daily workflow is phone-first.** A Today home shows attendance state, today's periods, marks still to enter and remarks (`core/views.py:1164-1280`). Attendance has "mark all present" that never overrides a choice, per-row autosave with a visible save state and Retry, and an explicit confirm-before-submit (`static/js/erp.js:236-560`; `core/views.py:1506-1620`).
5. **Guardian portal is separate, scoped and phone-first.** It has its own namespace, UUID URLs, a child switcher, a bottom tab bar, submitted attendance, published report cards (with PDF) and notices (`core/portal_urls.py`, `core/portal_views.py`, `templates/portal/`).

### Largest verified gaps

1. **No parent-to-school channel.** No requests, messages, leave, grievance or service requests exist, and no request status or ownership (GUA-04 to GUA-08, COM-01 to COM-03, COM-07, ANA-07). Two-way messaging and parent replies are out of scope by decision (`docs/PHASE_7_COMMUNICATION_DOCUMENTS_IMPORT_PLAN.md:100`); the rest has no decision either way.
2. **Exception lists are only partly actionable.** Missing attendance lists NOT_TAKEN sections without any link to act on them (`core/templates/core/report_missing_attendance.html:42-47`). The admin "Marks entered" ring has no link (`core/analytics.py:369-376`). Absence insight counts days in a period, not consecutive absence, and is admin-only (`core/analytics.py:414-447`).
3. **No guardian activation or engagement signal.** Guardians cannot recover a password themselves (no reset route in `config/urls.py:60-79`), and no page shows guardians who never signed in, inactive accounts or unread notices (ANA-05, ANA-06, GUA-01).
4. **No configurable exports.** The only CSV is the import-issues file (`core/import_views.py:117`); reports cannot be exported (ADM-05).
5. **Admin mobile coverage is broad but unproven page by page.** An offcanvas menu and phone cards exist for many lists, backed by many `test_ui_*phone*` tests, but there is no inventory showing every admin task works at phone width (ADM-08, MOB-01).

### Material divergences or conflicts

1. **ACA-04 result statuses diverge from a frozen decision.** Results are exactly MARKED or ABSENT, and "unrecorded" means there is no row (`core/models.py:3249-3253`; ADR 0009 `docs/adr/0009-phase-4-assessment-and-results-model.md:54-58`). Medical leave, exempted and not applicable would need a new ADR.
2. **Documentation drift on guardian PDFs.** `docs/ROADMAP.md:120` still says PDF report cards are excluded, but Phase 7 approved and the code serves the guardian's own report-card PDF (`docs/PHASE_7_COMMUNICATION_DOCUMENTS_IMPORT_PLAN.md:201`; `core/portal_views.py:166-177`).
3. **Demo data mentions fees.** The daily demo refresh can post a "Fee Payment Reminder" notice (`core/demo_refresh.py:295-297`). It is notice text only, not fee code, but on staging it suggests fee functionality that does not exist.

No P0 safety, authorization or data-integrity defect was verified.

## 3. Current product map

| Area | Current implementation | Primary evidence | Maturity | Important boundary |
| --- | --- | --- | --- | --- |
| Admin | School setup, years, calendar, classes/sections with archive, subjects, timetable, teachers, applicants→students, guardians, guardian accounts and access reviews, attendance registers and reports, assessments, grading, publication, documents, imports, announcements, message queue, sign-in lockouts, overview analytics | `core/urls.py:16-521`, `core/views.py`, `core/dashboard.py`, `core/analytics.py` | Mature (Phases 1, 2, 4–7) | Every route needs a Django permission; data classes need their own permission |
| Teacher | Today home, timetable, subjects, My Students (scoped), attendance capture/submit/history, assessments, gradebook (read-only), marks entry, results, report card view, term remarks | `core/urls.py:203-248`, `core/views.py:1164-2140` | Mature for Phase 5 scope | Access from assignments only; Teachers group has no model permissions |
| Guardian | Home (child cards and latest notices), child overview, attendance by month, report cards and PDF, notices | `core/portal_urls.py:9-32`, `core/portal_views.py`, `core/portal.py` | Read-only, mature | Admin-created accounts; explicit per-student grants; review holds |
| Attendance | Daily Section registers, PRESENT/ABSENT only, DRAFT→SUBMITTED, audited corrections, missing-attendance and absentee reports, monthly summaries | `core/models.py:1344-1836`, `core/reports.py` | Mature | No period attendance, no LATE/EXCUSED (ADR 0007) |
| Assessments | Offerings, terms, assessments with date-effective roster, DRAFT marks, finalize, corrections, grading scales, result sheets, term report cards, remarks, publication snapshots | `core/models.py:1838-3760`, `core/publication.py`, `core/assessment_reports.py` | Mature | MARKED/ABSENT only; no rank, GPA, rubrics (`docs/ROADMAP.md:83-85`) |
| Communication | Consent records, ASSIST-mode WhatsApp queue, absence and report-card alerts, announcements (school/class/section) with portal notices | `core/notifications.py`, `core/notification_producers.py`, `core/announcements.py` | Outbound only | No replies, SMS or email (Phase 7 plan:99-102) |
| Documents | Bonafide, report card, attendance summary PDFs with serials; immutable payload | `core/models.py:4146-4197`, `core/documents/service.py` | Partial | Transfer Certificate not built (Phase 7 plan:86) |
| PWA and mobile | Manifest, icons, install help page, phone install bar; responsive shells with phone tab bars for Teacher and Guardian | `core/pwa_views.py`, `templates/partials/_pwa_head.html`, `static/js/erp.js:952-1010` | Gate 1 done | Online-only: no service worker, offline, sync or push (PWA plan:8) |
| Analytics | Overview attention cards, completion rings, attendance trend/heatmap/class comparison, frequent absentees, students needing attention, marks snapshot, student progress | `core/dashboard.py`, `core/analytics.py`, `core/marks_analytics.py` | Partial: mostly counts; some actionable | Admin only; permission-gated per data class |
| Fees | None | Evidence Index §FIN | Absent (correct) | Phase 3 deferred; issue #274 |

## 4. Capability evidence matrix

Role abbreviations: **A** Administrator, **T** Teacher, **G** Guardian. Devices: **D** desktop, **M** mobile.

### 4.1 Administration and student records

| ID | Capability | Status | Current behaviour | Evidence | Tests | Roles and devices | Risk or impact | Dependency | Priority | Recommendation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ADM-01 | Role-aware global search | Missing | No global search. Each list has its own search (students, guardians, applicants, teachers, announcements, My Students). Student search drops guardian matching without `view_guardian`. | `core/views.py:4003-4030`; `core/templates/core/student_list.html:11`; `core/templates/core/my_students.html:18` | `test_security_gate4b_people_pages::test_absent_filter_needs_view_attendanceentry`; `test_search_filter_audit13` | A per-list search, D+M; T My Students only | Extra navigation to find a person; per-list search is safe | Search must reuse data-class permission checks | P2 | Improve later; preserve the per-list permission filtering |
| ADM-02 | Consolidated Student 360 | Partial | Profile shows status and history, placement, enrolment history, marks progress, monthly attendance, guardians (current and ended), corrections; links to attendance and results pages. It does not show issued documents, guardian portal access, consent or messages. | `core/views.py:4146-4194`; `core/templates/core/student_detail.html:110-223` | `test_student_progress`; `test_security_gate4b_people_pages`; `test_record_corrections::test_history_shows_on_the_record_with_who_why_and_values` | A, D+M ("On this page" menu) | Office checks several screens for access or communication questions | Data-class permissions per section | P2 | Improve |
| ADM-03 | Persistent selected-student context | Missing | No admin "current student" carried across pages. The guardian portal has a child switcher, which is a different thing. | `templates/portal/base.html:25` (guardian only); no admin equivalent found | No confirming test found | — | Low; value unproven | Must not widen access | Research | Research before designing |
| ADM-04 | Safe bulk actions | Partial | Preview→confirm→commit-once exists for imports, term publication (confirm token), announcements (publish once) and teacher-assignment copy; "mark all present" saves in one request. No bulk actions on lists (for example status change for many students). | `core/import_views.py:51-117`; `core/views.py:3415`; `core/announcement_views.py`; `core/views.py:2542-2570`; `core/views.py:1591` | `test_phase7_import::test_a_batch_commits_only_once`; `test_phase6_publication::test_confirming_twice_publishes_nothing_new`, `::test_stale_token_writes_nothing`; `test_announcement_publish_once::test_back_then_publish_again_does_not_send_twice`; `test_phase5_assignment_workflows::test_stale_preview_is_refused`; `test_attendance_bulk_present::test_forged_and_repeated_ids` | A, D+M | Strong safe pattern to reuse; missing list-level bulk work | Rollover (ADM-07) is the main bulk need | P2 | Preserve the pattern; improve where a real bulk task is named |
| ADM-05 | Configurable exports | Missing | Only exports: import-issues CSV and the import template. Reports and lists cannot be exported. PDFs are issued documents, not exports. | `core/import_views.py:117,128` | `test_ui_admin_desktop_d1_6e_bulk_imports` (CSV content type) | — | Office retypes or screenshots data | Export must apply data-class permissions and CSV neutralisation (`test_phase7_import::test_csv_cells_are_neutralised` shows the existing rule) | P2 | Improve, scoped to named reports |
| ADM-06 | Exception-led attendance administration | Partial | Missing-attendance report lists expected section-days that are NOT_TAKEN or DRAFT and skips non-school days; overview card and "Registers today" ring link to it for today; daily absentees and frequent absentees exist. NOT_TAKEN rows have no action link. "Late" or "conflicting" cannot exist with PRESENT/ABSENT only. | `core/reports.py:204-246`; `core/dashboard.py:39-56`; `core/analytics.py:319-345`; `core/templates/core/report_missing_attendance.html:42-47` | `test_ui_admin_desktop_d1_4c1_attendance_reports::test_draft_and_not_taken_are_distinct_and_never_absent`; `test_admin_overview_analytics::test_no_register_yet_is_expected_but_not_submitted` | A (`view_attendanceregister`), D+M | Office sees the gap but must navigate to act on it | Who should act on a NOT_TAKEN row (office capture vs teacher) | P1 | Improve (make NOT_TAKEN rows actionable) |
| ADM-07 | Controlled year rollover | Deferred | Not built. Plan is queued for a Gate 0 decision. Copy-from-last-year exists only for teacher assignments. | `docs/ACADEMIC_YEAR_ROLLOVER_PLAN.md:3-5`; `core/views.py:2542` | `test_phase5_assignment_workflows` (copy) | — | Year-end promotion done one student at a time (inference) | Rollover Gate 0 ADR | Deferred | Defer until Gate 0; pressure before the next year starts (inference) |
| ADM-08 | Admin mobile task coverage | Partial | Admin shell has an offcanvas sidebar on phones; many lists render phone cards; phone-specific UI tests exist for students, years, setup lists, registers, guardian attendance, history. No inventory proves every admin task works at phone width; tables need `.erp-keep` to survive phone rules. | `templates/base.html:14-20`; `static/css/erp.css` (67 `@media` blocks); tests at right | `test_ui_student_phone_cards`, `test_ui_year_cards`, `test_ui_setup_lists_phone`, `test_ui_register_cards`, `test_ui_guardian_attendance_phone`, `test_ui_student_history_phone`, `test_ui_hamburger` | A, M | Admin phone use may hit unconverted desktop tables | Page-by-page phone inventory; `feature/admin-home` (unmerged) | P1 | Improve; measure which admin tasks happen on phones |

### 4.2 Teaching and assessment

| ID | Capability | Status | Current behaviour | Evidence | Tests | Roles and devices | Risk or impact | Dependency | Priority | Recommendation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ACA-01 | Connected academic chain | Partial | Assessment → DRAFT results → finalize → corrections → term report card → publication snapshot → guardian, with one source of truth and STALE on correction. No planning or evidence layer. | `core/models.py:2889-3460`; `core/publication.py:376-428`; `core/assessment_reports.py:7` | `test_phase6_publication::test_correction_makes_it_stale_and_hidden`; `test_phase4_acceptance` | A, T, G | Chain is sound; planning/evidence absent by scope | Lesson plans and homework out of scope (`docs/ROADMAP.md:99-100`) | P3 | Preserve |
| ACA-02 | Assessment-first gradebook | Partial | Teacher "My assessments" lists assessments for current assignments; gradebook is read-only marks per subject and section; admin lists assessments per year. Ordering and grouping beyond that not verified. | `core/views.py:1974-2088`; `core/urls.py:242-243` | `test_ui_teacher_marks`; `test_phase4_teachers` | T M-first; A D+M | Unknown whether teachers find the latest assessment fast | Phone task measurement | P2 | Improve after measurement |
| ACA-03 | Fast repetitive grade entry | Partial | Three status radios per row, decimal keypad with "next" key, typed values kept on an invalid post, draft save, live counts. No autosave, bulk fill or per-row save, unlike attendance. | `core/forms.py:852`; `core/views.py:2090-2131` | `test_ui_teacher_marks::test_status_is_three_radios_and_score_has_keypad_hints`, `::test_invalid_post_keeps_typed_values` | T, M | Lost work if the network drops before Save (inference) | Same save model as attendance | P1 | Improve |
| ACA-04 | Explicit result statuses | Divergent | Exactly MARKED and ABSENT. "Not entered" is the absence of a row and is never treated as ABSENT. No medical leave, exempted or not applicable. | `core/models.py:3249-3253`; `docs/adr/0009-phase-4-assessment-and-results-model.md:54-58` | `test_phase4_results`; `test_ui_teacher_marks::test_saved_row_offers_no_not_entered_radio` | A, T | Schools may need exemptions; adding them changes report card meaning | New ADR superseding part of ADR 0009 | Research | Resolve conflict with the product owner |
| ACA-05 | Rubric or criteria assessment | Deferred | Not built. Rubrics and competency grading are out of scope for Phase 4. | `docs/ROADMAP.md:83-85` | — | — | — | School policy evidence | Deferred | Defer |
| ACA-06 | Evidence attachments | Missing | No attachment model or upload for student work. | Search for attachment/portfolio found no model (Evidence Index) | No confirming test found | — | — | Storage, privacy and retention decisions | Research | Research |
| ACA-07 | Guardian-view preview | Partial | Publication preview lists exactly what will be published and writes nothing; publishing uses a confirm token. It is an office table, not the guardian page, and teachers cannot open it. | `core/views.py:3415-3500`; `core/publication.py` | `test_phase6_publication::test_preview_lists_exact_content_and_writes_nothing` | A (`view_termpublication`; marks need `view_studentresult`) | Low; content is exact even if the layout differs | — | P2 | Improve (show guardian layout) |
| ACA-08 | Reusable academic blueprints | Partial | Grading scales are reused across class grades; teacher assignments can be copied from last year with a stale-preview guard. No reusable assessment or term templates. | `core/models.py:2727-2888`; `core/views.py:2542` | `test_phase5_assignment_workflows::test_stale_preview_is_refused`; `test_phase4_grading` | A | — | Rollover decisions | P3 | Preserve; research further need |
| ACA-09 | Lesson plan approval | Deferred | Not built; lesson plans out of scope for Phase 5. | `docs/ROADMAP.md:99-100` | — | — | — | School research | Deferred | Defer |
| ACA-10 | Portfolio | Missing | Not built; not a default requirement in the plan. | No model found | No confirming test found | — | — | ACA-06 | P3 | Defer |

### 4.3 Teacher daily operations

| ID | Capability | Status | Current behaviour | Evidence | Tests | Roles and devices | Risk or impact | Dependency | Priority | Recommendation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TEA-01 | Task-first Today home | Implemented | Lands teachers on My Day: attendance state per class-teacher duty (not taken, draft, submitted, no school day), today's periods, marks tile linking to entry, term remarks due. | `core/views.py:1164-1280`; `core/templates/core/my_home.html:11-82` | `test_phase5_teacher_home::test_teacher_lands_on_my_day_after_login`, `::test_states_follow_todays_register`; `test_ui_teacher_dashboard::test_one_assessment_links_straight_to_marks_entry` | T, M-first (tab bar) | — | — | P3 (preserve) | Preserve |
| TEA-02 | Default-plus-exceptions attendance | Implemented | "Mark all present" fills only unanswered rows, never overrides, and saves them in one request; absences are then marked; submit needs a complete roster and a confirmation. | `static/js/erp.js:310-345`; `core/views.py:1591-1620,1506` | `test_attendance_bulk_present::test_one_request_saves_every_listed_row_as_present`, `::test_an_already_saved_absent_row_not_in_the_batch_is_untouched`; `test_phase5_teacher_attendance::test_incomplete_roster_cannot_be_submitted` | T (class teacher for that section and date) | — | — | P3 (preserve) | Preserve |
| TEA-03 | Submission summary and controlled correction | Implemented | Confirmation page shows counts and notes; a second confirm changes nothing; submitted registers are read-only to teachers; corrections are admin-only with an audit row. | `core/views.py:1506`; `core/views.py:4608-4645`; `core/models.py:1793-1836` | `test_attendance_submit_confirm::test_confirmation_page_shows_context_counts_and_notes`, `::test_second_confirm_does_not_change_the_submission`; `test_phase5_teacher_attendance::test_submitted_register_is_read_only_to_teacher` | T submit; A correct (`change_attendanceentry`) | — | — | P3 (preserve) | Preserve |
| TEA-04 | Consecutive-absence insight | Partial | Admin sees students absent on 3+ reportable days in the chosen period, linked to the student, and a student-list "Absent 3+ days" filter. Not consecutive, not shown to teachers, no follow-up action. | `core/analytics.py:39,414-447`; `core/views.py:4058-4065`; `templates/partials/_attendance_analytics.html:112` | `test_admin_overview_analytics::test_absentee_cards_link_to_the_student`; `test_ui_student_list_filters::test_absent_3plus_days_chip` | A only (`view_student` + `view_attendanceentry`) | Late intervention; class teachers do not see it | Definition of "consecutive" with school days and corrections | P1 | Improve |
| TEA-05 | Assessment completeness | Partial | Teacher home lists open DRAFT assessments with unmarked students and links to entry. Admin "Marks entered" ring counts finalized vs total but has no link; no list of unfinalized or unpublished work for teachers. | `core/views.py:1011-1040`; `core/analytics.py:353-376` | `test_ui_teacher_dashboard::test_several_assessments_link_to_my_assessments_and_count_marks_not_students` | T, A | Admin cannot drill into incomplete marks | — | P2 | Improve |
| TEA-06 | Assignment and homework | Deferred | Not built; homework is out of scope for Phase 5. | `docs/ROADMAP.md:99-100` | — | — | — | Roadmap decision | Deferred | Defer |
| TEA-07 | Mobile repetitive-task quality | Partial | Attendance: autosave per row, "Saving… / All changes saved / Changes not saved", Retry, fallback Save draft, unsaved warning when autosave is off. Marks: no autosave. No tap or time measurement exists. | `static/js/erp.js:236-560` | `test_attendance_bulk_present`; `test_ui_teacher_daily`; `test_ui_teacher_marks` | T, M | Marks entry is the weaker half | ACA-03; measurement | P1 | Improve; measure first |

### 4.4 Guardian engagement and self-service

| ID | Capability | Status | Current behaviour | Evidence | Tests | Roles and devices | Risk or impact | Dependency | Priority | Recommendation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GUA-01 | Activation and recovery | Partial | Office creates the account after confirming identity; temporary password shown once; forced password change on first sign-in; office can reset the password. No self-service recovery; no onboarding progress tracking. | `core/views.py:3720,3840`; `accounts/models.py:28`; `accounts/middleware.py:64-100`; `core/templates/core/guardian_account_form.html:10-12`; `config/urls.py:60-79` (no reset route) | `test_phase6_guardian_accounts::test_everything_redirects_to_password_change`; `test_credential_slip` | A creates/resets; G, M | Every forgotten password becomes an office task | Identity rules for any self-service reset | P1 | Research recovery, then improve |
| GUA-02 | Consolidated child home | Implemented | Home lists each granted child with attendance and results stats and latest notices; pending-review children show "access under review" with no link; child overview and switcher. Pending actions do not exist (no requests). | `core/portal_views.py:74-104`; `templates/portal/home.html:12-40`; `core/portal.py:239` | `test_phase6_portal_shell::test_lists_only_granted_students`, `::test_pending_review_listed_without_link`, `::test_switcher_shows_every_visible_child` | G, M-first | — | GUA-05 for pending actions | P3 (preserve) | Preserve |
| GUA-03 | Unified updates inbox | Partial | Notices list and detail for announcements to the guardian's audience. Absence alerts and report-card notices go by WhatsApp and are not kept in the portal. | `core/portal_views.py:180-199`; `core/announcements.py:157-186` | `test_phase7_announcements::test_class_and_section_reach_only_matching_guardians` | G, M | Guardians cannot see past alerts in one place | Retention of alerts in-portal (MOB-05) | P2 | Improve |
| GUA-04 | Structured school communication | Deferred | No guardian-to-school channel. Two-way chat and parent replies are out of scope. | `docs/PHASE_7_COMMUNICATION_DOCUMENTS_IMPORT_PLAN.md:100`; `docs/ROADMAP.md:100` | — | — | Parents still phone the office | Product decision to reopen | Research | Research |
| GUA-05 | Request ownership and status | Missing | No request model. | No model in `core/models.py` (Evidence Index) | No confirming test found | — | — | GUA-04 | P2 | Research with GUA-04 |
| GUA-06 | Guardian leave application | Missing | Not built. Attendance has PRESENT/ABSENT only, so leave could not change a status without a new decision. | `core/models.py:1344-1357` | No confirming test found | — | — | ADR 0007 statuses; school policy | Research | Research |
| GUA-07 | Grievance workflow | Missing | Not built. | — | No confirming test found | — | Privacy-sensitive | Policy and safeguarding | Research | Research |
| GUA-08 | Certificate and service requests | Missing | Office issues bonafide/attendance summary; guardians cannot request them. TC not built. | `core/models.py:4154-4157`; Phase 7 plan:86 | No confirming test found | — | — | Back-office workflow, TC format | P3 | Defer |
| GUA-09 | Downloadable verified documents | Partial | Guardian downloads the PDF of their own child's published report card, built from an immutable issued document; stale publications give nothing. Other documents are office-only. | `core/portal_views.py:166-177`; `core/models.py:4146-4183` | `test_phase7_documents::test_guardian_downloads_own_childs_card`, `::test_other_guardians_child_is_404`, `::test_stale_publication_gives_nothing_to_guardian_or_office` | G, M | — | Which other documents guardians may self-serve | P2 | Preserve; research scope |
| GUA-10 | Verified fee visibility | Deferred | No fee code. | `docs/ROADMAP.md:66,118`; issue #274 FIN-G4 | `test_phase6_portal_shell::test_no_database_ids_and_no_excluded_features` | — | — | FIN-G0 to G3 | Deferred | Defer |

### 4.5 Communication

| ID | Capability | Status | Current behaviour | Evidence | Tests | Roles and devices | Risk or impact | Dependency | Priority | Recommendation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| COM-01 | Typed request routing | Deferred | No inbound requests (see GUA-04). | Phase 7 plan:100 | — | — | — | GUA-04 | Research | Research |
| COM-02 | Reply policy | Deferred | Every message is one-way by decision; there is no per-message reply setting. | Phase 7 plan:100 | — | — | — | GUA-04 | Research | Research |
| COM-03 | Ownership and service target | Missing | No requests to own. Outbound messages record who marked them sent or dismissed. | `core/notifications.py:254-290` | No confirming test found | — | — | GUA-05 | Research | Research |
| COM-04 | Correction-aware history | Implemented | Announcements cannot be edited, only withdrawn with who/when/why; consent is append-only; notification, consent, issued-document and correction history are guarded by database triggers; corrections mark publications STALE. | `core/announcements.py:47-70`; `core/migrations/0057_notification_history_guards.py:72-100`; `core/migrations/0089_recordcorrection_history_guards.py:23`; `core/publication.py:376` | `test_phase7_announcements::test_withdraw_records_who_when_and_why`; `test_phase7_notifications::test_consent_is_append_only`; `test_phase7_documents::test_update_is_refused`, `::test_delete_is_refused` | A | — | — | P3 (preserve) | Preserve |
| COM-05 | Consent and audience recheck | Implemented | Prepared only with consent; queue drops messages whose consent or portal access has gone; link and mark-sent both recheck under a row lock. A documented gap remains between handing out the link and the manual WhatsApp send in ASSIST mode. | `core/notifications.py:64-100,185-275`; `docs/OPERATIONS.md:257` | `test_phase7_send_queue_recheck::test_grant_revoked_before_display`, `::test_relationship_ended_before_display`, `::test_login_deactivated_before_display`; `test_phase7_notifications::test_mark_sent_after_opt_out_skips` | A (`send_notification`) | Residual ASSIST gap is known and documented | — | P3 (preserve) | Preserve |
| COM-06 | Idempotency and deduplication | Implemented | Unique idempotency key per type/guardian/student/subject; announcement publish-once tokens; import commits once; publication confirm is idempotent. | `core/models.py:4011`; `core/notifications.py:90-100` | `test_phase7_alerts::test_absent_student_gets_one_prepared_alert_per_portal_guardian`; `test_announcement_publish_once::test_back_then_publish_again_does_not_send_twice`; `test_phase7_notifications::test_mark_sent_twice_is_refused` | A | — | — | P3 (preserve) | Preserve |
| COM-07 | Escalation and closure | Missing | No requests to escalate. Outbound dismissals need a reason. | `core/notifications.py:277-290` | `test_phase7_notifications::test_dismiss_needs_reason_and_happens_once` | — | — | GUA-05 | Research | Research |

### 4.6 Mobile, PWA and notifications

| ID | Capability | Status | Current behaviour | Evidence | Tests | Roles and devices | Risk or impact | Dependency | Priority | Recommendation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MOB-01 | Admin desktop and mobile parity | Partial | Same root as ADM-08. | See ADM-08 | See ADM-08 | A, D+M | See ADM-08 | See ADM-08 | P1 | Improve (one gap: G-04) |
| MOB-02 | Teacher mobile-first | Implemented | Phone tab bar, Today home, autosaving attendance, keypad hints on marks. | `templates/partials/_tabbar.html:1-8`; `templates/base.html:63` | `test_ui_teacher_daily`; `test_ui_teacher_cards`; `test_ui_teacher_polish` | T, M | Marks save model (ACA-03) | — | P3 (preserve) | Preserve |
| MOB-03 | Guardian mobile-first | Implemented | Phone tab bar (Notices, Overview, Attendance, Reports), child switcher, phone attendance month view. | `templates/portal/_portal_nav.html:5-9`; `templates/portal/attendance.html:33` | `test_ui_guardian_nav_consistency`; `test_ui_guardian_cards`; `test_portal_query_budget` | G, M | — | — | P3 (preserve) | Preserve |
| MOB-04 | Login convenience | Missing | Password sign-in with throttling, idle/absolute session limits and a session warning. No passkey or device sign-in. | `accounts/middleware.py:64-100`; `static/js/erp.js:1130-1170` | `test_phase6_security::test_rule_a_refuses_even_the_right_password`; `test_session_errors_audit18` | All | Repeated sign-in friction (unmeasured) | Measurement; security review | Research | Research |
| MOB-05 | Notification centre | Partial | Portal notices only (same root as GUA-03). | See GUA-03 | See GUA-03 | G | See GUA-03 | — | P2 | Improve (one gap: G-07) |
| MOB-06 | Push notifications | Deferred | None. Gate 1 excludes push. | `docs/PWA_GATE_1_PLAN.md:8`; `core/pwa_views.py:3` | `test_pwa_gate1::test_no_service_worker_is_registered` | — | — | Consent, reliability and usage research | Research | Unresolved decision |
| MOB-07 | Offline read | Deferred | None. Install page says every page needs a connection. | `docs/PWA_GATE_1_PLAN.md:8`; `templates/pwa/install.html:8` | `test_pwa_gate1::test_no_service_worker_is_registered` | — | — | Network-loss measurement | Research | Unresolved decision |
| MOB-08 | Offline write and sync | Deferred | None. Saves fail visibly and stay unsaved. | `docs/PWA_GATE_1_PLAN.md:8`; `static/js/erp.js:345-560` | `test_pwa_gate1` | — | — | Workflow evidence | Research | Unresolved decision |
| MOB-09 | Background sync | Deferred | None. | `docs/PWA_GATE_1_PLAN.md:8` | `test_pwa_gate1` | — | — | MOB-08 | Research | Unresolved decision |
| MOB-10 | Native apps | Deferred | None. Product follows the PWA path; Phase 5 excluded mobile apps. | `docs/ROADMAP.md:100`; `docs/PWA_GATE_1_PLAN.md` | — | — | — | PWA measurement (Gate 2) | Research | Unresolved decision |

### 4.7 Analytics and insights

| ID | Capability | Status | Current behaviour | Evidence | Tests | Roles and devices | Risk or impact | Dependency | Priority | Recommendation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ANA-01 | Attendance not submitted | Partial | Overview card and ring count today's missing sections and link to the missing report; DRAFT rows open the register; NOT_TAKEN rows have no link. Teachers see their own state on My Day. | `core/dashboard.py:39-56`; `core/templates/core/report_missing_attendance.html:42-47` | `test_admin_overview_analytics::test_counts_only_submitted_registers_today`; `test_ui_admin_desktop_d1_4c1_attendance_reports::test_draft_and_not_taken_are_distinct_and_never_absent` | A, T | Dead end for NOT_TAKEN | G-02 | P1 | Improve |
| ANA-02 | Consecutive or repeated absence | Partial | Same root as TEA-04. | See TEA-04 | See TEA-04 | A | See TEA-04 | — | P1 | Improve (one gap: G-03) |
| ANA-03 | Incomplete assessment or marks | Partial | Teacher tile is actionable; admin ring is not. | `core/views.py:1011-1040`; `core/analytics.py:369-376` | `test_ui_teacher_dashboard::test_one_assessment_links_straight_to_marks_entry` | T, A | — | — | P2 | Improve |
| ANA-04 | Unpublished or stale report | Implemented | Corrections mark publications STALE (hidden from guardians); stale list page, nav badge and overview card link to it; "Results published" ring excludes stale versions. | `core/publication.py:376-428`; `core/views.py:3505-3510`; `core/nav_badges.py:33`; `core/dashboard.py:71-76` | `test_phase6_publication::test_correction_makes_it_stale_and_hidden`; `test_admin_overview_analytics::test_published_ring_counts_students_and_drops_stale_versions` | A (`view_termpublication`) | — | — | P3 (preserve) | Preserve |
| ANA-05 | Guardian account inactive | Missing | Teachers show last sign-in; guardian accounts do not, and no list of never-signed-in guardians exists. | `core/teacher_views.py:35`; no guardian equivalent found | No confirming test found | — | Office cannot see who never activated | GUA-01 | P2 | Improve |
| ANA-06 | Unread important update | Missing | No read tracking on notices. | No `read_at`/acknowledgement field found | No confirming test found | — | — | Privacy decision on read tracking | Research | Research |
| ANA-07 | Overdue parent request | Missing | No requests exist. | — | No confirming test found | — | — | GUA-05 | Research | Research |
| ANA-08 | Authorization or integrity hold | Partial | Guardian access reviews hold a child's portal access until an explicit decision; overview card links to them; messages for lost access are dismissed by the system. No general integrity-hold mechanism. | `core/guardian_access.py:112-175`; `core/dashboard.py:79-85`; `core/notifications.py:176-183` | `test_phase6_portal_shell::test_pending_review_listed_without_link`; `test_phase7_send_queue_recheck::test_pending_review_before_display` | A, G | — | FIN-G4 will need a fail-safe hold | P2 | Preserve; extend only with a decision |
| ANA-09 | Fee reconciliation exception | Deferred | No fee code. | Issue #274 FIN-G3 | — | — | — | FIN-G0 to G3 | Deferred | Defer |

### 4.8 Fee management

| ID | Capability | Status | Current behaviour | Evidence | Tests | Roles and devices | Risk or impact | Dependency | Priority | Recommendation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FIN-G0 | Financial rules and threat model | Deferred | Not started; next work only when resumed. | Issue #274; `docs/ROADMAP.md:66-69` | — | — | — | Product-owner decision | Deferred | Defer |
| FIN-G1 | Protected ledger | Deferred | No fee model or migration. | §10 | — | — | — | FIN-G0 | Deferred | Defer |
| FIN-G2 | Finance-office workflow | Deferred | No route or template. | §10 | — | — | — | FIN-G1 | Deferred | Defer |
| FIN-G3 | Reconciliation and audit | Deferred | None. | §10 | — | — | — | FIN-G2 | Deferred | Defer |
| FIN-G4 | Read-only guardian fees | Deferred | No guardian fee exposure; tests forbid the word "fee" on portal pages. | `core/tests/test_phase6_portal_shell.py:74-81`; `core/tests/test_ui_foundation.py:249` | `test_phase6_portal_shell::test_no_database_ids_and_no_excluded_features` | — | — | FIN-G0 to G3 | Deferred | Defer |
| FIN-G5 | Fee reminder queue | Deferred | Notification types are absence, report card, announcement only. | `core/models.py:3983-4050` | — | — | — | Ledger, reconciliation | Deferred | Defer |
| FIN-G6 | Online payment | Deferred | No payment code. | §10 | — | — | — | All prior gates | Deferred | Defer |

### 4.9 Counts

| Status | Count |
| --- | --- |
| Implemented | 10 |
| Partial | 21 |
| UI-only | 0 |
| Backend-only | 0 |
| Missing | 15 |
| Divergent | 1 |
| Deferred | 21 |
| Not applicable | 0 |
| Unknown | 0 |
| **Total** | **68** |

| Priority | Count |
| --- | --- |
| P0 | 0 |
| P1 | 9 |
| P2 | 14 |
| P3 | 14 (10 of them "preserve" for Implemented rows) |
| Research | 18 |
| Deferred | 13 |
| **Total** | **68** |

## 5. Role and device coverage

| Journey | Admin desktop | Admin mobile | Teacher mobile-first | Guardian mobile-first | Evidence and notes |
| --- | --- | --- | --- | --- | --- |
| Sign in and landing | Overview | Overview, offcanvas menu | My Day | Portal home | `core/views.py:933` routes by area; multi-role logins choose (`core/authorization.py:418-433`); `test_phase5_teacher_home::test_teacher_with_admin_rights_chooses_an_area` |
| Primary navigation | Sidebar groups | Offcanvas sidebar (no tab bar) | Bottom tab bar | Bottom tab bar | `templates/base.html:14-63` |
| Search or lookup | Per-list search | Same pages, phone cards on several lists | My Students search (scoped) | Child switcher | No global search (ADM-01) |
| Attendance | Registers, capture, corrections, reports | Register cards on phones | Capture, autosave, submit, history | Monthly view | `test_ui_register_cards`; `test_phase6_portal_attendance` |
| Assessments and reports | Full | Partly phone-converted (unverified per page) | Marks entry, gradebook, results, remarks | Published report cards and PDF | ACA-03 weaker on phones |
| Communication | Announcements, queue, consent | Same pages | None | Notices only | No inbound channel |
| Documents | Issue PDFs | Same pages | None | Own child's report card PDF | GUA-09 |
| Failure and recovery | Server validation, error summaries | Same | Autosave states, Retry, fallback Save; session warning | Read-only; session warning | Network loss leaves data unsaved and says so (`static/js/erp.js:247-262`); offline launch unsupported |

## 6. Critical journey findings

### Administrator

1. **Find a student:** `/students/?q=` → `administrator_required("core.view_student")` → name/admission/guardian search; guardian matching only with `view_guardian`, absent filter only with `view_attendanceentry` (`core/views.py:4003-4030`) → `student_detail` (`core/views.py:4146-4194`) gates guardians, attendance and progress sections separately. Test: `test_security_gate4b_people_pages::test_absent_filter_needs_view_attendanceentry`.
2. **Repeated task (bulk import):** upload → staged rows (no school records written) → preview → commit once → issues CSV (`core/import_views.py:51-128`; `core/imports.py`). Tests: `test_phase7_import::test_validation_changes_no_school_records`, `::test_a_batch_commits_only_once`.
3. **Operational exception:** overview card "Attendance today" → missing-attendance report → DRAFT row opens the register; NOT_TAKEN row is a dead end (`core/templates/core/report_missing_attendance.html:42-47`).
4. **Phone:** offcanvas sidebar and phone card lists exist; the admin home redesign for phones is on an unmerged branch. Verified by UI tests, not by device.

### Teacher

1. **Landing:** sign-in → `home` → My Day (`core/views.py:933,1164`).
2. **Attendance:** `my-attendance` → `can_take_attendance` (class teacher for that section, date and year) → row autosave (`core/views.py:1543`) or bulk present (`:1591`) → submit with confirmation (`:1506`) → register SUBMITTED, read-only. Tests: `test_phase5_teacher_attendance::test_other_section_is_forbidden`, `::test_subject_teacher_who_is_not_class_teacher_is_forbidden`.
3. **Marks:** `assessment-marks-entry` → `can_enter_results(user, offering, section)` (`core/views.py:2092`) → `save_draft_result` per row → admin finalizes (`core.finalize_assessment`).
4. **Permitted student:** `my-student-detail` → `teacher_student_scope` (`core/authorization.py:252-289`); guardian contact only when allowed (`:289`).
5. **Phone:** tab bar, autosave and keypad hints; marks entry has no autosave.

### Guardian

1. **Activation:** office creates the account with a temporary password shown once → first sign-in forced to change password (`accounts/middleware.py:93`). No self-service recovery.
2. **Select a child:** portal home lists granted children; switcher; UUID URLs; other families' children 404 (`core/portal_views.py:38-49`).
3. **Attendance:** submitted entries only, by month (`core/portal.py:83-195`).
4. **Report cards:** only PUBLISHED, non-stale publications; PDF from the issued document (`core/portal.py:196-238`; `core/portal_views.py:166-177`).
5. **Announcements:** notices by audience (`core/announcements.py:157-186`). Documents other than the report card: none.
6. **Two-way communication, structured requests, leave, request status:** none exist.

### Communication

1. **Consent:** office records opt-in/opt-out with a source and note; history is append-only (`core/notification_views.py:28`; `core/notifications.py:52-57`).
2. **Preparation:** producers create messages for portal guardians only (absence on submit, absence corrected, report card published, announcement) (`core/notification_producers.py:75-160`).
3. **Recheck before send:** `to_send`, `open_whatsapp`, `mark_sent` recheck consent and portal access under lock (`core/notifications.py:185-275`).
4. **Dedup, correction, dismissal, history:** idempotency key, dismiss with reason, trigger-guarded history.

### Fee boundary

See §10. No fee code; boundary intact.

## 7. Mobile and PWA findings

| Capability | Present | Evidence | Behaviour | Decision status |
| --- | --- | --- | --- | --- |
| Manifest and installability | Yes | `core/pwa_views.py`; `config/urls.py:61-62`; `templates/partials/_pwa_head.html`; `static/pwa/` (192, 512, maskable 512, Apple 180) | Public manifest, install help page, phone install bar, 30-day dismissal | Gate 1 done; Gate 2 device checks not run |
| Responsive Admin | Partial | `templates/base.html:14-20`; phone UI tests | Offcanvas menu, phone cards on many lists | Product direction: full support |
| Mobile-first Teacher | Yes | `templates/partials/_tabbar.html` | Tab bar, Today, autosave | — |
| Mobile-first Guardian | Yes | `templates/portal/_portal_nav.html` | Tab bar, switcher | — |
| Service worker | No | `core/pwa_views.py:3`; `test_pwa_gate1::test_no_service_worker_is_registered` | — | Excluded by Gate 1 |
| Offline fallback | No | `templates/pwa/install.html:8` | Pages need a connection | Excluded |
| Offline write queue | No | `static/js/erp.js:345-560` | Failed saves stay unsaved with Retry | Excluded |
| Client-side storage | UI preferences only | `static/js/erp.js:138-186,984-997`; `templates/base.html:12` | localStorage holds sidebar state and install-bar dismissal only; no school data (inference from all call sites) | Allowed |
| Background sync | No | — | — | Excluded |
| Push notifications | No | — | — | Excluded |
| Passkey or device-assisted login | No | `config/urls.py:60-79` | Password only | Not decided |
| Safe behaviour on network loss | Yes (attendance) | `static/js/erp.js:247-262`; session check retries (`:1163`) | "Changes not saved", Retry, fallback Save draft | — |

Note: HTMX 2.0.4 is loaded only on the teacher attendance page (`core/templates/core/my_attendance.html:52`). No `hx-boost` or `hx-push-url` is used, so HTMX's history cache is not exercised (inference from search; Evidence Index §MOB).

## 8. Parent-engagement findings

- **Activation:** office-led, identity-verified, temporary password once, forced change. Strong on security, weak on self-service.
- **Recovery:** office reset only. No email or phone recovery.
- **Child selection:** explicit grants per student; review holds show "access under review" without data. Strong.
- **Attendance:** submitted only; DRAFT never shown; monthly view on phones. Strong.
- **Results:** published snapshots only; stale versions disappear; PDF from immutable document. Strong.
- **Announcements:** audience-targeted notices; withdrawal hides them. Present.
- **Documents:** report card PDF only.
- **Communication and requests:** none; two-way chat and replies are out of scope by decision.
- **Consent:** WhatsApp consent is recorded by the office; guardians cannot see or change it in the portal (inference from portal routes).
- **Follow-up:** no read tracking, no "never signed in" list, no request status.
- **Fees:** absent, and tests forbid fee wording on portal pages.

## 9. Analytics findings

| Insight or report | Source of truth | Role scope | Actionable | Links to evidence | Test coverage | Finding |
| --- | --- | --- | --- | --- | --- | --- |
| Attendance today card | `reports.missing_attendance` (registers vs expected days) | `view_attendanceregister` | Yes | Missing report for today | `test_admin_overview_analytics` | True insight |
| Missing attendance report | Same | `view_attendanceregister` | Partly | DRAFT rows only | `test_ui_admin_desktop_d1_4c1_attendance_reports` | Dead end for NOT_TAKEN |
| Registers today ring | `today_strip` | `view_attendanceregister` | Yes | Missing report | `test_admin_overview_analytics` | Insight |
| Marks entered ring | Assessments finalized vs total in term | `view_studentresult` | No | `url: None` (`core/analytics.py:375`) | `test_admin_overview_analytics` | Count only |
| Results published ring | PUBLISHED publications vs ACTIVE enrolled | `view_termpublication` | No | `url: None` (`core/analytics.py:400`) | `::test_published_ring_counts_students_and_drops_stale_versions` | Count only |
| Results to publish (stale) card | `TermPublication.STALE` | `view_termpublication` | Yes | Stale list | `test_phase6_publication` | True insight |
| Pending access reviews card | `guardian_access.pending_reviews` | `view_guardianaccessreview` | Yes | Review page | `test_ui_admin_desktop_d1_3c_access_reviews` | True insight (integrity hold) |
| Messages to send card | PREPARED notifications | `send_notification` | Yes | Queue | `test_ui_admin_desktop_d1_6d_notification_queue` | True insight |
| Applicants awaiting decision | PENDING applicants | `view_applicant` | Yes | Filtered list | `test_ui_admin_overview_glance` | Insight |
| Sign-in lockouts | Login failures | `clear_login_lockout` | Yes | Lockout page | `test_ui_admin_desktop_d1_6a_security_operations` | Insight |
| Frequent absentees | ABSENT entries, submitted, reportable, ≥3 in period | `view_student` + `view_attendanceentry` | Yes (to student) | Student profile | `::test_absentee_cards_link_to_the_student` | Useful; not consecutive |
| Students needing attention | Marks + attendance | + `view_studentresult` | Yes | Student | `test_marks_analytics` | Useful; check meaning with the school |
| Trend, heatmap, class comparison | Submitted entries | Attendance perms | Class rows link to class | Class page | `test_admin_overview_analytics` | Descriptive charts |
| Glance cards (students, guardians, teachers) | Counts | `view_school` (links need own perm) | No | Lists | `test_ui_admin_overview_glance` | Counts only (deliberate bundle) |
| Not found | — | — | — | — | — | No guardian-inactive, unread-notice, overdue-request or consecutive-absence insight |

## 10. Fee boundary verification

- **Phase 3 status:** DEFERRED / NOT IMPLEMENTED (`docs/ROADMAP.md:66-69`). Issue #274 is OPEN and marked deferred.
- **Fee models or migrations found:** None. No model with fee, payment, invoice, receipt, instalment or balance meaning in `core/models.py` or `accounts/models.py`; no migration file name contains fee or pay (95 migration files checked).
- **Fee routes or templates found:** None in `core/urls.py`, `core/portal_urls.py`, `config/urls.py`.
- **Guardian fee exposure found:** None. Portal tests assert "fee" does not appear (`core/tests/test_phase6_portal_shell.py:74-81`; `core/tests/test_ui_foundation.py:240-251`).
- **Reminder or payment code found:** None. Notification types are absence, report card and announcement only.
- **Mutable balance or placeholder risk:** None in code. One demo notice titled "Fee Payment Reminder", with text about paying at the office (`core/demo_refresh.py:295-297`). This is seed text, not a feature, but it can suggest fee support on staging.
- **Issue #274 consistency:** Consistent. Monolith kept; no placeholders, guardian fees, reminders or payments.

## 11. Deduplicated gap register

| Gap ID | Canonical gap | Related candidate IDs | Evidence | Root cause | User impact | Dependency | Priority | Recommended disposition |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| G-01 | No parent-to-school channel (requests, leave, grievance, service requests, ownership, escalation) | GUA-04, GUA-05, GUA-06, GUA-07, GUA-08, COM-01, COM-02, COM-03, COM-07, ANA-07 | Phase 7 plan:100; no models | Out of scope by decision (two-way) and never planned (requests) | Parents phone the office; nothing is tracked | Product decision; policy research | Research | Interview schools before any decision |
| G-02 | Exception lists stop short of the action | ANA-01, ADM-06, ANA-03, TEA-05 | `report_missing_attendance.html:42-47`; `analytics.py:375,400` | Rows and rings built for counting, not acting | Extra navigation; NOT_TAKEN dead end | Who acts on a NOT_TAKEN row | P1 | Improve |
| G-03 | Absence insight is count-based and admin-only | TEA-04, ANA-02 | `analytics.py:414-447` | Threshold over a period, no consecutive rule | Late follow-up; class teacher unaware | Consecutive definition across school days | P1 | Improve |
| G-04 | Admin phone coverage not inventoried | ADM-08, MOB-01 | `base.html`; phone UI tests | Page-by-page conversion | Some admin pages may be hard on phones | `feature/admin-home` merge; phone inventory | P1 | Improve; measure |
| G-05 | Marks entry lacks the attendance save model | ACA-03, TEA-07 | `views.py:2090-2131` vs `erp.js:345-560` | Built earlier, without autosave | Lost marks on network loss (inference) | — | P1 | Improve |
| G-06 | Guardian activation, recovery and engagement are invisible | GUA-01, ANA-05, ANA-06, MOB-04 | `config/urls.py:60-79`; no guardian last-sign-in display | Office-led model, no signals | Office does all resets; nobody sees inactive families | Identity rules; privacy of read tracking | P1 | Research recovery; improve signals |
| G-07 | Guardian updates are notices only | GUA-03, MOB-05 | `portal_views.py:180-199` | Alerts sent by WhatsApp only | No in-portal history of alerts | Retention decision | P2 | Improve |
| G-08 | No configurable exports | ADM-05 | `import_views.py:117` | Never built | Retyping | Permission-aware export | P2 | Improve |
| G-09 | Student 360 misses access, consent and documents | ADM-02 | `views.py:4146-4194` | Profile built phase by phase | Office checks several pages | — | P2 | Improve |
| G-10 | No global search | ADM-01, ADM-03 | Per-list search only | Not planned | Slower lookup | Permission reuse | P2 | Improve later |
| G-11 | Guardian-layout preview missing | ACA-07 | `views.py:3415` | Preview is an office table | Low | — | P2 | Improve |
| G-12 | Result-status vocabulary conflicts with candidate | ACA-04 | ADR 0009:54-58 | Frozen decision | Exemptions cannot be recorded | ADR | Research | Resolve conflict |
| G-13 | Documentation drift and demo fee text | — | `ROADMAP.md:120`; `demo_refresh.py:295` | Docs not updated after Phase 7; seed text | Confuses reviewers and demo users | — | P3 | Correct docs and seed text when approved |

Deferred items (ADM-07, ACA-05, ACA-09, TEA-06, GUA-10, ANA-09, MOB-06 to MOB-10, FIN-G0 to G6) are not gaps; they are governed decisions.

## 12. Conflict register

| Conflict | Candidate or source | Governing project decision | Evidence | Recommended resolution |
| --- | --- | --- | --- | --- |
| Extra result statuses (medical leave, exempted, N/A) | ACA-04 (Toddle) | ADR 0009: exactly MARKED and ABSENT | `core/models.py:3249-3253` | Product owner decides whether to open a superseding ADR |
| Guardian leave and late/excused | GUA-06 (Edunext) | ADR 0007: PRESENT and ABSENT only | `core/models.py:1344-1357` | Decide statuses before any leave workflow |
| Two-way communication and replies | GUA-04, COM-01, COM-02 (Edunext) | Phase 7 out of scope | Phase 7 plan:100 | Keep out unless school research justifies reopening |
| Homework, lesson plans | TEA-06, ACA-09 (Toddle) | Phase 5 out of scope | `ROADMAP.md:99-100` | Keep deferred |
| Rubrics | ACA-05 (Toddle) | Phase 4 out of scope | `ROADMAP.md:83-85` | Keep deferred |
| Offline, push, native | MOB-06 to MOB-10 | PWA Gate 1 online-only | `PWA_GATE_1_PLAN.md:8` | Measure in Gate 2 first |
| Guardian PDF report cards | — (internal) | ROADMAP Phase 6 says excluded; Phase 7 plan approves | `ROADMAP.md:120` vs Phase 7 plan:201 | Update ROADMAP wording (docs only) |
| Parent-facing fees | GUA-10, FIN | Phase 3 deferred; issue #274 | §10 | Keep deferred |

## 13. Research questions

| Question | Why code cannot answer it | Required participants or measurement | Decision unlocked |
| --- | --- | --- | --- |
| Which parent requests reach the office most often, and who owns them? | No inbound channel exists | Front-office interviews; call log sample | Whether G-01 is worth reopening |
| How should "consecutive absence" count holidays, Saturdays and corrections? | Policy, not code | Class teachers, principal | G-03 design |
| Who should act on a NOT_TAKEN register: office or teacher? | Workflow ownership | Office and teachers | G-02 action |
| Do schools need exempted / medical-leave result states? | Policy and board rules | Exam coordinators | ACA-04 ADR |
| Which admin tasks are really done on phones? | No usage data | Device and route measurement without personal data | G-04 scope |
| How often do saves fail from network loss, and on which pages? | No telemetry | Error counts per route | MOB-07/08 decision |
| How many guardians never activate, and why? | No signal | Activation counts; office interviews | G-06 recovery design |
| Is read-receipt tracking acceptable to families? | Privacy | Parents, school leadership | ANA-06 |
| What is the school's TC format? | Not collected | School office | GUA-08 / Phase 7 Gate 7 |
| How long does marks entry take per class on a phone? | No measurement | Timed sessions with teachers | G-05 priority |

## 14. Next-move options

### Option A: Make existing exceptions actionable (workflow, no new domain)

- **Outcome:** NOT_TAKEN rows, the marks ring and absence lists lead straight to the right action; teachers see their own repeated absences.
- **Included gaps:** G-02, G-03 (after the definition is agreed).
- **Dependencies:** Decide who acts on NOT_TAKEN; agree the consecutive-absence rule.
- **Risks:** Low. Reuses existing permissions and queries; must keep data-class gating.
- **Why choose it:** Highest value for daily operations with the least new surface.
- **Why defer it:** If the admin-home branch already reshapes these screens, wait for it to merge first.

### Option B: Phone save quality and measurement

- **Outcome:** Marks entry gets the attendance save model; a privacy-safe measure of task time, failed saves and phone use per area.
- **Included gaps:** G-05, G-04 (inventory); inputs to MOB-07/08 and G-06.
- **Dependencies:** Agreement on what may be measured and kept; PWA Gate 2 device checks.
- **Risks:** Medium. Measurement must not record personal data or field values.
- **Why choose it:** Turns the mobile decisions (offline, native, push) from opinion into evidence.
- **Why defer it:** Needs a measurement policy before any code.

### Option C: Parent engagement discovery (research only)

- **Outcome:** School interviews on requests, leave, recovery and read tracking; a decision on whether to reopen two-way communication.
- **Included gaps:** G-01, G-06, G-07; the ACA-04 and GUA-06 conflicts.
- **Dependencies:** Access to one or two schools; product-owner time.
- **Risks:** None in code; scope can grow if not time-boxed.
- **Why choose it:** The largest benchmark gap is also the one with no decision behind it.
- **Why defer it:** If daily operations work (Option A) is more urgent for the pilot school.

FIN-G0 can be resumed separately at any time as its own project; it is not part of these options.

## 15. Audit completion checklist

- [x] Every candidate ID has one status (68 of 68).
- [x] Every implemented or partial finding has code evidence.
- [x] Every deferred finding cites its governing decision.
- [x] Server-side authorization was checked where applicable (route inventory and view bodies).
- [x] Mobile and desktop exposure were separated.
- [x] PWA installability was separated from offline and push capability.
- [x] Fee absence and issue #274 boundaries were verified.
- [x] Gaps were deduplicated (13 canonical gaps).
- [x] Strengths and gaps were both recorded.
- [x] No competitor feature was treated as automatically required.
- [x] No application implementation was performed.
