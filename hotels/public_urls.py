from django.urls import path
from . import views_public

app_name = "hotel"

urlpatterns = [
    # HOME
    path("", views_public.public_home, name="home"),
    path("about/", views_public.public_about, name="about"),

    # HOTELS
    path("hotels/", views_public.public_hotels_list, name="hotels_list"),

    # SINGLE HOTEL (ONE PAGE)
    path("hotels/<slug:slug>/", views_public.public_hotel_profile, name="hotel_profile"),

    # OPTIONAL
    path("hotels/<slug:slug>/gallery/", views_public.public_hotel_gallery, name="hotel_gallery"),
    path("hotels/<slug:slug>/reviews/", views_public.public_hotel_reviews, name="hotel_reviews"),
]