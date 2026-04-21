from django.urls import path
from . import views

app_name = "services"

urlpatterns = [
    path("", views.ServiceDashboardView.as_view(), name="dashboard"),

    path("categories/", views.ServiceCategoryListView.as_view(), name="category_list"),
    path("categories/new/", views.ServiceCategoryCreateView.as_view(), name="category_create"),
    path("categories/<int:pk>/edit/", views.ServiceCategoryUpdateView.as_view(), name="category_update"),

    path("list/", views.ServiceUnitListView.as_view(), name="service_list"),
    path("list/new/", views.ServiceUnitCreateView.as_view(), name="service_create"),
    path("list/<int:pk>/edit/", views.ServiceUnitUpdateView.as_view(), name="service_update"),

    path("resources/", views.ServiceResourceListView.as_view(), name="resource_list"),
    path("resources/new/", views.ServiceResourceCreateView.as_view(), name="resource_create"),
    path("resources/<int:pk>/edit/", views.ServiceResourceUpdateView.as_view(), name="resource_update"),

    path("bookings/", views.ServiceBookingListView.as_view(), name="booking_list"),
    path("bookings/new/", views.ServiceBookingCreateView.as_view(), name="booking_create"),
    path("bookings/<int:pk>/", views.ServiceBookingDetailView.as_view(), name="booking_detail"),
    path("bookings/<int:pk>/edit/", views.ServiceBookingUpdateView.as_view(), name="booking_update"),

    path("bookings/<int:booking_pk>/payment/new/", views.ServicePaymentCreateView.as_view(), name="payment_create"),

    path("bookings/<int:pk>/check-in/", views.service_booking_check_in, name="booking_check_in"),
    path("bookings/<int:pk>/check-out/", views.service_booking_check_out, name="booking_check_out"),
    path("bookings/<int:pk>/cancel/", views.service_booking_cancel, name="booking_cancel"),
    path("bookings/<int:pk>/complete/", views.service_booking_complete, name="booking_complete"),
]