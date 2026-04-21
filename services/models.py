from __future__ import annotations

from decimal import Decimal
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Max, Sum, F, DecimalField, ExpressionWrapper
from django.utils import timezone

from hotels.models import Hotel
from bookings.models import Booking

D0 = Decimal("0.00")


class ServiceCategory(models.Model):
    """
    Broad grouping:
    - wellness
    - recreation
    - venue
    - transport
    - catering
    - laundry
    - other
    """
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="service_categories")
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["hotel", "name"], name="uniq_service_category_per_hotel"),
        ]
        indexes = [
            models.Index(fields=["hotel", "is_active"]),
            models.Index(fields=["hotel", "sort_order"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.hotel.name})"


class ServiceUnit(models.Model):
    """
    A service/facility/package definition.
    Examples:
    - Sauna
    - Steam Bath
    - Gym
    - Swimming Pool
    - Garden
    - Outdoor Catering
    - Conference Hall
    """
    class ServiceType(models.TextChoices):
        FACILITY = "facility", "Facility"
        PACKAGE = "package", "Package"
        VENUE = "venue", "Venue"
        ACTIVITY = "activity", "Activity"
        TRANSPORT = "transport", "Transport"
        OTHER = "other", "Other"

    class PricingMode(models.TextChoices):
        FIXED = "fixed", "Fixed"
        PER_PERSON = "per_person", "Per Person"
        PER_HOUR = "per_hour", "Per Hour"
        PER_DAY = "per_day", "Per Day"
        PER_SESSION = "per_session", "Per Session"
        CUSTOM = "custom", "Custom"

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="service_units")
    category = models.ForeignKey(ServiceCategory, on_delete=models.PROTECT, related_name="services")

    name = models.CharField(max_length=150)
    code = models.CharField(max_length=30, blank=True, null=True)
    service_type = models.CharField(max_length=20, choices=ServiceType.choices, default=ServiceType.FACILITY)

    pricing_mode = models.CharField(max_length=20, choices=PricingMode.choices, default=PricingMode.FIXED)
    base_price = models.DecimalField(max_digits=12, decimal_places=2, default=D0)

    default_duration_minutes = models.PositiveIntegerField(default=60)
    max_capacity = models.PositiveIntegerField(default=1)

    requires_schedule = models.BooleanField(default=True)
    allows_walk_in = models.BooleanField(default=True)
    allow_post_to_room = models.BooleanField(default=True)
    requires_attendant = models.BooleanField(default=False)

    location = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["hotel", "name"], name="uniq_service_unit_name_per_hotel"),
        ]
        indexes = [
            models.Index(fields=["hotel", "category"]),
            models.Index(fields=["hotel", "service_type"]),
            models.Index(fields=["hotel", "is_active"]),
        ]

    def clean(self):
        super().clean()
        if self.category_id and self.hotel_id and self.category.hotel_id != self.hotel_id:
            raise ValidationError("Category must belong to the same hotel.")
        if self.base_price < D0:
            raise ValidationError("Base price cannot be negative.")
        if self.default_duration_minutes <= 0:
            raise ValidationError("Default duration must be greater than zero.")
        if self.max_capacity <= 0:
            raise ValidationError("Max capacity must be greater than zero.")

    def __str__(self):
        return f"{self.name} ({self.hotel.name})"


class ServicePackageItem(models.Model):
    """
    Optional package components.
    Example Outdoor Catering package may include:
    - Tent
    - Chairs
    - Sound
    - Meals
    """
    service = models.ForeignKey(ServiceUnit, on_delete=models.CASCADE, related_name="package_items")
    item_name = models.CharField(max_length=150)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("1.00"))
    unit = models.CharField(max_length=30, default="unit")
    extra_price = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    is_optional = models.BooleanField(default=False)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["id"]

    def clean(self):
        super().clean()
        if self.quantity <= 0:
            raise ValidationError("Quantity must be greater than zero.")
        if self.extra_price < D0:
            raise ValidationError("Extra price cannot be negative.")

    def __str__(self):
        return f"{self.item_name} - {self.service.name}"


class ServiceResource(models.Model):
    """
    Physical or logical sub-resource used for scheduling.
    Examples:
    - Sauna Room 1
    - Pool Lane A
    - Garden Main Space
    - Conference Hall A
    - Catering Van 1
    """
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="service_resources")
    service = models.ForeignKey(ServiceUnit, on_delete=models.CASCADE, related_name="resources")

    name = models.CharField(max_length=120)
    capacity = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["service", "name"], name="uniq_service_resource_name"),
        ]
        indexes = [
            models.Index(fields=["hotel", "service"]),
            models.Index(fields=["hotel", "is_active"]),
        ]

    def clean(self):
        super().clean()
        if self.service_id and self.hotel_id and self.service.hotel_id != self.hotel_id:
            raise ValidationError("Service must belong to the same hotel.")
        if self.capacity <= 0:
            raise ValidationError("Capacity must be greater than zero.")

    def __str__(self):
        return f"{self.name} - {self.service.name}"


class ServiceBooking(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        RESERVED = "reserved", "Reserved"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        NO_SHOW = "no_show", "No Show"

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PARTIAL = "partial", "Partial"
        PAID = "paid", "Paid"
        ROOM_POSTED = "room_posted", "Posted to Room"
        WAIVED = "waived", "Waived"

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="service_bookings")
    booking = models.ForeignKey(
        Booking,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_entries",
    )

    service = models.ForeignKey(ServiceUnit, on_delete=models.PROTECT, related_name="bookings")
    resource = models.ForeignKey(
        ServiceResource,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bookings",
    )

    reference = models.CharField(max_length=60, blank=True, null=True)

    customer_name = models.CharField(max_length=255)
    customer_phone = models.CharField(max_length=30, blank=True, null=True)

    attendants = models.PositiveIntegerField(default=1)

    scheduled_start = models.DateTimeField()
    scheduled_end = models.DateTimeField(blank=True, null=True)

    pricing_mode = models.CharField(max_length=20, choices=ServiceUnit.PricingMode.choices, blank=True)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("1.00"))

    discount = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    deposit_paid = models.DecimalField(max_digits=12, decimal_places=2, default=D0)

    post_to_room = models.BooleanField(default=False)
    notes = models.TextField(blank=True, null=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RESERVED, db_index=True)
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING, db_index=True)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_service_bookings",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-scheduled_start", "-id"]
        indexes = [
            models.Index(fields=["hotel", "service"]),
            models.Index(fields=["hotel", "status"]),
            models.Index(fields=["hotel", "payment_status"]),
            models.Index(fields=["hotel", "scheduled_start"]),
            models.Index(fields=["hotel", "reference"]),
        ]

    def clean(self):
        super().clean()

        if self.service_id and self.hotel_id and self.service.hotel_id != self.hotel_id:
            raise ValidationError("Service must belong to the same hotel.")

        if self.resource_id:
            if self.resource.hotel_id != self.hotel_id:
                raise ValidationError("Resource must belong to the same hotel.")
            if self.resource.service_id != self.service_id:
                raise ValidationError("Resource must belong to the selected service.")

        if self.booking_id and self.hotel_id and self.booking.hotel_id != self.hotel_id:
            raise ValidationError("Booking must belong to the same hotel.")

        if self.post_to_room:
            if not self.booking_id:
                raise ValidationError("Booking is required when posting to room.")
            if not self.service.allow_post_to_room:
                raise ValidationError("This service cannot be posted to room.")

        if self.attendants <= 0:
            raise ValidationError("Attendants must be at least 1.")

        if self.resource_id and self.attendants > self.resource.capacity:
            raise ValidationError("Attendants exceed selected resource capacity.")
        elif self.attendants > self.service.max_capacity:
            raise ValidationError("Attendants exceed service max capacity.")

        if self.quantity <= 0:
            raise ValidationError("Quantity must be greater than zero.")

        if self.unit_price < D0 or self.discount < D0 or self.tax < D0 or self.deposit_paid < D0:
            raise ValidationError("Amounts cannot be negative.")

        if self.scheduled_end and self.scheduled_start and self.scheduled_end <= self.scheduled_start:
            raise ValidationError("End time must be after start time.")

        if self.service.requires_schedule and not self.scheduled_start:
            raise ValidationError("This service requires scheduling.")

        if self.resource_id and self.scheduled_start and self.scheduled_end:
            overlap = ServiceBooking.objects.filter(
                resource=self.resource,
                status__in=[self.Status.RESERVED, self.Status.IN_PROGRESS],
                scheduled_start__lt=self.scheduled_end,
                scheduled_end__gt=self.scheduled_start,
            ).exclude(pk=self.pk)

            if overlap.exists():
                raise ValidationError("This resource is already booked for the selected time.")

    @property
    def subtotal(self) -> Decimal:
        return Decimal(self.unit_price or D0) * Decimal(self.quantity or 0)

    @property
    def total_amount(self) -> Decimal:
        total = self.subtotal - Decimal(self.discount or D0) + Decimal(self.tax or D0)
        return total if total > D0 else D0

    @property
    def balance_due(self) -> Decimal:
        bal = self.total_amount - Decimal(self.deposit_paid or D0)
        return bal if bal > D0 else D0

    @property
    def duration_minutes(self) -> int:
        if self.scheduled_start and self.scheduled_end:
            return int((self.scheduled_end - self.scheduled_start).total_seconds() / 60)
        return 0

    def generate_reference(self):
        prefix = "SRV"
        d = timezone.localdate().strftime("%Y%m%d")
        last = ServiceBooking.objects.filter(
            hotel=self.hotel,
            reference__startswith=f"{prefix}-{d}-"
        ).aggregate(m=Max("reference"))["m"]

        if last:
            try:
                last_no = int(last.split("-")[-1])
            except Exception:
                last_no = 0
            next_no = last_no + 1
        else:
            next_no = 1

        return f"{prefix}-{d}-{next_no:04d}"

    def set_defaults_from_service(self):
        if self.service_id:
            if not self.pricing_mode:
                self.pricing_mode = self.service.pricing_mode
            if not self.unit_price or self.unit_price <= D0:
                self.unit_price = self.service.base_price
            if not self.scheduled_end and self.scheduled_start and self.service.default_duration_minutes:
                self.scheduled_end = self.scheduled_start + timedelta(minutes=self.service.default_duration_minutes)

            if self.pricing_mode == ServiceUnit.PricingMode.PER_PERSON and (not self.quantity or self.quantity <= 0):
                self.quantity = Decimal(str(self.attendants))
            elif self.pricing_mode in [
                ServiceUnit.PricingMode.FIXED,
                ServiceUnit.PricingMode.PER_SESSION,
            ] and (not self.quantity or self.quantity <= 0):
                self.quantity = Decimal("1.00")

    def update_payment_status(self):
        if self.post_to_room:
            self.payment_status = self.PaymentStatus.ROOM_POSTED
            return

        if self.total_amount <= D0:
            self.payment_status = self.PaymentStatus.WAIVED
            return

        if self.deposit_paid <= D0:
            self.payment_status = self.PaymentStatus.PENDING
        elif self.deposit_paid < self.total_amount:
            self.payment_status = self.PaymentStatus.PARTIAL
        else:
            self.payment_status = self.PaymentStatus.PAID

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = self.generate_reference()

        self.set_defaults_from_service()
        self.update_payment_status()

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.reference} - {self.customer_name} - {self.service.name}"


class ServiceBookingExtra(models.Model):
    """
    Extra add-ons attached to a service booking.
    Example:
    - extra towels
    - drinks
    - projector
    - chairs
    - transport surcharge
    """
    service_booking = models.ForeignKey(ServiceBooking, on_delete=models.CASCADE, related_name="extras")
    name = models.CharField(max_length=150)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("1.00"))
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["id"]

    def clean(self):
        super().clean()
        if self.quantity <= 0:
            raise ValidationError("Quantity must be greater than zero.")
        if self.unit_price < D0:
            raise ValidationError("Unit price cannot be negative.")

    @property
    def line_total(self):
        return Decimal(self.quantity or 0) * Decimal(self.unit_price or D0)

    def __str__(self):
        return f"{self.name} - {self.service_booking.reference}"


class ServicePayment(models.Model):
    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        MOBILE = "mobile", "Mobile Money"
        CARD = "card", "Card"
        BANK = "bank", "Bank Transfer"
        ROOM_POST = "room_post", "Room Post"
        OTHER = "other", "Other"

    service_booking = models.ForeignKey(ServiceBooking, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=20, choices=Method.choices, default=Method.CASH)
    reference = models.CharField(max_length=120, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    paid_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-paid_at", "-id"]
        indexes = [
            models.Index(fields=["paid_at"]),
        ]

    def clean(self):
        super().clean()
        if self.amount <= D0:
            raise ValidationError("Payment amount must be greater than zero.")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        booking = self.service_booking
        total_paid = booking.payments.aggregate(s=Sum("amount"))["s"] or D0
        booking.deposit_paid = total_paid
        booking.update_payment_status()
        booking.save(update_fields=["deposit_paid", "payment_status", "updated_at"])

    def __str__(self):
        return f"{self.service_booking.reference} - {self.amount}"


class ServiceAttendance(models.Model):
    """
    Optional check-in/check-out tracking for scheduled services.
    Useful for gym, pool, sauna, garden entry, etc.
    """
    service_booking = models.OneToOneField(ServiceBooking, on_delete=models.CASCADE, related_name="attendance")
    checked_in_at = models.DateTimeField(blank=True, null=True)
    checked_out_at = models.DateTimeField(blank=True, null=True)
    checked_in_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_checkins",
    )
    checked_out_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_checkouts",
    )
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Attendance - {self.service_booking.reference}"