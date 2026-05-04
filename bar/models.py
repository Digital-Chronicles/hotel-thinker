from __future__ import annotations

from decimal import Decimal
from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Sum, DecimalField, ExpressionWrapper, Max, Q
from django.utils import timezone

from hotels.models import Hotel
from bookings.models import Booking

D0 = Decimal("0.00")


class BarCategory(models.Model):
    """Categories for bar items (e.g., Beer, Wine, Spirits, Soft Drinks)"""
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="bar_categories")
    name = models.CharField(max_length=120, help_text="Category name (e.g., Beer, Wine, Spirits)")
    sort_order = models.PositiveIntegerField(default=0, help_text="Lower numbers appear first")
    is_active = models.BooleanField(default=True, help_text="Inactive categories won't appear in item selection")
    created_at = models.DateTimeField(default=timezone.now, help_text="Creation timestamp")
    updated_at = models.DateTimeField(auto_now=True, help_text="Last update timestamp")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hotel", "name"], name="uniq_bar_category_per_hotel"),
        ]
        indexes = [
            models.Index(fields=["hotel", "is_active"]),
            models.Index(fields=["hotel", "sort_order"]),
            models.Index(fields=["hotel", "name"]),
        ]
        ordering = ["sort_order", "name"]
        verbose_name = "Bar Category"
        verbose_name_plural = "Bar Categories"

    def __str__(self) -> str:
        return f"{self.name} ({self.hotel.name})"


class BarItem(models.Model):
    """Individual bar items with pricing and stock tracking"""
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="bar_items")
    category = models.ForeignKey(BarCategory, on_delete=models.PROTECT, related_name="items")

    name = models.CharField(max_length=160, help_text="Name of the beverage")
    sku = models.CharField(max_length=60, blank=True, null=True, help_text="Stock keeping unit / barcode")
    unit = models.CharField(max_length=30, default="bottle", help_text="Unit of measurement (bottle, can, glass, etc.)")

    # Pricing
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, help_text="Selling price to customers")
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=D0, help_text="Cost price for profit calculation")

    # Stock management
    track_stock = models.BooleanField(default=True, help_text="Enable automatic stock tracking")
    stock_qty = models.DecimalField(max_digits=12, decimal_places=2, default=D0, help_text="Current stock quantity")
    reorder_level = models.DecimalField(max_digits=12, decimal_places=2, default=D0, help_text="Stock level that triggers low stock alert")

    # Status
    is_active = models.BooleanField(default=True, help_text="Available for ordering")

    # Metadata
    created_at = models.DateTimeField(default=timezone.now, help_text="Creation timestamp")
    updated_at = models.DateTimeField(auto_now=True, help_text="Last update timestamp")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hotel", "name"], name="uniq_bar_item_name_per_hotel"),
            models.UniqueConstraint(fields=["hotel", "sku"], name="uniq_bar_item_sku_per_hotel", condition=Q(sku__isnull=False)),
        ]
        indexes = [
            models.Index(fields=["hotel", "category"]),
            models.Index(fields=["hotel", "is_active"]),
            models.Index(fields=["hotel", "name"]),
            models.Index(fields=["hotel", "sku"]),
            models.Index(fields=["hotel", "track_stock", "stock_qty"]),
        ]
        ordering = ["category__sort_order", "name"]
        verbose_name = "Bar Item"
        verbose_name_plural = "Bar Items"

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
        if self.track_stock and self.stock_qty < 0:
            raise ValidationError("Stock quantity cannot be negative when stock tracking is enabled.")

    @property
    def profit_margin(self) -> Decimal:
        """Calculate profit margin percentage"""
        if self.selling_price > 0:
            return ((self.selling_price - self.cost_price) / self.selling_price) * 100
        return D0

    @property
    def is_low_stock(self) -> bool:
        """Check if stock is below reorder level"""
        return self.track_stock and self.stock_qty <= self.reorder_level

    @property
    def is_out_of_stock(self) -> bool:
        """Check if item is out of stock"""
        return self.track_stock and self.stock_qty <= 0

    def __str__(self) -> str:
        return f"{self.name} (UGX {self.selling_price})"


class BarStockMovement(models.Model):
    """Track all stock movements for bar items"""
    class MovementType(models.TextChoices):
        OPENING = "opening", "Opening Stock"
        PURCHASE = "purchase", "Purchase"
        SALE = "sale", "Sale"
        ADJUSTMENT = "adjustment", "Adjustment"
        DAMAGE = "damage", "Damage"
        RETURN = "return", "Return"

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="bar_stock_movements")
    item = models.ForeignKey(BarItem, on_delete=models.PROTECT, related_name="stock_movements")
    movement_type = models.CharField(max_length=20, choices=MovementType.choices, db_index=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, help_text="Positive for in, negative for out")
    balance_after = models.DecimalField(max_digits=12, decimal_places=2, default=D0, help_text="Stock balance after movement")

    reference = models.CharField(max_length=120, blank=True, null=True, help_text="Order number or purchase reference")
    note = models.TextField(blank=True, null=True, help_text="Additional notes about the movement")

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["hotel", "item", "-created_at"]),
            models.Index(fields=["hotel", "movement_type", "-created_at"]),
            models.Index(fields=["hotel", "created_at"]),
            models.Index(fields=["reference"]),
        ]
        ordering = ["-created_at"]
        verbose_name = "Bar Stock Movement"
        verbose_name_plural = "Bar Stock Movements"

    def clean(self):
        super().clean()
        if self.item_id and self.hotel_id and self.item.hotel_id != self.hotel_id:
            raise ValidationError("Item must belong to the same hotel.")
        if self.quantity == 0:
            raise ValidationError("Quantity cannot be zero.")

    def save(self, *args, **kwargs):
        # Auto-calculate balance_after based on previous balance
        if not self.pk:
            previous_balance = BarStockMovement.objects.filter(
                hotel=self.hotel,
                item=self.item
            ).order_by("-created_at").values_list("balance_after", flat=True).first()
            
            if previous_balance is None:
                previous_balance = self.item.stock_qty - self.quantity
            else:
                previous_balance = Decimal(previous_balance or D0)
            
            self.balance_after = previous_balance + self.quantity
        
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.item.name} - {self.get_movement_type_display()} - {self.quantity}"


class BarOrder(models.Model):
    """Bar orders for walk-in customers and hotel guests"""
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        SERVED = "served", "Served"
        BILLED = "billed", "Billed"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="bar_orders")
    booking = models.ForeignKey(
        Booking, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="bar_orders",
        help_text="Link to guest booking for room charges"
    )

    guest_name = models.CharField(
        max_length=255, 
        blank=True, 
        null=True, 
        help_text="For walk-in customers or order identification"
    )
    room_charge = models.BooleanField(
        default=False, 
        help_text="Post to room/booking instead of immediate cash payment"
    )

    status = models.CharField(
        max_length=20, 
        choices=Status.choices, 
        default=Status.OPEN, 
        db_index=True
    )
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=D0, help_text="Discount amount")
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=D0, help_text="Tax amount")

    order_number = models.CharField(max_length=60, blank=True, null=True, unique=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    closed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=["hotel", "status", "-created_at"]),
            models.Index(fields=["hotel", "created_at"]),
            models.Index(fields=["hotel", "order_number"]),
            models.Index(fields=["booking", "room_charge"]),
        ]
        ordering = ["-created_at"]
        verbose_name = "Bar Order"
        verbose_name_plural = "Bar Orders"

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

    def generate_order_number(self) -> str:
        """Generate unique order number"""
        prefix = "BAR"
        d = timezone.localdate().strftime("%Y%m%d")
        last = BarOrder.objects.filter(
            hotel=self.hotel,
            order_number__startswith=f"{prefix}-{d}-"
        ).aggregate(m=Max("order_number"))["m"]

        if last:
            try:
                last_num = int(last.split("-")[-1])
            except Exception:
                last_num = 0
            next_num = last_num + 1
        else:
            next_num = 1

        return f"{prefix}-{d}-{next_num:04d}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = self.generate_order_number()
        super().save(*args, **kwargs)

    @property
    def subtotal(self) -> Decimal:
        """Calculate subtotal from order items"""
        expr = ExpressionWrapper(
            F("qty") * F("unit_price"),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )
        s = self.items.aggregate(s=Sum(expr))["s"]
        return Decimal(s or D0)

    @property
    def total(self) -> Decimal:
        """Calculate total after discount and tax"""
        total = (self.subtotal - Decimal(self.discount or D0)) + Decimal(self.tax or D0)
        return total if total > D0 else D0

    @property
    def display_name(self) -> str:
        """Return a display name for the order"""
        if self.guest_name:
            return self.guest_name
        if self.booking and self.booking.guest:
            return self.booking.guest.get_full_name() or self.booking.guest.email
        return f"Order {self.order_number or self.pk}"

    @property
    def item_count(self) -> int:
        """Total quantity of items in the order"""
        return self.items.aggregate(total=Sum("qty"))["total"] or 0

    def can_set_status(self, new_status: str) -> bool:
        """Check if status transition is allowed"""
        allowed = {
            self.Status.OPEN: {self.Status.SERVED, self.Status.BILLED, self.Status.PAID, self.Status.CANCELLED},
            self.Status.SERVED: {self.Status.BILLED, self.Status.PAID, self.Status.CANCELLED},
            self.Status.BILLED: {self.Status.PAID, self.Status.CANCELLED},
            self.Status.PAID: set(),
            self.Status.CANCELLED: set(),
        }
        return new_status in allowed.get(self.status, set())

    @transaction.atomic
    def set_status(self, new_status: str, user=None):
        """Change order status with validation"""
        if new_status == self.status:
            return

        if new_status not in dict(self.Status.choices):
            raise ValidationError("Invalid order status.")

        if not self.can_set_status(new_status):
            raise ValidationError(f"Cannot move order from '{self.get_status_display()}' to '{dict(self.Status.choices).get(new_status, new_status)}'.")

        if new_status == self.Status.PAID and self.items.count() == 0:
            raise ValidationError("Cannot mark an empty order as Paid.")

        self.status = new_status
        
        if new_status in {self.Status.PAID, self.Status.CANCELLED} and not self.closed_at:
            self.closed_at = timezone.now()
        
        self.save(update_fields=["status", "closed_at", "updated_at"])

    @transaction.atomic
    def mark_paid(self):
        """Mark order as paid (simplified, stock handled in view)"""
        if self.items.count() == 0:
            raise ValidationError("Cannot pay an empty order.")
        self.status = self.Status.PAID
        if not self.closed_at:
            self.closed_at = timezone.now()
        self.save(update_fields=["status", "closed_at", "updated_at"])

    def __str__(self) -> str:
        if self.guest_name:
            return f"{self.order_number} - {self.guest_name}"
        if self.booking:
            return f"{self.order_number} - {self.booking}"
        return self.order_number or f"Bar Order #{self.pk}"


class BarOrderItem(models.Model):
    """Items within a bar order"""
    order = models.ForeignKey(BarOrder, on_delete=models.CASCADE, related_name="items")
    item = models.ForeignKey(BarItem, on_delete=models.PROTECT, related_name="order_items")

    qty = models.PositiveIntegerField(default=1, help_text="Quantity ordered")
    unit_price = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        help_text="Price at time of order (snapshot)"
    )
    note = models.CharField(
        max_length=255, 
        blank=True, 
        null=True, 
        help_text="Special instructions for this item"
    )

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["order"]),
            models.Index(fields=["item"]),
        ]
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["order", "item"], name="uniq_bar_order_item_per_order"),
        ]
        verbose_name = "Bar Order Item"
        verbose_name_plural = "Bar Order Items"

    def clean(self):
        super().clean()
        if not self.item_id:
            return
        
        if self.order_id and self.item_id and self.order.hotel_id != self.item.hotel_id:
            raise ValidationError("Item must belong to the same hotel as the order.")
        
        if self.qty <= 0:
            raise ValidationError("Quantity must be at least 1.")
        
        if self.unit_price is not None and self.unit_price < D0:
            raise ValidationError("Unit price cannot be negative.")
        
        # Only check stock for new items (not yet saved)
        if self.item.track_stock and self.pk is None:
            if Decimal(self.qty) > Decimal(self.item.stock_qty):
                raise ValidationError(f"Not enough stock for {self.item.name}. Available: {self.item.stock_qty}")

    def save(self, *args, **kwargs):
        # Auto-populate unit_price from item if not set
        if self.item_id and (self.unit_price is None or self.unit_price <= 0):
            self.unit_price = self.item.selling_price
        super().save(*args, **kwargs)

    @property
    def line_total(self) -> Decimal:
        """Calculate line total"""
        return Decimal(self.unit_price or D0) * Decimal(self.qty or 0)

    def __str__(self) -> str:
        return f"{self.qty} x {self.item.name}"


# ============================================================================
# Signals for automatic stock adjustments
# ============================================================================

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


@receiver(post_delete, sender=BarOrderItem)
def restore_stock_on_item_delete(sender, instance: BarOrderItem, **kwargs):
    """Restore stock when an order item is deleted (only for open/served orders)"""
    if instance.order.status in [BarOrder.Status.OPEN, BarOrder.Status.SERVED]:
        if instance.item.track_stock:
            instance.item.stock_qty += instance.qty
            instance.item.save(update_fields=["stock_qty", "updated_at"])
            
            # Create stock movement record
            BarStockMovement.objects.create(
                hotel=instance.order.hotel,
                item=instance.item,
                movement_type=BarStockMovement.MovementType.ADJUSTMENT,
                quantity=instance.qty,
                reference=f"Restore from cancelled item in order {instance.order.order_number}",
                note=f"Item removed from order {instance.order.order_number}",
            )


@receiver(post_save, sender=BarOrderItem)
def update_item_stock_on_order_item(sender, instance: BarOrderItem, created, **kwargs):
    """Update stock when order items are added or quantity changes"""
    # Only adjust stock for open/served orders
    if instance.order.status not in [BarOrder.Status.OPEN, BarOrder.Status.SERVED]:
        return
    
    if not instance.item.track_stock:
        return
    
    # For new items, deduct stock
    if created:
        if instance.item.stock_qty >= instance.qty:
            instance.item.stock_qty -= instance.qty
            instance.item.save(update_fields=["stock_qty", "updated_at"])
            
            # Create stock movement record (will be created when order is paid)
            pass
    else:
        # For existing items, check if quantity changed
        try:
            old_instance = BarOrderItem.objects.get(pk=instance.pk)
            if old_instance.qty != instance.qty:
                difference = old_instance.qty - instance.qty
                instance.item.stock_qty += difference
                instance.item.save(update_fields=["stock_qty", "updated_at"])
        except BarOrderItem.DoesNotExist:
            pass