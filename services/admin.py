from django.contrib import admin
from .models import (
    ServiceCategory,
    ServiceUnit,
    ServicePackageItem,
    ServiceResource,
    ServiceBooking,
    ServiceBookingExtra,
    ServicePayment,
    ServiceAttendance,
)


class ServicePackageItemInline(admin.TabularInline):
    model = ServicePackageItem
    extra = 1
    fields = ("item_name", "quantity", "unit", "extra_price", "is_optional", "notes")


class ServiceResourceInline(admin.TabularInline):
    model = ServiceResource
    extra = 1
    fields = ("name", "capacity", "is_active", "notes")


class ServiceBookingExtraInline(admin.TabularInline):
    model = ServiceBookingExtra
    extra = 1
    fields = ("name", "quantity", "unit_price", "notes")


class ServicePaymentInline(admin.TabularInline):
    model = ServicePayment
    extra = 0
    fields = ("amount", "method", "reference", "received_by", "paid_at", "notes")
    readonly_fields = ("created_at",)


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "hotel", "sort_order", "is_active")
    list_filter = ("hotel", "is_active")
    search_fields = ("name", "hotel__name")
    ordering = ("hotel", "sort_order", "name")


@admin.register(ServiceUnit)
class ServiceUnitAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "hotel",
        "category",
        "service_type",
        "pricing_mode",
        "base_price",
        "default_duration_minutes",
        "max_capacity",
        "requires_schedule",
        "allow_post_to_room",
        "is_active",
    )
    list_filter = (
        "hotel",
        "category",
        "service_type",
        "pricing_mode",
        "requires_schedule",
        "allow_post_to_room",
        "is_active",
    )
    search_fields = (
        "name",
        "code",
        "location",
        "category__name",
        "hotel__name",
    )
    autocomplete_fields = ("hotel", "category")
    list_editable = ("base_price", "is_active")
    inlines = [ServicePackageItemInline, ServiceResourceInline]
    ordering = ("hotel", "category", "name")


@admin.register(ServicePackageItem)
class ServicePackageItemAdmin(admin.ModelAdmin):
    list_display = (
        "item_name",
        "service",
        "quantity",
        "unit",
        "extra_price",
        "is_optional",
    )
    list_filter = ("is_optional", "service__hotel")
    search_fields = (
        "item_name",
        "service__name",
        "service__hotel__name",
    )
    autocomplete_fields = ("service",)


@admin.register(ServiceResource)
class ServiceResourceAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "hotel",
        "service",
        "capacity",
        "is_active",
    )
    list_filter = ("hotel", "service", "is_active")
    search_fields = (
        "name",
        "service__name",
        "hotel__name",
    )
    autocomplete_fields = ("hotel", "service")
    ordering = ("hotel", "service", "name")


@admin.register(ServiceBooking)
class ServiceBookingAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "hotel",
        "service",
        "resource",
        "customer_name",
        "customer_phone",
        "attendants",
        "scheduled_start",
        "scheduled_end",
        "status",
        "payment_status",
        "post_to_room",
        "deposit_paid",
        "total_amount_display",
        "balance_due_display",
    )
    list_filter = (
        "hotel",
        "service",
        "status",
        "payment_status",
        "post_to_room",
        "scheduled_start",
        "created_at",
    )
    search_fields = (
        "reference",
        "customer_name",
        "customer_phone",
        "service__name",
        "resource__name",
        "booking__guest__first_name",
        "booking__guest__last_name",
        "hotel__name",
    )
    autocomplete_fields = (
        "hotel",
        "booking",
        "service",
        "resource",
        "created_by",
        "assigned_to",
    )
    readonly_fields = (
        "reference",
        "created_at",
        "updated_at",
        "payment_status",
    )
    inlines = [ServiceBookingExtraInline, ServicePaymentInline]
    ordering = ("-scheduled_start", "-id")

    @admin.display(description="Total Amount")
    def total_amount_display(self, obj):
        return obj.total_amount

    @admin.display(description="Balance Due")
    def balance_due_display(self, obj):
        return obj.balance_due


@admin.register(ServiceBookingExtra)
class ServiceBookingExtraAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "service_booking",
        "quantity",
        "unit_price",
        "line_total_display",
    )
    search_fields = (
        "name",
        "service_booking__reference",
        "service_booking__customer_name",
    )
    autocomplete_fields = ("service_booking",)

    @admin.display(description="Line Total")
    def line_total_display(self, obj):
        return obj.line_total


@admin.register(ServicePayment)
class ServicePaymentAdmin(admin.ModelAdmin):
    list_display = (
        "service_booking",
        "amount",
        "method",
        "reference",
        "received_by",
        "paid_at",
        "created_at",
    )
    list_filter = ("method", "paid_at", "created_at")
    search_fields = (
        "service_booking__reference",
        "reference",
        "notes",
        "service_booking__customer_name",
    )
    autocomplete_fields = ("service_booking", "received_by")
    readonly_fields = ("created_at",)
    ordering = ("-paid_at", "-id")


@admin.register(ServiceAttendance)
class ServiceAttendanceAdmin(admin.ModelAdmin):
    list_display = (
        "service_booking",
        "checked_in_at",
        "checked_out_at",
        "checked_in_by",
        "checked_out_by",
    )
    search_fields = (
        "service_booking__reference",
        "service_booking__customer_name",
    )
    autocomplete_fields = (
        "service_booking",
        "checked_in_by",
        "checked_out_by",
    )