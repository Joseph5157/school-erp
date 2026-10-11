from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.core.exceptions import PermissionDenied

from accounts.models import User
from accounts.usernames import USERNAME_HELP, clean_new_username, normalize_username


def is_guardian_linked(user):
    """A login with an active guardian link (ADR 0013, OD-4)."""
    return user is not None and user.pk is not None and user.guardian_accounts.filter(
        revoked_at__isnull=True
    ).exists()


class NormalizedUsernameMixin:
    """Site-administration forms use the same username rule as the ERP."""

    def clean_username(self):
        value = self.cleaned_data.get("username")
        current = getattr(self, "instance", None)
        if current is not None and current.pk and normalize_username(value) == normalize_username(
            current.username
        ):
            return current.username  # unchanged; existing names are never rewritten
        return clean_new_username(value, exclude_user=current if current and current.pk else None)


class ERPUserCreationForm(NormalizedUsernameMixin, UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username",)
        help_texts = {"username": USERNAME_HELP}


class ERPUserChangeForm(NormalizedUsernameMixin, UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if is_guardian_linked(self.instance) and "username" in self.fields:
            self.fields["username"].disabled = True
            self.fields["username"].help_text = (
                "Guardian logins change their username only through the audited guardian "
                "account workflow."
            )
        for name in ("must_change_password", "session_version"):
            if name in self.fields:
                self.fields[name].disabled = True


@admin.register(User)
class ERPUserAdmin(UserAdmin):
    form = ERPUserChangeForm
    add_form = ERPUserCreationForm
    readonly_fields = ("must_change_password", "session_version")
    fieldsets = UserAdmin.fieldsets + (
        ("Account security", {"fields": ("must_change_password", "session_version")}),
    )

    def user_change_password(self, request, id, form_url=""):
        user = self.get_object(request, admin.utils.unquote(id))
        if is_guardian_linked(user):
            messages.error(
                request,
                "Guardian passwords are reset only through the audited guardian account workflow.",
            )
            raise PermissionDenied
        return super().user_change_password(request, id, form_url)
