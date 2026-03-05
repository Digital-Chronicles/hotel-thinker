# hotels/urls.py
from django.urls import path
from . import views

app_name = "hotels"

urlpatterns = [
    path("", views.hotel_detail, name="detail"),
    path("settings/", views.hotel_settings, name="settings"),
]