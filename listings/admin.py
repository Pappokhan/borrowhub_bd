from django.contrib import admin, messages
from django.utils.html import format_html

from core.models import notify

from .models import Category, Favorite, Listing, ListingImage


class ListingImageInline(admin.TabularInline):
    model = ListingImage
    extra = 0
    readonly_fields = ("preview",)
    fields = ("image", "preview", "order")

    @admin.display(description="Preview")
    def preview(self, obj):
        if obj and obj.image:
            return format_html('<img src="{}" style="height:60px;border-radius:4px">', obj.image.url)
        return "—"


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "icon", "order", "is_active", "listing_count")
    list_editable = ("order", "is_active")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)

    @admin.display(description="Listings")
    def listing_count(self, obj):
        return obj.listings.count()


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ("thumb", "title", "owner", "category", "city", "price_per_day", "security_deposit",
                    "status", "is_featured", "views_count", "created_at")
    list_display_links = ("thumb", "title")
    list_filter = ("status", "is_featured", "category", "city", "condition", "delivery_available", "created_at")
    search_fields = ("title", "brand", "description", "owner__username", "owner__email", "area")
    list_editable = ("status", "is_featured")
    list_select_related = ("owner", "category")
    date_hierarchy = "created_at"
    readonly_fields = ("slug", "views_count", "created_at", "updated_at")
    inlines = [ListingImageInline]
    autocomplete_fields = ()
    raw_id_fields = ("owner",)
    actions = ["approve", "reject", "pause", "feature", "unfeature"]
    fieldsets = (
        ("Item", {"fields": ("owner", "category", "title", "slug", "brand", "description", "condition", "rules")}),
        ("Pricing", {"fields": ("price_per_day", "security_deposit", "min_days", "max_days")}),
        ("Location & handover", {"fields": ("city", "area", "pickup_available", "delivery_available", "delivery_fee")}),
        ("Moderation", {"fields": ("status", "is_featured", "views_count", "created_at", "updated_at")}),
    )

    @admin.display(description="")
    def thumb(self, obj):
        cover = obj.cover
        if cover:
            return format_html('<img src="{}" style="height:42px;width:56px;object-fit:cover;border-radius:6px">',
                               cover.image.url)
        return "—"

    @admin.action(description="✔ Approve / activate selected")
    def approve(self, request, queryset):
        for listing in queryset.exclude(status=Listing.Status.ACTIVE):
            listing.status = Listing.Status.ACTIVE
            listing.save(update_fields=["status", "updated_at"])
            notify(listing.owner, f"Your listing “{listing.title}” is now live.", listing.get_absolute_url())
        self.message_user(request, "Listings approved.", messages.SUCCESS)

    @admin.action(description="✖ Reject selected")
    def reject(self, request, queryset):
        for listing in queryset:
            listing.status = Listing.Status.REJECTED
            listing.save(update_fields=["status", "updated_at"])
            notify(listing.owner, f"Your listing “{listing.title}” was not approved. Please edit and contact support.",
                   "/listings/mine/")
        self.message_user(request, "Listings rejected.", messages.WARNING)

    @admin.action(description="Pause selected")
    def pause(self, request, queryset):
        queryset.update(status=Listing.Status.PAUSED)

    @admin.action(description="★ Feature selected")
    def feature(self, request, queryset):
        queryset.update(is_featured=True)

    @admin.action(description="☆ Remove featured")
    def unfeature(self, request, queryset):
        queryset.update(is_featured=False)


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ("user", "listing", "created_at")
    raw_id_fields = ("user", "listing")
