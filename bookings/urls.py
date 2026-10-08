from django.urls import path

from . import views

app_name = "bookings"
urlpatterns = [
    path("", views.booking_list, name="list"),
    path("<str:code>/", views.booking_detail, name="detail"),
    path("<str:code>/invoice/", views.booking_invoice, name="invoice"),
    path("<str:code>/<slug:action>/", views.booking_action, name="action"),
]
