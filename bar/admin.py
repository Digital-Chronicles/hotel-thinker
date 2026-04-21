from django.contrib import admin
from .models import (
    BarCategory,
    BarItem,
    BarStockMovement,
    BarOrder,
    BarOrderItem,
)


class BarItemInline(admin.TabularInline):
    model = BarOrderItem
    extra = 1
    autocomplete_fields = ("item",)
    fields = ("item", "qty", "unit_price", "note")
    show_change_link = True


@admin.register(BarCategory)
class BarCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "hotel", "sort_order", "is_active")
    list_filter = ("hotel", "is_active")
    search_fields = ("name", "hotel__name")
    ordering = ("hotel", "sort_order", "name")


@admin.register(BarItem)
class BarItemAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "hotel",
        "category",
        "unit",
        "selling_price",
        "cost_price",
        "stock_qty",
        "reorder_level",
        "track_stock",
        "is_active",
    )
    list_filter = (
        "hotel",
        "category",
        "track_stock",
        "is_active",
    )
    search_fields = (
        "name",
        "sku",
        "hotel__name",
        "category__name",
    )
    list_editable = ("selling_price", "stock_qty", "reorder_level", "is_active")
    autocomplete_fields = ("hotel", "category")
    ordering = ("hotel", "category", "name")


@admin.register(BarStockMovement)
class BarStockMovementAdmin(admin.ModelAdmin):
    list_display = (
        "item",
        "hotel",
        "movement_type",
        "quantity",
        "balance_after",
        "reference",
        "created_by",
        "created_at",
    )
    list_filter = ("hotel", "movement_type", "created_at")
    search_fields = (
        "item__name",
        "reference",
        "note",
        "hotel__name",
    )
    autocomplete_fields = ("hotel", "item", "created_by")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)


@admin.register(BarOrder)
class BarOrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number",
        "hotel",
        "guest_name",
        "booking",
        "room_charge",
        "status",
        "discount",
        "tax",
        "created_by",
        "created_at",
        "closed_at",
    )
    list_filter = (
        "hotel",
        "status",
        "room_charge",
        "created_at",
    )
    search_fields = (
        "order_number",
        "guest_name",
        "booking__guest__first_name",
        "booking__guest__last_name",
        "hotel__name",
    )
    autocomplete_fields = ("hotel", "booking", "created_by")
    readonly_fields = ("order_number", "created_at", "closed_at")
    inlines = [BarItemInline]
    ordering = ("-created_at",)


@admin.register(BarOrderItem)
class BarOrderItemAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "item",
        "qty",
        "unit_price",
        "line_total_display",
    )
    search_fields = (
        "order__order_number",
        "item__name",
        "note",
    )
    autocomplete_fields = ("order", "item")

    @admin.display(description="Line Total")
    def line_total_display(self, obj):
        return obj.line_total