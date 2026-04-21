# bookings/models.py
from __future__ import annotations

import hashlib
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from hotels.models import Hotel
from rooms.models import Room


ZERO = Decimal("0")
HALF = Decimal("0.50")


def _d(v) -> Decimal:
    try:
        return Decimal(v or 0)
    except Exception:
        return ZERO


# -----------------------------------------------------------------------------
# Guest
# -----------------------------------------------------------------------------
class Guest(models.Model):
    class GuestType(models.TextChoices):
        INDIVIDUAL = "individual", _("Individual")
        CORPORATE = "corporate", _("Corporate")
        TRAVEL_AGENCY = "travel_agency", _("Travel Agency")
        TOUR_OPERATOR = "tour_operator", _("Tour Operator")
        VIP = "vip", _("VIP")

    class IDType(models.TextChoices):
        PASSPORT = "passport", _("Passport")
        NATIONAL_ID = "national_id", _("National ID")
        DRIVERS_LICENSE = "drivers_license", _("Driver's License")
        OTHER = "other", _("Other")

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="guests")

    guest_id = models.CharField(max_length=50, unique=True, editable=False)

    full_name = models.CharField(max_length=255, db_index=True)
    preferred_name = models.CharField(max_length=100, blank=True, null=True)
    guest_type = models.CharField(
        max_length=20, choices=GuestType.choices, default=GuestType.INDIVIDUAL, db_index=True
    )

    phone = models.CharField(max_length=30, db_index=True)
    alternative_phone = models.CharField(max_length=30, blank=True, null=True)
    email = models.EmailField(blank=True, null=True, db_index=True)

    id_type = models.CharField(max_length=20, choices=IDType.choices, blank=True, null=True)
    id_number = models.CharField(max_length=120, blank=True, null=True)
    id_issue_date = models.DateField(blank=True, null=True)
    id_expiry_date = models.DateField(blank=True, null=True)
    id_scan = models.FileField(upload_to="guest_ids/%Y/%m/", blank=True, null=True)

    nationality = models.CharField(max_length=120, blank=True, null=True)
    language = models.CharField(max_length=10, default="en")

    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    postal_code = models.CharField(max_length=20, blank=True, null=True)

    company_name = models.CharField(max_length=255, blank=True, null=True)
    company_vat = models.CharField(max_length=50, blank=True, null=True)
    company_address = models.TextField(blank=True, null=True)

    special_requests = models.TextField(blank=True, null=True)
    dietary_restrictions = models.TextField(blank=True, null=True)
    room_preferences = models.TextField(blank=True, null=True)
    is_vip = models.BooleanField(default=False, db_index=True)

    marketing_consent = models.BooleanField(default=False)
    newsletter_subscribed = models.BooleanField(default=False)

    is_blacklisted = models.BooleanField(default=False, db_index=True)
    blacklist_reason = models.TextField(blank=True, null=True)
    blacklisted_at = models.DateTimeField(blank=True, null=True)
    blacklisted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="blacklisted_guests",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_guests",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["hotel", "full_name"]),
            models.Index(fields=["hotel", "phone"]),
            models.Index(fields=["hotel", "email"]),
            models.Index(fields=["hotel", "guest_type"]),
            models.Index(fields=["hotel", "is_blacklisted"]),
        ]
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.guest_id:
            unique_string = f"{self.hotel_id}-{self.full_name}-{timezone.now().timestamp()}"
            self.guest_id = hashlib.md5(unique_string.encode()).hexdigest()[:10].upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.full_name} - {self.guest_id}"


# -----------------------------------------------------------------------------
# Booking
# -----------------------------------------------------------------------------
class Booking(models.Model):
    class Status(models.TextChoices):
        PROVISIONAL = "provisional", _("Provisional")
        RESERVED = "reserved", _("Reserved")
        CONFIRMED = "confirmed", _("Confirmed")
        CHECKED_IN = "checked_in", _("Checked In")
        CHECKED_OUT = "checked_out", _("Checked Out")
        CANCELLED = "cancelled", _("Cancelled")
        NO_SHOW = "no_show", _("No Show")
        WAITLIST = "waitlist", _("Waitlist")

    class Source(models.TextChoices):
        DIRECT = "direct", _("Direct")
        WALK_IN = "walk_in", _("Walk-in")
        ONLINE_TRAVEL_AGENCY = "ota", _("Online Travel Agency")
        CORPORATE = "corporate", _("Corporate")
        TRAVEL_AGENT = "travel_agent", _("Travel Agent")
        PHONE = "phone", _("Phone")
        EMAIL = "email", _("Email")
        WEBSITE = "website", _("Website")
        MOBILE_APP = "mobile_app", _("Mobile App")

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        PARTIALLY_PAID = "partially_paid", _("Partially Paid")
        PAID = "paid", _("Paid")
        REFUNDED = "refunded", _("Refunded")
        CANCELLED = "cancelled", _("Cancelled")

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="bookings")
    guest = models.ForeignKey(Guest, on_delete=models.PROTECT, related_name="bookings")
    room = models.ForeignKey(Room, on_delete=models.PROTECT, related_name="bookings")

    booking_number = models.CharField(max_length=50, unique=True, editable=False)
    confirmation_code = models.CharField(max_length=50, blank=True, null=True)

    source = models.CharField(max_length=20, choices=Source.choices, default=Source.DIRECT)
    source_reference = models.CharField(max_length=100, blank=True, null=True)

    check_in = models.DateField(db_index=True)
    check_out = models.DateField(db_index=True)
    check_in_time = models.DateTimeField(blank=True, null=True)
    check_out_time = models.DateTimeField(blank=True, null=True)

    adults = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    children = models.PositiveIntegerField(default=0)
    infants = models.PositiveIntegerField(default=0)

    # Pricing snapshot
    use_room_rate = models.BooleanField(default=True)  # auto pull from room_type.base_price
    nightly_rate = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    extra_bed_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_type = models.CharField(
        max_length=20,
        choices=[("percentage", _("Percentage")), ("fixed", _("Fixed Amount"))],
        default="fixed",
    )

    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RESERVED, db_index=True)
    payment_status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING, db_index=True
    )

    special_requests = models.TextField(blank=True, null=True)
    guest_notes = models.TextField(blank=True, null=True)
    internal_notes = models.TextField(blank=True, null=True)

    cancelled_at = models.DateTimeField(blank=True, null=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cancelled_bookings",
    )
    cancellation_reason = models.TextField(blank=True, null=True)
    cancellation_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_bookings",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["hotel", "status", "check_in"]),
            models.Index(fields=["hotel", "payment_status"]),
            models.Index(fields=["hotel", "check_in", "check_out"]),
            models.Index(fields=["booking_number"]),
            models.Index(fields=["guest", "check_in"]),
        ]
        ordering = ["-check_in", "-created_at"]

    def __str__(self):
        return f"Booking {self.booking_number} - {self.guest.full_name}"

    # -----------------------------
    # Derived
    # -----------------------------
    @property
    def nights(self) -> int:
        if not self.check_in or not self.check_out:
            return 0
        return max((self.check_out - self.check_in).days, 0)

    @property
    def additional_charges_total(self) -> Decimal:
        if not self.pk:
            return ZERO
        return self.additional_charges.aggregate(total=Sum("total"))["total"] or ZERO

    @property
    def balance_due(self) -> Decimal:
        return max(_d(self.total_amount) - _d(self.amount_paid), ZERO)

    @property
    def is_fully_paid(self) -> bool:
        return self.balance_due <= ZERO

    @property
    def required_checkin_amount(self) -> Decimal:
        """
        Minimum paid required to allow check-in (50% of total).
        """
        total = _d(self.total_amount)
        if total <= 0:
            return ZERO
        return total * HALF

    # -----------------------------
    # Pricing source: RoomType.base_price
    # -----------------------------
    def set_nightly_rate_from_room(self) -> None:
        if not self.room_id:
            return
        base_price = getattr(self.room.room_type, "base_price", None)
        self.nightly_rate = _d(base_price)

    # -----------------------------
    # Totals
    # -----------------------------
    def calculate_totals(self) -> None:
        nights = Decimal(str(self.nights))
        room_part = _d(self.nightly_rate) * nights
        extra = _d(self.extra_bed_charge)
        charges = _d(self.additional_charges_total)

        subtotal = room_part + extra + charges

        # discount
        if self.discount_type == "percentage":
            disc = subtotal * (_d(self.discount) / Decimal("100")) if subtotal > 0 else ZERO
        else:
            disc = _d(self.discount)

        if disc > subtotal:
            disc = subtotal

        after_discount = subtotal - disc
        if after_discount < 0:
            after_discount = ZERO

        tax = after_discount * (_d(self.tax_rate) / Decimal("100")) if after_discount > 0 else ZERO

        self.subtotal = subtotal
        self.tax_amount = tax
        self.total_amount = after_discount + tax

    def refresh_payment_status(self) -> None:
        total = _d(self.total_amount)
        paid = _d(self.amount_paid)

        if total <= 0:
            self.payment_status = self.PaymentStatus.PAID
            return

        if paid <= 0:
            self.payment_status = self.PaymentStatus.PENDING
        elif paid < total:
            self.payment_status = self.PaymentStatus.PARTIALLY_PAID
        else:
            self.payment_status = self.PaymentStatus.PAID

    # -----------------------------
    # Validation
    # -----------------------------
    def clean(self):
        super().clean()

        if self.check_in and self.check_out and self.check_out <= self.check_in:
            raise ValidationError({"check_out": _("Check-out must be after check-in.")})

        if self.room_id and self.hotel_id and self.room.hotel_id != self.hotel_id:
            raise ValidationError({"room": _("Selected room does not belong to this hotel.")})

        if self.guest_id and self.hotel_id and self.guest.hotel_id != self.hotel_id:
            raise ValidationError({"guest": _("Selected guest does not belong to this hotel.")})

        if self.room and self.check_in and self.check_out:
            exists = (
                Booking.objects.filter(
                    room=self.room,
                    status__in=[self.Status.RESERVED, self.Status.CONFIRMED, self.Status.CHECKED_IN],
                    check_in__lt=self.check_out,
                    check_out__gt=self.check_in,
                )
                .exclude(pk=self.pk)
                .exists()
            )
            if exists:
                raise ValidationError(_("Room is not available for the selected dates."))

    # -----------------------------
    # Save
    # -----------------------------
    def generate_booking_number(self) -> str:
        prefix = "BK"
        date_part = timezone.now().strftime("%y%m")
        last_booking = (
            Booking.objects.filter(booking_number__startswith=f"{prefix}{date_part}")
            .order_by("booking_number")
            .last()
        )
        if last_booking:
            last_num = int(last_booking.booking_number[-4:])
            new_num = last_num + 1
        else:
            new_num = 1
        return f"{prefix}{date_part}{new_num:04d}"

    def save(self, *args, **kwargs):
        if not self.booking_number:
            self.booking_number = self.generate_booking_number()

        if self.use_room_rate:
            self.set_nightly_rate_from_room()

        self.calculate_totals()
        self.refresh_payment_status()

        super().save(*args, **kwargs)

    # -----------------------------
    # Actions with payment rules
    # -----------------------------
    def check_in_guest(self, user):
        """
        RULE: must have at least 50% paid before check-in.
        """
        if self.status not in [self.Status.RESERVED, self.Status.CONFIRMED]:
            raise ValidationError(_("Booking cannot be checked in."))

        # ensure totals current
        if self.use_room_rate:
            self.set_nightly_rate_from_room()
        self.calculate_totals()

        required = self.required_checkin_amount
        paid = _d(self.amount_paid)

        if paid < required:
            raise ValidationError(
                _("Check-in requires at least 50% payment. Required: {req}, Paid: {paid}.").format(
                    req=required, paid=paid
                )
            )

        self.status = self.Status.CHECKED_IN
        self.check_in_time = timezone.now()

        self.room.status = Room.Status.OCCUPIED
        self.room.save(update_fields=["status"])

        self.save()

        BookingAuditLog.objects.create(
            booking=self,
            action=BookingAuditLog.Action.CHECK_IN,
            user=user,
            description=f"Guest checked in by {user.get_full_name()}",
        )

    def check_out_guest(self, user):
        """
        RULE: must clear full balance before check-out (100% paid).
        """
        if self.status != self.Status.CHECKED_IN:
            raise ValidationError(_("Booking is not checked in."))

        if self.use_room_rate:
            self.set_nightly_rate_from_room()
        self.calculate_totals()

        if self.balance_due > ZERO:
            raise ValidationError(
                _("Cannot check out. Balance due is {bal}. Please clear it first.").format(bal=self.balance_due)
            )

        self.status = self.Status.CHECKED_OUT
        self.check_out_time = timezone.now()

        self.room.status = Room.Status.AVAILABLE
        self.room.save(update_fields=["status"])

        self.payment_status = self.PaymentStatus.PAID
        self.save()

        BookingAuditLog.objects.create(
            booking=self,
            action=BookingAuditLog.Action.CHECK_OUT,
            user=user,
            description=f"Guest checked out by {user.get_full_name()}",
        )

    def cancel(self, user, reason=None, fee=0):
        if self.status in [self.Status.CHECKED_OUT, self.Status.CANCELLED]:
            raise ValidationError(_("Booking cannot be cancelled."))

        self.status = self.Status.CANCELLED
        self.cancelled_at = timezone.now()
        self.cancelled_by = user
        self.cancellation_reason = reason
        self.cancellation_fee = _d(fee)
        self.save()

        if self.room.status == Room.Status.OCCUPIED:
            self.room.status = Room.Status.AVAILABLE
            self.room.save(update_fields=["status"])

        BookingAuditLog.objects.create(
            booking=self,
            action=BookingAuditLog.Action.CANCEL,
            user=user,
            description=f"Booking cancelled by {user.get_full_name()}. Reason: {reason}",
        )


# -----------------------------------------------------------------------------
# Booking Audit Log
# -----------------------------------------------------------------------------
class BookingAuditLog(models.Model):
    class Action(models.TextChoices):
        CREATE = "create", _("Created")
        UPDATE = "update", _("Updated")
        CHECK_IN = "check_in", _("Checked In")
        CHECK_OUT = "check_out", _("Checked Out")
        CANCEL = "cancel", _("Cancelled")
        ADD_CHARGE = "add_charge", _("Additional Charge")
        ADD_PAYMENT = "add_payment", _("Payment Added")

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="audit_logs")
    action = models.CharField(max_length=30, choices=Action.choices)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["booking", "-created_at"])]

    def __str__(self):
        return f"{self.booking.booking_number} - {self.action}"


# -----------------------------------------------------------------------------
# Additional Charges
# -----------------------------------------------------------------------------
class AdditionalCharge(models.Model):
    class Category(models.TextChoices):
        MINI_BAR = "mini_bar", _("Mini Bar")
        RESTAURANT = "restaurant", _("Restaurant")
        LAUNDRY = "laundry", _("Laundry")
        SPA = "spa", _("Spa")
        TRANSPORT = "transport", _("Transport")
        OTHER = "other", _("Other")

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="additional_charges")
    category = models.CharField(max_length=20, choices=Category.choices)
    description = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["booking", "category"])]

    def clean(self):
        super().clean()
        if self.quantity <= 0:
            raise ValidationError({"quantity": _("Quantity must be at least 1.")})
        if self.unit_price is None or _d(self.unit_price) <= ZERO:
            raise ValidationError({"unit_price": _("Unit price must be greater than 0.")})

    def save(self, *args, **kwargs):
        self.total = (Decimal(int(self.quantity or 1)) * _d(self.unit_price))
        super().save(*args, **kwargs)

        # recompute booking totals (keeps invoice/totals updated via booking.save)
        booking = self.booking
        booking.save()

        BookingAuditLog.objects.create(
            booking=booking,
            action=BookingAuditLog.Action.ADD_CHARGE,
            user=self.created_by,
            description=f"Added/updated charge: {self.description} ({self.total})",
        )

    def __str__(self):
        return f"{self.description} - {self.total}"