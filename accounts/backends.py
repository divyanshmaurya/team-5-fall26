"""Authentication backend that accepts an email address or a username.

Both username and email matching are case-insensitive.
Usernames may contain "@", so a login identifier might match both a username
and a different user's email address; each match is checked against the
password in turn.
Contains timing-attack protection: hash password even when no matching user exists.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.core.exceptions import PermissionDenied
from django.db.models import Q


class EmailOrUsernameBackend(ModelBackend):
    """Log users in with either their username or their email address.

    Both are matched regardless of case. Usernames may contain "@", so one
    login can match a username and a different user's email address; each
    match is checked against the password in turn. Accounts the login page
    has locked after too many failures are skipped, so they can't be
    guessed at while another account matching the same text logs in.
    Once it has checked the unlocked accounts, it stops Django from trying
    later backends, which would otherwise check a locked account's password.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        Return the active user whose username or email and password match.

        Args:
            request: Django HttpRequest object
            username: user-supplied login identifier (username or email string)
            password: user-supplied plaintext password
        Returns:
            User object if credentials valid and user is active; None otherwise
        Raises:
            PermissionDenied: no unlocked account matched and some matching
                accounts are locked, so no other backend may try them
        """
        User = get_user_model()
        if username is None or password is None:
            return None
        locked_ids = getattr(request, "login_locked_user_ids", ())
        users = User._default_manager.filter(
            Q(username__iexact=username) | Q(email__iexact=username)
        ).exclude(pk__in=locked_ids)
        for user in users:
            if user.check_password(password) and self.user_can_authenticate(user):
                return user
        if not users:
            # Hash password to prevent timing attacks that detect existing accounts
            User().set_password(password)
        if locked_ids:
            # ModelBackend would still match a locked account by its username.
            # PermissionDenied makes django.contrib.auth.authenticate() stop
            # here instead of trying the next backend.
            raise PermissionDenied
        return None
