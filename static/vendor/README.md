# Vendored front-end libraries

These files are served from our own domain instead of a CDN, so no third-party server can change
the code that runs in the app. They are exact, unmodified copies of the published releases.
Each library keeps its LICENSE next to it (all MIT).

| Library | Version | Files | Source |
|---|---|---|---|
| Bootstrap | 5.3.3 | `bootstrap/5.3.3/css/bootstrap.min.css` (+ `.map`), `bootstrap/5.3.3/js/bootstrap.bundle.min.js` (+ `.map`, includes Popper) | `https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/` |
| HTMX | 2.0.4 | `htmx/2.0.4/htmx.min.js` | `https://cdn.jsdelivr.net/npm/htmx.org@2.0.4/dist/` |
| SortableJS | 1.15.6 | `sortablejs/1.15.6/Sortable.min.js` | `https://cdn.jsdelivr.net/npm/sortablejs@1.15.6/` |

## Checksums (sha384, base64)

These match each project's published Subresource Integrity values. `core/tests/test_vendored_assets.py`
recomputes them, so a changed file fails the tests.

| File | sha384 |
|---|---|
| `bootstrap/5.3.3/css/bootstrap.min.css` | `QWTKZyjpPEjISv5WaRU9OFeRpok6YctnYmDr5pNlyT2bRjXh0JMhjY6hW+ALEwIH` |
| `bootstrap/5.3.3/js/bootstrap.bundle.min.js` | `YvpcrYf0tY3lHB60NNkmXc5s9fDVZLESaAA55NDzOxhy9GkcIdslK1eN7N6jIeHz` |
| `htmx/2.0.4/htmx.min.js` | `HGfztofotfshcF7+8n44JQL2oJmowVChPTg48S+jvZoztPfvwD79OC/LTtG6dMp+` |
| `sortablejs/1.15.6/Sortable.min.js` | `HZZ/fukV+9G8gwTNjN7zQDG0Sp7MsZy5DDN6VfY3Be7V9dvQpEpR2jF2HlyFUUjU` |

## Rules

- Keep the `.map` files. The minified files end with a `sourceMappingURL` comment, and
  `collectstatic` with `CompressedManifestStaticFilesStorage` fails the deploy if a referenced map is missing.
- `.gitattributes` marks `static/vendor/**` as `-text`, so Git never changes line endings (that would
  break the checksums on Windows checkouts).
- Never edit these files. Put overrides in `static/css/erp.css` or `static/js/erp.js`.

## Updating a library

1. Download the new release files into a new version folder, e.g. `bootstrap/5.3.4/`, with its LICENSE.
2. Check the sha384 against the project's published SRI value:
   `openssl dgst -sha384 -binary FILE | openssl base64 -A`
3. Update the `{% static %}` paths in the templates, this README, and `EXPECTED` in
   `core/tests/test_vendored_assets.py`.
4. Delete the old version folder, run the tests, and check the pages that use the library.
