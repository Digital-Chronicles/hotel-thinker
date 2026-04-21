from __future__ import annotations

from decimal import Decimal
from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Sum, F, ExpressionWrapper, DecimalField, Max, Q
from django.utils import timezone

from hotels.models import Hotel

D0 = Decimal("0.00")


class DiningArea(models.Model):
    """Dining areas/zones within a restaurant (e.g., Main Hall, Terrace, Private Room)"""
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="dining_areas")
    name = models.CharField(max_length=120, help_text="e.g., Main Hall, Terrace, VIP Room")
    description = models.TextField(blank=True, null=True, help_text="Optional description of the area")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now, help_text="Creation timestamp")
    updated_at = models.DateTimeField(auto_now=True, help_text="Last update timestamp")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hotel", "name"], name="uniq_rest_area_per_hotel"),
        ]
        indexes = [
            models.Index(fields=["hotel", "name"]),
            models.Index(fields=["hotel", "is_active"]),
        ]
        ordering = ["hotel__name", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.hotel.name})"


class Table(models.Model):
    """Restaurant tables with seating capacity"""
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="restaurant_tables")
    area = models.ForeignKey(DiningArea, on_delete=models.PROTECT, related_name="tables")
    number = models.CharField(max_length=30, help_text="Table number or identifier")
    seats = models.PositiveIntegerField(default=4, help_text="Maximum seating capacity")
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True, help_text="Special notes about the table (location, view, etc.)")
    created_at = models.DateTimeField(default=timezone.now, help_text="Creation timestamp")
    updated_at = models.DateTimeField(auto_now=True, help_text="Last update timestamp")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hotel", "number"], name="uniq_rest_table_number_per_hotel"),
        ]
        indexes = [
            models.Index(fields=["hotel", "is_active"]),
            models.Index(fields=["hotel", "area"]),
            models.Index(fields=["hotel", "number"]),
        ]
        ordering = ["hotel__name", "number"]

    def clean(self):
        super().clean()
        if self.area_id and self.hotel_id and self.area.hotel_id != self.hotel_id:
            raise ValidationError("Dining area must belong to the same hotel as the table.")
        if self.seats < 1:
            raise ValidationError("Table must have at least 1 seat.")

    @property
    def is_occupied(self) -> bool:
        """Check if table currently has an open order"""
        return self.orders.filter(
            status__in=[RestaurantOrder.Status.OPEN, RestaurantOrder.Status.KITCHEN, RestaurantOrder.Status.SERVED]
        ).exists()

    def __str__(self) -> str:
        return f"Table {self.number} ({self.seats} seats)"


class MenuCategory(models.Model):
    """Categories for organizing menu items"""
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="menu_categories")
    name = models.CharField(max_length=120, help_text="e.g., Appetizers, Main Course, Desserts, Beverages")
    description = models.TextField(blank=True, null=True, help_text="Optional category description")
    sort_order = models.PositiveIntegerField(default=0, help_text="Lower numbers appear first")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now, help_text="Creation timestamp")
    updated_at = models.DateTimeField(auto_now=True, help_text="Last update timestamp")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hotel", "name"], name="uniq_menu_category_per_hotel"),
        ]
        indexes = [
            models.Index(fields=["hotel", "is_active"]),
            models.Index(fields=["hotel", "sort_order"]),
            models.Index(fields=["hotel", "name"]),
        ]
        ordering = ["hotel__name", "sort_order", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.hotel.name})"


class MenuItem(models.Model):
    """Individual menu items with pricing and stock tracking"""
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="menu_items")
    category = models.ForeignKey(MenuCategory, on_delete=models.PROTECT, related_name="items")
    name = models.CharField(max_length=160, help_text="Name of the dish/beverage")
    description = models.TextField(blank=True, null=True, help_text="Detailed description of the item")
    ingredients = models.TextField(blank=True, null=True, help_text="List of main ingredients")
    
    # Pricing
    price = models.DecimalField(max_digits=12, decimal_places=2, default=D0, help_text="Selling price to customers")
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=D0, help_text="Cost price for profit calculation")
    
    # Stock management
    track_stock = models.BooleanField(default=False, help_text="Enable automatic stock tracking")
    stock_qty = models.DecimalField(max_digits=12, decimal_places=2, default=D0, help_text="Current stock quantity")
    reorder_level = models.DecimalField(max_digits=12, decimal_places=2, default=D0, help_text="Stock level that triggers reorder alert")
    
    # Dietary and features
    is_vegetarian = models.BooleanField(default=False, help_text="Suitable for vegetarians")
    is_vegan = models.BooleanField(default=False, help_text="Suitable for vegans")
    is_gluten_free = models.BooleanField(default=False, help_text="Gluten-free option")
    is_spicy = models.BooleanField(default=False, help_text="Contains spicy ingredients")
    is_featured = models.BooleanField(default=False, help_text="Featured on the menu")
    is_recommended = models.BooleanField(default=False, help_text="Chef's recommendation")
    
    # Status
    is_active = models.BooleanField(default=True, help_text="Available for ordering")
    
    # Metadata
    preparation_time = models.PositiveIntegerField(default=15, help_text="Estimated preparation time in minutes")
    created_at = models.DateTimeField(default=timezone.now, help_text="Creation timestamp")
    updated_at = models.DateTimeField(auto_now=True, help_text="Last update timestamp")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hotel", "name"], name="uniq_menu_item_name_per_hotel"),
        ]
        indexes = [
            models.Index(fields=["hotel", "is_active"]),
            models.Index(fields=["hotel", "category"]),
            models.Index(fields=["hotel", "name"]),
            models.Index(fields=["hotel", "is_featured"]),
            models.Index(fields=["hotel", "is_recommended"]),
        ]
        ordering = ["hotel__name", "category__sort_order", "name"]

    def clean(self):
        super().clean()
        if self.category_id and self.hotel_id and self.category.hotel_id != self.hotel_id:
            raise ValidationError("Category must belong to the same hotel as the menu item.")
        if self.price is not None and self.price < D0:
            raise ValidationError("Price cannot be negative.")
        if self.cost_price is not None and self.cost_price < D0:
            raise ValidationError("Cost price cannot be negative.")
        if self.track_stock and self.stock_qty < D0:
            raise ValidationError("Stock quantity cannot be negative when stock tracking is enabled.")
        if self.reorder_level < D0:
            raise ValidationError("Reorder level cannot be negative.")

    @property
    def profit_margin(self) -> Decimal:
        """Calculate profit margin percentage"""
        if self.price > 0:
            return ((self.price - self.cost_price) / self.price) * 100
        return D0

    @property
    def is_low_stock(self) -> bool:
        """Check if stock is below reorder level"""
        return self.track_stock and self.stock_qty <= self.reorder_level

    def __str__(self) -> str:
        return f"{self.name} (${self.price})"


class RestaurantOrder(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        KITCHEN = "kitchen", "In Kitchen"
        SERVED = "served", "Served"
        BILLED = "billed", "Billed"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="restaurant_orders")
    table = models.ForeignKey(Table, on_delete=models.PROTECT, null=True, blank=True, related_name="orders")

    customer_name = models.CharField(max_length=255, blank=True, null=True, help_text="Customer name for walk-ins")
    customer_phone = models.CharField(max_length=30, blank=True, null=True, help_text="Customer contact number")
    customer_email = models.EmailField(blank=True, null=True, help_text="Customer email for receipts")
    
    # Guest booking reference (for hotel guests)
    booking = models.ForeignKey(
        "bookings.Booking", 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="restaurant_orders",
        help_text="Link to guest booking for room charges"
    )
    room_charge = models.BooleanField(default=False, help_text="Charge to guest's room")

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)

    # Discount and Tax fields with defaults
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=D0, help_text="Discount amount")
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=D0, help_text="Discount percentage")
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=D0, help_text="Tax amount")
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=D0, help_text="Tax percentage")
    service_charge = models.DecimalField(max_digits=12, decimal_places=2, default=D0, help_text="Service charge amount")

    order_number = models.CharField(max_length=60, blank=True, null=True, unique=True)

    # Notes with proper blank/null handling
    special_instructions = models.TextField(blank=True, null=True, help_text="Special requests or instructions")
    kitchen_notes = models.TextField(blank=True, null=True, help_text="Internal notes for kitchen staff")

    # User tracking
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="created_restaurant_orders"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="updated_restaurant_orders"
    )
    
    # Timestamps
    created_at = models.DateTimeField(default=timezone.now, help_text="Creation timestamp")
    updated_at = models.DateTimeField(auto_now=True, help_text="Last update timestamp")
    closed_at = models.DateTimeField(blank=True, null=True, help_text="Closure timestamp")

    class Meta:
        indexes = [
            models.Index(fields=["hotel", "status"]),
            models.Index(fields=["hotel", "created_at"]),
            models.Index(fields=["hotel", "order_number"]),
            models.Index(fields=["hotel", "table", "status"]),
            models.Index(fields=["booking", "room_charge"]),
        ]
        ordering = ["-created_at"]

    def clean(self):
        super().clean()
        if self.table_id and self.hotel_id and self.table.hotel_id != self.hotel_id:
            raise ValidationError("Table must belong to the same hotel as the order.")
        if self.discount is not None and self.discount < D0:
            raise ValidationError("Discount cannot be negative.")
        if self.discount_percent is not None and self.discount_percent < 0:
            raise ValidationError("Discount percentage cannot be negative.")
        if self.tax is not None and self.tax < D0:
            raise ValidationError("Tax cannot be negative.")
        if self.tax_percent is not None and self.tax_percent < 0:
            raise ValidationError("Tax percentage cannot be negative.")
        if self.service_charge is not None and self.service_charge < D0:
            raise ValidationError("Service charge cannot be negative.")
        
        # Validate that discount and discount_percent are not both used
        if self.discount > D0 and self.discount_percent > D0:
            raise ValidationError("Cannot use both fixed discount and percentage discount.")
        
        # Validate that tax and tax_percent are not both used
        if self.tax > D0 and self.tax_percent > D0:
            raise ValidationError("Cannot use both fixed tax and percentage tax.")

    def generate_order_number(self) -> str:
        """Generate unique order number"""
        prefix = "RST"
        d = timezone.localdate().strftime("%Y%m%d")
        last = RestaurantOrder.objects.filter(
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
        total = self.subtotal
        
        # Apply discount (percentage takes precedence)
        if self.discount_percent > 0:
            total = total * (Decimal('1') - self.discount_percent / Decimal('100'))
        else:
            total = total - self.discount
        
        # Apply tax (percentage takes precedence)
        if self.tax_percent > 0:
            total = total * (Decimal('1') + self.tax_percent / Decimal('100'))
        else:
            total = total + self.tax
        
        # Add service charge
        total = total + self.service_charge
        
        return total if total > D0 else D0

    def can_set_status(self, new_status: str) -> bool:
        allowed = {
            self.Status.OPEN: {self.Status.KITCHEN, self.Status.SERVED, self.Status.BILLED, self.Status.PAID, self.Status.CANCELLED},
            self.Status.KITCHEN: {self.Status.SERVED, self.Status.BILLED, self.Status.PAID, self.Status.CANCELLED},
            self.Status.SERVED: {self.Status.BILLED, self.Status.PAID, self.Status.CANCELLED},
            self.Status.BILLED: {self.Status.PAID, self.Status.CANCELLED},
            self.Status.PAID: set(),
            self.Status.CANCELLED: set(),
        }
        return new_status in allowed.get(self.status, set())

    def set_status(self, new_status: str, user=None):
        if new_status == self.status:
            return

        if new_status not in dict(self.Status.choices):
            raise ValidationError("Invalid order status.")

        if not self.can_set_status(new_status):
            raise ValidationError(f"Cannot move order from '{self.get_status_display()}' to '{dict(self.Status.choices).get(new_status, new_status)}'.")

        # Guard: cannot pay empty order
        if new_status == self.Status.PAID and self.items.count() == 0:
            raise ValidationError("Cannot mark an empty order as Paid.")

        # Update stock when moving to kitchen or cancelling
        if new_status == self.Status.KITCHEN:
            self._reserve_stock()
        elif new_status == self.Status.CANCELLED and self.status != self.Status.PAID:
            self._release_stock()

        old_status = self.status
        self.status = new_status
        
        if new_status in {self.Status.PAID, self.Status.CANCELLED} and not self.closed_at:
            self.closed_at = timezone.now()
        
        if user:
            self.updated_by = user
        
        self.save(update_fields=["status", "closed_at", "updated_by", "updated_at"])

    def _reserve_stock(self):
        """Reserve stock when order goes to kitchen"""
        for item in self.items.all():
            if item.item.track_stock:
                if item.item.stock_qty < item.qty:
                    raise ValidationError(f"Insufficient stock for {item.item.name}. Available: {item.item.stock_qty}")
                item.item.stock_qty -= item.qty
                item.item.save(update_fields=["stock_qty", "updated_at"])

    def _release_stock(self):
        """Release reserved stock when order is cancelled"""
        for item in self.items.all():
            if item.item.track_stock:
                item.item.stock_qty += item.qty
                item.item.save(update_fields=["stock_qty", "updated_at"])

    @transaction.atomic
    def bill(self, user=None) -> RestaurantInvoice:
        invoice, created = RestaurantInvoice.objects.get_or_create(
            order=self,
            defaults={
                "hotel": self.hotel,
                "subtotal": self.subtotal,
                "discount": self.discount,
                "discount_percent": self.discount_percent,
                "tax": self.tax,
                "tax_percent": self.tax_percent,
                "service_charge": self.service_charge,
                "total": self.total,
            }
        )
        
        if not created:
            invoice.subtotal = self.subtotal
            invoice.discount = self.discount
            invoice.discount_percent = self.discount_percent
            invoice.tax = self.tax
            invoice.tax_percent = self.tax_percent
            invoice.service_charge = self.service_charge
            invoice.total = self.total
            if not invoice.issued_at:
                invoice.issued_at = timezone.now()
            invoice.save()
        
        if self.status not in {self.Status.BILLED, self.Status.PAID, self.Status.CANCELLED}:
            self.set_status(self.Status.BILLED, user=user)
        
        return invoice

    @transaction.atomic
    def pay(self, amount: Decimal, method: str, user=None, reference=None) -> RestaurantPayment:
        if self.status in {self.Status.PAID, self.Status.CANCELLED}:
            raise ValidationError("Order is closed.")

        if self.items.count() == 0:
            raise ValidationError("Cannot pay an empty order.")

        amt = Decimal(str(amount))
        if amt <= D0:
            raise ValidationError("Payment amount must be greater than 0.")

        if amt != self.total:
            raise ValidationError(f"Payment amount must equal order total ({self.total}).")

        if method not in dict(RestaurantPayment.Method.choices):
            raise ValidationError("Invalid payment method.")

        invoice = self.bill(user=user)

        payment = RestaurantPayment.objects.create(
            hotel=self.hotel,
            invoice=invoice,
            method=method,
            amount=amt,
            reference=reference,
            received_by=user,
        )

        invoice.status = RestaurantInvoice.Status.PAID
        invoice.paid_at = timezone.now()
        invoice.save(update_fields=["status", "paid_at"])

        self.set_status(self.Status.PAID, user=user)
        return payment

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = self.generate_order_number()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.order_number} - {self.get_status_display()}"


class RestaurantOrderItem(models.Model):
    order = models.ForeignKey(RestaurantOrder, on_delete=models.CASCADE, related_name="items")
    item = models.ForeignKey(MenuItem, on_delete=models.PROTECT, related_name="order_items")

    qty = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=D0, help_text="Price at time of order")

    note = models.CharField(max_length=255, blank=True, null=True, help_text="Special instructions for this item")
    
    created_at = models.DateTimeField(default=timezone.now, help_text="Creation timestamp")
    updated_at = models.DateTimeField(auto_now=True, help_text="Last update timestamp")

    class Meta:
        indexes = [
            models.Index(fields=["order"]),
            models.Index(fields=["item"]),
        ]
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["order", "item"], name="uniq_rest_order_item_per_order"),
        ]

    def clean(self):
        super().clean()
        if self.order_id and self.item_id and self.order.hotel_id != self.item.hotel_id:
            raise ValidationError("Menu item must belong to the same hotel as the order.")
        if self.qty <= 0:
            raise ValidationError("Quantity must be at least 1.")
        if self.unit_price is not None and self.unit_price < D0:
            raise ValidationError("Unit price cannot be negative.")

        if self.order_id and self.order.status in {RestaurantOrder.Status.PAID, RestaurantOrder.Status.CANCELLED}:
            raise ValidationError("You cannot modify items for a closed order.")

    def save(self, *args, **kwargs):
        if self.item_id and (self.unit_price is None or Decimal(str(self.unit_price)) <= D0):
            self.unit_price = self.item.price
        super().save(*args, **kwargs)

    @property
    def line_total(self) -> Decimal:
        return Decimal(self.unit_price or D0) * Decimal(self.qty or 0)

    def __str__(self) -> str:
        return f"{self.qty} x {self.item.name}"


class RestaurantInvoice(models.Model):
    class Status(models.TextChoices):
        ISSUED = "issued", "Issued"
        PAID = "paid", "Paid"
        VOID = "void", "Void"

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="restaurant_invoices")
    order = models.OneToOneField(RestaurantOrder, on_delete=models.PROTECT, related_name="invoice")

    invoice_number = models.CharField(max_length=60, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ISSUED, db_index=True)

    # Financial details with defaults
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=D0)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=D0)
    service_charge = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=D0)

    # Timestamps
    created_at = models.DateTimeField(default=timezone.now, help_text="Creation timestamp")
    issued_at = models.DateTimeField(blank=True, null=True, help_text="Issuance timestamp")
    paid_at = models.DateTimeField(blank=True, null=True, help_text="Payment timestamp")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hotel", "invoice_number"], name="uniq_rest_invoice_number_per_hotel"),
        ]
        indexes = [
            models.Index(fields=["hotel", "status"]),
            models.Index(fields=["hotel", "created_at"]),
            models.Index(fields=["hotel", "invoice_number"]),
            models.Index(fields=["status", "issued_at"]),
        ]
        ordering = ["-created_at"]

    @classmethod
    def _next_invoice_number(cls, hotel: Hotel) -> str:
        prefix = "INV"
        ym = timezone.localdate().strftime("%Y%m")
        last = cls.objects.filter(hotel=hotel, invoice_number__startswith=f"{prefix}-{ym}-").aggregate(m=Max("invoice_number"))["m"]
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
        if not self.invoice_number:
            self.invoice_number = self._next_invoice_number(self.hotel)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.invoice_number} - {self.get_status_display()}"


class RestaurantPayment(models.Model):
    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        MOMO = "momo", "Mobile Money"
        CARD = "card", "Card"
        BANK = "bank", "Bank Transfer"
        ROOM = "room", "Room Charge"

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="restaurant_payments")
    invoice = models.ForeignKey(RestaurantInvoice, on_delete=models.PROTECT, related_name="payments")

    method = models.CharField(max_length=20, choices=Method.choices, default=Method.CASH)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    reference = models.CharField(max_length=120, blank=True, null=True, help_text="Transaction reference number")

    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    received_at = models.DateTimeField(default=timezone.now, help_text="Receipt timestamp")

    notes = models.TextField(blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=["hotel", "received_at"]),
            models.Index(fields=["hotel", "method"]),
            models.Index(fields=["hotel", "invoice"]),
            models.Index(fields=["method", "received_at"]),
        ]
        ordering = ["-received_at"]

    def clean(self):
        super().clean()
        if self.invoice_id and self.hotel_id and self.invoice.hotel_id != self.hotel_id:
            raise ValidationError("Invoice does not belong to this hotel.")
        if self.amount is not None and Decimal(self.amount) <= D0:
            raise ValidationError("Amount must be greater than 0.")

    def __str__(self) -> str:
        return f"{self.amount} {self.get_method_display()} - {self.invoice.invoice_number}"


# Signals for automatic stock adjustments
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

@receiver(post_save, sender=RestaurantOrderItem)
def update_menu_item_stock_on_order(sender, instance, created, **kwargs):
    """Update stock when order items are added or modified"""
    if instance.order.status == RestaurantOrder.Status.KITCHEN and instance.item.track_stock:
        # This is handled in the order's _reserve_stock method
        pass


@receiver(post_delete, sender=RestaurantOrderItem)
def restore_stock_on_item_delete(sender, instance, **kwargs):
    """Restore stock when order item is deleted"""
    if instance.order.status == RestaurantOrder.Status.KITCHEN and instance.item.track_stock:
        instance.item.stock_qty += instance.qty
        instance.item.save(update_fields=["stock_qty", "updated_at"])