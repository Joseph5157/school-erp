"""Guardian portal accounts that were created but not yet used (G-06 spec, ANA-05). Read-only.

An account is listed when its link is active, its login is active, and the guardian still has at
least one current grant (grant not revoked, relationship not ended). "Never signed in" means the
login has no `last_login`; "temporary password" means it signed in but still must change the
password. `last_login` belongs to the login, so a teacher-parent who signed in as a teacher is not
listed (by design, spec §2).
"""
from django.db.models import Exists, OuterRef

from core.models import GuardianAccount, GuardianStudentAccess

NEVER = "never"
TEMPORARY = "temporary"
CHIPS = ((NEVER, "Never signed in"), (TEMPORARY, "Temporary password still active"))


def current_grants():
    return GuardianStudentAccess.objects.filter(
        revoked_at__isnull=True, student_guardian__ended_at__isnull=True
    )


def unused_accounts(chip=NEVER, student_ids=None):
    """The listed accounts. `student_ids` limits them to guardians granted one of those students."""
    grants = current_grants().filter(student_guardian__guardian_id=OuterRef("guardian_id"))
    if student_ids is not None:
        grants = grants.filter(student_guardian__student_id__in=student_ids)
    accounts = GuardianAccount.objects.filter(
        Exists(grants), revoked_at__isnull=True, user__is_active=True
    )
    if chip == TEMPORARY:
        return accounts.filter(user__last_login__isnull=False, user__must_change_password=True)
    return accounts.filter(user__last_login__isnull=True)
