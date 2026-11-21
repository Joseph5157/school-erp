# Admin home: 4 tabs by job (design)

Date: 2026-11-18 · Status: APPROVED by the owner 2026-11-18 · Next: implementation plan (writing-plans), then build PR 1

## Why

The current admin Overview (`core/templates/core/admin_overview.html` + `templates/partials/_attendance_analytics.html`) shows about 14 blocks on one page, about 10 of them charts. The owner finds it crowded, and especially dislikes the "Still to finish" rings. The goal is a home page that school clients (principals and owners) find useful and satisfying in a demo. Each screen answers one worry with a number, the change against before, and a name to act on.

## Goals

- Four tabs, each answering one question:
  - **Today**: what do I do now?
  - **Attendance**: are children coming?
  - **Academics**: are they learning?
  - **Parents**: are parents with us?
- 3–6 cards per tab. Nothing repeats across tabs.
- Phone first (admin mobile is the focus). Desktop shows the same tabs with a wider grid.

## Non-goals

- Fees, staff leave and staff birthdays: separate future features.
- New chart types. Use cards, lists, bars and the existing heatmap only.

## Anti-goals (failure even if it works)

- Rings, gauges or decorative charts coming back.
- A tab that turns into a long scroll of charts again.
- Numbers with no action (every list row links somewhere).

## Approaches considered

1. **By job: Today / Attendance / Academics / Parents.** CHOSEN by the owner 2026-11-18. Balanced tabs that match a principal's mental model.
2. By time (Today / Week / Term / Parents). Least change, but Term would hold about 9 analytics cards, which is the crowding we are removing.
3. By people (Today / Students / Teachers / Parents). Gives teacher accountability its own tab, but Students would be heavy and mix attendance with marks.

This replaces the earlier approved "Today / Week / Students / Announcements" layout. Week items fold into Today, as "this week" lists.

## Removed (code included)

Checklist row, term gauge, rings, daily attendance line chart, by-class column/bar chart, score bands, attendance period picker.

## Merges

- "Students needing attention" + "At-risk students" become one **At-risk students** list.
- "Marks by subject" + "Subject weak spots" become one **Subjects** card: averages, lowest first, with the change vs last term.
- "Frequent absentees" + "Chronic absentees" become one **Absentees** card with a switch between "this month" and "below 75% this term".

## Tabs

**Today**
1. School at a glance (students, teachers, classes, current term)
2. Attendance today: donut (present / late / absent) + classes that haven't taken attendance, each with its teacher
3. Teacher compliance: today's late or missing registers, plus assessments overdue for marks
4. Assessments: today, then the rest of this week
5. Birthdays: today, then the rest of this week (students only)

**Attendance**
1. Trend vs last month: this month's % vs last month's, with up/down
2. Heatmap, last 4 weeks (existing)
3. Day-of-week pattern (e.g. "Mondays are 4% lower")
4. Best and worst 3 classes by attendance
5. Absentees: this month (N+ days) / below 75% this term

**Academics**
1. Results to finish: marking in progress, ready to finalize, finalized but not published (with a Publish action)
2. Pass rate + grade spread per class, latest exam
3. Best and worst 3 classes by marks
4. Subjects: average, lowest first, change vs last term
5. At-risk students
6. Top improvers (biggest rise in marks vs last term)

**Parents**
1. New announcement form (title, message, audience) + sent list
2. Parent engagement: % of students with a parent account, % of parents active
3. Guardian access: classes with missing accounts (Invite) + access requests (Review)

## Data check (2026-11-18)

- Registers: `AttendanceRegister.submitted_at` exists, so "on time" is possible once a cut-off rule is set.
- Marks: `Assessment.assessment_date` + `finalized_at` exist, so "on time" is possible once a deadline rule is set.
- Announcement reads: **not tracked**. `Announcement` has no read records.
- Students: `date_of_birth` exists (optional), so birthdays only show students who have one.
- Term-over-term comparisons need a previous term with finalized results. Show "No comparison yet" otherwise.

## Owner decisions (settled 2026-11-18)

1. **Register late:** not submitted by **10:00** on a school day. A per-school setting, default 10:00.
2. **Marks late:** an assessment not finalized within **15 days** of its `assessment_date`.
3. **Parent engagement:** launch with "% of parents who logged in this month" (from existing login data). Announcement read tracking is a **later** PR.
4. **"Remind" button:** **later**. Not in this build. Classes that haven't taken attendance show "Open" (go to the register) only.

## My calls (the owner can override)

- Week items fold into Today, as "this week" lists.
- At-risk definition: the existing "needing attention" rule (below pass in 2+ subjects, or 1 subject and often absent) + falling marks vs last term.
- Improvers: top 5 by average rise vs last term, with at least 2 assessments in each term.
- Best/worst lists show 3 each and hide when fewer than 4 classes have data.
- Each tab is its own URL (`?tab=attendance`), so it works without JavaScript and can be linked from elsewhere.

## Left to the builder

Query design and caching; how compliance numbers are computed; empty states; desktop grid; tests (including the `test_ui_*` CSS string tests).

## Build order (a suggestion for the plan)

One PR per tab, in order, per the owner's one-PR-at-a-time rule: (1) tab shell + removals + Today, (2) Attendance, (3) Academics, (4) Parents.

Later, separate: announcement read tracking; the "Remind" teacher button; fees; staff leave and staff birthdays.
