import random
import string
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse

ZERO = Decimal("0.00")


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Awaiting owner"
        ACCEPTED = "accepted", "Awaiting payment"
        PAID = "paid", "Paid · ready for handover"
        ACTIVE = "active", "On rent"
        RETURNED = "returned", "Returned · inspection"
        COMPLETED = "completed", "Completed"
        DISPUTED = "disputed", "In dispute"
        REJECTED = "rejected", "Declined"
        CANCELLED = "cancelled", "Cancelled"

    class Delivery(models.TextChoices):
        PICKUP = "pickup", "Pickup from owner"
        DELIVERY = "delivery", "Delivery & return by owner"

    class DepositStatus(models.TextChoices):
        UNPAID = "unpaid", "Not collected"
        HELD = "held", "Held by BorrowHub"
        REFUNDED = "refunded", "Fully refunded"
        PARTIAL = "partial", "Partially refunded"
        FORFEITED = "forfeited", "Kept for damages"

    code = models.CharField(max_length=12, unique=True, editable=False)
    listing = models.ForeignKey("listings.Listing", on_delete=models.PROTECT, related_name="bookings")
    renter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="rentals")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="owner_bookings")

    start_date = models.DateField()
    end_date = models.DateField()
    days = models.PositiveSmallIntegerField(default=1)
    delivery_method = models.CharField(max_length=10, choices=Delivery.choices, default=Delivery.PICKUP)
    delivery_address = models.TextField(blank=True)
    message = models.TextField("message to owner", blank=True)

    # Money snapshot (taken when the booking is requested so later edits don't change old deals)
    daily_rate = models.DecimalField(max_digits=10, decimal_places=2)
    rental_amount = models.DecimalField(max_digits=10, decimal_places=2)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO)
    security_deposit = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO)
    total_payable = models.DecimalField(max_digits=10, decimal_places=2,
                                        help_text="Rental + delivery + refundable deposit")
    commission_percent = models.DecimalField(max_digits=5, decimal_places=2, default=ZERO)
    commission_amount = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO)
    owner_payout = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO,
                                       help_text="Rental + delivery − commission (before any deposit deduction)")

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    deposit_status = models.CharField(max_length=10, choices=DepositStatus.choices, default=DepositStatus.UNPAID)
    deposit_deduction = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO)
    inspection_note = models.TextField(blank=True)
    cancel_reason = models.CharField(max_length=255, blank=True)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name="+")

    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    handed_over_at = models.DateTimeField(null=True, blank=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["listing", "status", "start_date", "end_date"])]
        constraints = [models.CheckConstraint(condition=models.Q(end_date__gte=models.F("start_date")),
                                              name="booking_end_after_start")]

    def __str__(self):
        return f"{self.code} · {self.listing}"

    def save(self, *args, **kwargs):
        if not self.code:
            while True:
                code = "BH" + "".join(random.choices(string.digits, k=7))
                if not Booking.objects.filter(code=code).exists():
                    self.code = code
                    break
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("bookings:detail", args=[self.code])

    PROGRESS = {"pending": 0, "accepted": 1, "paid": 2, "active": 3, "returned": 4, "disputed": 4, "completed": 5}

    @property
    def progress_step(self):
        return self.PROGRESS.get(self.status, -1)

    @property
    def badge_class(self):
        return {"pending": "warn", "accepted": "info", "paid": "info", "active": "info", "returned": "warn",
                "completed": "ok", "disputed": "bad", "rejected": "bad", "cancelled": "muted"}[self.status]

    @property
    def refund_due(self):
        return self.security_deposit - self.deposit_deduction

    def other_party(self, user):
        return self.owner if user.id == self.renter_id else self.renter


class Payment(models.Model):
    class Kind(models.TextChoices):
        COLLECTION = "collection", "Renter → BorrowHub"
        PAYOUT = "payout", "BorrowHub → Owner"
        REFUND = "refund", "BorrowHub → Renter"

    class Method(models.TextChoices):
        BKASH = "bkash", "bKash"
        NAGAD = "nagad", "Nagad"
        ROCKET = "rocket", "Rocket"
        BANK = "bank", "Bank transfer"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed / rejected"

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="payments")
    kind = models.CharField(max_length=12, choices=Kind.choices)
    method = models.CharField(max_length=10, choices=Method.choices, default=Method.BKASH)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    trx_id = models.CharField("transaction ID", max_length=40, blank=True)
    account = models.CharField("sender / receiver number", max_length=60, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    processed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_kind_display()} ৳{self.amount} ({self.get_status_display()})"


class Dispute(models.Model):
    class Reason(models.TextChoices):
        DAMAGE = "damage", "Item damaged"
        NOT_RETURNED = "not_returned", "Item not returned"
        NOT_AS_DESCRIBED = "not_as_described", "Item not as described"
        DEDUCTION = "deduction", "Disagree with deposit deduction"
        NO_SHOW = "no_show", "Other party didn't show up"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        REVIEW = "review", "Under review"
        RESOLVED = "resolved", "Resolved"

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="disputes")
    raised_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="disputes_raised")
    reason = models.CharField(max_length=20, choices=Reason.choices)
    details = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    final_deduction = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Set the amount of deposit that goes to the owner, then set status to Resolved.")
    resolution_note = models.TextField(blank=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name="+")
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Dispute on {self.booking.code}"


class Review(models.Model):
    class Direction(models.TextChoices):
        FOR_OWNER = "for_owner", "Renter reviewed owner/item"
        FOR_RENTER = "for_renter", "Owner reviewed renter"

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="reviews")
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews_written")
    reviewee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews_received")
    listing = models.ForeignKey("listings.Listing", on_delete=models.CASCADE, related_name="reviews")
    direction = models.CharField(max_length=12, choices=Direction.choices)
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("booking", "reviewer")

    def __str__(self):
        return f"{self.rating}★ by {self.reviewer} on {self.booking.code}"
