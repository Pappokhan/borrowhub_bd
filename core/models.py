from decimal import Decimal

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class SiteSetting(models.Model):
    """Singleton with marketplace-wide business settings, editable in the admin."""

    site_name = models.CharField(max_length=80, default="BorrowHub BD")
    tagline = models.CharField(max_length=160, default="Kenar dorkar nei — proyojon hole rent nao.")
    commission_percent = models.DecimalField(
        "Commission (%)", max_digits=5, decimal_places=2, default=Decimal("10.00"),
        validators=[MinValueValidator(0), MaxValueValidator(50)],
        help_text="Charged to the owner on the rental amount of every completed booking. "
                  "Each booking stores the rate that applied when it was requested.",
    )
    payment_window_hours = models.PositiveSmallIntegerField(
        default=24, help_text="Renter must pay within this many hours after the owner accepts.")
    inspection_window_hours = models.PositiveSmallIntegerField(
        default=48, help_text="Renter has this long to accept or dispute a deposit deduction.")
    require_listing_approval = models.BooleanField(
        default=False, help_text="If on, new listings stay 'Pending' until staff approve them.")
    auto_verify_payments = models.BooleanField(
        default=True,
        help_text="DEMO MODE: payments are marked verified instantly. Turn OFF in production so "
                  "staff verify each bKash/Nagad transaction ID manually (or connect a gateway).")
    bkash_number = models.CharField(max_length=20, blank=True, default="01700-000000")
    nagad_number = models.CharField(max_length=20, blank=True, default="01800-000000")
    rocket_number = models.CharField(max_length=20, blank=True, default="01900-000000")
    support_phone = models.CharField(max_length=30, blank=True, default="+880 1700-000000")
    support_email = models.EmailField(blank=True, default="support@borrowhub.bd")
    office_address = models.CharField(max_length=200, blank=True, default="Dhaka, Bangladesh")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Site settings"
        verbose_name_plural = "Site settings"

    def __str__(self):
        return "Site settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def payment_numbers(self):
        return {"bkash": self.bkash_number, "nagad": self.nagad_number, "rocket": self.rocket_number}


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    message = models.CharField(max_length=255)
    url = models.CharField(max_length=255, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} — {self.message[:40]}"


logger = logging.getLogger("borrowhub")


def _email_user(user_id, message, url):
    from django.contrib.auth import get_user_model
    try:
        user = get_user_model().objects.get(pk=user_id)
        if not user.email:
            return
        link = f"\n\nOpen: {settings.SITE_URL}{url}" if url else ""
        send_mail(f"[BorrowHub BD] {message[:80]}", f"Hi {user.display_name},\n\n{message}{link}\n\n— BorrowHub BD",
                  settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True)
    except Exception:  # an email problem must never break a booking
        logger.exception("Could not send notification email")


def notify(user, message, url=""):
    """Create an in-app notification (and optionally an email once the transaction commits)."""
    if user is None:
        return None
    note = Notification.objects.create(user=user, message=message[:255], url=url)
    if settings.EMAIL_NOTIFICATIONS:
        from django.db import transaction
        transaction.on_commit(lambda: _email_user(user.pk, message, url))
    return note


class ContactMessage(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    subject = models.CharField(max_length=150)
    message = models.TextField()
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.subject} ({self.email})"
