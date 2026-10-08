from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from bookings.models import Booking, Review
from core.models import notify
from core.security import rate_limited
from listings.models import Listing

from .forms import ProfileForm, RegisterForm, VerificationForm
from .models import User


def register(request):
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and rate_limited(request, "register", 10, 3600):
        messages.error(request, "Too many sign-ups from your network. Please try again later.")
        return render(request, "accounts/register.html", {"form": RegisterForm()}, status=429)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user, backend="accounts.backends.EmailOrUsernameBackend")
        notify(user, "Welcome to BorrowHub BD! Add your payout details so you can earn and get refunds.",
               reverse("accounts:profile"))
        messages.success(request, "Account created. Welcome to BorrowHub BD!")
        nxt = request.GET.get("next", "")
        if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
            return redirect(nxt)
        return redirect("accounts:dashboard")
    return render(request, "accounts/register.html", {"form": form})


@login_required
def dashboard(request):
    u = request.user
    S = Booking.Status
    mine_owner = Booking.objects.filter(owner=u).select_related("listing", "renter")
    mine_renter = Booking.objects.filter(renter=u).select_related("listing", "owner")
    checks = [bool(u.phone), bool(u.city), bool(u.area), bool(u.avatar), bool(u.payout_account), u.is_verified]
    ctx = {
        "pending_requests": mine_owner.filter(status=S.PENDING)[:5],
        "to_pay": mine_renter.filter(status=S.ACCEPTED)[:5],
        "owner_todo": mine_owner.filter(status__in=[S.PAID, S.ACTIVE, S.RETURNED, S.DISPUTED])[:5],
        "renter_live": mine_renter.filter(status__in=[S.PAID, S.ACTIVE, S.RETURNED, S.DISPUTED])[:5],
        "earnings": mine_owner.filter(status=S.COMPLETED).aggregate(s=Sum("owner_payout"))["s"] or 0,
        "spent": mine_renter.filter(status=S.COMPLETED).aggregate(
            s=Sum(F("rental_amount") + F("delivery_fee")))["s"] or 0,
        "listing_count": Listing.objects.filter(owner=u).count(),
        "active_listing_count": Listing.objects.filter(owner=u, status="active").count(),
        "rentals_count": mine_renter.count(),
        "recent": Booking.objects.filter(Q(owner=u) | Q(renter=u)).select_related(
            "listing", "owner", "renter").order_by("-created_at")[:6],
        "completeness": int(sum(checks) / len(checks) * 100),
    }
    return render(request, "accounts/dashboard.html", ctx)


@login_required
def profile_edit(request):
    form = ProfileForm(request.POST or None, request.FILES or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profile saved.")
        return redirect("accounts:profile")
    return render(request, "accounts/profile_edit.html", {"form": form})


@login_required
def verification_request(request):
    user = request.user
    if user.is_verified:
        messages.info(request, "You're already verified.")
        return redirect("accounts:dashboard")
    form = VerificationForm(request.POST or None, request.FILES or None, instance=user)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.verification_status = User.Verification.PENDING
        obj.save()
        messages.success(request, "Submitted! Our team will review your NID within 1–2 working days.")
        return redirect("accounts:dashboard")
    return render(request, "accounts/verification.html", {"form": form})


def public_profile(request, username):
    member = get_object_or_404(User, username=username, is_active=True)
    listings = Listing.objects.public().with_stats().filter(owner=member)
    reviews = Review.objects.filter(reviewee=member).select_related("reviewer", "listing")[:10]
    done = Booking.objects.filter(owner=member, status=Booking.Status.COMPLETED).count()
    return render(request, "accounts/public_profile.html", {
        "member": member, "listings": listings, "reviews": reviews, "done": done})
