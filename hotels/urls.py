from django.urls import path
from . import views, views_public

app_name = "hotels"

urlpatterns = [
    # Public website pages
    path("", views_public.public_home, name="home"),
    path("hotels/", views_public.public_hotels_list, name="hotels_list"),
    path("hotels/<slug:slug>/", views_public.public_hotel_profile, name="hotel_profile"),
    path("hotels/<slug:slug>/gallery/", views_public.public_hotel_gallery, name="hotel_gallery"),
    path("hotels/<slug:slug>/reviews/", views_public.public_hotel_reviews, name="hotel_reviews"),
    path("experiences/", views_public.public_experiences_list, name="experiences_list"),
    path("about/", views_public.public_about, name="about"),

    # Logged-in hotel admin/settings pages
    path("hotel-detail/", views.hotel_detail, name="detail"),
    path("settings/", views.hotel_settings, name="settings"),
]
