# G-06 spec: guardians who have never signed in (ANA-05)

- **Status:** draft r1, awaiting product-owner approval. Not approved for build.
- **Baseline:** `origin/main` c6aad3d.
- **Risk tier:** **High** (guardian access and roles and permissions, `IMPLEMENTATION_WORKFLOW.md` §3).
- **Independent of recovery.** This list uses only existing data and existing actions. It does not depend
  on any decision in [ADR 0029](../adr/0029-guardian-account-recovery.md) and must not wait for it.
- **Relies on:** ADR 0004 (authorization foundation), ADR 0013 (accounts, grants, reviews, sessions),
  ADR 0024 (ended relationships revoke access), ADR 0027 (no new measurement). **No new ADR needed.**
- **Research:** [G06_PHASE0_GUARDIAN_ACCESS_RESEARCH.md](G06_PHASE0_GUARDIAN_ACCESS_RESEARCH.md) §5.

## 1. Outcome

An office user can open one page that lists guardian portal accounts that were created but never used,
filter it by class and section, and go straight to the guardian's profile or the existing password reset.
It makes activation follow-up possible today.

## 2. Which accounts count

An account is listed when **all** of these hold:

| Rule | Field | Evidence |
| --- | --- | --- |
| The account link is active | `GuardianAccount.revoked_at IS NULL` | `core/models.py:3529`, `:3566-3568` |
| The login is active | `User.is_active = True` | inactive logins cannot sign in (`accounts/backends.py:31`) |
| Never signed in | `User.last_login IS NULL` | Django's field; set on every successful sign-in |
| At least one current grant | a `GuardianStudentAccess` with `revoked_at IS NULL` on a `StudentGuardian` with `ended_at IS NULL` | `core/models.py:3575-3623`; ADR 0024 |

A grant that is pending a date-based review (ADR 0013 OD-8) still counts: the account is still unused.
The row says "Access under review" so the office does not chase a family whose access is paused
(`core/guardian_access.py:128-155`).

**Second view, same page (OD-N3):** a chip "Signed in, password not changed" lists accounts with
`last_login` set and `must_change_password = True` (`accounts/models.py:28`). These guardians used the slip
once but never finished activation. Same rules otherwise.

**Excluded:** revoked links; inactive logins; accounts whose only grants are revoked or whose relationships
have ended; guardians with no account (already counted by the Parents tab's missing-accounts card,
`core/home_parents.py:80-98`).

## 3. Filters and sort

| Filter | Values | Rule |
| --- | --- | --- |
| Status chip | Never signed in (default); Signed in, password not changed | §2 |
| Class | Class grades | A linked, granted student has a current placement in that class. Same placement rule as the Parents tab (`core/home_parents.py:24-43`). |
| Section | Sections of the chosen class | Same, by section |

Default sort: account created, oldest first. Paginated with the existing `build_table` helper, as on the
guardian list (`core/views.py:3449`).

Students without a current placement (inactive, or between years) do not match a class filter. With no
class filter, their guardians still appear if §2 holds.

## 4. Columns

| Column | Shown when | Notes |
| --- | --- | --- |
| Guardian name (links to guardian detail) | always | `core:guardian-detail` |
| Username | always | already on the guardian profile |
| Account created | always | date, and "N days ago" |
| Created by | always | staff name from `GuardianAccount.created_by` |
| Children with access | viewer has `core.view_student` | first name and class-section of each granted child; "Access under review" flag |
| Actions | see §5 | |

Never shown: passwords (never stored), phone, email, verification note, security events. Contact details
stay one tap away on the guardian profile, where the existing permissions already apply (OD-N4).

## 5. Actions (links only; this page changes nothing)

| Action | Target | Shown when |
| --- | --- | --- |
| Open guardian | `core:guardian-detail` (`core/views.py:3627-3673`) | always |
| Reset password | `core:guardian-account-reset-password` (`core/views.py:4138-4163`), its own confirm page | viewer has `core.reset_guardian_password` |

The reset link only opens the existing confirm page. The page has no POST, no bulk action and no message
sending.

## 6. Permission

- **Page gate:** `core.view_guardianaccount` **and** `core.view_guardian`. Both exist.
  `view_guardianaccount` already gates the portal-account section of the guardian profile
  (`core/views.py:3632`); `view_guardian` gates guardian names (`core/data_access.py:17`;
  `docs/PERMISSIONS.md:29`). Implement with `administrator_required` (`core/authorization.py:14-26`) for
  one and an explicit check for the other, or a small two-permission variant used the same way.
- **Children column and class filter:** also need `core.view_student` (`core/data_access.py:18`), the
  same rule as `_without_unseen_children` (`core/views.py:3390-3398`). Without it the column is hidden and
  class or section parameters are ignored, so a filter cannot reveal which class a guardian's child is in.
- **No new permission is needed.** If the owner wants a separate "view activation" permission, that is
  decision OD-N1, not an assumption.
- Guardians and teachers without these permissions get 403; anonymous users go to sign-in.

## 7. Where it is linked from

- The admin home Parents tab engagement card (`templates/partials/home/_parents.html:31-34`): add a line
  "N accounts never signed in" linking to the page, shown only when the viewer passes §6. The count uses the
  same query as the page, unfiltered.
- The guardian list (`core/templates/core/guardian_list.html`): a link near the header, same condition.

## 8. Empty states

| Case | Text |
| --- | --- |
| No accounts match, no filter | "Every guardian with portal access has signed in at least once." |
| No accounts match the filter | "No guardians in this class or section are waiting to sign in." plus a clear-filter link |
| No guardian accounts at all | "No guardian portal accounts yet." with a link to the guardian list |

## 9. Phone layout

Reuse the Package C patterns: the table inside `erp-table-scroll--stack` with `erp-table--stack`
(`static/css/erp.css:1350-1358`), so each row becomes a card at phone width; filters use the compact phone
filter pattern from C7. No new CSS component. Check at 360, 390 and desktop widths.

## 10. Route

| Name | Path | Method | Guard |
| --- | --- | --- | --- |
| `core:guardian-never-signed-in` | `guardians/never-signed-in/` | GET only (`require_safe`) | §6 |

Add it to `core/tests/route_permissions.json` with both permissions and `core.view_student` as an inner
permission, as `core:guardian-list` does (`core/tests/route_permissions.json:751-760`).

No migration. `makemigrations --check --dry-run` must report no changes. No usage-measurement route is
added (that is an ADR 0027 enum change and out of scope).

## 11. Tests

**Permission boundaries**

- Allowed: a user with `view_guardianaccount` + `view_guardian` gets 200.
- Refused: missing either permission gets 403; a teacher gets 403; a guardian login gets 403; anonymous is
  redirected to sign-in.
- Without `view_student`: no children column, and `?class=` and `?section=` are ignored (same rows as
  unfiltered).
- The Reset password link appears only with `reset_guardian_password`.
- The Parents tab link and count appear only when §6 passes.
- POST to the route returns 405.

**Query edge cases**

- Never signed in (`last_login` null) is listed; signed in once is not.
- Signed in once with `must_change_password` set appears only under the second chip.
- Inactive login is excluded.
- Revoked account link is excluded; a new active link for the same guardian is listed on its own terms.
- All grants revoked is excluded; one revoked and one active is listed.
- Relationship ended (ADR 0024) is excluded.
- Grant pending review is listed with the review flag.
- Inactive (archived) student: guardian still listed with no class filter; not matched by a class filter.
- Guardian with two children in two sections matches either section and appears once.
- A teacher who is also a guardian with a null `last_login` is listed once.
- Query count is fixed for 1 and 25 rows (no per-row queries).

**Inventory and guards**

- `core.tests.test_security_gate4b_route_inventory` passes with the new route.
- `--pattern="test_ui*.py"` passes if any CSS text changes (none expected).

## 12. Acceptance checklist

- [ ] Spec approved and OD-N1 to OD-N4 recorded.
- [ ] Page lists exactly the §2 accounts; both chips work.
- [ ] Class and section filters work with `view_student` and are ignored without it.
- [ ] Links open the existing guardian profile and reset confirm page; nothing is changed from this page.
- [ ] No contact data, password or security event shown.
- [ ] Parents tab and guardian list links appear only for permitted users.
- [ ] Phone (360, 390) and desktop checked; rows stack as cards.
- [ ] Route inventory updated; targeted tests and `ruff check .` pass; full CI green on the final head.
- [ ] Owner acceptance on staging; rollback (revert the squash commit; no data to undo) written in the PR.

## 13. Out of scope

- Sending any message, reminder or invitation (WhatsApp, SMS, email).
- Bulk reset, bulk revoke or any bulk action.
- Exporting the list.
- Recovery changes of any kind (ADR 0029).
- Guardians with no account (the Parents tab already shows them by section).
- Per-guardian activity beyond "never signed in" (ANA-06 read tracking).
- New usage counters.

## 14. Decisions for the product owner

| ID | Decision | Options | Recommendation |
| --- | --- | --- | --- |
| OD-N1 | Permission | Existing `view_guardianaccount` + `view_guardian`; a new dedicated permission | Existing permissions |
| OD-N2 | Inactive logins | Exclude; show behind a filter | Exclude (they cannot sign in; reactivation is a separate task) |
| OD-N3 | "Signed in, password not changed" chip | Include; leave out | Include (no model change, closes the same follow-up gap) |
| OD-N4 | Phone number column for follow-up calls | Omit; show to users with `view_guardian` | Omit in v1; the profile is one tap away |
