# bookings/urls.py
from django.urls import path
from . import views

app_name = "bookings"

urlpatterns = [

    # Guests
    path("guests/", views.GuestListView.as_view(), name="guest_list"),
    path("guests/new/", views.GuestCreateView.as_view(), name="guest_create"),
    path("guests/<int:pk>/edit/", views.GuestUpdateView.as_view(), name="guest_update"),

    # AJAX quick guest create
    path("guests/quick-create/", views.guest_quick_create, name="guest_quick_create"),


    # BOOKINGS
    path("", views.BookingListView.as_view(), name="booking_list"),
    path("new/", views.BookingCreateView.as_view(), name="booking_create"),
    path("<int:pk>/", views.BookingDetailView.as_view(), name="booking_detail"),
    path("<int:pk>/edit/", views.BookingUpdateView.as_view(), name="booking_update"),


    # PAYMENT
    path(
        "<int:pk>/add-payment/",
        views.booking_add_payment,
        name="booking_add_payment"
    ),


    # ACTIONS
    path("<int:pk>/check-in/", views.booking_check_in, name="booking_check_in"),
    path("<int:pk>/check-out/", views.booking_check_out, name="booking_check_out"),
    path("<int:pk>/cancel/", views.booking_cancel, name="booking_cancel"),
]