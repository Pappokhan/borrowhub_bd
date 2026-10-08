class SecurityHeadersMiddleware:
    """Adds a few cheap hardening headers that Django doesn't set by default."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        response.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        if request.path.startswith("/private/"):
            response["Cache-Control"] = "private, no-store"
        return response
