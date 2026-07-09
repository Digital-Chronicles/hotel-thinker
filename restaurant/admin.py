from django.contrib import admin
from .models import (
    DiningArea,
    Table,
    MenuCategory,
    MenuItem,
    RestaurantOrder,
    RestaurantOrderItem,
)


@admin.register(DiningArea)
class DiningAreaAdmin(admin.ModelAdmin):
    list_display = ("hotel", "name")
    list_filter = ("hotel",)
    search_fields = ("hotel__name", "name")
    ordering = ("hotel__name", "name")
    autocomplete_fields = ("hotel",)


@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = ("hotel", "area", "number", "seats", "is_active")
    list_filter = ("hotel", "area", "is_active")
    search_fields = ("hotel__name", "number", "area__name")
    ordering = ("hotel__name", "number")
    autocomplete_fields = ("hotel", "area")


@admin.register(MenuCategory)
class MenuCategoryAdmin(admin.ModelAdmin):
    list_display = ("hotel", "name", "sort_order", "image_url", "is_active")
    list_filter = ("hotel", "is_active")
    fields = ("hotel", "name", "description", "image_url", "sort_order", "is_active")
    search_fields = ("hotel__name", "name", "description", "image_url")
    ordering = ("hotel__name", "sort_order", "name")
    autocomplete_fields = ("hotel",)


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ("hotel", "category", "name", "price", "image_url", "is_active")
    list_filter = ("hotel", "category", "is_active")
    fields = (
        "hotel", "category", "name", "description", "image_url", "ingredients",
        "price", "cost_price", "track_stock", "stock_qty", "reorder_level",
        "is_vegetarian", "is_vegan", "is_gluten_free", "is_spicy",
        "is_featured", "is_recommended", "is_active", "preparation_time",
    )
    search_fields = ("hotel__name", "name", "description", "category__name", "image_url")
    ordering = ("hotel__name", "category__name", "name")
    autocomplete_fields = ("hotel", "category")


class RestaurantOrderItemInline(admin.TabularInline):
    model = RestaurantOrderItem
    extra = 0
    autocomplete_fields = ("item",)
    fields = ("item", "qty", "unit_price", "note")
    

@admin.register(RestaurantOrder)
class RestaurantOrderAdmin(admin.ModelAdmin):
    list_display = ("hotel", "id", "table", "customer_name", "status", "created_by", "created_at")
    list_filter = ("hotel", "status", "created_at")
    search_fields = ("hotel__name", "id", "table__number", "customer_name", "created_by__username")
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)
    autocomplete_fields = ("hotel", "table", "created_by")
    inlines = [RestaurantOrderItemInline]

    actions = ["mark_kitchen", "mark_served", "mark_billed", "mark_paid", "mark_cancelled"]

    @admin.action(description="Mark selected orders as In Kitchen")
    def mark_kitchen(self, request, queryset):
        queryset.update(status=RestaurantOrder.Status.KITCHEN)

    @admin.action(description="Mark selected orders as Served")
    def mark_served(self, request, queryset):
        queryset.update(status=RestaurantOrder.Status.SERVED)

    @admin.action(description="Mark selected orders as Billed")
    def mark_billed(self, request, queryset):
        queryset.update(status=RestaurantOrder.Status.BILLED)

    @admin.action(description="Mark selected orders as Paid")
    def mark_paid(self, request, queryset):
        queryset.update(status=RestaurantOrder.Status.PAID)

    @admin.action(description="Mark selected orders as Cancelled")
    def mark_cancelled(self, request, queryset):
        queryset.update(status=RestaurantOrder.Status.CANCELLED)
