# UI Design Rules

Status: adopted 2026-10-18 with U3.1 Teacher Mobile Polish (Gate T0).
Applies to every screen. Tokens live in `static/css/erp.css` (`--erp-*`); behaviour rules stay in `docs/UI_REFERENCES.md` ("Rules the design must keep").

These rules refine the U1/U2/U3 decisions. They do not replace them: Django + Bootstrap 5.3.3, server-rendered, no build step, works with JS off.

## 1. Hierarchy and cards

- Every card or row has **one dominant element** (the thing the user scans for), one secondary line, and at most one action.
- Cards are **purposeful, not card-everywhere**. Use a card for a unit of work or a record the user acts on. Plain text, a heading, or a list row is better for supporting information.
- Never nest a card in a card. Never put a card around a single link.
- Three text tiers only: **primary** (`--erp-ink`), **secondary** (`--erp-ink-soft`), **muted** (helper text, timestamps). Weight and size carry hierarchy before colour does.

## 2. Spacing (8pt grid)

- Base unit 8px. Use 8 (related lines), 16 (groups inside a card, card padding), 24 (between major blocks), 32+ (page sections).
- Spacing inside a group is always smaller than spacing between groups.
- Page gutter 16px on phones.

## 3. Colour, depth, corners, motion

- **One accent colour** (`--erp-accent`) for actions and the active destination. Status colours (ok, warn, bad, info) are for semantic status only, never decoration.
- Never rely on colour alone: every status also has text.
- Border and surface first. A very subtle downward shadow only where depth genuinely helps (sticky bars, floating menus).
- Corners: card outer radius 10-12px (`--erp-radius`), inner controls 6-8px (`--erp-radius-sm`). No 24px consumer-app rounding.
- Motion only where it explains a change: about 150-250ms, ease-out. Honour `prefers-reduced-motion` (already in `erp.css`).

## 4. Buttons and actions

- A real `<button>` performs an action; a real `<a>` navigates. Do not style one as the other's semantics.
- **One primary action per decision area.** Secondary actions are outline or link style.
- Destructive actions are spatially separated from the primary action and say what they destroy.
- Labels are verb + object ("Save draft", "Take attendance"), never "Submit" or "OK".
- A disabled-looking control must be visibly different from a secondary one (see Phase 3E).
- Status labels (pills) must not look tappable: no hover state, no button shape.

## 5. Forms and validation

- Every input has a visible label; helper text is muted and sits under the field.
- Validation errors are announced (live region), associated with the field, and say what to fix.
- Keep the user's input on error. Never clear a form to show an error.
- Use the right `inputmode` / `autocomplete` / `enterkeyhint` for the field.

## 6. Loading, error and empty states

These are three distinct states and must never look alike.

- **Loading:** shows that work is in progress. No fake progress percentages; show real counts ("18 of 32 written") or nothing.
- **Error:** says what failed and what the user can do. Never blame the user.
- **Empty:** says what this place is for, why it is empty, and what happens next. Use `partials/_empty.html`. A fully done task ("Nothing waiting") is a deliberate completed state, not an empty one.
- Headers, filters and navigation stay visible in an empty state (pick 5.11).

## 7. Navigation

- A user can always answer: where am I, where can I go, how do I go back.
- The active destination is unmistakable (colour + weight + `aria-current="page"`, not colour alone).
- Primary destinations are always visible with **text labels**; icons support the label and are never the only signal.
- Phone primary navigation is a bottom bar of at most four or five items. No hamburger for those destinations.
- Navigation links stay permission-gated in templates; views still enforce access.

## 8. Lists and pagination

- Rows are scannable: dominant name left, secondary detail below, status right.
- When a whole row navigates, the whole row is the tap target and only one link carries the accessible name.
- Show counts. Page long lists; do not infinite-scroll.
- Order is meaningful and stable (by name, by date); never rank by performance.

## 9. Tables

- Use a real `<table>` with `<caption>`/`scope` for tabular data (gradebook, report card on wide screens).
- On phones prefer rows/cards over wide tables. A table that must stay a table scrolls inside its own box, never the page.
- Numbers right-aligned in tables; blanks read "No mark" / "Not marked", never 0 and never absent.

## 10. Search

- Search sits above the list it filters, keeps its query after submit, and shows the result count.
- "No results" names the query and offers a way to clear it.

## 11. Onboarding and first use

- A first-time user sees what to do next, not a blank page. Empty states double as onboarding.
- Explain a rule where it applies ("Blank is not absent"), in one short line, not in a manual.

## 12. Connected flows

- A task that spans screens (take attendance, enter marks) shows where the user is in it and where it ends, and returns them to a sensible place afterwards.
- Success is confirmed through the live-region message, naming what happened.
- Draft vs final state is always visible.

## 13. Accessibility

- **Touch targets are at least 44x44 CSS px** on phones, with spacing so neighbouring targets are not mis-hit.
- Visible keyboard focus ring on every interactive element (`--erp-focus-ring`).
- Text contrast at least 4.5:1 (3:1 for large text and UI boundaries).
- Layouts work at 360px with no page-level horizontal scroll, and at 200% zoom.
- Landmarks and headings in order; one `<h1>` per page; decorative icons and avatars are `aria-hidden`.
- Everything works with JS off; JS only enhances.

## 14. Domain rules the UI must keep

From `docs/UI_REFERENCES.md`, unchanged:

- Draft vs submitted attendance; an unopened register is never "present".
- Blank marks mean "not marked yet", not absent.
- No totals, weighting, averages or ranks on teacher or guardian result views.
- Never invent data to fill a design.
