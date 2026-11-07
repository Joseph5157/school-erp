# Security audit closeout (Gates 1 to 4B)

What the November 2026 security audit found, which pull request fixed each part, what was
checked on staging, and what is still open. It describes classes of problem and the fixes, not
step-by-step exploits. Rules for who may see what are in `docs/PERMISSIONS.md`; deployment
variables and recovery steps are in `docs/OPERATIONS.md`.

## How the audit was done

- Tool: the open-source `cloudflare/security-audit-skill`, standard profile, source only.
- Run on 2026-11-06 against commit `c6284df`. It had no sandbox (Windows host), so it
  produced **0 confirmed findings and 12 leads that needed validation**.
- A second, read-only pass on 2026-11-07 audited an exact export of `main` at `76e091e` and a
  mechanical map of all routes to the permission each view enforces. It confirmed leads 7 to 12
  on the then-current code and found two more places that showed another class of data.
- The raw report and the lead ledger live outside the repository, in the maintainer's
  `security-audit-skill/school-erp/run-1/` folder. This page does not claim every lead in the
  ledger is closed, only what the gates below changed.

## What each gate changed

| Gate | PR | Merge commit | Change |
|---|---|---|---|
| 1 | #201 | `88b6db3` | One shared rule decides which logins a guardian link, password reset or rename may touch (`is_portal_manageable`). The Django admin sign-in shares the ERP's throttle and audit. |
| 2 | #202 | `2b74722` | Production refuses to start with a blank or `django-insecure-` secret key, with HTTPS explicitly switched off, or with a malformed `DJANGO_TRUSTED_PROXIES`. HTTPS defaults on in production, and a blank on/off flag uses its default instead of being read as a value. |
| 3A | #203 | `14cba05` | Class-teacher authority is tied to the record's academic year, so a teacher who led a section last year has no authority over this year's records. Student scope, guardian contacts, report cards, remarks, attendance and the teacher home all key on (section, year). |
| 3B | #204 | `e05bbd2` | The WhatsApp send queue rechecks portal access three times (listing, opening the message, marking sent). A guardian who lost access is dismissed with a system reason. |
| 4A | #205 | `76e091e` | Crash emails are built from an allow-list (route pattern, exception types, `file:line in function`) with no URLs, IPs, usernames, messages or variables, and absolute server paths are never shown. Mail stays off until an email host and recipients are both configured. |
| 4B | #206 | `8e312e8` | Each class of personal data needs its own view permission (guardians, attendance entries, marks, staged import rows). Import problems never repeat a cell value, the uploaded file's name needs `run_import`, and a route inventory test pins the permission of every route, including the root ones. |

Full rules for 4B are in `docs/PERMISSIONS.md`. Superusers and the School Administrators group
hold every permission, so Gate 4B changes nothing for them; only a custom role can be narrower.

## Staging

All six gates are deployed on staging, web and cron, at `8e312e8`. For each gate the previous
deployments were retired, the logs showed no tracebacks or `ImproperlyConfigured` errors, public
pages returned 200, protected pages redirected to sign-in, an anonymous POST without a CSRF
token returned 403, and HTTPS redirect and security headers (HSTS, `nosniff`, `DENY`) were
correct. The staging secret key was rotated on 2026-11-06 and an independent
`DJANGO_SOURCE_HASH_KEY` was set.

## Known limits and open follow-ups

- **Limited roles were not exercised on staging.** Staging has no custom role (0 custom groups,
  0 logins with direct permissions), so Gate 4B's limited-role behavior is proven by tests only
  (78 Gate 4B tests, direct and group holders, plus the full CI suite), not on a live school.
  Check again with `python manage.py role_permission_gaps` before the first custom role goes
  live; it is read-only and lists incomplete permission combinations.
- **Signed-in send queue not checked on staging.** Gate 3B's queue flow is covered by CI tests;
  no administrator login was used to walk it on staging.
- **Send queue limits (3B).** Access grants are not locked while a message is open, the badge
  can be briefly stale, and the refusal message appears in the new tab. Marking a message sent
  records what happened but cannot stop a manual send already in progress. See
  `docs/OPERATIONS.md`.
- **Email is not configured.** No provider is chosen, so crash emails are off. Choose one,
  set `EMAIL_HOST` and `DJANGO_ADMINS`, and test with the in-memory backend first, never with
  real mail on staging.
- **Other installs.** Only staging has been inventoried. Any other school install needs the
  environment variable check from Gates 1 and 2 before it gets those changes, because a missing
  secret key now stops the build.
- **Teacher and register rules left alone.** Subject-teacher authorization was not changed in
  3A. Publication remarks stay under `view_studentresult` and security events under
  `manage_teacher_accounts`, as documented bundles in `docs/PERMISSIONS.md`.
- **Housekeeping.** The merged remote branches `security/gate-1-account-protection`,
  `gate-2-deployment-safety`, `gate-3a-academic-year-authorization`,
  `gate-3b-send-queue-recheck` and `gate-4a-crash-email-privacy` can be deleted.

## Keeping it this way

- `core/tests/route_permissions.json` fails the build when a route is added, removed or
  changes permission, and the scan fails on route forms it cannot read.
- A test fails if an import problem message could carry a cell value.
- The full suite runs on GitHub CI for each pull request; merges are done with
  `gh pr merge --match-head-commit <sha>` after CI is green on that exact commit.
