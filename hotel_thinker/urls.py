from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),

    # Public authentication aliases used by older templates.
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="/"), name="logout"),

    # Register the hotels app under BOTH namespaces because existing templates
    # use both {% url 'hotel:...' %} and {% url 'hotels:...' %}.
    path("", include(("hotels.urls", "hotel"), namespace="hotel")),
    path("", include(("hotels.urls", "hotels"), namespace="hotels")),

    path("accounts/", include("accounts.urls")),
    path("rooms/", include("rooms.urls")),
    path("bookings/", include("bookings.urls")),
    path("finance/", include("finance.urls")),
    path("restaurant/", include("restaurant.urls")),
    path("bar/", include("bar.urls")),
    path("store/", include("store.urls")),
    path("services/", include("services.urls")),
    path("reports/", include("reports.urls")),
    path("bulk/", include("bulk.urls")),
    path("operations/", include("operations.urls")),
    path("api/mobile/", include("mobile_api.urls")),
    path("api/public/", include("public_api.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
