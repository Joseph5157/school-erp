# UI References (Mobbin)

Status: 34 team picks recorded 2026-10-14. U1 Foundation merged (PR #44). The admin audit's Phase 0 safety fixes are in PR #54; Phase 1 responsive shell and shared component foundation is implemented on branch `ui/audit-phase1-responsive-foundation`. U2 Teacher daily screens implemented on branch `ui/u2-teacher-daily`; U3 Teacher marks and students implemented on branch `ui/u3-teacher-marks`; Phase 2 admin Overview landing page and breadcrumbs (with a section-aware sidebar) are implemented on branch `ui/audit-phase2-overview-navigation`; Phase 3A shared data table (sort, pagination, status filters on the attendance register, student and applicant lists) is implemented on branch `ui/audit-phase3a-data-table`; U4–U7 pending (see roadmap).
Implementation plans: `docs/superpowers/plans/2026-10-14-ui-redesign-roadmap.md`.

Full illustrated report (private artifact, share from its Share menu):
https://claude.ai/artifact/7zr4DVJGh3fB5ZMbF8xxEQ

Mobbin screens are third-party app screenshots, so this file keeps links only.

## Who uses what

| Group | Main device | Areas |
|---|---|---|
| School office | Desktop | Setup, admissions, assignments, attendance admin, results, publication, reports, audit |
| Teachers | Phone | My day, take attendance, marks entry, my students |
| Guardians | Phone | Portal home, child's attendance, report cards |

## Known UI problems (from `origin/main`)

- `templates/base.html` and `registration/login.html` have no viewport meta tag, so staff pages render shrunk on phones.
- The top bar uses `navbar-expand` and never collapses; up to 8 office + 4 teacher links in one row.
- Wide tables on phones: report card (7 columns), attendance list (6), marks entry (select + input per row).
- Attendance capture uses small radio buttons per student.
- Student, guardian and applicant lists have no filters, counts or paging.
- Static storage is `CompressedManifestStaticFilesStorage`, so any `{% static %}` tag fails until `collectstatic` has run (this broke `/admin/login/` locally).

## Team picks (34)

| Need | Screen | Take from it |
|---|---|---|
| 1.1 Desktop app shell | [Square](https://mobbin.com/screens/886e2593-684e-4167-ae7f-46141a76b360) | Grouped, expandable left sidebar |
| 1.2 Phone navigation | [Shopify](https://mobbin.com/screens/fcfd23ed-f847-402d-ab2f-81f826fd847e) | Full-height menu with expandable groups |
| 1.3 Sign in | [ShopBack](https://mobbin.com/screens/a5f63e2a-29cb-466d-a53f-7867096747ad) | Two fields, helper text, one button |
| 2.1 Lists | [HoneyBook](https://mobbin.com/screens/96ea2ca5-0bf9-4838-a137-58ea907f0a5e), [Sprig](https://mobbin.com/screens/abdc1314-5b82-4136-b99b-2462e0079afc), [Calendly](https://mobbin.com/screens/4fa38a4e-3819-4092-82a3-a37df95a38e2) | Count + status pills; filter buttons with picked values; saved views and paging |
| 2.2 Admissions pipeline | [HoneyBook](https://mobbin.com/screens/f5036961-b128-458f-a143-ac2f6abc8d0d) | Board by status with counts |
| 2.3 Record pages | [Calendly](https://mobbin.com/screens/da0b2691-7235-44b0-82cf-b1a4a89d1405) | Tabs, dated activity feed, details rail |
| 2.5 Academic calendar | [Calendly](https://mobbin.com/screens/260f2a45-9d33-4b9b-a17e-dcdadaf6fca3) | Month grid, state per day |
| 2.7 Reports hub | [Shopify](https://mobbin.com/screens/60c99ad3-212d-4383-9a10-afe66d0facfa), [HoneyBook](https://mobbin.com/screens/5ed1ee20-c294-478f-9907-e37fbe348336) | Searchable report list with category chips; From/To dates and headline numbers |
| 2.8 History and audit | [Basecamp](https://mobbin.com/screens/07446502-ce66-4714-a13d-fd4d6b9707a9) | Readable vertical timeline |
| 3.1 My day | [Insight Timer](https://mobbin.com/screens/71782ac6-9f21-4620-8cc7-e1d53c6f57c0) | Week strip, progress, one action per card |
| 3.2 Take attendance | [Luma](https://mobbin.com/screens/9dd54074-60d0-4ca4-8723-fc41ad08b5ef) | Count tabs, bottom sheet with one big action |
| 3.3 Marks entry on phone | [Yazio](https://mobbin.com/screens/8d4da5f3-dcf9-4d31-a452-0331d6b3216d) | Keypad with up/down to move rows |
| 3.4 My students | [Cash App](https://mobbin.com/screens/b30ee8ed-caff-4863-9f99-38312d2264e6) | Initials avatars in search results |
| 4.1 Child switcher | [Cash App](https://mobbin.com/screens/a62eac79-fa7d-4a4f-826d-e159c7e2f2f9) | "Choose" sheet with a check on the current child |
| 4.2 Child's attendance | [Insight Timer](https://mobbin.com/screens/6792d749-c9b2-452e-971a-6562ec9ee737), [MacroFactor](https://mobbin.com/screens/20a1a56c-579e-43be-acc1-56ef497595b9) | Month card with summary line; legend under grid |
| 4.3 Report cards | [Coursera](https://mobbin.com/screens/58a40a06-8525-46ec-aeb2-d67f838ea306) | Assessment rows, value on the right |
| 5.1 Section page | [Google Classroom people](https://mobbin.com/screens/f50252ba-15b7-4e50-b4a2-2bbfa07c5b43), [Google Classroom class cards](https://mobbin.com/screens/efee226c-f56a-4bae-94cc-7bf8306eeceb) | Teachers + students on one page with count; one card per class |
| 5.2 Gradebook (covers 2.6) | [Google Classroom marks](https://mobbin.com/screens/e8387b5e-1dde-48c3-b0e9-204cbfe310c1) | Date and "out of N" in column headers; blanks read "No mark" |
| 5.3 Office attendance grid | [Fibery](https://mobbin.com/screens/9454b4cf-8d8a-4d16-bebf-2a081b4bbebd) | Present column per student, footer totals |
| 5.4 Teacher's class overview | [SchoolAI](https://mobbin.com/screens/14950322-bbc7-4cea-90ed-66e9909b8468) | Student rows with status chips |
| 5.5 Report card, larger screens | [Coursera web](https://mobbin.com/screens/35b8baea-dca0-422b-83ee-01dd411da127) | Item / status / grade table; drop weight and overall % |
| 5.7 Office home | [HoneyBook](https://mobbin.com/screens/42826bc0-101e-41ce-820f-3333f5788168) | Date, headline counts, Create new shortcuts |
| 5.8 Publish / withdraw results | [Sweatpals](https://mobbin.com/screens/16a5c747-079b-4175-9b14-a7459648bc7f) | Confirmation listing what changes, Save as draft alternative |
| 5.9 Grading scale editor | [Zoho CRM](https://mobbin.com/screens/a2dd5732-8d64-4f8f-bfc5-ac21443b0852) | Range rows with add/remove |
| 5.10 Add people to a section | [Square](https://mobbin.com/screens/8b317877-df63-4b01-a60d-35c69b10d591) | Searchable checklist dialog with count and one Save |
| 5.11 Empty states | [Sprig](https://mobbin.com/screens/20b41041-1173-4e0f-af93-10be683f33e1) | Keep headers/filters visible; icon + two lines |
| 5.12 Change password | [Fresha](https://mobbin.com/screens/24743e9b-a85a-4718-ab51-c4b52da1dddd) | Three fields with Show toggles |
| 5.13 Attendance feedback | [Luma](https://mobbin.com/screens/e02a3aa3-e02c-4019-82cf-163fa8b1eafd) | Toast + counts updating |
| 5.14 Announcements (Phase 7) | [Mindtrip](https://mobbin.com/screens/95b3d1e5-2adc-4935-9104-247464e1d0b4) | Unread count, Mark all as read |

Still open:
- 1.4 / 5.6 Switching roles — no pick. Default: reuse the 4.1 Cash App "choose" sheet style.
- 2.4 Admission and enrolment forms — only flows (Workable, Gusto); decide during the admissions plan.

## Rules the design must keep

- Draft vs submitted attendance; an unopened register is never "present".
- Blank marks mean "not marked yet", not absent.
- Report cards show each assessment separately: no totals, weighting or ranks.
- Guardians sign in with a username from their credential slip, not an email.
- Navigation links stay permission-gated in templates; views still enforce access.
