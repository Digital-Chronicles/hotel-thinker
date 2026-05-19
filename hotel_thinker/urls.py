# hotel_thinker/urls.py

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views

urlpatterns = [
    path("admin/", admin.site.urls),

    # Public-facing hotel profiles
    path("", include("hotels.public_urls", namespace="hotel_public")),

    # Authentication
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(
            template_name="accounts/login.html",
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path(
        "accounts/logout/",
        auth_views.LogoutView.as_view(
            next_page="/accounts/login/",
        ),
        name="logout",
    ),

    # Core apps
    path("accounts/", include("accounts.urls", namespace="accounts")),
    path("hotel/", include("hotels.urls", namespace="hotels")),
    path("rooms/", include("rooms.urls", namespace="rooms")),
    path("bookings/", include("bookings.urls", namespace="bookings")),
    path("finance/", include("finance.urls", namespace="finance")),

    # Operations
    path("restaurant/", include("restaurant.urls", namespace="restaurant")),
    path("bar/", include("bar.urls", namespace="bar")),
    path("store/", include("store.urls", namespace="store")),
    path("services/", include("services.urls", namespace="services")),

    # Reports
    path("reports/", include("reports.urls", namespace="reports")),
    path("bulk/", include("bulk.urls", namespace="bulk")),

    # APIs
    path("api/mobile/", include("mobile_api.urls", namespace="mobile_api")),
    path("api/public/", include("public_api.urls", namespace="public_api")),
]