from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.core.paginator import Paginator
from django.db.models import F, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from bookings import services
from bookings.forms import BookingForm
from bookings.models import Booking, Review
from core.constants import BD_CITIES
from core.models import SiteSetting

from .forms import ListingForm
from .models import Category, Favorite, Listing, ListingImage

SORTS = {
    "newest": "-created_at",
    "price_low": "price_per_day",
    "price_high": "-price_per_day",
    "popular": "-views_count",
}


def _decimal(value):
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError):
        return None


def listing_list(request):
    qs = Listing.objects.public().with_stats()
    g = request.GET
    q = g.get("q", "").strip()
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(brand__icontains=q)
                       | Q(category__name__icontains=q))
    if g.get("category"):
        qs = qs.filter(category__slug=g["category"])
    if g.get("city"):
        qs = qs.filter(city=g["city"])
    lo, hi = _decimal(g.get("min_price")), _decimal(g.get("max_price"))
    if lo is not None:
        qs = qs.filter(price_per_day__gte=lo)
    if hi is not None:
        qs = qs.filter(price_per_day__lte=hi)
    if g.get("delivery") == "1":
        qs = qs.filter(delivery_available=True)
    start, end = g.get("start"), g.get("end")
    if start and end:
        try:
            busy = Booking.objects.filter(status__in=services.BLOCKING, start_date__lte=end,
                                          end_date__gte=start).values("listing_id")
            qs = qs.exclude(pk__in=busy)
        except Exception:  # malformed dates are ignored
            pass
    sort = g.get("sort", "newest")
    qs = qs.order_by(SORTS.get(sort, "-created_at"))

    page = Paginator(qs, 12).get_page(g.get("page"))
    params = g.copy()
    params.pop("page", None)
    return render(request, "listings/list.html", {
        "page": page, "categories": Category.objects.filter(is_active=True), "cities": BD_CITIES,
        "query_string": params.urlencode(), "sort": sort, "total": page.paginator.count,
        "filters_active": any(g.get(k) for k in ("q", "category", "city", "min_price", "max_price", "delivery", "start")),
    })


def listing_detail(request, slug):
    listing = get_object_or_404(Listing.objects.with_stats(), slug=slug)
    user = request.user
    is_owner = user.is_authenticated and listing.owner_id == user.id
    if listing.status != Listing.Status.ACTIVE and not (is_owner or user.is_staff):
        raise Http404
    form = None
    if listing.status == Listing.Status.ACTIVE and not is_owner:
        form = BookingForm(request.POST or None, listing=listing)

    if request.method == "POST":
        if not user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if form is None:
            messages.error(request, "You can't book this listing.")
            return redirect(listing)
        if form.is_valid():
            try:
                booking = services.create_booking(listing=listing, renter=user, **form.cleaned_data)
            except services.ServiceError as exc:
                form.add_error(None, str(exc))
            else:
                messages.success(request, "Request sent! The owner will confirm shortly.")
                return redirect(booking)
    elif not is_owner:
        Listing.objects.filter(pk=listing.pk).update(views_count=F("views_count") + 1)

    booked = Booking.objects.filter(listing=listing, status__in=services.BLOCKING,
                                    end_date__gte=timezone.localdate()).order_by("start_date")
    return render(request, "listings/detail.html", {
        "listing": listing, "form": form, "is_owner": is_owner, "booked_ranges": booked,
        "reviews": Review.objects.filter(listing=listing, direction="for_owner").select_related("reviewer")[:10],
        "similar": Listing.objects.public().with_stats().filter(category=listing.category)
                          .exclude(pk=listing.pk)[:4],
        "is_favorite": user.is_authenticated and Favorite.objects.filter(user=user, listing=listing).exists(),
    })


def _save_images(listing, files):
    start = listing.images.count()
    for i, f in enumerate(files):
        ListingImage.objects.create(listing=listing, image=f, order=start + i)


@login_required
def listing_create(request):
    form = ListingForm(request.POST or None, request.FILES or None, require_images=True)
    if request.method == "POST" and form.is_valid():
        listing = form.save(commit=False)
        listing.owner = request.user
        needs_review = SiteSetting.load().require_listing_approval and not request.user.is_staff
        listing.status = Listing.Status.PENDING if needs_review else Listing.Status.ACTIVE
        listing.save()
        _save_images(listing, form.cleaned_data["images"])
        if needs_review:
            messages.info(request, "Listing submitted. It will go live once our team approves it.")
        else:
            messages.success(request, "Your listing is live!")
        return redirect("listings:mine")
    return render(request, "listings/form.html", {"form": form, "mode": "create"})


@login_required
def listing_update(request, slug):
    listing = get_object_or_404(Listing, slug=slug, owner=request.user)
    form = ListingForm(request.POST or None, request.FILES or None, instance=listing,
                       existing_images=listing.images.count())
    if request.method == "POST" and form.is_valid():
        form.save()
        _save_images(listing, form.cleaned_data["images"])
        messages.success(request, "Listing updated.")
        return redirect("listings:mine")
    return render(request, "listings/form.html", {
        "form": form, "mode": "edit", "listing": listing, "images": listing.images.all()})


@login_required
def my_listings(request):
    items = Listing.objects.filter(owner=request.user).with_stats()
    return render(request, "listings/my_listings.html", {"items": items})


@login_required
@require_POST
def listing_toggle(request, slug):
    listing = get_object_or_404(Listing, slug=slug, owner=request.user)
    if listing.status == Listing.Status.ACTIVE:
        listing.status = Listing.Status.PAUSED
        messages.info(request, "Listing paused — it's hidden from search.")
    elif listing.status == Listing.Status.PAUSED:
        listing.status = Listing.Status.ACTIVE
        messages.success(request, "Listing is live again.")
    else:
        messages.error(request, "This listing is waiting for staff approval.")
        return redirect("listings:mine")
    listing.save(update_fields=["status", "updated_at"])
    return redirect("listings:mine")


@login_required
def listing_delete(request, slug):
    listing = get_object_or_404(Listing, slug=slug, owner=request.user)
    if request.method == "POST":
        if listing.bookings.exists():
            listing.status = Listing.Status.PAUSED
            listing.save(update_fields=["status", "updated_at"])
            messages.warning(request, "This listing has booking history, so it was paused instead of deleted.")
        else:
            listing.delete()
            messages.success(request, "Listing deleted.")
        return redirect("listings:mine")
    return render(request, "listings/confirm_delete.html", {"listing": listing})


@login_required
@require_POST
def image_delete(request, pk):
    image = get_object_or_404(ListingImage, pk=pk, listing__owner=request.user)
    listing = image.listing
    if listing.images.count() <= 1:
        messages.error(request, "A listing needs at least one photo.")
    else:
        image.delete()
        messages.success(request, "Photo removed.")
    return redirect("listings:update", slug=listing.slug)


@login_required
@require_POST
def favorite_toggle(request, slug):
    listing = get_object_or_404(Listing, slug=slug)
    fav, created = Favorite.objects.get_or_create(user=request.user, listing=listing)
    if not created:
        fav.delete()
    return redirect(listing)


@login_required
def favorites(request):
    ids = Favorite.objects.filter(user=request.user).values_list("listing_id", flat=True)
    items = Listing.objects.public().with_stats().filter(pk__in=ids)
    return render(request, "listings/favorites.html", {"items": items})
