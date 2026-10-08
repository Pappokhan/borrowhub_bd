from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils._os import safe_join
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from accounts.models import User
from bookings.models import Booking
from core.constants import BD_CITIES
from listings.models import Category, Listing

from .forms import ContactForm
from .security import rate_limited


def home(request):
    base = Listing.objects.public().with_stats()
    context = {
        "categories": Category.objects.filter(is_active=True).annotate(
            n=Count("listings", filter=Q(listings__status="active"))),
        "featured": base.filter(is_featured=True)[:4],
        "latest": base[:8],
        "cities": BD_CITIES[:8],
        "stats": {
            "listings": Listing.objects.public().count(),
            "members": User.objects.filter(is_active=True).count(),
            "completed": Booking.objects.filter(status=Booking.Status.COMPLETED).count(),
        },
    }
    return render(request, "core/home.html", context)


def how_it_works(request):
    return render(request, "core/how_it_works.html")


def terms(request):
    return render(request, "core/terms.html")


def contact(request):
    form = ContactForm(request.POST or None)
    if request.method == "POST" and rate_limited(request, "contact", 5, 3600):
        messages.error(request, "Too many messages from your network. Please try again later.")
        return redirect("core:contact")
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Thanks — we received your message and will reply by email soon.")
        return redirect("core:contact")
    return render(request, "core/contact.html", {"form": form})


@login_required
def notifications(request):
    items = list(request.user.notifications.all()[:60])
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return render(request, "core/notifications.html", {"items": items})


@never_cache
@require_GET
def healthz(request):
    """Liveness/readiness probe for Docker, load balancers and uptime monitors."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return JsonResponse({"status": "error"}, status=503)
    return JsonResponse({"status": "ok"})


@require_GET
def robots_txt(request):
    lines = [
        "User-agent: *",
        f"Disallow: /{settings.ADMIN_URL}",
        "Disallow: /accounts/",
        "Disallow: /bookings/",
        "Disallow: /private/",
        "Disallow: /notifications/",
        "",
        f"Sitemap: {settings.SITE_URL}/sitemap.xml",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")


@staff_member_required
def private_file(request, path):
    """Staff-only download of sensitive uploads such as NID photos."""
    try:
        full = safe_join(settings.PRIVATE_MEDIA_ROOT, path)
    except Exception:
        raise Http404
    try:
        return FileResponse(open(full, "rb"))
    except (FileNotFoundError, IsADirectoryError):
        raise Http404
