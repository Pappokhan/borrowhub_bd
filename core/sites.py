from django.contrib import admin
from django.contrib.admin.forms import AdminAuthenticationForm
from django.db.models import Count, Sum
from django.utils import timezone

from .security import LoginThrottleMixin


class ThrottledAdminLoginForm(LoginThrottleMixin, AdminAuthenticationForm):
    pass


class BorrowHubAdminSite(admin.AdminSite):
    site_header = "BorrowHub BD"
    site_title = "BorrowHub BD admin"
    index_title = "Marketplace control center"
    login_form = ThrottledAdminLoginForm

    def index(self, request, extra_context=None):
        from accounts.models import User
        from bookings.models import Booking, Dispute, Payment
        from listings.models import Listing

        B, P = Booking.Status, Payment
        done = Booking.objects.filter(status=B.COMPLETED)
        month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        pending_out = Payment.objects.filter(kind__in=[P.Kind.PAYOUT, P.Kind.REFUND], status=P.Status.PENDING)
        stats = {
            "users": User.objects.count(),
            "pending_verifications": User.objects.filter(verification_status="pending").count(),
            "listings_active": Listing.objects.filter(status="active").count(),
            "listings_pending": Listing.objects.filter(status="pending").count(),
            "bookings_total": Booking.objects.count(),
            "bookings_live": Booking.objects.filter(status__in=[B.PENDING, B.ACCEPTED, B.PAID, B.ACTIVE]).count(),
            "gmv": done.aggregate(s=Sum("rental_amount"))["s"] or 0,
            "commission": done.aggregate(s=Sum("commission_amount"))["s"] or 0,
            "commission_month": done.filter(completed_at__gte=month_start).aggregate(s=Sum("commission_amount"))["s"] or 0,
            "payments_to_verify": Payment.objects.filter(kind=P.Kind.COLLECTION, status=P.Status.PENDING).count(),
            "payouts_pending": pending_out.count(),
            "payouts_pending_amount": pending_out.aggregate(s=Sum("amount"))["s"] or 0,
            "deposits_held": Booking.objects.filter(deposit_status=Booking.DepositStatus.HELD)
                                     .aggregate(s=Sum("security_deposit"))["s"] or 0,
            "disputes_open": Dispute.objects.exclude(status=Dispute.Status.RESOLVED).count(),
        }
        top = (Listing.objects.filter(status="active").annotate(n=Count("bookings"))
               .order_by("-n")[:5])
        extra_context = extra_context or {}
        extra_context.update(
            stats=stats,
            top_listings=top,
            recent_bookings=Booking.objects.select_related("listing", "renter").order_by("-created_at")[:8],
        )
        return super().index(request, extra_context)
