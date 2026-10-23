# UI-D1-4A — Admin Attendance Register List: synthetic screenshot evidence

**Local synthetic evidence only.** Captured with Playwright (Chromium) against a throwaway local PostgreSQL database seeded with invented data ("Demo Student One/Two/Three", one long Academic Year, Class/Grade and Section name). Not production, not staging, no real student data.

- `before-*` — `main` at `436fa75` template. `after-*` — this branch.
- Widths: 390, 768, 992, 1024, 1280, 1440 (full-page PNGs). **360px** was measured only (no PNG).
- Document-level horizontal overflow (`scrollWidth - clientWidth`) was **0px** at all seven widths in all five states, before and after. The six-column table scrolls only inside its labelled `erp-table-scroll` region.

| State | URL | What it shows |
| --- | --- | --- |
| `base` | `/attendance/` | 32 registers, 25 per page, newest first, no summary |
| `filtered` | `/attendance/?section=A` | Section summary panel (reportable submitted only), Draft and Submitted rows, Clear filters |
| `long-section` | `/attendance/?section=<long name>` | Long Section / Class / Academic Year names wrap without clipping |
| `no-results` | `/attendance/?section=C` | "No attendance registers match these filters." plus the shared footer "No results / Clear filters" |
| `invalid-range` | `/attendance/?start=2026-09-30&end=2026-07-01&section=A` | Error shown once, entered values kept, "Filters were not applied; showing all registers." |

## Known limits

- The "no registers at all" empty state is covered by tests, not by a screenshot.
- Keyboard focus order and 200% zoom were not exercised in a browser; the register table region is `tabindex="0"` with a label, as asserted in tests.
- The shared table footer's "Clear filters" and the toolbar's "Clear filters" both appear in a filtered empty result.
