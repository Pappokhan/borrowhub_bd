from .models import SiteSetting


def site(request):
    ctx = {"SITE": SiteSetting.load()}
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        ctx["unread_count"] = user.notifications.filter(is_read=False).count()
    return ctx
