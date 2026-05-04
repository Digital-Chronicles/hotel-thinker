from django.urls import path
from . import views

app_name = "bookings"

urlpatterns = [
    path("", views.BookingListView.as_view(), name="booking_list"),
    path("create/", views.BookingCreateView.as_view(), name="booking_create"),
    path("<int:pk>/", views.BookingDetailView.as_view(), name="booking_detail"),
    path("<int:pk>/edit/", views.BookingUpdateView.as_view(), name="booking_update"),

    path("<int:pk>/check-in/", views.booking_check_in, name="booking_check_in"),
    path("<int:pk>/check-out/", views.booking_check_out, name="booking_check_out"),
    path("<int:pk>/cancel/", views.booking_cancel, name="booking_cancel"),

    path("<int:pk>/add-payment/", views.booking_add_payment, name="booking_add_payment"),
    path("<int:pk>/add-charge/", views.booking_add_charge, name="booking_add_charge"),
    path("charges/<int:pk>/delete/", views.booking_delete_charge, name="booking_delete_charge"),

    path("guests/", views.GuestListView.as_view(), name="guest_list"),
    path("guests/create/", views.GuestCreateView.as_view(), name="guest_create"),
    path("guests/<int:pk>/", views.GuestDetailView.as_view(), name="guest_detail"),
    path("guests/<int:pk>/edit/", views.GuestUpdateView.as_view(), name="guest_update"),
    path("guests/<int:pk>/toggle-blacklist/", views.guest_toggle_blacklist, name="guest_toggle_blacklist"),
    path("guests/quick-create/", views.guest_quick_create, name="guest_quick_create"),

    path("dashboard/", views.BookingDashboardView.as_view(), name="dashboard"),
    path("reports/", views.booking_report, name="booking_report"),
    path("room-availability/", views.room_availability_calendar, name="room_availability"),
    path("check-room-availability/", views.check_room_availability, name="check_room_availability"),
    path("stats-api/", views.booking_stats_api, name="booking_stats_api"),
    path("quick-stats-api/", views.booking_quick_stats_api, name="booking_quick_stats_api"),
]