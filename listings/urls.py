from django.urls import path

from . import views

app_name = "listings"
urlpatterns = [
    path("", views.listing_list, name="list"),
    path("new/", views.listing_create, name="create"),
    path("mine/", views.my_listings, name="mine"),
    path("favorites/", views.favorites, name="favorites"),
    path("image/<int:pk>/delete/", views.image_delete, name="image_delete"),
    path("<slug:slug>/", views.listing_detail, name="detail"),
    path("<slug:slug>/edit/", views.listing_update, name="update"),
    path("<slug:slug>/delete/", views.listing_delete, name="delete"),
    path("<slug:slug>/toggle/", views.listing_toggle, name="toggle"),
    path("<slug:slug>/favorite/", views.favorite_toggle, name="favorite"),
]
