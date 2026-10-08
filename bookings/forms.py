from datetime import timedelta
from decimal import Decimal

from django import forms
from django.utils import timezone

from core.forms import BootstrapFormMixin

from . import services
from .models import Booking, Dispute, Payment, Review


class BookingForm(BootstrapFormMixin, forms.Form):
    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    end_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    delivery_method = forms.ChoiceField(choices=Booking.Delivery.choices, widget=forms.RadioSelect,
                                        initial=Booking.Delivery.PICKUP)
    delivery_address = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}),
                                       label="Delivery address")
    message = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}),
                              label="Message to owner (optional)")

    def __init__(self, *args, listing, **kwargs):
        super().__init__(*args, **kwargs)
        self.listing = listing
        choices = []
        if listing.pickup_available:
            choices.append((Booking.Delivery.PICKUP, "Pickup from owner · free"))
        if listing.delivery_available:
            fee = f"৳{listing.delivery_fee:.0f}" if listing.delivery_fee else "free"
            choices.append((Booking.Delivery.DELIVERY, f"Delivery & return · {fee}"))
        self.fields["delivery_method"].choices = choices
        self.fields["delivery_method"].initial = choices[0][0] if choices else None
        today = timezone.localdate().isoformat()
        self.fields["start_date"].widget.attrs["min"] = today
        self.fields["end_date"].widget.attrs["min"] = today

    def clean(self):
        data = super().clean()
        start, end = data.get("start_date"), data.get("end_date")
        if not start or not end:
            return data
        today = timezone.localdate()
        if start < today:
            self.add_error("start_date", "Start date can't be in the past.")
        if end < start:
            self.add_error("end_date", "End date must be on or after the start date.")
        if self.errors:
            return data
        days = (end - start).days + 1
        l = self.listing
        if days < l.min_days:
            self.add_error("end_date", f"Minimum rental is {l.min_days} day(s).")
        elif days > l.max_days:
            self.add_error("end_date", f"Maximum rental is {l.max_days} day(s).")
        elif start > today + timedelta(days=180):
            self.add_error("start_date", "You can book up to 6 months ahead.")
        elif not services.is_available(l, start, end):
            raise forms.ValidationError("Those dates are already booked. See the unavailable dates below.")
        if data.get("delivery_method") == Booking.Delivery.DELIVERY and not data.get("delivery_address", "").strip():
            self.add_error("delivery_address", "Enter the address for delivery.")
        return data


class PaymentForm(BootstrapFormMixin, forms.Form):
    method = forms.ChoiceField(choices=[c for c in Payment.Method.choices if c[0] != "bank"], label="Paid via")
    trx_id = forms.CharField(min_length=6, max_length=40, label="Transaction ID (TrxID)")
    sender = forms.CharField(max_length=20, label="Number you paid from")

    def clean_trx_id(self):
        trx = self.cleaned_data["trx_id"].strip().upper()
        if Payment.objects.filter(kind=Payment.Kind.COLLECTION, trx_id=trx).exclude(
                status=Payment.Status.FAILED).exists():
            raise forms.ValidationError("This transaction ID has already been used.")
        return trx


class InspectionForm(BootstrapFormMixin, forms.Form):
    deduction = forms.DecimalField(min_value=Decimal("0"), max_digits=10, decimal_places=2, initial=0,
                                   label="Deposit deduction for damage (৳)",
                                   help_text="Leave 0 if the item came back in good condition.")
    note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), label="Inspection note")

    def clean(self):
        data = super().clean()
        if (data.get("deduction") or 0) > 0 and not data.get("note", "").strip():
            self.add_error("note", "Describe the damage so the renter understands the deduction.")
        return data


class DisputeForm(BootstrapFormMixin, forms.Form):
    reason = forms.ChoiceField(choices=Dispute.Reason.choices)
    details = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), min_length=15,
                              label="What happened?")


class ReviewForm(BootstrapFormMixin, forms.Form):
    rating = forms.ChoiceField(choices=[(i, f"{i}★") for i in range(5, 0, -1)], widget=forms.RadioSelect)
    comment = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}), label="Comment")

    def clean_rating(self):
        return int(self.cleaned_data["rating"])
