# Admin Home PR 4: Parents Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the interim Parents tab with three cards: New announcement (form + sent list), Parent engagement, and Guardian access (sections missing a parent on the portal, with Invite; access reviews, with Review).

**Architecture:** A new `core/home_parents.py` builds the tab's data in a fixed number of queries, the same way `core/home_academics.py` does for Academics. The announcement form on the card posts to the existing `core:announcement-create` view, so the preview-then-publish safety step and the one-time token stay exactly as they are; nothing new handles POST. "Invite" opens the Students list filtered to one section and a new "No parent on the portal" chip.

**Tech Stack:** Django 5, server-rendered templates, PostgreSQL, the Everclass design system in `static/css/erp.css`.

**Spec:** `docs/superpowers/specs/2026-11-18-admin-home-tabs-design.md` (the Parents tab section; Owner decision 3). The spec file is untracked in the main checkout at `C:\Users\sikha\school-erp\docs\superpowers\specs\`.

**Branch:** worktree `C:\Users\sikha\school-erp\.worktrees\admin-home-pr4`, branch `ui/admin-home-parents`, cut from `origin/feature/admin-home` (1120153). The PR targets `feature/admin-home`, never main.

## Global Constraints

- The Parents tab answers "are parents with us?" Its cards: "1. New announcement form (title, message, audience) + sent list; 2. Parent engagement: % of students with a parent account, % of parents active; 3. Guardian access: classes with missing accounts (Invite) + access requests (Review)."
- Engagement launches with "% of parents who logged in this month" from existing login data (`User.last_login`). Announcement read tracking is a later PR: do not add read records.
- Nothing repeats across tabs. Every list row links somewhere when the viewer may open it.
- No rings, gauges or new chart types. Cards, lists and stage counts only.
- Phone first; desktop is the same cards on a wider grid.
- New templates use only `erp-` classes. Banned in the page body: `class="btn`, ` btn-`, `visually-hidden`, `text-muted`, `"progress"`, `progress-bar`, `mt-auto`, `align-self-start` (`HomeTabsTests.BANNED`). Use `erp-sr-only`, not `visually-hidden`. The shared `partials/_form_field.html` uses `visually-hidden`, so the card must not include it.
- "Students with a parent on the portal" uses the same rule as who can read a notice: a current enrollment (effective today and inside its academic year) and at least one guardian with an active, non-pending access grant and an active portal login (`notification_producers.portal_grants_for_students`).
- "Parents" are guardians with an active `GuardianAccount` whose login `is_active`. "Signed in this month" means `user.last_login` is on or after local midnight on the 1st of the business month.
- Percent: `round(100 * part / whole)` as an int; `None` when `whole == 0`.
- Security Gate 4B: counts carry no personal data and show for every administrator who can open the overview. Student or guardian names need both `data_access.STUDENT` and `data_access.GUARDIAN`. Links show only when the viewer has the permission the destination page needs.
- Tests: `DJANGO_DEBUG=True ../../.venv/Scripts/python.exe manage.py test <labels> --noinput`. Run UI tests with `--pattern="test_ui*.py" --parallel 4` after CSS edits. Never run the full suite locally (CI does). Ruff must be clean (`ruff check .`; 0.16.7 wants `zip(strict=)`).
- The business date comes from `business_today()`. Tests pin it to `TODAY = 2026-07-14` through `AnalyticsFixture` (it patches `core.views.business_today`); new code takes `today` as an argument and never calls `business_today()` itself.

## Review Focus

1. **A grant waiting on a review.** A guardian whose only grant is pending a date-based review cannot read notices, so their child must not count as "on the portal". Pinned by `test_pending_grant_does_not_count` (Task 1).
2. **A deactivated guardian login.** An account whose user has `is_active=False` is neither a parent on the portal nor a child's portal parent. Pinned by `test_inactive_login_counts_nowhere` (Task 1).
3. **Sign-in on the last day of last month in local time.** The month boundary is local midnight, not UTC. Pinned by `test_signed_in_this_month_uses_local_midnight` (Task 1).
4. **The home form bounces back with errors.** An invalid post from the card must land on the normal New notice page with the errors and the typed text, not a blank home. This needs no new code: the form posts to `announcement-create`, which renders `announcement_form.html` on errors. Pinned by `test_card_form_errors_land_on_new_notice_page` (Task 3).
5. **Many sections.** The tab's query count must not grow with the number of sections or students. Pinned by `test_parents_tab_queries_do_not_grow_with_sections` (Task 3).

---

### Task 1: Parents tab data (`core/home_parents.py`)

**Files:**
- Create: `core/home_parents.py`
- Modify: `core/notification_producers.py:42-57` (`portal_grants_for_students` gains `on_date=None`, passed to `guardian_access.pending_map(grants, on_date)`)
- Test: `core/tests/test_home_parents.py` (new)

**Interfaces:**
- Produces, all in `core/home_parents.py`:
  - `NOTICE_LIMIT = 5`
  - `portal_student_ids(student_ids, today) -> set[int]`: the students among `student_ids` with at least one grant from `portal_grants_for_students(student_ids, on_date=today)`.
  - `engagement(today) -> dict` with keys `students`, `students_on_portal`, `students_pct`, `parents`, `parents_active`, `parents_pct` (the two `_pct` values are int or None).
  - `missing_accounts(today, *, invite_links) -> list[dict]`: one row per current section with at least one student missing a portal parent, with keys `section_id`, `class_name`, `section_name`, `missing`, `students`, `url` (str or None).
  - `access_reviews(today, *, with_names, decide_links) -> dict` with keys `count`, `url` (the reviews list), and `rows` (a list of dicts with keys `student_name`, `guardian_name`, `url`, or None when `with_names` is False).
  - `sent_notices(limit=NOTICE_LIMIT) -> list[dict]` with keys `title`, `audience`, `published_on` (date), `withdrawn` (bool), `url`.

- [ ] **Step 1: Write the failing tests**

Build on `MarksFixture` from `core/tests/test_admin_overview_analytics.py` (it gives `self.s1`, `self.s2` in Grade 1 A, `self.class_grade`, `self.section`, `self.admin_user` and `enroll_student`). Copy the `link` / `account` / `grant` helpers' shape from `core/tests/test_ui_guardian_cards.py:57-74`. Tests in class `HomeParentsDataTests(MarksFixture, TestCase)`:

```python
def test_engagement_counts_students_with_a_portal_parent(self):
    self.portal_parent(self.s1)                       # guardian + active account + grant
    e = home_parents.engagement(TODAY)
    self.assertEqual((e["students"], e["students_on_portal"], e["students_pct"]), (2, 1, 50))

def test_pending_grant_does_not_count(self):
    # A grant is pending only when its student has no enrollment effective TODAY (end s1's placement).
    # Such a student is outside engagement anyway; the chip lists unplaced students, so check the helper.
    ...
    self.assertEqual(home_parents.portal_student_ids([s1_student.pk], TODAY), set())

def test_inactive_login_counts_nowhere(self):
    self.portal_parent(self.s1, active=False)
    e = home_parents.engagement(TODAY)
    self.assertEqual((e["students_on_portal"], e["parents"]), (0, 0))

def test_parents_active_this_month(self):
    a = self.portal_parent(self.s1); b = self.portal_parent(self.s2)
    set_last_login(a, aware(2026, 7, 3, 9, 0)); set_last_login(b, aware(2026, 6, 20, 9, 0))
    e = home_parents.engagement(TODAY)
    self.assertEqual((e["parents"], e["parents_active"], e["parents_pct"]), (2, 1, 50))

def test_signed_in_this_month_uses_local_midnight(self):
    a = self.portal_parent(self.s1)
    set_last_login(a, local(2026, 6, 30, 23, 59))     # last month, local time
    self.assertEqual(home_parents.engagement(TODAY)["parents_active"], 0)
    set_last_login(a, local(2026, 7, 1, 0, 0))
    self.assertEqual(home_parents.engagement(TODAY)["parents_active"], 1)

def test_empty_school_percentages_are_none(self):
    # no enrollments effective TODAY and no accounts
    e = home_parents.engagement(datetime.date(2030, 1, 1))
    self.assertEqual((e["students_pct"], e["parents_pct"]), (None, None))

def test_missing_accounts_rows_and_order(self):
    # Grade 1 A: s1 on portal, s2 not -> missing 1 of 2. Grade 2 A: two students, none -> 2 of 2.
    rows = home_parents.missing_accounts(TODAY, invite_links=True)
    self.assertEqual([(r["class_name"], r["section_name"], r["missing"], r["students"]) for r in rows],
                     [("Grade 2", "A", 2, 2), ("Grade 1", "A", 1, 2)])
    self.assertEqual(rows[1]["url"],
                     reverse("core:student-list") + f"?section={self.section.pk}&chip=no_portal")

def test_missing_accounts_skip_full_sections_and_hide_links(self):
    self.portal_parent(self.s1); self.portal_parent(self.s2)
    self.assertEqual(home_parents.missing_accounts(TODAY, invite_links=False), [])
    # and with one missing, invite_links=False gives url None

def test_missing_accounts_tie_break_by_class_order_then_section(self): ...

def test_student_counted_once_under_latest_placement(self):
    # two effective enrollments for one student: counted only in the later one (start_date, then pk)

def test_access_reviews_rows_and_links(self):
    # one pending grant -> count 1, row names, url to guardian-access-review-decide
    r = home_parents.access_reviews(TODAY, with_names=True, decide_links=True)
    self.assertEqual(r["count"], 1)
    self.assertEqual(r["rows"][0]["url"], reverse("core:guardian-access-review-decide", args=[grant.pk]))
    self.assertEqual(r["url"], reverse("core:guardian-access-reviews"))
    r = home_parents.access_reviews(TODAY, with_names=True, decide_links=False)
    self.assertEqual(r["rows"][0]["url"], reverse("core:guardian-access-reviews"))
    self.assertIsNone(home_parents.access_reviews(TODAY, with_names=False, decide_links=True)["rows"])

def test_sent_notices_newest_first_with_withdrawn_flag(self):
    # three notices, one withdrawn; limit=2 returns the two newest
    rows = home_parents.sent_notices(limit=2)
    self.assertEqual([r["title"] for r in rows], ["Third", "Second"])
    self.assertEqual(rows[0]["audience"], "Whole school")
    self.assertEqual(rows[0]["url"], reverse("core:announcement-detail", args=[third.pk]))

def test_portal_grants_for_students_honours_on_date(self):
    # a grant pending on one date is usable on a date when the enrollment is effective
```

Make each `...` a real test with its own data; the comments name what to build. Use `django.utils.timezone.make_aware` for `local(...)`, so the test follows `settings.TIME_ZONE`. Create announcements through `core.announcements.publish(...)`; withdraw one with `announcements.withdraw(...)`.

- [ ] **Step 2: Run the tests and watch them fail**

Run: `DJANGO_DEBUG=True ../../.venv/Scripts/python.exe manage.py test core.tests.test_home_parents --noinput`
Expected: FAIL with `ModuleNotFoundError` / `ImportError` for `core.home_parents`.

- [ ] **Step 3: Implement**

- Current placements: `AcademicEnrollment.objects.effective_on(today).filter(academic_year__end_date__gte=today)`, which is the rule in `announcements._current_enrollments`. Copy it; don't import the private function. Read `student_id`, `section_id`, `start_date`, `pk`, the section's name and class name, and the class's `display_order` in one `values_list`. Keep one placement per student: the latest `start_date`, then the highest pk.
- `engagement`: students = the distinct students in placements. `students_on_portal` comes from `portal_student_ids`. Parents = `GuardianAccount.objects.filter(revoked_at__isnull=True, user__is_active=True)`, counting distinct `guardian_id`. Active means `user__last_login__gte=timezone.make_aware(datetime.datetime.combine(today.replace(day=1), datetime.time.min))`.
- `missing_accounts`: group placements by section in Python. Order rows by missing (descending), then class `display_order`, class name and section name. Build the URL with `reverse("core:student-list") + f"?section={section_id}&chip=no_portal"`.
- `access_reviews`: `guardian_access.pending_reviews(today)`. Names come from `row["grant"].student_guardian.student.full_name` and `.guardian.full_name`.
- `sent_notices`: `Announcement.objects.select_related("class_grade", "section__class_grade").order_by("-published_at", "-pk")[:limit]`. The audience text is `notice.audience_label()`. `published_on` is `timezone.localdate(notice.published_at)`.
- The total query count must not depend on the number of sections or students: no queries in loops.

- [ ] **Step 4: Run the tests and watch them pass**

Run: `DJANGO_DEBUG=True ../../.venv/Scripts/python.exe manage.py test core.tests.test_home_parents core.tests.test_notification_producers --noinput` (if the second label doesn't exist, run the test module that covers `portal_grants_for_students`; `grep -rl portal_grants_for_students core/tests` finds it).
Expected: all pass. `ruff check core/home_parents.py core/notification_producers.py core/tests/test_home_parents.py` is clean.

- [ ] **Step 5: Commit**

```bash
git add core/home_parents.py core/notification_producers.py core/tests/test_home_parents.py
git commit -m "feat(home): Parents tab data: engagement, sections missing a portal parent, reviews, sent notices"
```

---

### Task 2: Students list chip "No parent on the portal"

**Files:**
- Modify: `core/views.py`: `STUDENT_CHIP_CHOICES` (around line 4033), the chip builder (around 4060-4085, which already skips `absent` without its permission), and `student_list` (around 4086-4150)
- Test: `core/tests/test_ui_student_list_filters.py`

**Interfaces:**
- Consumes: `home_parents.portal_student_ids(student_ids, today)` (Task 1).
- Produces: the URL `?section=<id>&chip=no_portal` on `core:student-list`, which lists the section's students with no parent on the portal. Task 1's Invite links already point here.

- [ ] **Step 1: Write the failing tests**

```python
def test_no_portal_chip_lists_students_without_a_portal_parent(self):
    # one student with a portal parent, one without
    response = self.administrator.get(self.url, {"chip": "no_portal"})
    names = [s.full_name for s in response.context["students"]]
    self.assertIn(without.full_name, names); self.assertNotIn(with_parent.full_name, names)
    self.assertContains(response, "No parent on the portal")

def test_no_portal_chip_combines_with_section(self):
    response = self.administrator.get(self.url, {"chip": "no_portal", "section": section.pk})
    # only that section's students without a portal parent

def test_no_portal_chip_needs_guardian_permission(self):
    # a viewer with view_student but not view_guardian: chip not offered, ?chip=no_portal ignored (all students listed)
```

Use the file's existing fixture and helpers. Add guardian helpers in the style of `test_ui_guardian_cards.py:57-74` if the file has none.

- [ ] **Step 2: Run the tests and watch them fail**

Run: `DJANGO_DEBUG=True ../../.venv/Scripts/python.exe manage.py test core.tests.test_ui_student_list_filters --noinput`
Expected: the 3 new tests FAIL (the chip is unknown, so every student is listed and the label is missing).

- [ ] **Step 3: Implement**

- Add `("no_portal", "No parent on the portal")` as the last entry of `STUDENT_CHIP_CHOICES`.
- Offer the chip only when the viewer has `data_access.GUARDIAN`, the same way `absent` is gated: skip it in the chip builder and reset `chip = None` in `student_list` when the permission is missing.
- Filter: `ids = list(students.values_list("pk", flat=True))`, then `students = students.exclude(pk__in=home_parents.portal_student_ids(ids, business_today()))`.

- [ ] **Step 4: Run the tests and watch them pass**

Run: `DJANGO_DEBUG=True ../../.venv/Scripts/python.exe manage.py test core.tests.test_ui_student_list_filters core.tests.test_home_parents --noinput`
Expected: all pass; ruff clean.

- [ ] **Step 5: Commit**

```bash
git add core/views.py core/tests/test_ui_student_list_filters.py
git commit -m "feat(students): 'No parent on the portal' chip, the target of the home Invite links"
```

---

### Task 3: The Parents tab cards (view and templates)

**Files:**
- Modify: `core/home_parents.py` (add `parents_tab_context`)
- Modify: `core/views.py`: replace `_parents_tab` (around line 1028) and its call in `admin_overview`
- Rewrite: `templates/partials/home/_parents.html`
- Create: `templates/partials/home/_notice_form.html`, `_notice_row.html`, `_missing_row.html`, `_review_row.html`
- Modify: `core/dashboard.py`: delete `parents_glance` (its only caller is `_parents_tab`); delete the tests that call it in `core/tests/test_ui_admin_overview_glance.py`
- Test: `core/tests/test_ui_admin_home_tabs.py`

**Interfaces:**
- Consumes: everything Task 1 produces.
- Produces: `parents_tab_context(today, *, notice_form, show_sent, invite_links, include_reviews, review_names, decide_links, guardians_link) -> dict`, with keys:
  - `form` (an unbound `AnnouncementForm()` or None) and `form_url` (`reverse("core:announcement-create")`)
  - `sent` (a list or None) and `all_notices_url` (str or None)
  - `engagement` and `guardians_url` (`reverse("core:guardian-list")` or None)
  - `missing` (a list)
  - `reviews` (a dict or None)
- The view passes these flags:

| Flag | Value |
|---|---|
| `notice_form` | `has_perm("core.add_announcement")` |
| `show_sent` | `has_perm("core.view_announcement")` |
| `invite_links` | `has_perm(data_access.STUDENT) and has_perm(data_access.GUARDIAN)` |
| `include_reviews` | `has_perm("core.view_guardianaccessreview")` |
| `review_names` | `has_perm(data_access.STUDENT) and has_perm(data_access.GUARDIAN)` |
| `decide_links` | `has_perm("core.add_guardianaccessreview")` |
| `guardians_link` | `has_perm(data_access.GUARDIAN)` |

**Card markup.** Each card is `<article class="erp-card erp-card--X">` inside `<section class="erp-analytics{modifiers}" aria-labelledby="parents-title">`, with `<h2 class="erp-sr-only" id="parents-title">Parents</h2>`.

1. **`erp-card--notice`**, title "New announcement". It renders when `form` or `sent` is set.
   - Form, when `form` is set: `<form method="post" action="{{ p.form_url }}" class="erp-form erp-notice-form" data-erp-audience-form>` with `{% csrf_token %}`, then `_notice_form.html`:
     - title and body fields, each in `erp-field` markup with the char counter partial; the required mark uses `erp-required-mark` plus `<span class="erp-sr-only"> (required)</span>`;
     - `{{ form.audience.as_field_group }}` inside `<div class="erp-field">`;
     - class and section in `data-erp-audience-field="CLASS"` / `"SECTION"` wrappers;
     - `<button type="submit" class="erp-btn erp-btn--primary">Preview notice</button>`;
     - the helper line `<p class="erp-field-help">You'll see a preview before anything is sent.</p>`.
   - The body field's label reads "Message". Set `label="Message"` on `AnnouncementForm.body`; the spec says "title, message, audience", and the New notice page benefits too.
   - Sent list, when `sent` is set: `<h4 class="erp-home-sub">Sent</h4>`, then the rows through `_fold_rows.html` with `_notice_row.html`. Each row shows the title, with "{{ audience }} · {{ published_on|date:'j M' }}" and " · Withdrawn" when withdrawn in `erp-home-meta`, and the link "Open" with an sr-only title. Then `<p><a href="{{ p.all_notices_url }}">All announcements</a></p>`. With no rows: `<p class="erp-card-empty">No notices sent yet.</p>`.
2. **`erp-card--engagement`**, title "Parent engagement". `<ul class="erp-stage-list erp-stage-list--two">` holds two `li.erp-stage`:
   - count `{{ students_pct }}%`, label "Students with a parent on the portal", `<span class="erp-stage-meta">{{ students_on_portal }} of {{ students }}</span>`;
   - count `{{ parents_pct }}%`, label "Parents who signed in this month", meta `{{ parents_active }} of {{ parents }}`.
   - A `None` percent shows "–" with the meta text "No students in a class yet" / "No parents on the portal yet".
   - Below the list: `<p class="erp-analytics-sub">Notice reads aren't tracked yet.</p>`. When `guardians_url` is set: `<a href="{{ guardians_url }}">Guardians</a>`.
3. **`erp-card--access`**, title "Guardian access".
   - `<h4 class="erp-home-sub">Missing a parent on the portal</h4>`, then `missing` through `_fold_rows.html` (noun "sections"). `_missing_row.html` shows "{{ class_name }} {{ section_name }}", the meta "{{ missing }} of {{ students }} students", and, when `url` is set, the link "Invite" with sr-only " parents in {{ class_name }} {{ section_name }}".
   - Empty: "Every student in a class has a parent on the portal." When `engagement.students == 0`: "No students in a class yet."
   - When `reviews` is set: `<h4 class="erp-home-sub">Access reviews</h4>`. With `count == 0`: `<p class="erp-card-empty">No access reviews waiting.</p>`. With rows: `_fold_rows.html` with `_review_row.html` (student name, meta guardian name, link "Review" with sr-only student name). With `rows` None: one row "{{ count }} waiting" with the link "Review" to `reviews.url`.
- Section modifier: `erp-analytics--no-notice` when the notice card is absent.
- The interim parts go away: the "Parents at a glance" heading, the glance tile, the "Pending access reviews" stat card and the bare "Announcements" link.

- [ ] **Step 1: Write the failing tests** (in `HomeTabsTests`; add `seed_parents(fx)` next to `seed_academics`, giving s1 a portal parent, a pending-review grant for one more student, and one published notice)

```python
def test_parents_tab_shows_three_cards(self):
    seed_parents(self)
    html = self.get(self.superuser_client, tab="parents").content.decode()
    for name, title in (("notice", "New announcement"), ("engagement", "Parent engagement"),
                        ("access", "Guardian access")):
        self.assertIn(title, card_html(html, name))
    self.assertNotIn("Parents at a glance", html)
    self.assertNotIn("Pending access reviews", html)

def test_card_form_posts_to_the_preview_page(self):
    html = card_html(self.get(self.superuser_client, tab="parents").content.decode(), "notice")
    self.assertIn(f'action="{reverse("core:announcement-create")}"', html)
    self.assertIn("data-erp-audience-form", html)
    self.assertIn('class="erp-btn erp-btn--primary"', html)
    self.assertIn("Message", html)

def test_card_form_errors_land_on_new_notice_page(self):
    response = self.superuser_client.post(reverse("core:announcement-create"),
                                          {"title": "", "body": "Hello", "audience": "ALL"})
    self.assertTemplateUsed(response, "core/announcement_form.html")
    self.assertContains(response, "Hello")

def test_card_form_preview_then_publish_still_works(self):
    # post the card's fields -> preview template; nothing saved until confirm
    response = self.superuser_client.post(reverse("core:announcement-create"),
                                          {"title": "Trip", "body": "Bring lunch", "audience": "ALL"})
    self.assertTemplateUsed(response, "core/announcement_preview.html")
    self.assertFalse(Announcement.objects.filter(title="Trip").exists())

def test_sent_list_newest_first_links_to_detail(self): ...
def test_engagement_card_shows_percent_and_counts(self):  # "50%" and "1 of 2"
def test_engagement_card_without_students_shows_dash(self): ...
def test_missing_rows_invite_link_needs_student_and_guardian(self):
    # superuser: Invite href = student-list?section=..&chip=no_portal ; view_school+view_student only: no Invite link
def test_reviews_need_view_guardianaccessreview(self):
    # plain view_school: context reviews None and "Access reviews" absent
def test_review_names_need_student_and_guardian(self):
    # view_school+view_guardianaccessreview only: rows None, "1 waiting" + Review link, no student name in HTML
def test_review_rows_link_to_decide_with_add_permission(self): ...
def test_notice_card_permissions(self):
    # view_school only: no form, no sent list, no erp-card--notice, section has erp-analytics--no-notice
    # add_announcement only: form, no sent list; view_announcement only: sent list, no form
def test_parents_tab_queries_do_not_grow_with_sections(self):
    # count queries for the parents tab, add 5 sections with 2 students each (one with a portal parent),
    # count again: equal
```

Update the existing tests that pin the interim tab:
- Rewrite `test_parents_tab_shows_guardians_and_links_only_what_the_viewer_may_open` to cover the new keys (or delete it if the new tests cover it).
- `test_nothing_repeats_across_tabs`: replace "Pending access reviews" with "Guardian access".
- Add `("parents", {})` to the tab lists in `test_tab_bar_markup_and_phone_css` and `test_overview_cards_use_erp_card`, and call `seed_parents(self)` in `test_overview_uses_no_bootstrap_classes`.
- `test_only_the_active_tab_is_queried` must still pass. If the Parents tab's query count reaches Today's, change that assertion to compare against a tab that is clearly heavier, and record the change in the task report.

- [ ] **Step 2: Run the tests and watch them fail**

Run: `DJANGO_DEBUG=True ../../.venv/Scripts/python.exe manage.py test core.tests.test_ui_admin_home_tabs --noinput`
Expected: the new tests FAIL (no `erp-card--notice`, and the interim text is still present).

- [ ] **Step 3: Implement** the context function, the view call, the templates, the `body` label, and the deletion of `parents_glance` with its tests, as specified above. Each new template starts with a `{# ... #}` comment saying what it renders and what it takes, like the existing row partials.

- [ ] **Step 4: Run the tests and watch them pass**

Run: `DJANGO_DEBUG=True ../../.venv/Scripts/python.exe manage.py test core.tests.test_ui_admin_home_tabs core.tests.test_ui_admin_overview_glance core.tests.test_home_parents core.tests.test_admin_overview_analytics --noinput`, then `grep -rln "announcement" core/tests | xargs` to find the announcement tests and run those modules too (the `body` label changed).
Expected: all pass; ruff clean.

- [ ] **Step 5: Commit**

```bash
git add -A core templates
git commit -m "feat(home): Parents tab cards: new announcement + sent list, parent engagement, guardian access"
```

---

### Task 4: Desktop grid, CSS and design doc

**Files:**
- Modify: `static/css/erp.css`: next to `.erp-stage-*` (around line 1428) and the desktop `.erp-analytics` spans (around 1650-1663)
- Modify: `docs/DESIGN_SYSTEM.md` (the "Stage counts" row)
- Test: `core/tests/test_ui_admin_home_tabs.py`

**Interfaces:**
- Consumes: the class names Task 3 put in the markup: `erp-card--notice`, `erp-card--engagement`, `erp-card--access`, `erp-analytics--no-notice`, `erp-stage-list--two`, `erp-stage-meta`, `erp-notice-form`.

- [ ] **Step 1: Write the failing CSS pin tests**

```python
def test_parents_css(self):
    css = Path(settings.BASE_DIR, "static", "css", "erp.css").read_text(encoding="utf-8")
    self.assertIn(".erp-stage-list--two { grid-template-columns: repeat(2, minmax(0, 1fr)); }", css)
    self.assertRegex(css, r"\.erp-stage-meta \{[^}]*font-size: var\(--erp-text-sm\)")
    self.assertIn(".erp-home .erp-analytics > .erp-card--notice { grid-column: span 7; }", css)
    self.assertIn(".erp-home .erp-analytics > .erp-card--engagement { grid-column: span 5; align-self: start; }", css)
    self.assertIn(".erp-home .erp-analytics > .erp-card--access { grid-column: span 12; }", css)
    self.assertIn(".erp-home .erp-analytics--no-notice > .erp-card--engagement { grid-column: span 12; }", css)
```

- [ ] **Step 2: Run the test and watch it fail**

Run: `DJANGO_DEBUG=True ../../.venv/Scripts/python.exe manage.py test core.tests.test_ui_admin_home_tabs.HomeTabsTests.test_parents_css --noinput`
Expected: FAIL (the rules don't exist yet).

- [ ] **Step 3: Implement**

- Add the exact rules the test pins: the desktop ones inside the same desktop media block as the Academics spans, the `--two` and `-meta` rules next to `.erp-stage-*`. `.erp-stage-meta` also gets `color: var(--erp-ink-soft)`.
- `.erp-notice-form` lays out its fields with `display: grid; gap: var(--erp-space-3);` and its textarea is full width.
- Add the new classes to the "Stage counts" row in `docs/DESIGN_SYSTEM.md` (`--two`, `-meta`).

- [ ] **Step 4: Run the UI tests**

Run: `DJANGO_DEBUG=True ../../.venv/Scripts/python.exe manage.py test --pattern="test_ui*.py" --parallel 4 --noinput`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add static/css/erp.css docs/DESIGN_SYSTEM.md core/tests/test_ui_admin_home_tabs.py
git commit -m "style(home): Parents tab desktop grid, two-up stage counts, notice form layout"
```

**After Task 4 (the controller does this, not the implementer):**
- Restart runserver and open `/static/css/erp.css` once to refresh it.
- Sign in as the local demo admin and open `/overview/?tab=parents`.
- Check 360px for no sideways scroll and 1280px for no grid gaps.
- Type a notice in the card, press Preview, and confirm the preview page opens with the text; do not publish.
