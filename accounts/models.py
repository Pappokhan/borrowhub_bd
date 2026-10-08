from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Avg, Count

from core.constants import BD_CITIES
from core.images import optimize_upload
from core.storage import private_storage

phone_validator = RegexValidator(
    r"^(?:\+?88)?01[3-9]\d{8}$",
    "Enter a valid Bangladeshi mobile number, e.g. 01712345678.",
)


class User(AbstractUser):
    class Verification(models.TextChoices):
        UNVERIFIED = "unverified", "Not verified"
        PENDING = "pending", "Under review"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"

    class PayoutMethod(models.TextChoices):
        BKASH = "bkash", "bKash"
        NAGAD = "nagad", "Nagad"
        ROCKET = "rocket", "Rocket"
        BANK = "bank", "Bank account"

    email = models.EmailField("email address", unique=True)
    phone = models.CharField(max_length=20, blank=True, validators=[phone_validator])
    city = models.CharField(max_length=60, blank=True, choices=BD_CITIES)
    area = models.CharField("area / thana", max_length=100, blank=True)
    address = models.TextField(blank=True)
    bio = models.TextField(max_length=400, blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True)

    nid_number = models.CharField("NID number", max_length=20, blank=True)
    nid_photo = models.ImageField("NID photo", upload_to="nid/", blank=True, storage=private_storage)
    verification_status = models.CharField(
        max_length=12, choices=Verification.choices, default=Verification.UNVERIFIED)

    payout_method = models.CharField(max_length=10, choices=PayoutMethod.choices, default=PayoutMethod.BKASH)
    payout_account = models.CharField(
        "payout account / number", max_length=60, blank=True,
        help_text="Where BorrowHub sends your earnings and refunds.")

    class Meta:
        ordering = ["-date_joined"]

    def save(self, *args, **kwargs):
        optimize_upload(self.avatar, max_side=600)
        optimize_upload(self.nid_photo, max_side=1800, quality=88)
        super().save(*args, **kwargs)

    @property
    def display_name(self):
        return self.get_full_name() or self.username

    @property
    def is_verified(self):
        return self.verification_status == self.Verification.VERIFIED

    def rating_summary(self):
        data = self.reviews_received.aggregate(avg=Avg("rating"), n=Count("id"))
        return {"avg": data["avg"], "count": data["n"]}

    def __str__(self):
        return self.display_name
