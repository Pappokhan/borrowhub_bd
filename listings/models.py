import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Avg, Count, Q
from django.urls import reverse
from django.utils.text import slugify

from core.constants import BD_CITIES
from core.images import optimize_upload


class Category(models.Model):
    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(unique=True)
    icon = models.CharField(max_length=40, default="bi-box-seam",
                            help_text="Bootstrap Icons class, e.g. bi-camera")
    description = models.CharField(max_length=160, blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class ListingQuerySet(models.QuerySet):
    def public(self):
        return self.filter(status=Listing.Status.ACTIVE)

    def with_stats(self):
        review_filter = Q(reviews__direction="for_owner")
        return (self.select_related("category", "owner").prefetch_related("images")
                .annotate(avg_rating=Avg("reviews__rating", filter=review_filter),
                          review_count=Count("reviews", filter=review_filter, distinct=True)))


class Listing(models.Model):
    class Condition(models.TextChoices):
        NEW = "new", "Brand new"
        LIKE_NEW = "like_new", "Like new"
        GOOD = "good", "Good"
        FAIR = "fair", "Fair"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending approval"
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        REJECTED = "rejected", "Rejected"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="listings")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="listings")
    title = models.CharField(max_length=120)
    slug = models.SlugField(max_length=150, unique=True, blank=True)
    brand = models.CharField("brand / model", max_length=80, blank=True)
    description = models.TextField()
    condition = models.CharField(max_length=10, choices=Condition.choices, default=Condition.GOOD)
    rules = models.TextField("usage rules", blank=True, help_text="e.g. No outdoor use in rain. Return fully charged.")

    price_per_day = models.DecimalField("price per day (৳)", max_digits=9, decimal_places=2,
                                        validators=[MinValueValidator(1)])
    security_deposit = models.DecimalField("security deposit (৳)", max_digits=9, decimal_places=2, default=0,
                                           validators=[MinValueValidator(0)])
    min_days = models.PositiveSmallIntegerField("minimum rental days", default=1)
    max_days = models.PositiveSmallIntegerField("maximum rental days", default=14)

    city = models.CharField(max_length=60, choices=BD_CITIES)
    area = models.CharField("area / thana", max_length=100)
    pickup_available = models.BooleanField(default=True)
    delivery_available = models.BooleanField(default=False)
    delivery_fee = models.DecimalField("delivery fee (৳)", max_digits=8, decimal_places=2, default=0,
                                       validators=[MinValueValidator(0)])

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    is_featured = models.BooleanField(default=False)
    views_count = models.PositiveIntegerField(default=0, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ListingQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "city"])]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = f"{slugify(self.title)[:100] or 'item'}-{uuid.uuid4().hex[:6]}"
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("listings:detail", args=[self.slug])

    @property
    def cover(self):
        images = list(self.images.all())
        return images[0] if images else None


class ListingImage(models.Model):
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="listings/%Y/%m/")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def save(self, *args, **kwargs):
        optimize_upload(self.image)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Image for {self.listing_id}"


class Favorite(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favorites")
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name="favorited_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "listing")
        ordering = ["-created_at"]
