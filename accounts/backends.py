from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q


class EmailOrUsernameBackend(ModelBackend):
    """Let members sign in with either their username or their email."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
        if not username or password is None:
            return None
        user = User.objects.filter(Q(username__iexact=username) | Q(email__iexact=username)).first()
        if user is None:
            User().set_password(password)  # mitigate timing differences
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
