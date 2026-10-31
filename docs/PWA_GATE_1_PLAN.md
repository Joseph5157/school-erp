# PWA Gate 1 — installable online app

Status: approved by the product owner on 31 October 2026; implemented on `feat/pwa-gate1-installable` (draft PR).
Parent plan: [PWA_STARTER_PLAN.md](PWA_STARTER_PLAN.md). Gate 2 (device acceptance) has not started.

## Scope

Online-only, installable app. No service worker, offline page, client-side storage, background sync or push. No change to
the Teacher, Guardian or Administrator workflows.

## Decisions

| Decision | Choice |
| --- | --- |
| App name / short name | School ERP / School ERP |
| Launch | `id: /`, `start_url: /`, `scope: /`, `display: standalone` |
| Icon | Code-generated: cobalt rounded square, white open-book glyph |
| Cobalt | The design system's info blue `--erp-info` `#1d5fa8` (`core/pwa_views.ICON_COLOUR`). The stylesheet has no token literally named "cobalt"; its only blue is the info colour, so that is used rather than adding a palette. The app's own accent is green `#1f6b52`. |
| `theme_color` / `background_color` | `#ffffff` (the topbar surface) / `#f5f6f3` (`--erp-paper`) |
| Hostnames | None in the manifest. Every path is origin-relative; the production domain stays open. |

## Findings from the code review, and what Gate 1 does about them

1. **The manifest is a Django view, not a static JSON file.** `CompressedManifestStaticFilesStorage` does not rewrite
   icon URLs inside a `.json` file. A view calls `static()` so production hashed names are used.
2. **A narrow middleware bypass is needed.** WhiteNoise sits before `AccountSecurityMiddleware`, so static icons never
   reach it, but a view does. For a signed-in user the manifest would refresh `_auth_last_seen` and, during a forced
   password change, be redirected. `AccountSecurityMiddleware.__call__` therefore returns early when
   `request.path_info` equals the literal `MANIFEST_PATH = "/manifest.webmanifest"` (defined in
   `accounts/middleware.py`), before `request.user` is read. No other path changes. It is a literal rather than
   `reverse("pwa-manifest")` because the middleware runs on every request, including under test URLconfs that have no
   such route, where `reverse()` raises and turns the request into a 500. `config/urls.py` builds the route from the
   same constant, and `test_route_matches_the_path_the_middleware_lets_through` asserts that
   `reverse("pwa-manifest") == MANIFEST_PATH`, so the route and the bypass cannot drift apart.
3. **The manifest must work whether or not a session cookie is sent.** The `<link rel="manifest">` has no
   `crossorigin` attribute, but same-origin requests can still carry cookies, so omitting it is not what guarantees
   this. The guarantee is that the manifest needs no authentication and ignores the session entirely (finding 2).

## What was added

| Piece | Where |
| --- | --- |
| Manifest view (`application/manifest+json`, `Cache-Control: public, max-age=3600`, GET/HEAD only) | `core/pwa_views.py`, route `manifest.webmanifest` (`pwa-manifest`) |
| Install help page (login required; plain instructions for Android, iPhone/iPad Safari, desktop) | `core/pwa_views.install_help`, route `install/` (`pwa-install`), `templates/pwa/install.html` |
| Shared head metadata (manifest link, theme colour, Apple touch icon and title) | `templates/partials/_pwa_head.html`, included by `base.html` and `portal/base.html` |
| "Install app" account-menu entry | `templates/partials/_account_menu.html` |
| Custom Install button, hidden until `beforeinstallprompt` fires, only on the install page | `static/js/erp.js` |
| Icons: 192, 512, maskable 512, Apple touch 180 | `static/pwa/`, regenerate with `manage.py generate_pwa_icons` |
| Tests | `core/tests/test_pwa_gate1.py` |

The Apple touch icon and maskable icon are fully opaque (iOS turns transparency black; maskable icons are cropped by the
OS). The maskable glyph stays inside the central safe zone.

## Tests (automated)

Manifest: public 200 with the manifest content type, identity fields, origin-relative paths with no account data, required
icon sizes and a maskable icon, colours matching the shell meta tag, POST refused.

Session rules: loads during a forced password change while `/` still redirects to password change; does not move the idle
clock; does not keep an expired session alive; works with a stale session cookie; other pages still require login;
look-alike paths get no bypass.

Shells: both shells carry the same metadata and no `use-credentials`; no service worker anywhere.

Icons: sizes, opacity, rounded corners, colour. Install page: platform instructions, button hidden by default, menu link,
listener attached only when the button exists.

## Production static check

Run with the production storage (DEBUG off, not testing) into a throwaway `STATIC_ROOT`: `collectstatic` succeeds, the
manifest returns 200 with hashed icon URLs (for example `/static/pwa/icon-192.<hash>.png`), and each file exists.

## Gate 2 checks to run on real devices

Not performed in Gate 1. Record the browser and OS versions beside each result, and do not mark an unperformed check as
passed.

| Device | Checks |
| --- | --- |
| Android Chrome | Install from the browser prompt and from "Install app"; relaunch; icon and name; uninstall |
| iPhone Safari | Add to Home Screen following the on-page steps; relaunch; icon (opaque Apple icon) and name; remove |
| Desktop Chrome and Edge | Install from the address bar; relaunch in its own window; uninstall |
| Normal browser | Everything still works without installing |

Journeys: logged-out launch, teacher, guardian, multi-role, first-login password change (manifest and icons still load),
expired or revoked session, account A logout then account B login, network loss during a save (stays unsaved), offline
launch (unsupported; no cached school page), removal. Full table: the parent plan, Gate 2.

## Not done here

Deployment, live configuration and merging. Production domain and final branding stay open.
