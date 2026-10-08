from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views
from .forms import ThrottledAuthenticationForm

app_name = "accounts"
urlpatterns = [
    path("register/", views.register, name="register"),
    path("login/", auth_views.LoginView.as_view(template_name="accounts/login.html",
                                                 redirect_authenticated_user=True,
                                                 authentication_form=ThrottledAuthenticationForm), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("password/", auth_views.PasswordChangeView.as_view(
        template_name="accounts/password_change.html", success_url=reverse_lazy("accounts:dashboard")),
        name="password_change"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("profile/", views.profile_edit, name="profile"),
    path("verification/", views.verification_request, name="verification"),
    path("u/<str:username>/", views.public_profile, name="public_profile"),
]
