import csv

from django.contrib import admin, messages
from django.http import HttpResponse
from django.utils import timezone
from django.utils.html import format_html

from core.models import notify

from . import services
from .models import Booking, Dispute, Payment, Review


def export_csv(modeladmin, request, queryset):
    meta = modeladmin.model._meta
    fields = [f.name for f in meta.fields]
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f"attachment; filename={meta.model_name}s-{timezone.localdate()}.csv"
    writer = csv.writer(response)
    writer.writerow(fields)
    for obj in queryset:
        writer.writerow([str(getattr(obj, f)) for f in fields])
    return response


export_csv.short_description = "⬇ Export selected to CSV"


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    fields = ("kind", "method", "amount", "trx_id", "account", "status", "note", "processed_at")
    readonly_fields = ("processed_at",)
    show_change_link = True


class DisputeInline(admin.StackedInline):
    model = Dispute
    extra = 0
    fields = ("raised_by", "reason", "details", "status")
    readonly_fields = ("raised_by", "reason", "details", "status")
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("code", "listing", "renter", "owner", "start_date", "end_date", "colored_status",
                    "total_payable", "commission_amount", "deposit_status", "created_at")
    list_filter = ("status", "deposit_status", "delivery_method", "created_at", "listing__category")
    search_fields = ("code", "listing__title", "renter__username", "renter__phone", "owner__username",
                     "owner__phone")
    date_hierarchy = "created_at"
    list_select_related = ("listing", "renter", "owner")
    raw_id_fields = ("listing", "renter", "owner", "cancelled_by")
    readonly_fields = ("code", "days", "daily_rate", "rental_amount", "delivery_fee", "security_deposit",
                       "total_payable", "commission_percent", "commission_amount", "owner_payout",
                       "created_at", "accepted_at", "paid_at", "handed_over_at", "returned_at",
                       "completed_at", "cancelled_at")
    inlines = [PaymentInline, DisputeInline]
    actions = [export_csv]
    fieldsets = (
        ("Booking", {"fields": ("code", "status", "listing", "renter", "owner", "start_date", "end_date", "days",
                                "delivery_method", "delivery_address", "message")}),
        ("Money (৳)", {"fields": ("daily_rate", "rental_amount", "delivery_fee", "security_deposit",
                                  "total_payable", "commission_percent", "commission_amount", "owner_payout")}),
        ("Deposit & inspection", {"fields": ("deposit_status", "deposit_deduction", "inspection_note")}),
        ("Cancellation", {"fields": ("cancel_reason", "cancelled_by")}),
        ("Timeline", {"fields": ("created_at", "accepted_at", "paid_at", "handed_over_at", "returned_at",
                                 "completed_at", "cancelled_at")}),
    )

    @admin.display(description="Status", ordering="status")
    def colored_status(self, obj):
        colors = {"ok": "#0b7a55", "bad": "#c0392b", "warn": "#b7791f", "info": "#2b6cb0", "muted": "#718096"}
        return format_html('<b style="color:{}">{}</b>', colors[obj.badge_class], obj.get_status_display())


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "booking", "kind", "method", "amount", "trx_id", "account", "status", "created_at")
    list_filter = ("status", "kind", "method", "created_at")
    search_fields = ("booking__code", "trx_id", "account", "booking__renter__username", "booking__owner__username")
    date_hierarchy = "created_at"
    list_select_related = ("booking",)
    raw_id_fields = ("booking",)
    readonly_fields = ("processed_at", "processed_by", "created_at")
    actions = ["verify_incoming", "reject_incoming", "mark_sent", export_csv]

    @admin.action(description="✔ Verify selected incoming payments (renter paid)")
    def verify_incoming(self, request, queryset):
        ok = 0
        for p in queryset.filter(kind=Payment.Kind.COLLECTION, status=Payment.Status.PENDING):
            try:
                services.verify_payment(p, by=request.user)
                ok += 1
            except services.ServiceError as exc:
                self.message_user(request, str(exc), messages.WARNING)
        self.message_user(request, f"{ok} payment(s) verified; bookings moved to Paid.", messages.SUCCESS)

    @admin.action(description="✖ Reject selected incoming payments")
    def reject_incoming(self, request, queryset):
        n = 0
        for p in queryset.filter(kind=Payment.Kind.COLLECTION, status=Payment.Status.PENDING):
            services.reject_payment(p, by=request.user)
            n += 1
        self.message_user(request, f"{n} payment(s) rejected.", messages.WARNING)

    @admin.action(description="💸 Mark selected payouts/refunds as SENT")
    def mark_sent(self, request, queryset):
        n = 0
        for p in queryset.exclude(kind=Payment.Kind.COLLECTION).filter(status=Payment.Status.PENDING):
            p.status = Payment.Status.COMPLETED
            p.processed_at = timezone.now()
            p.processed_by = request.user
            p.save(update_fields=["status", "processed_at", "processed_by"])
            target = p.booking.owner if p.kind == Payment.Kind.PAYOUT else p.booking.renter
            notify(target, f"৳{p.amount} has been sent to your {p.get_method_display()} account"
                   + (f" (TrxID {p.trx_id})." if p.trx_id else "."), p.booking.get_absolute_url())
            n += 1
        self.message_user(request, f"{n} transfer(s) marked as sent.", messages.SUCCESS)


@admin.register(Dispute)
class DisputeAdmin(admin.ModelAdmin):
    list_display = ("id", "booking", "raised_by", "reason", "status", "final_deduction", "created_at")
    list_filter = ("status", "reason", "created_at")
    search_fields = ("booking__code", "raised_by__username", "details")
    raw_id_fields = ("booking", "raised_by")
    readonly_fields = ("booking", "raised_by", "reason", "details", "created_at", "resolved_by", "resolved_at")
    fieldsets = (
        ("Case", {"fields": ("booking", "raised_by", "reason", "details", "created_at")}),
        ("Decision", {"fields": ("status", "final_deduction", "resolution_note", "resolved_by", "resolved_at"),
                      "description": "To close the case: enter the final deduction (৳ going to the owner, the rest "
                                     "of the deposit is refunded to the renter), add a note, and set status to Resolved."}),
    )

    def has_add_permission(self, request):
        return False  # disputes are opened by members from the booking page

    def save_model(self, request, obj, form, change):
        was_resolved = Dispute.objects.filter(pk=obj.pk, status=Dispute.Status.RESOLVED).exists() if obj.pk else False
        if obj.status == Dispute.Status.RESOLVED and not was_resolved:
            if obj.final_deduction is None:
                obj.final_deduction = 0
            try:
                services.resolve_dispute(obj, obj.final_deduction, obj.resolution_note, request.user)
            except services.ServiceError as exc:
                self.message_user(request, str(exc), messages.ERROR)
                return
            for party in (obj.booking.renter, obj.booking.owner):
                notify(party, f"Dispute on {obj.booking.code} resolved. See booking for details.",
                       obj.booking.get_absolute_url())
        else:
            super().save_model(request, obj, form, change)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("booking", "reviewer", "reviewee", "direction", "rating", "created_at")
    list_filter = ("direction", "rating", "created_at")
    search_fields = ("booking__code", "reviewer__username", "reviewee__username", "comment")
    raw_id_fields = ("booking", "reviewer", "reviewee", "listing")
