from django.contrib import admin

from .models import ContactMessage, Notification, SiteSetting


@admin.register(SiteSetting)
class SiteSettingAdmin(admin.ModelAdmin):
    fieldsets = (
        ("Brand", {"fields": ("site_name", "tagline", "support_phone", "support_email", "office_address")}),
        ("Money", {"fields": ("commission_percent", "payment_window_hours", "inspection_window_hours")}),
        ("Moderation & payments", {"fields": ("require_listing_approval", "auto_verify_payments")}),
        ("Where renters send money (mobile banking)", {"fields": ("bkash_number", "nagad_number", "rocket_number")}),
    )

    def has_add_permission(self, request):
        return not SiteSetting.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("subject", "name", "email", "is_resolved", "created_at")
    list_filter = ("is_resolved", "created_at")
    search_fields = ("subject", "name", "email", "message")
    list_editable = ("is_resolved",)
    readonly_fields = ("name", "email", "subject", "message", "created_at")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "message", "is_read", "created_at")
    list_filter = ("is_read", "created_at")
    search_fields = ("user__username", "message")
