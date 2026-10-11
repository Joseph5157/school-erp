from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models.functions import Lower

from accounts.usernames import normalize_username


class NormalizedUsernameBackend(ModelBackend):
    """Sign in by the normalized username, compared case-insensitively.

    Existing usernames are never rewritten (ADR 0013); the database
    constraint on Lower("username") guarantees at most one match.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if username is None or password is None:
            return None
        key = normalize_username(username)
        user = (
            UserModel._default_manager.annotate(_username_key=Lower("username"))
            .filter(_username_key=key)
            .first()
        )
        if user is None:
            # Run the hasher anyway to reduce timing differences.
            UserModel().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
