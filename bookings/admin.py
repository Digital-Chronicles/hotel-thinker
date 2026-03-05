# bookings/admin.py
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db.models import Sum

from .models import Guest, Booking, AdditionalCharge, BookingAuditLog


# -------------------------
# Inlines
# -------------------------
class AdditionalChargeInline(admin.TabularInline):
    model = AdditionalCharge
    extra = 0
    fields = ("category", "description", "quantity", "unit_price", "total", "created_by", "created_at")
    readonly_fields = ("total", "created_at")
    autocomplete_fields = ("created_by",)


class BookingAuditLogInline(admin.TabularInline):
    model = BookingAuditLog
    extra = 0
    fields = ("created_at", "action", "user", "description")
    readonly_fields = ("created_at", "action", "user", "description")
    can_delete = False


# -------------------------
# Guest
# -------------------------
@admin.register(Guest)
class GuestAdmin(admin.ModelAdmin):
    list_display = (
        "hotel",
        "full_name",
        "guest_id",
        "phone",
        "email",
        "guest_type",
        "is_vip",
        "is_blacklisted",
        "created_at",
    )
    list_filter = ("hotel", "guest_type", "is_vip", "is_blacklisted", "created_at")
    search_fields = (
        "hotel__name",
        "full_name",
        "preferred_name",
        "guest_id",
        "phone",
        "alternative_phone",
        "email",
        "id_number",
        "company_name",
    )
    ordering = ("hotel__name", "full_name")
    readonly_fields = ("guest_id", "created_at", "updated_at")
    autocomplete_fields = ("hotel", "created_by", "blacklisted_by")

    fieldsets = (
        ("Hotel", {"fields": ("hotel",)}),
        ("Identity", {"fields": ("guest_id", "guest_type", "full_name", "preferred_name", "is_vip")}),
        ("Contacts", {"fields": ("phone", "alternative_phone", "email", "language")}),
        ("ID Details", {"fields": ("id_type", "id_number", "id_issue_date", "id_expiry_date", "id_scan")}),
        ("Address", {"fields": ("address", "city", "country", "postal_code")}),
        ("Company (optional)", {"fields": ("company_name", "company_vat", "company_address")}),
        ("Preferences", {"fields": ("special_requests", "dietary_restrictions", "room_preferences")}),
        (
            "Marketing",
            {"fields": ("marketing_consent", "newsletter_subscribed")},
        ),
        (
            "Blacklist",
            {
                "fields": ("is_blacklisted", "blacklist_reason", "blacklisted_at", "blacklisted_by"),
            },
        ),
        ("Audit", {"fields": ("created_by", "created_at", "updated_at")}),
    )


# -------------------------
# Booking
# -------------------------
@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        "hotel",
        "booking_number",
        "guest",
        "room",
        "check_in",
        "check_out",
        "status",
        "payment_status",
        "total_amount",
        "amount_paid",
        "balance_due_admin",
        "created_at",
    )
    list_filter = (
        "hotel",
        "status",
        "payment_status",
        "check_in",
        "check_out",
        "created_at",
    )
    search_fields = (
        "hotel__name",
        "booking_number",
        "confirmation_code",
        "guest__full_name",
        "guest__phone",
        "room__number",
    )
    ordering = ("-check_in", "-created_at")
    autocomplete_fields = ("hotel", "guest", "room", "created_by", "cancelled_by")
    readonly_fields = (
        "booking_number",
        "subtotal",
        "tax_amount",
        "total_amount",
        "payment_status",
        "created_at",
        "updated_at",
    )
    inlines = (AdditionalChargeInline, BookingAuditLogInline)

    actions = ("admin_check_in", "admin_check_out", "admin_cancel")

    fieldsets = (
        ("Core", {"fields": ("hotel", "booking_number", "guest", "room", "status")}),
        ("Dates", {"fields": ("check_in", "check_out", "check_in_time", "check_out_time")}),
        ("Source", {"fields": ("source", "source_reference", "confirmation_code")}),
        ("Guests", {"fields": ("adults", "children", "infants")}),
        (
            "Pricing",
            {
                "fields": (
                    "use_room_rate",
                    "nightly_rate",
                    "extra_bed_charge",
                    "discount",
                    "discount_type",
                    "tax_rate",
                    "subtotal",
                    "tax_amount",
                    "total_amount",
                    "amount_paid",
                    "payment_status",
                )
            },
        ),
        ("Notes", {"fields": ("special_requests", "guest_notes", "internal_notes")}),
        (
            "Cancellation",
            {"fields": ("cancelled_at", "cancelled_by", "cancellation_reason", "cancellation_fee")},
        ),
        ("Audit", {"fields": ("created_by", "created_at", "updated_at")}),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("hotel", "guest", "room")

    @admin.display(description="Balance Due")
    def balance_due_admin(self, obj: Booking):
        # Uses model property (already Decimal-safe)
        return obj.balance_due

    # -------------------------
    # Admin actions (use model rules)
    # -------------------------
    @admin.action(description="Check-in selected bookings (requires >= 50% paid)")
    def admin_check_in(self, request, queryset):
        ok, failed = 0, 0
        for booking in queryset.select_related("room"):
            try:
                booking.check_in_guest(request.user)
                ok += 1
            except ValidationError as e:
                failed += 1
                self.message_user(
                    request,
                    f"{booking.booking_number}: {', '.join(e.messages)}",
                    level=messages.ERROR,
                )
        if ok:
            self.message_user(request, f"Checked in {ok} booking(s).", level=messages.SUCCESS)
        if failed and not ok:
            self.message_user(request, f"Failed to check in {failed} booking(s).", level=messages.ERROR)

    @admin.action(description="Check-out selected bookings (requires 100% paid)")
    def admin_check_out(self, request, queryset):
        ok, failed = 0, 0
        for booking in queryset.select_related("room"):
            try:
                booking.check_out_guest(request.user)
                ok += 1
            except ValidationError as e:
                failed += 1
                self.message_user(
                    request,
                    f"{booking.booking_number}: {', '.join(e.messages)}",
                    level=messages.ERROR,
                )
        if ok:
            self.message_user(request, f"Checked out {ok} booking(s).", level=messages.SUCCESS)
        if failed and not ok:
            self.message_user(request, f"Failed to check out {failed} booking(s).", level=messages.ERROR)

    @admin.action(description="Cancel selected bookings")
    def admin_cancel(self, request, queryset):
        ok, failed = 0, 0
        for booking in queryset.select_related("room"):
            try:
                booking.cancel(user=request.user, reason="Cancelled via admin action", fee=0)
                ok += 1
            except ValidationError as e:
                failed += 1
                self.message_user(
                    request,
                    f"{booking.booking_number}: {', '.join(e.messages)}",
                    level=messages.ERROR,
                )
        if ok:
            self.message_user(request, f"Cancelled {ok} booking(s).", level=messages.SUCCESS)
        if failed and not ok:
            self.message_user(request, f"Failed to cancel {failed} booking(s).", level=messages.ERROR)


# -------------------------
# Extra admin registrations (optional but useful)
# -------------------------
@admin.register(AdditionalCharge)
class AdditionalChargeAdmin(admin.ModelAdmin):
    list_display = ("booking", "category", "description", "quantity", "unit_price", "total", "created_at")
    list_filter = ("category", "created_at")
    search_fields = ("booking__booking_number", "description")
    ordering = ("-created_at",)
    autocomplete_fields = ("booking", "created_by")
    readonly_fields = ("total", "created_at")


@admin.register(BookingAuditLog)
class BookingAuditLogAdmin(admin.ModelAdmin):
    list_display = ("booking", "action", "user", "created_at")
    list_filter = ("action", "created_at")
    search_fields = ("booking__booking_number", "description", "user__username", "user__first_name", "user__last_name")
    ordering = ("-created_at",)
    autocomplete_fields = ("booking", "user")
    readonly_fields = ("created_at",)