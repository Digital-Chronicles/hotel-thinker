from django.urls import path
from . import views

app_name = "public_api"

urlpatterns = [
    path("hotels/", views.PublicHotelListAPIView.as_view(), name="hotel_list"),
    path("hotels/<slug:slug>/", views.PublicHotelDetailAPIView.as_view(), name="hotel_detail"),
    path("hotels/<slug:slug>/availability/", views.PublicAvailabilityAPIView.as_view(), name="availability"),
    path("hotels/<slug:slug>/menu/", views.PublicMenuAPIView.as_view(), name="menu"),
    path("hotels/<slug:slug>/bar/", views.PublicBarAPIView.as_view(), name="bar"),
    path("hotels/<slug:slug>/bookings/", views.PublicBookingCreateAPIView.as_view(), name="create_booking"),
    path("hotels/<slug:slug>/food-orders/", views.PublicRestaurantOrderCreateAPIView.as_view(), name="create_food_order"),
    path("hotels/<slug:slug>/drink-orders/", views.PublicBarOrderCreateAPIView.as_view(), name="create_drink_order"),
]
