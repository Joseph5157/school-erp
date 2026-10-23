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

## Review follow-up: invalid-filter note and keyboard/zoom checks

- "Filters were not applied; showing all registers." now appears for **any** invalid filter form (inverted range, unparseable date, unknown Section), not only the non-field range error. Existing messages and submitted values are unchanged. Covered by `test_every_invalid_form_says_filters_were_not_applied_and_valid_ones_do_not`.
- `after-table-scrolled-mobile-390.png` shows the register table scrolled to its far edge by keyboard.

Keyboard and zoom were exercised with scripted Chromium (Playwright) on the same synthetic database, on the filtered and invalid-range states at 390px, 320px, 1280px, and 200% zoom (390px device at 195 CSS px; 1280px at 640 CSS px):

| Check | Result |
| --- | --- |
| Tab / Shift+Tab | Tab reaches every control (Section, Start, End, Filter, Clear filters, summary and table regions, sort links, row links, pagination) with no keyboard trap; Shift+Tab steps back through the previous stops (row links in reverse). The full stop-by-stop order was not recorded. |
| Focus visibility | Section, Start, End, summary and table regions, sort links, row links and pagination show a 3px green outline. Filter and Clear filters show the shared 3.2px focus ring. |
| Table keyboard scrolling | The focused table region scrolls with the arrow keys and reaches its far edge (390px: 1041 of 1041 px; 200% desktop: 63 of 63 px). At 1280px it fits and needs no scrolling. |
| Document overflow | 0px at 320, 390, 1280 and 200% desktop. |

## Known limits

- The "no registers at all" empty state is covered by tests, not by a screenshot.
- At 200% zoom on a 390px phone (195 CSS px, narrower than the 320px WCAG reflow width) the document overflows by 43px. The cause is the shared topbar account menu (`.erp-account`), not this page; shared layout is out of scope for D1-4A.
- The keyboard check is scripted, not a manual screen-reader or assistive-technology pass. Native date inputs expose several Tab stops each (day, month, year, picker).
- The shared table footer's "Clear filters" and the toolbar's "Clear filters" both appear in a filtered empty result.
