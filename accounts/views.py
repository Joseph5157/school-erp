from urllib.parse import urlsplit

from django.contrib import messages
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth import views as auth_views
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse, reverse_lazy
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from accounts.middleware import seconds_left
from accounts.models import SecurityEvent
from accounts.return_path import return_path
from core import usage


class LoginView(auth_views.LoginView):
    """Django's login page, sending a signed-in user on instead of showing the form.

    redirect_authenticated_user sends a signed-in login to a safe ?next= or home. A ?next= that
    points back at the login page is dropped: Django would refuse to redirect the page to itself
    (ValueError, a 500) for a signed-in user, and loop an anonymous one straight back here.
    """

    redirect_authenticated_user = True

    def form_valid(self, form):
        # The expiry marker survives login() (it only cycles an anonymous session's key) and is
        # removed after every successful sign-in, whatever its age. ?expired= is never trusted.
        relogin = usage.take_relogin(self.request)
        response = super().form_valid(form)
        area = usage.area_of_user(form.get_user())
        if area:
            usage.record(self.request, area=area, workflow="sign_in", step="completed")
            if relogin:
                usage.record(self.request, area=area, workflow="session",
                             step="relogin_after_expiry")
        return response

    def form_invalid(self, form):
        # A failed sign-in has no authenticated role, so it is always "public" (ADR 0027).
        step = "throttled" if getattr(form, "was_throttled", False) else "failed"
        usage.record(self.request, area="public", workflow="sign_in", step=step)
        return super().form_invalid(form)

    def get_redirect_url(self):
        url = super().get_redirect_url()
        if url and urlsplit(url).path == self.request.path:
            return ""
        return url


def csrf_failure(request, reason=""):
    """CSRF_FAILURE_VIEW: a plain-words page instead of Django's technical one.

    A form's security token goes stale when a page is left open for a long time or the user signs in
    or out in another tab, which phone users hit often. Nothing was saved, so the page offers a fresh
    copy of the page that showed the form (audit 18 ERR-02: an action-only URL would answer 405).
    Logout is POST-only, so its retry goes home instead.
    """
    path = return_path(request, reverse("home"))
    if path.split("?", 1)[0] == reverse("logout"):
        path = reverse("home")
    return render(request, "403_csrf.html", {"retry_url": path}, status=403)


@never_cache
@require_http_methods(["GET", "POST"])
def session_status(request):
    """Seconds left before sign-out (GET, which is not activity) or Stay signed in (POST).

    accounts.middleware has already signed out an expired session and redirected to login, so an
    answer here means the session is live; a POST counted as activity there (audit 15 NOTIF-01).
    """
    if not request.user.is_authenticated:
        return JsonResponse({"idle": 0, "absolute": 0}, status=401)
    return JsonResponse(seconds_left(request.session))


class LogoutView(auth_views.LogoutView):
    """Log out and ask the browser to drop cached signed-in pages (audit 18 ERR-03)."""

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        response["Clear-Site-Data"] = '"cache"'
        return response


logout = LogoutView.as_view()


class PasswordChangeView(auth_views.PasswordChangeView):
    """Change one's own password; clears a forced change (ADR 0013).

    Django keeps the current session (update_session_auth_hash) and every
    other session of this login stops verifying because the password changed.
    """

    template_name = "registration/password_change_form.html"
    success_url = reverse_lazy("home")

    def get_context_data(self, **kwargs):
        # The rules checklist quotes the real minimum, so the page never disagrees with the server.
        context = super().get_context_data(**kwargs)
        lengths = [
            v.min_length for v in password_validation.get_default_password_validators()
            if isinstance(v, password_validation.MinimumLengthValidator)
        ]
        context["password_min_length"] = max(lengths, default=0)
        # After a rejected POST, focus starts on the first invalid input (the template sets autofocus).
        form = context["form"]
        context["first_invalid"] = next(
            (name for name in form.fields if form.is_bound and name in form.errors), None
        )
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        user = form.user
        if user.must_change_password:
            get_user_model().objects.filter(pk=user.pk).update(must_change_password=False)
            area = usage.area_of_user(user)
            if area:
                usage.record(self.request, area=area, workflow="sign_in",
                             step="password_changed_first")
        SecurityEvent.record(
            SecurityEvent.EventType.PASSWORD_CHANGED, actor=user, subject_user=user
        )
        messages.success(self.request, "Your password has been changed.")
        return response


password_change = never_cache(PasswordChangeView.as_view())
