from django import forms
from django.core.exceptions import ValidationError

from core.forms import BootstrapFormMixin

from .models import Listing

MAX_IMAGES = 6
MAX_IMAGE_BYTES = 5 * 1024 * 1024


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        if not data:
            if self.required:
                raise ValidationError(self.error_messages["required"], code="required")
            return []
        if not isinstance(data, (list, tuple)):
            data = [data]
        if len(data) > MAX_IMAGES:
            raise ValidationError(f"You can upload at most {MAX_IMAGES} photos.")
        cleaned = []
        for f in data:
            if f.size > MAX_IMAGE_BYTES:
                raise ValidationError(f"{f.name} is larger than 5 MB.")
            cleaned.append(super(MultipleImageField, self).clean(f, initial))
        return cleaned


class ListingForm(BootstrapFormMixin, forms.ModelForm):
    images = MultipleImageField(required=False, label="Photos",
                                help_text="Up to 6 photos, 5 MB each. The first one is the cover.")

    class Meta:
        model = Listing
        fields = ["category", "title", "brand", "description", "condition", "rules",
                  "price_per_day", "security_deposit", "min_days", "max_days",
                  "city", "area", "pickup_available", "delivery_available", "delivery_fee"]
        widgets = {"description": forms.Textarea(attrs={"rows": 5}), "rules": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, require_images=False, existing_images=0, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["images"].required = require_images
        self.existing_images = existing_images
        from .models import Category
        self.fields["category"].queryset = Category.objects.filter(is_active=True)

    def clean(self):
        data = super().clean()
        if data.get("min_days") and data.get("max_days") and data["max_days"] < data["min_days"]:
            self.add_error("max_days", "Maximum days must be at least the minimum days.")
        if not data.get("pickup_available") and not data.get("delivery_available"):
            raise ValidationError("Offer at least one handover option: pickup or delivery.")
        if data.get("delivery_available") is False:
            data["delivery_fee"] = 0
        if len(data.get("images") or []) + self.existing_images > MAX_IMAGES:
            self.add_error("images", f"A listing can have at most {MAX_IMAGES} photos in total.")
        return data
