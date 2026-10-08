from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from core.constants import BD_CITIES
from core.forms import BootstrapFormMixin
from core.security import LoginThrottleMixin

from .models import User, phone_validator


class ThrottledAuthenticationForm(LoginThrottleMixin, AuthenticationForm):
    username = forms.CharField(label="Username or email", widget=forms.TextInput(attrs={"autofocus": True}))


class RegisterForm(BootstrapFormMixin, UserCreationForm):
    first_name = forms.CharField(max_length=60, label="First name")
    last_name = forms.CharField(max_length=60, label="Last name")
    phone = forms.CharField(max_length=20, validators=[phone_validator], label="Mobile number")
    city = forms.ChoiceField(choices=[("", "Select city")] + BD_CITIES)
    area = forms.CharField(max_length=100, label="Area / thana")
    agree_terms = forms.BooleanField(label="I agree to the Terms & Deposit Policy")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email", "phone", "city", "area")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email


class ProfileForm(BootstrapFormMixin, forms.ModelForm):
    city = forms.ChoiceField(choices=[("", "Select city")] + BD_CITIES)

    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone", "city", "area", "address", "bio",
                  "avatar", "payout_method", "payout_account"]
        widgets = {"address": forms.Textarea(attrs={"rows": 2}), "bio": forms.Textarea(attrs={"rows": 3})}


class VerificationForm(BootstrapFormMixin, forms.ModelForm):
    nid_number = forms.CharField(max_length=20, label="NID number")
    nid_photo = forms.ImageField(label="Photo of your NID (front)")

    class Meta:
        model = User
        fields = ["nid_number", "nid_photo"]
