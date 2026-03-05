from django.urls import path
from . import views

app_name = "rooms"

urlpatterns = [
    # Rooms Manager
    path("manage/", views.RoomsManageDashboardView.as_view(), name="manage_dashboard"),

    # Room Types
    path("room-types/", views.RoomTypeListView.as_view(), name="roomtype_list"),
    path("room-types/new/", views.RoomTypeCreateView.as_view(), name="roomtype_create"),
    path("room-types/<int:pk>/edit/", views.RoomTypeUpdateView.as_view(), name="roomtype_update"),

    # Rooms
    path("", views.RoomListView.as_view(), name="room_list"),
    path("new/", views.RoomCreateView.as_view(), name="room_create"),
    path("<int:pk>/", views.RoomDetailView.as_view(), name="room_detail"),
    path("<int:pk>/edit/", views.RoomUpdateView.as_view(), name="room_update"),
    path("<int:pk>/set-status/", views.room_set_status, name="room_set_status"),
]