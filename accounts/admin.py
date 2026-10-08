from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html

from core.models import notify

from .models import User


@admin.register(User)
class BorrowHubUserAdmin(UserAdmin):
    list_display = ("username", "display_name", "email", "phone", "city", "verification_status",
                    "is_active", "is_staff", "date_joined")
    list_filter = ("verification_status", "city", "is_active", "is_staff", "date_joined")
    search_fields = ("username", "email", "first_name", "last_name", "phone", "nid_number")
    list_per_page = 30
    readonly_fields = ("nid_preview", "avatar_preview", "last_login", "date_joined")
    fieldsets = UserAdmin.fieldsets + (
        ("BorrowHub profile", {"fields": ("phone", "city", "area", "address", "bio", "avatar", "avatar_preview")}),
        ("Identity verification", {"fields": ("verification_status", "nid_number", "nid_photo", "nid_preview")}),
        ("Payouts", {"fields": ("payout_method", "payout_account")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Contact", {"fields": ("email", "first_name", "last_name", "phone", "city")}),
    )
    actions = ["approve_verification", "reject_verification", "deactivate_users"]

    @admin.display(description="NID photo")
    def nid_preview(self, obj):
        if obj and obj.nid_photo:
            return format_html('<a href="{0}" target="_blank" rel="noopener"><img src="{0}" style="max-height:160px;border-radius:6px"></a>',
                               obj.nid_photo.url)
        return "—"

    @admin.display(description="Avatar")
    def avatar_preview(self, obj):
        if obj and obj.avatar:
            return format_html('<img src="{}" style="height:64px;width:64px;border-radius:50%;object-fit:cover">',
                               obj.avatar.url)
        return "—"

    @admin.action(description="✔ Approve identity verification")
    def approve_verification(self, request, queryset):
        users = list(queryset)
        queryset.update(verification_status=User.Verification.VERIFIED)
        for u in users:
            notify(u, "Your identity is verified. You now have the Verified badge!", "/accounts/dashboard/")
        self.message_user(request, f"{len(users)} member(s) verified.", messages.SUCCESS)

    @admin.action(description="✖ Reject identity verification")
    def reject_verification(self, request, queryset):
        users = list(queryset)
        queryset.update(verification_status=User.Verification.REJECTED)
        for u in users:
            notify(u, "We couldn't verify your NID. Please re-submit a clear photo.", "/accounts/verification/")
        self.message_user(request, f"{len(users)} request(s) rejected.", messages.WARNING)

    @admin.action(description="Deactivate selected accounts")
    def deactivate_users(self, request, queryset):
        n = queryset.exclude(pk=request.user.pk).update(is_active=False)
        self.message_user(request, f"{n} account(s) deactivated.", messages.WARNING)
