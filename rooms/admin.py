from django.contrib import admin
from .models import RoomType, Room


@admin.register(RoomType)
class RoomTypeAdmin(admin.ModelAdmin):
    list_display = ("hotel", "name", "base_price")
    list_filter = ("hotel",)
    search_fields = ("hotel__name", "name")
    ordering = ("hotel__name", "name")
    autocomplete_fields = ("hotel",)


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("hotel", "number", "room_type", "status", "is_active")
    list_filter = ("hotel", "status", "is_active", "room_type")
    search_fields = ("hotel__name", "number", "room_type__name")
    ordering = ("hotel__name", "number")
    autocomplete_fields = ("hotel", "room_type")