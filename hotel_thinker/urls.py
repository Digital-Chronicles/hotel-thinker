# hotel_thinker/urls.py
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),

    # Auth (login/logout/password views)
    path("accounts/", include("django.contrib.auth.urls")),

    # App UI
    path("", include("accounts.urls", namespace="accounts")),
    path("hotel/", include("hotels.urls", namespace="hotels")),
    path("rooms/", include("rooms.urls", namespace="rooms")),
    path("bookings/", include("bookings.urls", namespace="bookings")),
    path("finance/", include("finance.urls", namespace="finance")),
    path("restaurant/", include("restaurant.urls", namespace="restaurant")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)