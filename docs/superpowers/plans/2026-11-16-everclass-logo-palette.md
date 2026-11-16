# Everclass Logo and Teal Palette Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the book-and-sun mark with the Everclass loop-and-sprout logo and move the app accent from green to teal.

**Architecture:** One 64-unit glyph drawing shared by three outputs: the standalone SVG files in `static/brand/`, the inline mark in `templates/partials/_brand_mark.html`, and the PIL-drawn PWA icons in `generate_pwa_icons`. The palette changes only the legacy accent trio in `erp.css` `:root`; brand and action follow it by `var()`; ok stays a literal green trio.

**Tech Stack:** Django templates, plain CSS tokens, Pillow, Django `SimpleTestCase`.

**Spec:** `docs/superpowers/specs/2026-11-16-everclass-logo-palette-design.md`

## Global Constraints
- Accent: `#0e6b66`, strong `#115e59`, wash `#e0f2f1`.
- Logo-only colours: teal `#1bb5a8`, yellow `#f5b82e`, navy `#0b2a4a`. Logo teal is never used for text.
- `--erp-ok`, `--erp-ok-strong`, `--erp-ok-wash` stay `#1f6b52`, `#185842`, `#e3efe9`.
- Glyph sits on a transparent background in the app; PWA tiles are white (`ICON_COLOUR = "#ffffff"`).
- No layout changes. No changes to warn/bad/info or `--erp-viz-*`.
- After CSS edits run `python manage.py test --pattern="test_ui*.py" --parallel 4`.

## Review Focus
- Mark at 28px in the top bar and drawer: loop must read as a loop, not a blob (screenshot check, Task 2).
- Maskable icon cropped to a circle: glyph must stay inside the central 80% (Task 2 pixel test).
- Focus ring still visible on the new teal buttons (Task 3: focus colour re-tinted, contrast test).
- Success badges next to teal buttons must still read green (Task 3: ok trio pinned).
- Old green `#185842` left in templates (login scene) after the switch (Task 3 grep test).

---

### Task 1: Logo SVG files (shown to the user before Task 2)

**Files:**
- Create: `static/brand/everclass-mark.svg` (glyph only, viewBox `0 0 64 64`)
- Create: `static/brand/everclass-logo.svg` (glyph + wordmark "Everclass ERP" in navy, rounded sans font stack `Quicksand, Nunito, "Segoe UI", sans-serif`)
- Test: `core/tests/test_brand_assets.py`

**Interfaces:**
- Produces: the glyph geometry in 64 units, reused verbatim by Task 2:
  - Loop centreline (stroke width 7, round caps/joins): `M32 34 C38 24 52 24 52 34 C52 44 38 44 32 34 C26 24 12 24 12 34 C12 44 26 44 32 34`
  - Lower-right sweep in navy over the loop: the segment `M52 34 C52 44 38 44 32 34`
  - Yellow crescent inside the right lobe, sprout stem from the right lobe top with two teal leaves above it. Exact paths are the builder's call; keep everything inside x 8–56, y 10–50.

- [ ] **Step 1: Write `test_brand_assets.py`**: both files exist; mark has `viewBox="0 0 64 64"`; each contains `#1bb5a8`, `#f5b82e`, `#0b2a4a`; neither contains `#185842`; logo contains `Everclass ERP`.
- [ ] **Step 2: Run it, expect FAIL** (files missing): `python manage.py test core.tests.test_brand_assets`
- [ ] **Step 3: Draw both SVGs** with the geometry above.
- [ ] **Step 4: Run it, expect PASS.**
- [ ] **Step 5: Render both to PNG (browser screenshot) at 512px and 32px and show the user. Stop until they approve the look.**
- [ ] **Step 6: Commit** `feat(brand): Everclass loop-and-sprout logo SVGs`

### Task 2: In-app mark and PWA icons

**Files:**
- Modify: `templates/partials/_brand_mark.html` (keep `class="erp-brand-mark" aria-hidden="true" focusable="false" viewBox="0 0 64 64"`; drop the tile rect; inline the Task 1 glyph)
- Modify: `core/management/commands/generate_pwa_icons.py` (replace book/sun constants and drawing with the loop, sweep, crescent and sprout; reuse `curve()`; docstring updated)
- Modify: `core/pwa_views.py:19` (`ICON_COLOUR = "#ffffff"`, comment updated)
- Regenerate: `static/pwa/*.png` via `python manage.py generate_pwa_icons`
- Test: `core/tests/test_brand_assets.py` (extend)

**Interfaces:**
- Consumes: Task 1 glyph paths and colours.

- [ ] **Step 1: Add tests**: `_brand_mark.html` contains `#1bb5a8` and not `#185842` or `#e9b949`; `draw_icon(512, rounded=False, glyph_scale=0.72)` has the pixel at (256, 272) (loop crossing) within 40 of `#1bb5a8` per channel, and every pixel outside the central 80% circle is white.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** template, generator, `ICON_COLOUR`; run the generator.
- [ ] **Step 4: Run** the new tests plus `core.tests.test_pwa_gate1 core.tests.test_ui_hamburger core.tests.test_ui_login_phone core.tests.test_ui_admin_desktop_d1_4c1_attendance_reports`, expect PASS.
- [ ] **Step 5: Commit** `feat(brand): Everclass mark in the app and PWA icons`

### Task 3: Teal palette

**Files:**
- Modify: `static/css/erp.css:13-15` (accent trio to the Global Constraints values), `:88-89` (`--erp-focus-color: #0e6b66`, ring `rgba(14, 107, 102, .3)`), `--erp-action-wash-strong` to `#c7e7e4`, `--bs-primary-rgb` to `14,107,102`; update the comment on lines 17-18 if it names green.
- Modify: `templates/registration/_login_scene.html` (every `#185842` to `#115e59`)
- Modify: `core/tests/test_ui_palette_tokens.py` (`ACCENT` = new trio; ok family asserted against a new `OK = {"": "#1f6b52", "-strong": "#185842", "-wash": "#e3efe9"}`)
- Test: `core/tests/test_brand_assets.py` (extend)

- [ ] **Step 1: Update palette tests** as above and add: no file under `templates/` contains `#185842` or `#1f6b52`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Edit CSS and login scene.**
- [ ] **Step 4: Run** `python manage.py test --pattern="test_ui*.py" --parallel 4` and `core.tests.test_brand_assets`; fix any CSS-string test that pinned an old hex by updating its expected value only.
- [ ] **Step 5: Commit** `feat(ui): teal accent palette to match the Everclass logo`

### Task 4: Screenshots and PR

- [ ] **Step 1:** `collectstatic --noinput`, restart the dev server, screenshot login, admin overview and one guardian page at 375 and 1440, before (main) and after.
- [ ] **Step 2:** Open the PR with the screenshots; start the reviewer subagent; report a verdict table. Merge waits for the user's word.
