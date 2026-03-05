# accounts/admin.py
from django.contrib import admin
from .models import Profile, HotelMember


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone")
    search_fields = ("user__username", "user__email", "phone")
    ordering = ("user__username",)


@admin.register(HotelMember)
class HotelMemberAdmin(admin.ModelAdmin):
    list_display = ("hotel", "user", "role", "is_active", "joined_at")
    list_filter = ("hotel", "role", "is_active")
    search_fields = ("hotel__name", "user__username", "user__email")
    ordering = ("hotel__name", "user__username")
    readonly_fields = ("joined_at",)