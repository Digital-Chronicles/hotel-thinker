# accounts/urls.py
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    # Dashboard / Profile
    path("", views.dashboard, name="dashboard"),
    path("me/", views.my_profile, name="my_profile"),

    # Hotel members (staff)
    path("members/", views.HotelMembersListView.as_view(), name="hotel_members_list"),
    path("members/<int:pk>/edit/", views.HotelMemberUpdateView.as_view(), name="hotel_member_update"),
    path("members/<int:pk>/toggle-active/", views.hotel_member_toggle_active, name="hotel_member_toggle_active"),
]