# UI Design Rules

Status: **Proposed** (2026-10-18) with U3.1 Teacher Mobile Polish, Gate T0. It becomes adopted when Gate T0 is approved and merged.
Applies to every screen. Tokens live in `static/css/erp.css` (`--erp-*`); domain behaviour rules stay in `docs/UI_REFERENCES.md` ("Rules the design must keep") and are restated in section 16.

These rules refine the U1/U2/U3 decisions; they do not replace them: Django + Bootstrap 5.3.3, server-rendered, no build step, works with JS off.

**How to read them.** Each bullet is a rule a reviewer or a test can check. "Must" is binding; "prefer" is a default that needs a stated reason to break. Rules that apply in several places are written once and referenced.

## 1. Hierarchy and cards

- Every card or row has **one dominant element** (the thing the user scans for), one secondary line, and at most one primary action.
- Cards are **purposeful, not card-everywhere**: a card is a unit of work or a record the user acts on. Supporting information is plain text, a heading or a list row.
- Do not nest a card in a card.
- Do not create a decorative card merely to contain a naked link. A meaningful record or task card (a student, a term-remarks task, an assessment duty) **may itself be one navigation target**: one `<a>` carries the accessible name, covers the whole card/row (stretched link), and the card shows the affordance in section 5 (similarity/affordance).
- A card that is a navigation target contains no second interactive control that competes with it, unless that control is separated and independently reachable (for example a Gradebook link beside the main record link).
- Three text tiers only: **primary** (`--erp-ink`), **secondary** (`--erp-ink-soft`), **muted** (helper text, timestamps). Weight and size carry hierarchy before colour does.

## 2. Spacing (8pt grid)

- Base unit 8px: 8 (related lines), 16 (groups inside a card, card padding), 24 (between major blocks), 32+ (page sections).
- Spacing inside a group is always smaller than spacing between groups (proximity).
- Page gutter 16px on phones.

## 3. Colour, depth, corners, motion

- **One accent colour** (`--erp-accent`) for actions and the active destination. Status colours (ok, warn, bad, info) are for semantic status only, never decoration.
- Colour is never the only signal: every status also has text or an icon with a text equivalent.
- Border and surface first. A very subtle downward shadow only where depth genuinely helps (sticky bars, floating menus). Figure-ground: the thing in front (sheet, menu, sticky bar) is visibly separated from what is behind it.
- Corners: card outer radius 10-12px (`--erp-radius`), inner controls 6-8px (`--erp-radius-sm`). No 24px consumer-app rounding.
- Motion only where it explains a change: about 150-250ms, ease-out. Any motion that is introduced must respect `prefers-reduced-motion` (no transition or animation under `reduce`), and it must be checked when the motion is added. No motion that blocks input.

## 4. Buttons and actions

- A real `<button>` performs an action; a real `<a>` navigates. Do not style one as the other's semantics.
- **One primary action per decision area.** Secondary actions are outline or link style.
- Labels are verb + object ("Save draft", "Take attendance"), never a generic "Submit" or "OK". Outcome labels such as "Submit attendance" are correct.
- Destructive actions are spatially separated from the primary action, say what they destroy, and show the count when acting on several records ("Delete 12 students"). Where the action is reversible, offer **Undo** instead of a confirmation dialog; where it is not, confirm with the consequences listed.
- A disabled-looking control must be visibly different from a secondary one (Phase 3E). A control that cannot act says why, nearby, in text.
- A click or tap is acknowledged immediately (see section 7, immediate acknowledgement); a submit button is not left re-clickable while its request is in flight.

## 5. Interaction and perception laws

Each law is stated as the rule it imposes on this ERP.

| Law | Rule |
|---|---|
| **Fitts** (target size and distance) | Touch targets at least 44x44 CSS px with spacing; the primary action of a long or action-heavy task sits in thumb reach (see section 15 for when a sticky bar is used). |
| **Hick / choice overload** | A decision area shows few options: one primary action, at most two or three secondary. Long option sets are searchable or grouped, not a flat wall of buttons or a 30-item menu. |
| **Jakob** (familiarity) | Use platform and Bootstrap conventions: underlined/obvious links, a back path, bottom nav on phones, labelled form fields. Do not reinvent a control without a measured reason. |
| **Similarity and affordance** | Things that look the same behave the same. Tappable things look tappable (colour, chevron, underline or button shape); non-interactive things do not (status pills have no hover state, no button shape, no pointer cursor). |
| **Proximity** | Related items are grouped by spacing (section 2) before borders or boxes. |
| **Serial position** | The most important items go first (and, where a list has a prominent end, a needed action is not buried in the middle). In a list, items needing action come before finished items. |
| **Peak-end** | The end of a task is designed: after save/submit/finalize, show a clear confirmation naming what happened and a sensible next step. Errors end with a recovery path, never a dead end. |
| **Closure and goal gradient** | Multi-step tasks show a visible step indicator ("Step 2 of 4") and finished work. Completion shows a deliberate done state ("All marks entered"), not blank space. Where it helps, a **controlled partial glimpse** of the next card or section at the edge of the viewport may signal that content continues; do not manufacture overflow (no padding, clipping or fake rows to force a peek). |
| **Truthful, earned progress** | Progress reflects real counts ("18 of 32 written") from real data. No percentages, bars or streaks that are invented, padded or pre-filled to look further along. |
| **Figure-ground** | One thing is the focus at a time: a sheet or dialog dims or separates the page behind it; sticky bars have an edge or shadow. |
| **Banner blindness** | Important status is inline with the content it refers to, not in banner-like strips at the top or in coloured ad-like boxes. Keep banners for rare page-level state and make them specific. |
| **Postel (flexible input, strict meaning)** | Accept reasonable input variation (spaces, case, `+91`/leading zero in phone numbers, several date formats, thousands separators) and normalise it; store and display one strict canonical form, and show the user what was understood. Never guess a value that changes meaning (an ambiguous date, a score that could be out of range). |
| **Tesler (conservation of complexity) and Parkinson** | The system absorbs complexity: prefill from known data (today's date, the teacher's Section, the current term, the enrolment's Student), remember the last sensible choice, and ask only what the system cannot know. Give tasks sensible defaults and bounds so work does not expand to fill open-ended forms. |
| **Doherty threshold** | Acknowledge input within about 100ms; if work takes longer, show progress (section 7). |
| **Miller / chunking** | Group long records into labelled sections with an "On this page" menu (Phase 3G) rather than one long undifferentiated form. |

## 6. Forms and validation

- Every input has a visible `<label>`; helper text is muted and sits under the field, associated by `aria-describedby`.
- Right `type`, `inputmode`, `autocomplete` and `enterkeyhint` for the field (numeric keypad for scores, `tel` for phones).
- **Six input states are designed and distinct:** default, focus (visible focus ring), filled, error, success, disabled. **Read-only** is an additional seventh state where it applies (for example a locked value on a finalized record); it is not styled as disabled, and its value stays readable and selectable. Success is shown only when it is meaningful (a verified value), not on every valid field.
- **When to validate:** safe client-side feedback on **blur** (format, required, range), never on every keystroke while the user is still typing. **Final, authoritative validation happens on submit and on the server**; client checks never replace it. Visible **rule checklists** (for example password rules) may update live as the user types where that helps them meet the rule. Clear an error as soon as the value becomes valid.
- **Do not lose unsaved work:** a form with unsaved changes warns before in-app navigation or browser Back/close discards them, or keeps a draft; the warning is not shown when nothing changed. Server-rejected input is re-displayed, never dropped.
- **Messages are field-local and actionable:** shown next to the field, associated with it (`aria-describedby`, `aria-invalid="true"`), and say what to change ("Enter a score from 0 to 20"), not just what is wrong. A form-level summary may list the errors with links to the fields; it never replaces the field-local message.
- Errors are announced through the live region. Focus moves to the first invalid field or the summary after a failed submit.
- **Keep input on error.** Never clear the form or a field to show an error, and never silently alter what the user typed.
- Required vs optional is stated in text, not by an asterisk alone.
- Draft saving, where the domain has it (attendance, marks), is explicit: "Save draft" is distinct from the final action and the state is shown (section 13).

## 7. Loading, error and empty states

Loading, error, and each kind of empty state are different and must never look alike.

**Loading**
- **Reserve the layout** before content arrives (skeleton or fixed-height placeholder) so nothing shifts when data lands.
- **Immediate acknowledgement:** every click/tap shows a response within about 100ms (pressed state, spinner on the button, or navigation start).
- Prefer a skeleton shaped like the content over a spinner for page and list loads; use an inline spinner for a button action. No full-page blocking spinners.
- **Independent regions load independently:** a slow or failed region (a card, a list, a count) shows its own loading or error state and does not block or blank the rest of the page.
- **Ghost or sample previews are optional** and only when they are **clearly illustrative**: labelled as an example ("Sample"), visually distinct (dashed/muted, not interactive), and never styled or worded so they could be mistaken for real student, staff, attendance or marks data. They never contain realistic names, numbers or statuses that look real, and they disappear when real data arrives.
- Long operations have a **timeout** with a message ("This is taking longer than usual") and a **retry** action. The user can still leave.
- No invented progress. Show a real count/step, or an indeterminate indicator.

**Error**
- Says what failed, whether the user's work is safe, and what to do next, with a **Try again** control where retry is meaningful. Does not blame the user and does not show stack traces or codes without a plain sentence.
- Errors that block a whole page keep navigation visible.

**Empty** - four different situations, four different messages. Use `partials/_empty.html`, keep headers/filters/navigation visible (pick 5.11), and give the next action when the user has one.
- **First run** (nothing exists yet): what this place is for and how to start. Example: "No assessments assigned" + who assigns them.
- **All done** (work cleared): a deliberate completed state that confirms it ("All marks entered"), with a quiet link onward. Not styled like an error or like first run.
- **No results** (a search/filter matched nothing): names the query or active filters and offers to clear them (see section 11).
- **Error / unavailable** (could not load): follows the error rules above, never presented as "nothing here".

## 8. Navigation

- A user can always answer: where am I, where can I go, how do I go back.
- The active destination is unmistakable (colour + weight + indicator + `aria-current="page"`; never colour alone).
- Primary destinations are always visible with **text labels**; icons support the label and are never the only signal.
- Phone primary navigation is a bottom bar of at most four or five items with the most-used first (serial position). No hamburger for those destinations.
- Navigation links stay permission-gated in templates; views still enforce access.
- **Keep navigation shallow:** at most two levels visible; no deep or multi-level flyout menus, and no hover-only menus (they fail on touch and keyboard).
- Leaving a page with unsaved form work follows the unsaved-work rule in section 6.
- Breadcrumbs or a Back link on every page below a primary destination; Back never loses the user's place (section 9).

## 9. Lists, pagination and continuity

- Rows are scannable: dominant name left, secondary detail below, status right. Order is meaningful and stable (name, date); never rank by performance.
- Show the **count and position**: "Showing 26-50 of 1,284". The total is real, not estimated.
- **Paginate; do not infinite-scroll.** The pagination footer is reachable (not pushed away by content that loads below it) and shows previous/next plus page numbers for large sets.
- **Reserve space** for the list while loading and for the footer, so paging does not shift controls under the pointer.
- **State lives in the URL:** page, page size, sort, filters and search query are query parameters, so a link, refresh or shared URL reproduces the view.
- **Back restores context:** after opening a record and pressing Back (or following a "Back to list" link), the user returns to the same filters, page and scroll position. "Back to list" links carry the list's query string.
- **Explicit end of results:** the last page says so ("End of results" / disabled Next with a reason), and a page beyond the last redirects to the last page, not an empty one.
- When a whole row navigates, the whole row is the tap target and exactly one link carries the accessible name.
- Filters show their current values and a way to clear all of them; the result count updates with them.

## 10. Data tables

- Use a real `<table>` with `<caption>` (can be visually hidden), `<thead>`, `<th scope>`; never lay out tabular data with divs.
- **Sticky `<thead>`** inside the table's own scroll box when the table is taller than the viewport or the box.
- **Sortable columns** show the sorted column, direction arrow (with text/`aria-label`) and `aria-sort="ascending|descending"` on the active `<th>`. The sort control is a real `<button>` or link inside the `<th>`. Sort state is in the URL (section 9).
- **Numeric columns are right-aligned** and use `font-variant-numeric: tabular-nums`; text columns are left-aligned; headers align with their data.
- **Pagination shows range and total** ("Showing 26-50 of 1,284") and obeys section 9.
- **Bulk actions:** selection shows a count ("12 selected") and the action names it ("Delete 12 students"). Destructive bulk actions are separated from the selection controls; if reversible they offer **Undo** after the action, otherwise confirm with the consequences.
- **Narrow screens:** below about 600px, tables with more than three or four columns **stack each row** into a labelled card/definition list (label + value pairs); do not squeeze six columns or hide the key column. A table that must remain a grid (gradebook) scrolls inside its own box with a sticky first column and never scrolls the page.
- **Blank cells** are never read as zero or absent. See section 16: the meaning of a blank must be clear from the surrounding UI (column header, legend or row context). A compact grid such as the Gradebook may leave a blank cell empty provided that meaning is clear; no table is required to print a literal "No mark".
- No totals, averages, weights or ranks unless the domain rules allow them.

## 11. Search

- Search sits above the list it filters, keeps the query after submit, and the result count updates ("12 results for 'Aar'").
- **Zero results recover:** the message names the query, offers to clear it or loosen filters, and suggests a fix when one is safe ("Did you mean ...?"); it is the "No results" case of section 7, not a blank list.
- **Live search** debounces input by about 200-300ms, **cancels or ignores stale requests** so an older response never overwrites a newer one, and works without JS as a normal GET submit.
- **Typo tolerance:** fuzzy/typo-tolerant matching is allowed for names. **Critical identifiers** (admission number, username, register id, phone) match **exactly** (after the Postel normalisation of section 5); never auto-correct them.
- **On focus**, an empty search may show recent and common searches (per user, never another user's), dismissable.
- **Show why a result matched:** highlight the matched text and show enough context (Section, admission number) to tell similar names apart.
- **Suggestions/results list is an accessible combobox** when it appears under the field: `role="combobox"` on the input with `aria-expanded`, `aria-controls` and `aria-activedescendant`; a `role="listbox"` of `role="option"` items; a polite live region announcing the result count. Keyboard: **Down/Up** move through options, **Enter** chooses the active option (or submits the search if none), **Esc** closes the list and, on a second press, clears the field. Focus stays in the input while moving through options.
- Search results obey section 9: count, URL state, Back restores the query.

## 12. Onboarding and first use

- No tour slides, carousels or modal walkthroughs. Teach in context: empty states double as onboarding (section 7, first run) and point to the one next action.
- **Ask for permission or information just in time**, when the feature needs it and with the reason ("Allow notifications so you hear when marks are published"), not on first load. A refusal never blocks the rest of the app.
- Explain a rule where it applies, in one short line ("Blank is not absent"), not in a manual.
- Multi-step setup shows **visible step progress** ("Step 2 of 4"), allows **Back** without losing entries, and offers a clear **exit** (save and finish later, or cancel) at every step. Optional steps are marked optional and skippable.
- First sign-in flows (change of one-time password, role choice) state what is happening and what comes next.

## 13. Connected flows

- A task that spans screens (take attendance, enter marks, finalize) shows where the user is in it and where it ends, and returns them to a sensible place afterwards (peak-end).
- Success is confirmed through the live-region message, naming what happened ("Attendance saved and submitted").
- **Draft vs final state is always visible** (pill + text), and so is who may change it.
- Destructive or irreversible steps in a flow are the last step, separated and explicit.

## 14. Accessibility

- **Touch targets are at least 44x44 CSS px** on phones, with spacing so neighbouring targets are not mis-hit.
- Visible keyboard focus ring on every interactive element (`--erp-focus-ring`); logical tab order; no keyboard traps; dialogs and sheets trap and restore focus.
- Text contrast at least 4.5:1 (3:1 for large text and UI boundaries).
- Layouts work at 360px and 390px with no page-level horizontal scroll, and at 200% zoom.
- Landmarks and headings in order; one `<h1>` per page; decorative icons and avatars are `aria-hidden`; icon-only controls have an accessible name.
- Dynamic changes (messages, counts, results) are announced through a live region; the page does not move focus unexpectedly.
- Everything works with JS off; JS only enhances.

## 15. Mobile layout

- Phone-first for teachers and guardians; desktop-first for the office. Every page is usable at 360px.
- A **sticky bottom primary-action bar** is for long or action workflows where the action must stay reachable (take attendance, marks entry), not for every mobile page. Short pages keep their action inline. Where one is used it sits above the safe area, and the tab bar is hidden while it is shown (U2 decision).
- Content is not hidden behind sticky bars: pages reserve bottom padding for them.

## 16. Domain rules the UI must keep

From `docs/UI_REFERENCES.md`, unchanged:

- Draft vs submitted attendance; an unopened register is never "present".
- **Blank marks mean "not marked yet", never zero and never absent.** Wherever a blank can appear (entry, gradebook, results, counts), its meaning must be clear from the surrounding UI: a column header, a legend, a row state or a count such as "5 not marked". The wording may be compact ("Not marked", an empty cell with a legend, or a dash with a visually hidden label) but a blank must never be styled or announced as 0 or Absent. Absent is a separate, explicit state.
- No totals, weighting, averages or ranks on teacher or guardian result views.
- Never invent data to fill a design.
