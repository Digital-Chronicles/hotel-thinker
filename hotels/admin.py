# hotels/admin.py
from django.contrib import admin
from .models import Hotel, HotelSetting


@admin.register(Hotel)
class HotelAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "created_at", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("name",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(HotelSetting)
class HotelSettingAdmin(admin.ModelAdmin):
    list_display = ("hotel", "phone_number", "email", "updated_at")
    search_fields = ("hotel__name", "phone_number", "email")
    ordering = ("hotel__name",)
    readonly_fields = ("updated_at",)