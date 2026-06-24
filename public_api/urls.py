from django.urls import path
from . import views

app_name = "public_api"

urlpatterns = [
    path("auth/register/", views.GuestRegisterAPIView.as_view(), name="guest_register"),
    path("auth/login/", views.GuestLoginAPIView.as_view(), name="guest_login"),
    path("auth/me/", views.GuestMeAPIView.as_view(), name="guest_me"),
    path("auth/bookings/", views.GuestBookingListAPIView.as_view(), name="guest_bookings"),
    path("auth/bookings/<int:pk>/", views.GuestBookingDetailAPIView.as_view(), name="guest_booking_detail"),
    path("auth/profile/", views.GuestProfileUpdateAPIView.as_view(), name="guest_profile_update"),

    path("home/", views.PublicHomeAPIView.as_view(), name="home"),

    path("experiences/", views.PublicAllExperienceListAPIView.as_view(), name="all_experiences"),
    path("experiences/<int:pk>/", views.PublicExperienceDetailAPIView.as_view(), name="experience_detail"),

    path("hotels/", views.PublicHotelListAPIView.as_view(), name="hotel_list"),
    path("hotels/<slug:slug>/", views.PublicHotelDetailAPIView.as_view(), name="hotel_detail"),
    path("hotels/<slug:slug>/rooms/", views.PublicHotelRoomsAPIView.as_view(), name="hotel_rooms"),
    path("hotels/<slug:slug>/gallery/", views.PublicHotelGalleryAPIView.as_view(), name="hotel_gallery"),
    path("hotels/<slug:slug>/availability/", views.PublicAvailabilityAPIView.as_view(), name="availability"),
    path("hotels/<slug:slug>/menu/", views.PublicMenuAPIView.as_view(), name="menu"),
    path("hotels/<slug:slug>/bar/", views.PublicBarAPIView.as_view(), name="bar"),
    path("hotels/<slug:slug>/experiences/", views.PublicExperienceListCreateAPIView.as_view(), name="experiences"),
    path("hotels/<slug:slug>/reviews/", views.PublicReviewListCreateAPIView.as_view(), name="reviews"),
    path("hotels/<slug:slug>/bookings/", views.PublicBookingCreateAPIView.as_view(), name="create_booking"),
    path("hotels/<slug:slug>/food-orders/", views.PublicRestaurantOrderCreateAPIView.as_view(), name="create_food_order"),
    path("hotels/<slug:slug>/drink-orders/", views.PublicBarOrderCreateAPIView.as_view(), name="create_drink_order"),
]
