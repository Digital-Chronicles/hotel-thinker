from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Sum, DecimalField, ExpressionWrapper, Max
from django.utils import timezone

from hotels.models import Hotel
from bookings.models import Booking

D0 = Decimal("0")


class BarCategory(models.Model):
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="bar_categories")
    name = models.CharField(max_length=120)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hotel", "name"], name="uniq_bar_category_per_hotel"),
        ]
        indexes = [
            models.Index(fields=["hotel", "is_active"]),
            models.Index(fields=["hotel", "sort_order"]),
        ]
        ordering = ["hotel__name", "sort_order", "name"]

    def __str__(self):
        return f"{self.name} ({self.hotel.name})"


class BarItem(models.Model):
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="bar_items")
    category = models.ForeignKey(BarCategory, on_delete=models.PROTECT, related_name="items")

    name = models.CharField(max_length=160)
    sku = models.CharField(max_length=60, blank=True, null=True)
    unit = models.CharField(max_length=30, default="bottle")
    selling_price = models.DecimalField(max_digits=12, decimal_places=2)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=D0)

    track_stock = models.BooleanField(default=True)
    stock_qty = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    reorder_level = models.DecimalField(max_digits=12, decimal_places=2, default=D0)

    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hotel", "name"], name="uniq_bar_item_name_per_hotel"),
        ]
        indexes = [
            models.Index(fields=["hotel", "category"]),
            models.Index(fields=["hotel", "is_active"]),
            models.Index(fields=["hotel", "name"]),
            models.Index(fields=["hotel", "sku"]),
        ]
        ordering = ["hotel__name", "category__name", "name"]

    def clean(self):
        super().clean()
        if self.category_id and self.hotel_id and self.category.hotel_id != self.hotel_id:
            raise ValidationError("Category must belong to the same hotel.")
        if self.selling_price is not None and self.selling_price < D0:
            raise ValidationError("Selling price cannot be negative.")
        if self.cost_price is not None and self.cost_price < D0:
            raise ValidationError("Cost price cannot be negative.")
        if self.stock_qty is not None and self.stock_qty < D0:
            raise ValidationError("Stock quantity cannot be negative.")
        if self.reorder_level is not None and self.reorder_level < D0:
            raise ValidationError("Reorder level cannot be negative.")

    @property
    def is_low_stock(self):
        return self.track_stock and self.stock_qty <= self.reorder_level

    def __str__(self):
        return f"{self.name} ({self.hotel.name})"


class BarStockMovement(models.Model):
    class MovementType(models.TextChoices):
        OPENING = "opening", "Opening Stock"
        PURCHASE = "purchase", "Purchase"
        SALE = "sale", "Sale"
        ADJUSTMENT = "adjustment", "Adjustment"
        DAMAGE = "damage", "Damage"
        RETURN = "return", "Return"

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="bar_stock_movements")
    item = models.ForeignKey(BarItem, on_delete=models.PROTECT, related_name="stock_movements")
    movement_type = models.CharField(max_length=20, choices=MovementType.choices)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2, default=D0)

    reference = models.CharField(max_length=120, blank=True, null=True)
    note = models.TextField(blank=True, null=True)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["hotel", "item"]),
            models.Index(fields=["hotel", "movement_type"]),
            models.Index(fields=["hotel", "created_at"]),
        ]
        ordering = ["-created_at"]

    def clean(self):
        super().clean()
        if self.item_id and self.hotel_id and self.item.hotel_id != self.hotel_id:
            raise ValidationError("Item must belong to the same hotel.")
        if self.quantity == 0:
            raise ValidationError("Quantity cannot be zero.")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.item.name} - {self.movement_type} - {self.quantity}"


class BarOrder(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        SERVED = "served", "Served"
        BILLED = "billed", "Billed"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="bar_orders")
    booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name="bar_orders")

    guest_name = models.CharField(max_length=255, blank=True, null=True)
    room_charge = models.BooleanField(default=False, help_text="Post to room/booking instead of immediate cash payment")

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=D0)

    order_number = models.CharField(max_length=60, blank=True, null=True)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=["hotel", "status"]),
            models.Index(fields=["hotel", "created_at"]),
            models.Index(fields=["hotel", "order_number"]),
        ]
        ordering = ["-created_at"]

    def clean(self):
        super().clean()
        if self.booking_id and self.hotel_id and self.booking.hotel_id != self.hotel_id:
            raise ValidationError("Booking must belong to the same hotel.")
        if self.discount is not None and self.discount < D0:
            raise ValidationError("Discount cannot be negative.")
        if self.tax is not None and self.tax < D0:
            raise ValidationError("Tax cannot be negative.")
        if self.room_charge and not self.booking_id:
            raise ValidationError("A booking is required for room charge orders.")

    @property
    def subtotal(self) -> Decimal:
        expr = ExpressionWrapper(
            F("qty") * F("unit_price"),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )
        s = self.items.aggregate(s=Sum(expr))["s"]
        return Decimal(s or D0)

    @property
    def total(self) -> Decimal:
        total = (self.subtotal - Decimal(self.discount or D0)) + Decimal(self.tax or D0)
        return total if total > D0 else D0

    def generate_order_number(self):
        prefix = "BAR"
        ym = timezone.localdate().strftime("%Y%m%d")
        last = BarOrder.objects.filter(
            hotel=self.hotel,
            order_number__startswith=f"{prefix}-{ym}-"
        ).aggregate(m=Max("order_number"))["m"]

        if last:
            try:
                last_num = int(last.split("-")[-1])
            except Exception:
                last_num = 0
            next_num = last_num + 1
        else:
            next_num = 1

        return f"{prefix}-{ym}-{next_num:04d}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = self.generate_order_number()
        super().save(*args, **kwargs)

    @transaction.atomic
    def mark_paid(self):
        if self.items.count() == 0:
            raise ValidationError("Cannot pay an empty order.")
        self.status = self.Status.PAID
        if not self.closed_at:
            self.closed_at = timezone.now()
        self.save(update_fields=["status", "closed_at"])

    def __str__(self):
        return self.order_number or f"Bar Order #{self.pk}"


class BarOrderItem(models.Model):
    order = models.ForeignKey(BarOrder, on_delete=models.CASCADE, related_name="items")
    item = models.ForeignKey(BarItem, on_delete=models.PROTECT, related_name="order_items")

    qty = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    note = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        indexes = [models.Index(fields=["order"])]
        ordering = ["id"]

    def clean(self):
        super().clean()
        if self.order_id and self.item_id and self.order.hotel_id != self.item.hotel_id:
            raise ValidationError("Item must belong to the same hotel as the order.")
        if self.qty <= 0:
            raise ValidationError("Quantity must be at least 1.")
        if self.unit_price is not None and self.unit_price < D0:
            raise ValidationError("Unit price cannot be negative.")
        if self.item.track_stock and self.pk is None and Decimal(self.qty) > Decimal(self.item.stock_qty):
            raise ValidationError(f"Not enough stock for {self.item.name}.")

    def save(self, *args, **kwargs):
        if self.item_id and (self.unit_price is None or Decimal(str(self.unit_price)) <= D0):
            self.unit_price = self.item.selling_price
        super().save(*args, **kwargs)

    @property
    def line_total(self):
        return Decimal(self.unit_price or D0) * Decimal(self.qty or 0)

    def __str__(self):
        return f"{self.qty} x {self.item.name}"