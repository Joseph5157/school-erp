# Admin Desktop Product Direction

## Status

**Gate UI-D0 ACTIVE from 2026-10-20. Visual spike only; full admin migration needs separate review.**

This document records the agreed product direction so it can be resumed later without reopening the decision.

## Product principle

The School ERP should not force every desktop workflow into a phone-sized interface.

Use this split:

- **Desktop = administration, setup, review, bulk operations, and complex workflows.**
- **Mobile = day-to-day operational work and quick reference.**
- Responsive design does **not** mean every desktop feature must be squeezed into mobile.

## Screen categories

### Full mobile + desktop support

Use for frequent daily work:

- Teacher My Day
- Take attendance
- Enter marks
- Today's timetable
- My Students
- Student quick profile
- Guardian portal
- Notifications
- Term remarks
- Attendance summary

### Desktop-first / desktop-only administration

Use the full desktop workspace for tasks that depend on width, comparison, filters, or bulk operations:

- Academic Year Rollover
- Bulk student import
- Academic Year setup
- Class and Section configuration
- Class-teacher mapping
- Subject-teacher mapping
- Timetable construction
- Subject offerings
- Assessment configuration
- Bulk corrections
- Large reports and exports
- User/account administration

If a desktop-only page is opened directly on a small screen, show a clear **Desktop required** message instead of a broken compressed workflow. Hiding navigation is never an authorization mechanism.

## Breakpoint direction

Keep the project's existing major breakpoint:

- **< 992px:** mobile operational experience
- **>= 992px:** full ERP desktop workspace

Individual pages may remain responsive across both when the workflow benefits from it.

## Admin desktop shell

Build our own School ERP desktop administration shell.

### Foundation

- Bootstrap 5.3
- Existing ERP design tokens and UI-P1 color direction
- Existing Django views, forms, services, URLs, authorization and tests

### Tabler decision

Do **not** adopt the full Tabler theme as the application framework.

Use Tabler selectively as a design/component reference for solved desktop UI patterns such as:

- sidebar
- top navigation
- data tables
- filters
- tabs
- cards
- badges
- pagination
- dropdowns
- form layouts
- empty states
- desktop spacing patterns

School-specific workflows remain our own design.

The rule is:

> **School ERP owns the design system. Bootstrap is the foundation. Tabler is a reference/component source, not the application framework.**

Prefer project-owned classes such as:

- `.erp-admin-shell`
- `.erp-sidebar`
- `.erp-page-header`
- `.erp-data-table`
- `.erp-filter-bar`
- `.erp-stat-card`
- `.erp-status`

rather than spreading theme-specific coupling throughout the codebase.

## Portal split

### Teacher

Keep the current custom mobile-first experience focused on:

- Today
- Students
- Attendance
- Assessments
- Results
- Timetable

### Guardian

Keep the current custom mobile-first portal focused on:

- children
- attendance
- results/report cards
- announcements and other relevant parent-facing information

### Administrator

Move toward a desktop-first workspace with room for:

- Students
- Academics
- Attendance
- Assessments
- Teachers
- Timetable
- Guardians
- Documents
- Reports
- Imports
- Academic Year Rollover
- Settings

Desktop pages should be allowed to use wider tables, sticky headers, multi-column forms, bulk actions, side-by-side comparisons, and persistent filters instead of artificially staying narrow.

## Implementation approach when resumed

Use a small visual spike before changing the full admin area.

Prototype the desktop shell against a representative set of existing pages:

1. Overview
2. Students
3. Academic Year
4. Teacher mapping
5. Timetable

Freeze the shell and component rules only after reviewing those pages. Then migrate page-by-page without changing domain behavior or authorization.

