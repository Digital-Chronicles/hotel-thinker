# hotel_thinker/urls.py

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),

    # Public-facing hotel profiles
    path("", include("hotels.public_urls", namespace="hotel_public")),

    # Authentication
    path("accounts/", include("django.contrib.auth.urls")),

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

    # Mobile API
    path("api/mobile/", include("mobile_api.urls", namespace="mobile_api")),
]

# Media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)