from django.urls import path

from . import views

app_name = "core"
urlpatterns = [
    path("", views.home, name="home"),
    path("how-it-works/", views.how_it_works, name="how_it_works"),
    path("terms/", views.terms, name="terms"),
    path("contact/", views.contact, name="contact"),
    path("notifications/", views.notifications, name="notifications"),
    path("healthz/", views.healthz, name="healthz"),
    path("robots.txt", views.robots_txt, name="robots"),
    path("private/<path:path>", views.private_file, name="private_file"),
]
