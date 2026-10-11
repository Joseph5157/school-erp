from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy
from django.views.decorators.cache import never_cache

from accounts.models import SecurityEvent


class PasswordChangeView(auth_views.PasswordChangeView):
    """Change one's own password; clears a forced change (ADR 0013).

    Django keeps the current session (update_session_auth_hash) and every
    other session of this login stops verifying because the password changed.
    """

    template_name = "registration/password_change_form.html"
    success_url = reverse_lazy("home")

    def form_valid(self, form):
        response = super().form_valid(form)
        user = form.user
        if user.must_change_password:
            get_user_model().objects.filter(pk=user.pk).update(must_change_password=False)
        SecurityEvent.record(
            SecurityEvent.EventType.PASSWORD_CHANGED, actor=user, subject_user=user
        )
        messages.success(self.request, "Your password has been changed.")
        return response


password_change = never_cache(PasswordChangeView.as_view())
