from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self):
        from django.contrib.auth.signals import user_logged_in
        from django.db.models.signals import pre_save

        from accounts.middleware import mark_session_started
        from accounts.models import User

        user_logged_in.connect(mark_session_started, dispatch_uid="accounts_session_clock")
        pre_save.connect(end_sessions_on_deactivation, sender=User,
                         dispatch_uid="accounts_end_sessions_on_deactivation")


def end_sessions_on_deactivation(sender, instance, raw=False, **kwargs):
    """Deactivating a login ends all its sessions (ADR 0013)."""
    if raw or instance.pk is None or instance.is_active:
        return
    was_active = sender.objects.filter(pk=instance.pk, is_active=True).exists()
    if was_active:
        instance.session_version = (instance.session_version or 0) + 1
