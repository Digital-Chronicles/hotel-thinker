from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Sum, F, ExpressionWrapper, DecimalField, Max
from django.utils import timezone

from hotels.models import Hotel

D0 = Decimal("0")


class DiningArea(models.Model):
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="dining_areas")
    name = models.CharField(max_length=120)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hotel", "name"], name="uniq_rest_area_per_hotel"),
        ]
        indexes = [models.Index(fields=["hotel", "name"])]
        ordering = ["hotel__name", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.hotel.name})"


class Table(models.Model):
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="restaurant_tables")
    area = models.ForeignKey(DiningArea, on_delete=models.PROTECT, related_name="tables")
    number = models.CharField(max_length=30)
    seats = models.PositiveIntegerField(default=4)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hotel", "number"], name="uniq_rest_table_number_per_hotel"),
        ]
        indexes = [
            models.Index(fields=["hotel", "is_active"]),
            models.Index(fields=["hotel", "area"]),
        ]
        ordering = ["hotel__name", "number"]

    def clean(self):
        super().clean()
        if self.area_id and self.hotel_id and self.area.hotel_id != self.hotel_id:
            raise ValidationError("Dining area must belong to the same hotel as the table.")

    def __str__(self) -> str:
        return f"Table {self.number} ({self.hotel.name})"


class MenuCategory(models.Model):
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="menu_categories")
    name = models.CharField(max_length=120)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hotel", "name"], name="uniq_menu_category_per_hotel"),
        ]
        indexes = [
            models.Index(fields=["hotel", "is_active"]),
            models.Index(fields=["hotel", "sort_order"]),
        ]
        ordering = ["hotel__name", "sort_order", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.hotel.name})"


class MenuItem(models.Model):
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="menu_items")
    category = models.ForeignKey(MenuCategory, on_delete=models.PROTECT, related_name="items")
    name = models.CharField(max_length=160)
    price = models.DecimalField(max_digits=12, decimal_places=2)

    is_active = models.BooleanField(default=True)

    # Optional stock control
    track_stock = models.BooleanField(default=False)
    stock_qty = models.DecimalField(max_digits=12, decimal_places=2, default=D0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hotel", "name"], name="uniq_menu_item_name_per_hotel"),
        ]
        indexes = [
            models.Index(fields=["hotel", "is_active"]),
            models.Index(fields=["hotel", "category"]),
            models.Index(fields=["hotel", "name"]),
        ]
        ordering = ["hotel__name", "category__name", "name"]

    def clean(self):
        super().clean()
        if self.category_id and self.hotel_id and self.category.hotel_id != self.hotel_id:
            raise ValidationError("Category must belong to the same hotel as the menu item.")
        if self.price is not None and self.price < D0:
            raise ValidationError("Price cannot be negative.")
        if self.stock_qty is not None and self.stock_qty < D0:
            raise ValidationError("Stock cannot be negative.")

    def __str__(self) -> str:
        return f"{self.name} ({self.hotel.name})"


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

    customer_name = models.CharField(max_length=255, blank=True, null=True)
    customer_phone = models.CharField(max_length=30, blank=True, null=True)

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
        if self.table_id and self.hotel_id and self.table.hotel_id != self.hotel_id:
            raise ValidationError("Table must belong to the same hotel as the order.")
        if self.discount is not None and self.discount < D0:
            raise ValidationError("Discount cannot be negative.")
        if self.tax is not None and self.tax < D0:
            raise ValidationError("Tax cannot be negative.")

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

    # ✅ IMPORTANT: kitchen → paid is allowed now (and open → paid too)
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
            raise ValidationError(f"Cannot move order from '{self.status}' to '{new_status}'.")

        # guard: cannot pay empty order
        if new_status == self.Status.PAID and self.items.count() == 0:
            raise ValidationError("Cannot mark an empty order as Paid.")

        self.status = new_status
        if new_status in {self.Status.PAID, self.Status.CANCELLED} and not self.closed_at:
            self.closed_at = timezone.now()
        self.save(update_fields=["status", "closed_at"])

    @transaction.atomic
    def bill(self, user=None) -> "RestaurantInvoice":
        invoice = RestaurantInvoice.issue_for_order(self, user=user)
        if self.status not in {self.Status.BILLED, self.Status.PAID, self.Status.CANCELLED}:
            self.set_status(self.Status.BILLED, user=user)
        return invoice

    @transaction.atomic
    def pay(self, amount, method, user=None, reference=None) -> "RestaurantInvoice":
        invoice = RestaurantInvoice.issue_for_order(self, user=user)

        if self.status in {self.Status.PAID, self.Status.CANCELLED}:
            raise ValidationError("Order is closed.")

        if self.items.count() == 0:
            raise ValidationError("Cannot pay an empty order.")

        amt = Decimal(str(amount))
        if amt <= D0:
            raise ValidationError("Payment amount must be greater than 0.")

        # strict: payment must equal total (we can add partial payments later)
        if amt != self.total:
            raise ValidationError(f"Payment amount must equal order total ({self.total}).")

        if method not in dict(RestaurantPayment.Method.choices):
            raise ValidationError("Invalid payment method.")

        RestaurantPayment.objects.create(
            hotel=self.hotel,
            invoice=invoice,
            method=method,
            amount=amt,
            reference=reference,
            received_by=user,
        )

        invoice.status = RestaurantInvoice.Status.PAID
        invoice.save(update_fields=["status"])

        self.set_status(self.Status.PAID, user=user)
        return invoice

    def __str__(self) -> str:
        return self.order_number or f"Order #{self.pk}"


class RestaurantOrderItem(models.Model):
    order = models.ForeignKey(RestaurantOrder, on_delete=models.CASCADE, related_name="items")
    item = models.ForeignKey(MenuItem, on_delete=models.PROTECT, related_name="order_items")

    qty = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    note = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        indexes = [models.Index(fields=["order"])]
        ordering = ["id"]

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
            self.unit_price = self.item.price  # lock price
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

    invoice_number = models.CharField(max_length=60)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ISSUED, db_index=True)

    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=D0)

    created_at = models.DateTimeField(auto_now_add=True)
    issued_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hotel", "invoice_number"], name="uniq_rest_invoice_number_per_hotel"),
        ]
        indexes = [
            models.Index(fields=["hotel", "status"]),
            models.Index(fields=["hotel", "created_at"]),
            models.Index(fields=["hotel", "invoice_number"]),
        ]
        ordering = ["-created_at"]

    @property
    def total(self) -> Decimal:
        total = (Decimal(self.subtotal or D0) - Decimal(self.discount or D0)) + Decimal(self.tax or D0)
        return total if total > D0 else D0

    @classmethod
    def _next_invoice_number(cls, hotel: Hotel) -> str:
        prefix = "RT"
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

    @classmethod
    def issue_for_order(cls, order: RestaurantOrder, user=None) -> "RestaurantInvoice":
        inv = getattr(order, "invoice", None)
        if inv:
            inv.subtotal = order.subtotal
            inv.discount = order.discount or D0
            inv.tax = order.tax or D0
            if not inv.issued_at:
                inv.issued_at = timezone.now()
            inv.save()
            return inv

        inv = cls.objects.create(
            hotel=order.hotel,
            order=order,
            invoice_number=cls._next_invoice_number(order.hotel),
            status=cls.Status.ISSUED,
            subtotal=order.subtotal,
            discount=order.discount or D0,
            tax=order.tax or D0,
            issued_at=timezone.now(),
        )
        return inv

    def __str__(self) -> str:
        return f"{self.invoice_number} ({self.hotel.name})"


class RestaurantPayment(models.Model):
    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        MOMO = "momo", "Mobile Money"
        CARD = "card", "Card"
        BANK = "bank", "Bank Transfer"

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="restaurant_payments")
    invoice = models.ForeignKey(RestaurantInvoice, on_delete=models.PROTECT, related_name="payments")

    method = models.CharField(max_length=20, choices=Method.choices, default=Method.CASH)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.CharField(max_length=120, blank=True, null=True)

    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["hotel", "received_at"]),
            models.Index(fields=["hotel", "method"]),
            models.Index(fields=["hotel", "invoice"]),
        ]
        ordering = ["-received_at"]

    def clean(self):
        super().clean()
        if self.invoice_id and self.hotel_id and self.invoice.hotel_id != self.hotel_id:
            raise ValidationError("Invoice does not belong to this hotel.")
        if self.amount is not None and Decimal(self.amount) <= D0:
            raise ValidationError("Amount must be greater than 0.")

    def __str__(self) -> str:
        return f"{self.amount} {self.get_method_display()} ({self.hotel.name})"