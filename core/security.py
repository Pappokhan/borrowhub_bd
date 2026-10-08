"""Small, dependency-free rate limiting helpers (uses Django's cache)."""
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError


def client_ip(request):
    if settings.TRUST_PROXY_HEADERS:
        fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def hit(key, window):
    """Increment a counter that expires after `window` seconds; returns the new count."""
    cache.add(key, 0, timeout=window)
    try:
        return cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=window)
        return 1


def rate_limited(request, scope, limit, window=3600):
    """True once the caller (by IP) has used `limit` calls of `scope` in `window` seconds."""
    return hit(f"rl:{scope}:{client_ip(request)}", window) > limit


class LoginThrottleMixin:
    """Lock a username+IP pair after too many failed logins. Works for site and admin login forms."""

    def clean(self):
        request = getattr(self, "request", None)
        username = (self.data.get("username") or "").strip().lower()[:150]
        key = f"loginfail:{client_ip(request) if request else '-'}:{username}"
        if cache.get(key, 0) >= settings.LOGIN_MAX_ATTEMPTS:
            raise ValidationError(
                "Too many failed attempts. Please wait %(m)d minutes and try again.",
                code="locked", params={"m": settings.LOGIN_LOCKOUT_SECONDS // 60})
        try:
            cleaned = super().clean()
        except ValidationError:
            hit(key, settings.LOGIN_LOCKOUT_SECONDS)
            raise
        cache.delete(key)
        return cleaned
