# Everclass logo and teal palette (short design)

Date: 2026-11-16. Status: approved by the user in conversation.

## Intent
The product is now "Everclass ERP" (#237). The app still shows the provisional
book-and-sun mark in dark green (#185842). The user wanted a completely new
symbol for school demos and sales, picked one from Canva, and asked us to choose
the app colours that best fit it.

## Goals
- Replace the book-and-sun mark with the chosen Everclass logo everywhere the
  app shows a product mark: top bar fallback (`templates/partials/_brand_mark.html`),
  login scene, PWA icons (`core/pwa_views.py` + generated PNGs), favicon.
- Move the app accent from green to a teal that matches the logo.
- Keep readability at least as good as today.

## Non-goals
- Sales kit (go-to-market repo): separate PR afterwards.
- Changing status colours (ok/warn/bad/info) or chart colours.
- Any layout change.

## Anti-goals
- A teal that fails WCAG AA for text or white-on-button.
- "Present"/"Saved" success states turning teal: success stays green.

## The logo (user's pick)
Canva design DAHbC6jt_qE, version B1: a teal infinity loop with a leaf sprout
and a yellow accent, wordmark "Everclass ERP" in a navy rounded sans-serif.
- Full lockup: redrawn by hand as an inline SVG (Canva output is raster).
- Small icon: the loop and sprout only, with thicker strokes, for favicon, PWA
  icons and the top-bar mark; fine details are dropped because they blur below
  ~48px.

## Palette (our call, user said "choose best")
| Token | Old | New | Contrast on white |
|---|---|---|---|
| `--erp-accent` | #1f6b52 | #0e6b66 | 6.34 |
| `--erp-accent-strong` | #185842 | #115e59 | 7.58 |
| `--erp-accent-wash` | #e3efe9 | #e0f2f1 | n/a |
| logo teal (logo only) | n/a | #1bb5a8 | 2.55, never text |
| logo yellow (logo only) | n/a | #f5b82e | n/a |
| logo navy (wordmark) | n/a | #0b2a4a | 14.54 |

`--erp-ok*` stays green. Other accent-derived tokens (`--erp-focus-color`,
`--erp-action-wash-strong`, button soft tones) are re-tinted to teal only where
they are visibly green; the builder checks each against `test_ui_palette_tokens.py`.

## Approaches considered
1. Teal palette + new logo (chosen): consistent brand; touches every screen's colour.
2. Keep green, swap logo only: smallest change, but the logo clashes with the UI.
3. Use the bright logo teal as the accent: matches exactly but fails contrast (2.55).

## Verification
- Updated palette tests and CSS string tests (`--pattern="test_ui*.py"`).
- Before/after screenshots at 375 and 1440 for login, admin overview, a guardian
  page; collectstatic before screenshots.
- One PR; reviewer subagent after opening; merge waits for the user's word.
