# School ERP — PWA starter plan

Prepared: 31 October 2026
Status: Gate 0 readiness review complete; scope approved by the product owner on 31 October 2026. Gate 1 detail is in
[PWA_GATE_1_PLAN.md](PWA_GATE_1_PLAN.md).

## Outcome

Add an installable, online-only School ERP app to the existing Django application. Users open it from an app icon and
continue through the same login, permissions and role-specific portals. Every page, report and data-entry action
requires an internet connection.

The current PWA scope is installation and app-like launching only. Do not add a service worker, offline page, offline
storage, background synchronization or push notifications.

## Verified baseline

Repository: Joseph5157/school-erp. Reviewed `main` at `86bdf08e8f5fcd444e00744c00889f4902a1bb15`.

| Finding | Consequence for the PWA |
| --- | --- |
| Django Templates, Bootstrap and vanilla JavaScript are the approved frontend stack. | Add the PWA within this application; no separate frontend or build pipeline is needed. |
| No web app manifest, service-worker file or offline-page file appears in the repository tree. The inspected base templates and shared JavaScript contain no PWA integration. | This is a new foundation, not an upgrade of an existing PWA. |
| `templates/base.html` and `templates/portal/base.html` are separate shells. | Integrate installation metadata into both. |
| `/` uses the existing authenticated role-routing view. Multi-role users choose an area. | Use `/` as the common launch URL; retain explicit area choice. |
| Account security enforces forced password change and 30-minute idle / 8-hour absolute sessions. | Installation must preserve these rules. Public PWA resources must work while password change is required. |
| WhiteNoise uses hashed static-file storage outside local development/tests. | Verify icons and references with collected production static files. This storage manifest is unrelated to a PWA web app manifest. |
| Both shells load Bootstrap from a CDN. | Acceptable for the online-only scope; the installed app requires a connection. |
| The school-logo image view requires authentication. | Use public static app icons; do not use that authenticated endpoint as an installation icon. |

This was a source review. It did not verify the currently deployed commit, live HTTPS configuration, device
installation or staging acceptance.

## First-release choices

| Choice | Scope |
| --- | --- |
| App identity | One app per school origin, covering existing roles. Use the current name, School ERP, until product branding is selected. |
| Primary mobile users | Teachers and guardians, using their existing portals. |
| Administrator | Can use desktop installation; the approved desktop UI scope remains in place. |
| Launch and scope | Stable manifest `id: /`, `start_url: /`, `scope: /`, `display: standalone`. No user, student, role or session identifier in the manifest. |
| Account access | Existing Django authentication, role selection and permissions. |
| Working offline | Unsupported in the current scope. The browser may show its normal network-error experience. |
| Stored school data | No new persistent client storage for school data in this release. |
| Notifications | Deferred. Preserve the existing consent and communication rules. |
| UI | Minimal installation controls and instructions. Preserve the Teacher and Guardian portal designs. |

These are proposed PWA defaults, not a claim that a new ADR has been accepted. Record them through the repository's
normal gate process.

## Implementation gates

### Gate 1 — Installable online app

Deliver a valid web app manifest, public static icons and metadata in both application shells. Include normal 192×192
and 512×512 PNG icons, a dedicated maskable icon and a 180×180 Apple touch icon. Keep the existing identity; use a
simple code-drawn icon if no product asset is available.

Serve the manifest without authentication. It must contain public installation metadata only. Resolve icon URLs using
Django's static storage so production hashing works. Ensure the manifest can be fetched without a session; select and
verify the manifest link's credential mode if served from a Django view.

Public PWA resource requests must not refresh the idle-session clock or be redirected to password change. Use a
narrowly defined bypass for those exact public resources if required by their serving path; do not widen access to
application pages or weaken session enforcement.

Use the browser's installation affordance first. Any custom Install button must appear only when the browser provides a
usable install event. On iPhone/iPad, show accurate manual installation instructions. Do not display a broken
installation control or force a prompt at login. A minimal instruction page or account-menu entry is sufficient.

Pass criteria: manifest and icons load without login and during forced password change; both shells reference the same
app identity; installation and relaunch work on the supported device matrix; launch reaches the existing login or role
routing; ordinary browser use still works.

This gate introduces no service worker. A service worker is not required for installation, and offline behavior is
outside the approved current scope.

### Gate 2 — Regression checks and staging acceptance

Test the installed app on Android Chrome, iPhone Safari and desktop Chrome/Edge. Verify normal-browser fallback too.
Browser emulation and manifest validation are useful checks but do not replace real installation testing.

| Journey | Required result |
| --- | --- |
| Logged-out launch | Login appears; no private page is restored by the PWA cache. |
| Teacher launch | Existing teacher area and permissions. |
| Guardian launch | Existing guardian area, child switching and publication visibility. |
| Multi-role launch | Existing explicit area choice. |
| First-login password change | Security flow works; public PWA resources still load. |
| Expired/revoked session | Server denies or redirects as before. |
| Account A logout → account B login | No private response from account A is served by the PWA. |
| Network loss during a save | Save remains failed/unsaved; no background retry, queued write or success claim. |
| Offline launch | Offline use is unsupported; no cached school page or record is shown. |
| Removal | The user can uninstall the app using the operating system or browser controls. |

Capture actual outcomes and browser/device versions. Do not mark unperformed checks as passed. Coordinate staging
deployment with the existing acceptance work; PWA completion does not close unrelated production-readiness items.

## Later work

Offline pages, offline attendance and offline marks entry are deferred. They would require a separate approved design
for device storage, shared-device privacy, assignment changes, expired permissions, duplicate submissions, conflicts and
server reconciliation. Installation does not provide those features automatically.

Push notifications need a separate delivery and consent gate. They must respect ADR 0015 and existing
publication/guardian access rules. Do not request notification permission as part of installing the first release.

Choose the intended production domain before asking schools to install. An installation on the staging origin is a
separate app from one installed on the production origin.
