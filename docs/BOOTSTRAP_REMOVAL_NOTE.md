# Bootstrap removal note

**Planned start:** 18 November 2026

## Current position

Bootstrap 5.3.3 is locally hosted and remains a shared frontend dependency. The ERP design layer changes most of its appearance, but Bootstrap still supplies foundational styles and a small amount of interaction behavior.

The static audit found approximately 302 Bootstrap-class occurrences across 46 of 79 templates. Bootstrap is loaded by the main ERP shell, the Guardian Portal shell, and the standalone server-error page. The vendored files are approximately 233 KB of CSS and 81 KB of JavaScript before transfer compression.

## Where Bootstrap is still used

- Buttons and button variants
- Form controls, selects, labels, validation, and help text
- Responsive display, grid, flex, spacing, and typography utilities
- Alerts and dismiss buttons
- Sidebar navigation classes
- Tables and progress bars
- Visually hidden accessibility helpers
- The mobile administration sidebar through Bootstrap Offcanvas
- Message dismissal and automatic hiding through Bootstrap Alert

No Bootstrap modals, dropdowns, collapses, toasts, or popovers remain.

## Removal plan

1. Replace Bootstrap Offcanvas and Alert JavaScript with locally maintained ERP components.
2. Replace Bootstrap responsive, spacing, typography, and accessibility utility classes with ERP utilities.
3. Move buttons, forms, navigation, tables, alerts, and progress bars fully into the ERP component system.
4. Remove Bootstrap from the main shell, Guardian Portal shell, and server-error page.
5. Run application-wide desktop, mobile, print, keyboard, high-contrast, and no-JavaScript checks before deleting the vendored Bootstrap files.

## Important constraint

Do not remove the global Bootstrap files until every dependent class and JavaScript behavior has been replaced and visually verified. Keep all replacement components locally hosted and owned by the project.

