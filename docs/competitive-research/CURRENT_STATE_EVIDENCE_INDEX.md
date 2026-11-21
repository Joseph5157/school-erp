# Current-State Evidence Index

**Companion to:** `docs/competitive-research/CURRENT_STATE_BENCHMARK_AUDIT.md`
**Branch / HEAD:** `docs/erp-benchmark-codebase-audit` / `2edeee60d08f097080a02660453b121ee5721b3c`
**Audit date:** 21 November 2026

Paths are repository-relative. Line numbers refer to the HEAD above. Test references are `module::test_name` under `core/tests/` unless noted. Tests were read, not run (see the audit report §1).

## 1. Governing documents and ADRs

| Topic | Source |
| --- | --- |
| Product vision, portals separate from admin ERP | `docs/PRODUCT.md` (FROZEN sections); timetable scope update (ADR 0021) |
| Phase status, Phase 3 deferred | `docs/ROADMAP.md:66-69` |
| Phase 4 out of scope (rubrics, rank, GPA) | `docs/ROADMAP.md:83-85` |
| Phase 5 out of scope (homework, lesson plans, teacher-to-guardian messaging, mobile apps) | `docs/ROADMAP.md:99-100` |
| Phase 6 clarifications (no fees, PDF excluded) | `docs/ROADMAP.md:118-120` |
| Phase 7 approved; fee reminders wait | `docs/ROADMAP.md:134` |
| Phase 7 out of scope (two-way chat, replies, SMS/email, fee code) | `docs/PHASE_7_COMMUNICATION_DOCUMENTS_IMPORT_PLAN.md:99-102` |
| Guardians may download own child's report-card PDF | `docs/PHASE_7_COMMUNICATION_DOCUMENTS_IMPORT_PLAN.md:201` |
| TC still open | `docs/PHASE_7_COMMUNICATION_DOCUMENTS_IMPORT_PLAN.md:86` |
| PWA Gate 1 scope (online-only) | `docs/PWA_GATE_1_PLAN.md:8` |
| Rollover queued for Gate 0 | `docs/ACADEMIC_YEAR_ROLLOVER_PLAN.md:3-5` |
| Permission model and data classes | `docs/PERMISSIONS.md` |
| ASSIST WhatsApp queue and known gap | `docs/OPERATIONS.md:257` |
| Authorization foundation | ADR 0004 |
| Attendance statuses PRESENT/ABSENT | ADR 0007 |
| Result states MARKED/ABSENT | ADR 0009 (`docs/adr/0009-phase-4-assessment-and-results-model.md:54-58`) |
| Teacher assessment authorization | ADR 0010, ADR 0018 |
| Class teacher and attendance access | ADR 0011, ADR 0012 |
| Guardian accounts, grants, visible info, publication | ADR 0013, ADR 0014 |
| Notifications, consent, delivery modes | ADR 0015 |
| Issued documents and PDFs | ADR 0016 |
| Bulk import | ADR 0017 |
| Record corrections | ADR 0023 |
| Ending guardian relationships | ADR 0024 |
| Fee direction | GitHub issue #274 (OPEN, deferred, FIN-G0 to G6) |

## 2. Evidence by candidate ID

### ADM

- **ADM-01** Per-list search: `core/views.py:4003-4030` (student search; guardian match only with `view_guardian`). Search inputs: `core/templates/core/student_list.html:11`, `guardian_list.html:12`, `applicant_list.html:12`, `teacher_list.html:12`, `announcement_list.html:16`, `my_students.html:18`. No global search route in `core/urls.py`. Tests: `test_security_gate4b_people_pages::test_absent_filter_needs_view_attendanceentry`; `test_search_filter_audit13`; `test_ui_guardian_student_search`.
- **ADM-02** `core/views.py:4146-4194` (`student_detail`, sections gated by `data_access.GUARDIAN`, `data_access.ATTENDANCE_ENTRY`, `core.view_studentresult`); `core/templates/core/student_detail.html:9-223`. Tests: `test_student_progress`; `test_record_corrections::test_history_shows_on_the_record_with_who_why_and_values`; `test_security_gate4b_people_pages`.
- **ADM-03** Guardian-only switcher `templates/portal/base.html:25`; no admin context mechanism found. No test.
- **ADM-04** Import: `core/import_views.py:51-128`, `core/imports.py:3,643,829`. Publication: `core/views.py:3415`, `core/publication.py`. Announcements: `core/announcement_views.py`, `core/announcements.py:29-70`. Assignment copy: `core/views.py:2542-2570`. Bulk present: `core/views.py:1591`, `static/js/erp.js:310-345`. Tests: `test_phase7_import::test_a_batch_commits_only_once`, `::test_discard_and_expiry`, `::test_validation_changes_no_school_records`; `test_phase6_publication::test_confirming_twice_publishes_nothing_new`, `::test_stale_token_writes_nothing`; `test_announcement_publish_once::test_back_then_publish_again_does_not_send_twice`; `test_phase5_assignment_workflows::test_stale_preview_is_refused`; `test_attendance_bulk_present::test_forged_and_repeated_ids`, `::test_submitted_register_is_refused`.
- **ADM-05** Only exports: `core/import_views.py:117` (issues CSV) and `:128` (template). Tests: `test_ui_admin_desktop_d1_6e_bulk_imports` (CSV content type, line 251); `test_phase7_import::test_csv_cells_are_neutralised`.
- **ADM-06** `core/reports.py:173-246` (`expected_registers`, `missing_attendance`); `core/dashboard.py:39-56`; `core/analytics.py:319-345`; `core/templates/core/report_missing_attendance.html:36-52` (link only when `row.register`). Tests: `test_ui_admin_desktop_d1_4c1_attendance_reports::test_draft_and_not_taken_are_distinct_and_never_absent`, `::test_draft_register_absences_are_not_listed`; `test_admin_overview_analytics::test_no_register_yet_is_expected_but_not_submitted`, `::test_non_instructional_today_is_not_expected`.
- **ADM-07** `docs/ACADEMIC_YEAR_ROLLOVER_PLAN.md:3-5`. No rollover code: `rg -i "rollover|promot"` in `core/` outside tests and migrations found only a docstring at `core/assessment_reports.py:7` saying there is no promotion.
- **ADM-08** `templates/base.html:14-20` (offcanvas menu button, `d-lg-none`); 67 `@media` blocks in `static/css/erp.css`. Tests: `test_ui_student_phone_cards`, `test_ui_year_cards`, `test_ui_setup_lists_phone`, `test_ui_register_cards`, `test_ui_guardian_attendance_phone::test_submitted_attendance_has_phone_rows_with_note_and_correct_link`, `test_ui_student_history_phone`, `test_ui_year_assignments_phone`, `test_ui_hamburger`, `test_ui_phone_polish`.

### ACA

- **ACA-01** `core/models.py:2889` (Assessment), `:3256` (StudentResult), `:3411` (ResultCorrection), `:3460` (TermRemark), `:3682` (TermPublication), `:3763` (TermPublicationEntry); `core/publication.py:376-428`. Tests: `test_phase6_publication::test_correction_makes_it_stale_and_hidden`; `test_phase4_acceptance`; `test_phase4_corrections`.
- **ACA-02** `core/views.py:1974-2088` (`my_assessments`; `my_gradebook` docstring "Read-only marks for one of the teacher's Subject + Section assignments"). Tests: `test_ui_teacher_marks`; `test_phase4_teachers`.
- **ACA-03** `core/forms.py:852` (`inputmode: decimal`, `enterkeyhint: next`); `core/views.py:2090-2131`. Tests: `test_ui_teacher_marks::test_status_is_three_radios_and_score_has_keypad_hints`, `::test_invalid_post_keeps_typed_values`, `::test_counts_use_saved_results`.
- **ACA-04** `core/models.py:3249-3253`; ADR 0009:54-58. Tests: `test_ui_teacher_marks::test_saved_row_offers_no_not_entered_radio`; `test_phase4_results`.
- **ACA-05** `docs/ROADMAP.md:83-85`. `rg -i "rubric|criteria|criterion"` in code: no match.
- **ACA-06** `rg -i "attachment|portfolio|homework|lesson.plan"` in `core/` (non-test): only `core/documents/service.py` (PDF Content-Disposition) and `core/import_views.py` (file download); no model.
- **ACA-07** `core/views.py:3415-3500`. Route `core:term-publication` inner permissions `publish_termpublication`, `view_studentresult` (`core/tests/route_permissions.json`). Test: `test_phase6_publication::test_preview_lists_exact_content_and_writes_nothing`.
- **ACA-08** `core/models.py:2727-2888` (GradingScale, GradingScaleClassGrade, GradeBoundary); `core/views.py:2542`. Tests: `test_phase4_grading`; `test_phase5_assignment_workflows::test_stale_preview_is_refused`.
- **ACA-09** `docs/ROADMAP.md:99-100`.
- **ACA-10** No model found.

### TEA

- **TEA-01** `core/views.py:1164-1280` (`my_home`), `:1011-1040` (`_open_assessments_needing_marks`); `core/templates/core/my_home.html:11-82`. Tests: `test_phase5_teacher_home::test_teacher_lands_on_my_day_after_login`, `::test_states_follow_todays_register`, `::test_only_teachers_may_open_my_day`; `test_ui_teacher_dashboard::test_one_assessment_links_straight_to_marks_entry`.
- **TEA-02** `static/js/erp.js:310-345`; `core/views.py:1543` (row autosave), `:1591` (bulk present), `:1506` (submit). Tests: `test_attendance_bulk_present::test_one_request_saves_every_listed_row_as_present`, `::test_unlisted_rows_are_left_alone`, `::test_an_already_saved_absent_row_not_in_the_batch_is_untouched`; `test_phase5_teacher_attendance::test_incomplete_roster_cannot_be_submitted`.
- **TEA-03** `core/views.py:4608-4645` (`attendance_entry_correct`, `core.change_attendanceentry`); `core/models.py:1793-1836` (AttendanceCorrection). Tests: `test_attendance_submit_confirm::test_confirmation_page_shows_context_counts_and_notes`, `::test_second_confirm_does_not_change_the_submission`, `::test_incomplete_register_returns_to_roster_with_draft_kept`; `test_phase5_teacher_attendance::test_submitted_register_is_read_only_to_teacher`, `::test_administrator_submitted_register_is_read_only_too`.
- **TEA-04** `core/analytics.py:39` (`ABSENTEE_THRESHOLD_DAYS = 3`), `:414-447`; `core/views.py:4058-4065`; `templates/partials/_attendance_analytics.html:112`. `rg -i "consecutive|in a row|streak"`: only `core/management/commands/generate_pwa_icons.py` (unrelated). Tests: `test_admin_overview_analytics::test_absentee_cards_link_to_the_student`, `::test_absentee_list_is_hidden_without_permission_to_view_students`; `test_ui_student_list_filters::test_absent_3plus_days_chip`, `::test_absent_chip_ignores_absences_from_an_old_year`.
- **TEA-05** `core/views.py:1011-1040`; `core/analytics.py:353-376` (ring `url: None`). Test: `test_ui_teacher_dashboard::test_several_assessments_link_to_my_assessments_and_count_marks_not_students`.
- **TEA-06** `docs/ROADMAP.md:99-100`.
- **TEA-07** `static/js/erp.js:236-262` (save states), `:345-560` (HTMX autosave, failure, Retry, `beforeunload` warning when autosave is off). Tests: `test_attendance_bulk_present`; `test_ui_teacher_daily`.

### GUA

- **GUA-01** `core/views.py:3720` (`guardian_account_create`), `:3840` (`guardian_account_reset_password`); `accounts/models.py:28` (`must_change_password`); `accounts/middleware.py:64-100`; `core/templates/core/guardian_account_form.html:10-12`; `config/urls.py:60-79` (login, logout, session, password change only). Tests: `test_phase6_guardian_accounts::test_everything_redirects_to_password_change`; `test_credential_slip`.
- **GUA-02** `core/portal_views.py:74-104`; `core/portal.py:16-41,239`; `templates/portal/home.html:12-40`; `templates/portal/child.html:12`. Tests: `test_phase6_portal_shell::test_lists_only_granted_students`, `::test_pending_review_listed_without_link`, `::test_switcher_shows_every_visible_child`, `::test_query_count_constant`.
- **GUA-03** `core/portal_views.py:180-199`; `core/announcements.py:157-186`. Tests: `test_phase7_announcements::test_whole_school_reaches_every_portal_guardian`, `::test_class_and_section_reach_only_matching_guardians`, `::test_one_grant_per_guardian_with_two_children`.
- **GUA-04** Phase 7 plan:100. No inbound route in `core/portal_urls.py` (all views are `require_safe`, read-only).
- **GUA-05 to GUA-07** `rg -i "leave (application|request)|LeaveRequest|grievance"` in `core/`, `accounts/`, `templates/` (non-test): no match. No request model among the classes in `core/models.py`.
- **GUA-08** `core/models.py:4154-4157` (document types BONAFIDE, REPORT_CARD, ATTENDANCE_SUMMARY; no TC).
- **GUA-09** `core/portal_views.py:166-177`; `core/models.py:4146-4183` (IssuedDocument; docstring says triggers refuse UPDATE/DELETE). Tests: `test_phase7_documents::test_guardian_downloads_own_childs_card`, `::test_other_guardians_child_is_404`, `::test_stale_publication_gives_nothing_to_guardian_or_office`, `::test_guardian_cannot_use_the_office_route`, `::test_update_is_refused`, `::test_delete_is_refused`.
- **GUA-10** See §FIN.

### COM

- **COM-01, COM-02** Phase 7 plan:100.
- **COM-03, COM-07** `core/notifications.py:254-290` (`marked_sent_by`, `dismissed_by`, `dismiss_reason`). Test: `test_phase7_notifications::test_dismiss_needs_reason_and_happens_once`.
- **COM-04** `core/announcements.py:47-70` (withdraw); announcement routes have no edit (`core/urls.py:502-510`); `core/migrations/0057_notification_history_guards.py:72-100`; `core/migrations/0089_recordcorrection_history_guards.py:23`; `core/publication.py:376-428`. Tests: `test_phase7_announcements::test_withdraw_records_who_when_and_why`; `test_phase7_notifications::test_consent_is_append_only`, `::test_consent_latest_row_wins`.
- **COM-05** `core/notifications.py:41-57` (consent), `:64-100` (enqueue), `:140-183` (portal access), `:185-275` (queue, lock, recheck). Tests: `test_phase7_send_queue_recheck::test_grant_revoked_before_display`, `::test_relationship_ended_before_display`, `::test_account_link_revoked_before_display`, `::test_login_deactivated_before_display`, `::test_pending_review_before_display`, `::test_message_for_a_child_never_granted_is_not_shown`; `test_phase7_notifications::test_to_send_skips_withdrawn_consent`, `::test_mark_sent_after_opt_out_skips`, `::test_teacher_cannot_record_consent`.
- **COM-06** `core/models.py:4011` (`idempotency_key` unique); `core/notifications.py:90-100`. Tests: `test_phase7_alerts::test_absent_student_gets_one_prepared_alert_per_portal_guardian`; `test_phase7_notifications::test_mark_sent_twice_is_refused`; `test_announcement_publish_once` (all tests).

### MOB

- **MOB-01** See ADM-08.
- **MOB-02** `templates/partials/_tabbar.html:1-8`; `templates/base.html:14,63`. Tests: `test_ui_teacher_daily`, `test_ui_teacher_cards`, `test_ui_teacher_polish`, `test_ui_teacher_timetable`.
- **MOB-03** `templates/portal/_portal_nav.html:5-9`; `templates/portal/_tabbar.html`; `templates/portal/attendance.html:33`. Tests: `test_ui_guardian_nav_consistency`, `test_ui_guardian_cards`, `test_portal_query_budget`.
- **MOB-04** `accounts/middleware.py:64-100`; `accounts/models.py:164` (LoginFailure); `static/js/erp.js:1130-1170`. `rg -i "webauthn|passkey|navigator.credentials"`: no match. Tests: `test_phase6_security::test_rule_a_refuses_even_the_right_password`; `test_session_errors_audit18::test_answers_while_a_password_change_is_due`.
- **MOB-05** See GUA-03.
- **MOB-06 to MOB-09** Search for `serviceWorker|service-worker|sw.js|caches.|indexedDB|SyncManager|PushManager|pushsubscription|vapid` outside `static/vendor/`: no match. `core/pwa_views.py:3` states online-only. localStorage uses: `templates/base.html:12`, `static/js/erp.js:142,150,186` (sidebar), `:984,997` (install-bar dismissal). Test: `test_pwa_gate1::test_no_service_worker_is_registered`.
- **MOB-10** `docs/ROADMAP.md:100`; no native project in the repository.
- **Installability** `core/pwa_views.py`; `config/urls.py:61-62`; `templates/partials/_pwa_head.html`; `static/pwa/` (`icon-192.png`, `icon-512.png`, `icon-maskable-512.png`, `apple-touch-icon.png`); `static/js/erp.js:952-1010`. Tests: `test_pwa_gate1::test_public_manifest_served_with_manifest_content_type`, `::test_icons_cover_required_sizes_and_a_maskable_icon`, `::test_manifest_loads_while_password_change_is_required`.
- **HTMX** loaded only at `core/templates/core/my_attendance.html:52`; `rg "hx-boost|hx-push-url"`: no match.

### ANA

- **ANA-01** `core/dashboard.py:39-56`; `core/templates/core/report_missing_attendance.html:42-47`. Tests: `test_admin_overview_analytics::test_counts_only_submitted_registers_today`, `::test_submitted_register_is_counted`.
- **ANA-02** See TEA-04.
- **ANA-03** `core/analytics.py:353-376`; `core/views.py:1011-1040`.
- **ANA-04** `core/publication.py:376-428`; `core/views.py:3505-3510`; `core/nav_badges.py:33`; `core/dashboard.py:71-76`; `accounts/models.py:88` (PUBLICATION_STALE security event). Tests: `test_phase6_publication::test_correction_makes_it_stale_and_hidden`; `test_admin_overview_analytics::test_published_ring_counts_students_and_drops_stale_versions`.
- **ANA-05** Teachers only: `core/teacher_views.py:35`, `core/templates/core/teacher_list.html:49`, `teacher_detail.html:14`. `rg "last_login|never signed"` found no guardian use.
- **ANA-06** `rg -i "read_at|acknowledg|seen_at|opened_at"` in code: no match.
- **ANA-07** No request model.
- **ANA-08** `core/guardian_access.py:112-175`; `core/dashboard.py:79-85`; `core/notifications.py:176-183`. Tests: `test_phase6_portal_shell::test_pending_review_listed_without_link`; `test_phase7_send_queue_recheck::test_pending_review_before_display`; `test_phase6_access_boundary::test_missing_or_partial_decisions_change_nothing`.
- **ANA-09** See §FIN.

### FIN

- Search `\bfees?\b|payment|invoice|receipt|instal+ment|balance_due|razorpay|stripe` across `*.py`, `*.html`, `*.js` (excluding docs, vendor, worktrees, GTM folders): only `core/demo_refresh.py:295-296` (demo notice text), plus tests that assert fee wording is absent (`core/tests/test_phase6_portal_shell.py:74-81`, `core/tests/test_ui_foundation.py:240-251`) or use "Fee" as sample notice text (`core/tests/test_phase7_announcements.py:229`, `core/tests/test_ui_announcement_list.py:47`).
- `ls core/migrations | grep -i -E "fee|pay"`: no match (95 migration files).
- No fee route in `core/urls.py`, `core/portal_urls.py`, `config/urls.py`.
- Notification types: `core/models.py:3983-4050`.
- Issue #274 read with `gh issue view 274` (OPEN).

## 3. Authorization evidence (cross-cutting)

- `core/authorization.py:14-26`: `administrator_required` = `login_required` + `permission_required(raise_exception=True)`.
- `core/authorization.py:112` `teacher_required`; `:237` `can_take_attendance`; `:100` `can_enter_results`; `:252-289` teacher student scope; `:400` `guardian_required`; `:372-398` per-grant visibility; `:418-433` `user_areas`.
- `core/navigation.py:139-160`: area chosen only among entitled areas.
- Route inventory: `core/tests/route_permissions.json` (191 routes). Routes without a Django permission are guarded in other ways: 18 `teacher_required`, 8 `guardian_required`, `term-remarks` (`login_required` plus an in-body check at `core/views.py:878-893`), the public manifest, install help, home, choose-area, session status, framework-owned auth routes, and `school-logo` (conditional).
- Test: `test_security_gate4b_route_inventory`.

## 4. Commands used

| Command | Outcome |
| --- | --- |
| `git status --short` | 38 paths, all untracked (`??`); no tracked modifications |
| `git branch --show-current` | `docs/erp-benchmark-codebase-audit` |
| `git rev-parse HEAD` | `2edeee60d08f097080a02660453b121ee5721b3c` |
| `git remote get-url origin` | `https://github.com/Joseph5157/school-erp` |
| `git fetch origin docs/erp-benchmark-codebase-audit`; `git rev-parse` | Remote branch has the same SHA as HEAD |
| `git merge-base --is-ancestor origin/main HEAD` | True (`origin/main` = `febc57f`) |
| `python --version` | Python 3.13.15 |
| `requirements.txt`, `pyproject.toml`, `.github/workflows/ci.yml`, `config/settings.py` (grep) | Django 5.2.17, psycopg 3.3.5; CI on PostgreSQL 16; SQLite fallback for local only |
| `find . -name AGENTS.md` (excluding worktrees and GTM) | None |
| `gh issue view 274 --json title,state,body` | OPEN, deferred fee direction |
| `rg` searches listed in §2 | As recorded per candidate |
| Python read of `core/tests/route_permissions.json` | 191 routes; routes without a permission listed in §3 |
| Test suite | Not run (read-only audit; CI is authoritative) |

No command wrote to the database, changed a tracked file, switched branches, committed or pushed. Network use was limited to `git fetch` and `gh issue view`.

## 5. Could not be verified

- Whether every admin page is usable at phone width (no device or browser run; G-04).
- Real network-loss behaviour on devices; HTMX error paths were read, not exercised.
- PWA Gate 2 device checks (Android, iPhone, desktop install).
- Whether the tests pass on this HEAD (not run; CI state not checked for this branch).
- Teacher speed for marks entry and attendance (no measurement exists).
- The unmerged `feature/admin-home` branch (PRs #270–#273), which may change the admin overview findings once merged.
- The meaning of "students needing attention" for a real school (`core/marks_analytics.py:331`); its rules were not reviewed in depth.
