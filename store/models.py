from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Max, Sum
from django.utils import timezone

from hotels.models import Hotel

D0 = Decimal("0.00")


class StoreCategory(models.Model):
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="store_categories")
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hotel", "name"], name="uniq_store_category_per_hotel"),
        ]
        indexes = [
            models.Index(fields=["hotel", "name"]),
            models.Index(fields=["hotel", "is_active"]),
        ]
        ordering = ["hotel__name", "name"]

    def __str__(self):
        return f"{self.name} ({self.hotel.name})"


class StoreItem(models.Model):
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="store_items")
    category = models.ForeignKey(StoreCategory, on_delete=models.PROTECT, related_name="items")

    name = models.CharField(max_length=160)
    sku = models.CharField(max_length=60, blank=True, null=True)
    unit = models.CharField(max_length=30, default="pcs")

    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, default=D0)

    stock_qty = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    reorder_level = models.DecimalField(max_digits=12, decimal_places=2, default=D0)

    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hotel", "name"], name="uniq_store_item_name_per_hotel"),
        ]
        indexes = [
            models.Index(fields=["hotel", "category"]),
            models.Index(fields=["hotel", "name"]),
            models.Index(fields=["hotel", "sku"]),
            models.Index(fields=["hotel", "is_active"]),
        ]
        ordering = ["hotel__name", "category__name", "name"]

    def clean(self):
        super().clean()
        if self.category_id and self.hotel_id and self.category.hotel_id != self.hotel_id:
            raise ValidationError("Category must belong to the same hotel.")
        for field_name in ["cost_price", "selling_price", "stock_qty", "reorder_level"]:
            value = getattr(self, field_name, D0)
            if value is not None and value < D0:
                raise ValidationError(f"{field_name.replace('_', ' ').title()} cannot be negative.")

    @property
    def is_low_stock(self):
        return self.stock_qty <= self.reorder_level

    def __str__(self):
        return f"{self.name} ({self.hotel.name})"


class StoreStockMovement(models.Model):
    class MovementType(models.TextChoices):
        OPENING = "opening", "Opening"
        PURCHASE = "purchase", "Purchase"
        ISSUE = "issue", "Issue"
        SALE = "sale", "Sale"
        ADJUSTMENT = "adjustment", "Adjustment"
        DAMAGE = "damage", "Damage"
        RETURN = "return", "Return"

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="store_stock_movements")
    item = models.ForeignKey(StoreItem, on_delete=models.PROTECT, related_name="movements")

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

    def __str__(self):
        return f"{self.item.name} - {self.movement_type} - {self.quantity}"


class StoreSale(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="store_sales")
    sale_number = models.CharField(max_length=60, blank=True, null=True)

    customer_name = models.CharField(max_length=255, blank=True, null=True)
    customer_phone = models.CharField(max_length=30, blank=True, null=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=D0)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=["hotel", "status"]),
            models.Index(fields=["hotel", "created_at"]),
            models.Index(fields=["hotel", "sale_number"]),
        ]
        ordering = ["-created_at"]

    @property
    def subtotal(self):
        total = sum((item.line_total for item in self.items.all()), D0)
        return Decimal(total or D0)

    @property
    def total(self):
        total = self.subtotal - Decimal(self.discount or D0) + Decimal(self.tax or D0)
        return total if total > D0 else D0

    def generate_sale_number(self):
        prefix = "STR"
        d = timezone.localdate().strftime("%Y%m%d")
        last = StoreSale.objects.filter(
            hotel=self.hotel,
            sale_number__startswith=f"{prefix}-{d}-"
        ).aggregate(m=Max("sale_number"))["m"]

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
        if not self.sale_number:
            self.sale_number = self.generate_sale_number()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.sale_number or f"Store Sale #{self.pk}"


class StoreSaleItem(models.Model):
    sale = models.ForeignKey(StoreSale, on_delete=models.CASCADE, related_name="items")
    item = models.ForeignKey(StoreItem, on_delete=models.PROTECT, related_name="sale_items")

    qty = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        indexes = [models.Index(fields=["sale"])]
        ordering = ["id"]

    def clean(self):
        super().clean()
        if self.sale_id and self.item_id and self.sale.hotel_id != self.item.hotel_id:
            raise ValidationError("Item must belong to the same hotel as the sale.")
        if self.qty <= 0:
            raise ValidationError("Quantity must be greater than 0.")
        if self.unit_price is not None and self.unit_price < D0:
            raise ValidationError("Unit price cannot be negative.")

    def save(self, *args, **kwargs):
        if self.item_id and (self.unit_price is None or Decimal(str(self.unit_price)) <= D0):
            self.unit_price = self.item.selling_price
        super().save(*args, **kwargs)

    @property
    def line_total(self):
        return Decimal(self.qty or 0) * Decimal(self.unit_price or D0)

    def __str__(self):
        return f"{self.qty} x {self.item.name}"


class StoreSupplier(models.Model):
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="store_suppliers")
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=150, blank=True, null=True)
    phone = models.CharField(max_length=30, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    tin_number = models.CharField(max_length=60, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_store_suppliers",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hotel", "name"], name="uniq_store_supplier_per_hotel"),
        ]
        indexes = [
            models.Index(fields=["hotel", "name"]),
            models.Index(fields=["hotel", "is_active"]),
        ]
        ordering = ["hotel__name", "name"]

    def __str__(self):
        return f"{self.name} ({self.hotel.name})"


class StorePurchaseOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        APPROVED = "approved", "Approved"
        PARTIALLY_RECEIVED = "partially_received", "Partially Received"
        RECEIVED = "received", "Received"
        CANCELLED = "cancelled", "Cancelled"

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="store_purchase_orders")
    supplier = models.ForeignKey(StoreSupplier, on_delete=models.PROTECT, related_name="purchase_orders")

    po_number = models.CharField(max_length=60, blank=True, null=True)
    order_date = models.DateField(default=timezone.localdate)
    expected_date = models.DateField(blank=True, null=True)

    status = models.CharField(max_length=30, choices=Status.choices, default=Status.DRAFT, db_index=True)
    note = models.TextField(blank=True, null=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_store_purchase_orders",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_store_purchase_orders",
    )
    approved_at = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["hotel", "status"]),
            models.Index(fields=["hotel", "po_number"]),
            models.Index(fields=["hotel", "order_date"]),
        ]
        ordering = ["-created_at"]

    def clean(self):
        super().clean()
        if self.supplier_id and self.hotel_id and self.supplier.hotel_id != self.hotel_id:
            raise ValidationError("Supplier must belong to the same hotel.")
        if self.expected_date and self.order_date and self.expected_date < self.order_date:
            raise ValidationError("Expected date cannot be before order date.")

    def generate_po_number(self):
        prefix = "PO"
        d = timezone.localdate().strftime("%Y%m%d")
        last = StorePurchaseOrder.objects.filter(
            hotel=self.hotel,
            po_number__startswith=f"{prefix}-{d}-"
        ).aggregate(m=Max("po_number"))["m"]

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
    def subtotal(self):
        total = sum((item.line_total for item in self.items.all()), D0)
        return Decimal(total or D0)

    @property
    def total_received_qty(self):
        return self.items.aggregate(total=Sum("received_qty"))["total"] or D0

    def refresh_status(self):
        items = list(self.items.all())
        if not items:
            self.status = self.Status.DRAFT
        else:
            total_ordered = sum((Decimal(i.qty_ordered or 0) for i in items), D0)
            total_received = sum((Decimal(i.received_qty or 0) for i in items), D0)

            if total_received <= D0:
                if self.status != self.Status.CANCELLED:
                    self.status = self.Status.APPROVED if self.approved_at else self.Status.DRAFT
            elif total_received < total_ordered:
                self.status = self.Status.PARTIALLY_RECEIVED
            else:
                self.status = self.Status.RECEIVED

        self.save(update_fields=["status", "updated_at"])

    def save(self, *args, **kwargs):
        if not self.po_number:
            self.po_number = self.generate_po_number()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.po_number or f"PO #{self.pk}"


class StorePurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(
        StorePurchaseOrder,
        on_delete=models.CASCADE,
        related_name="items",
    )
    item = models.ForeignKey(
        StoreItem,
        on_delete=models.PROTECT,
        related_name="purchase_order_items",
    )

    qty_ordered = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    received_qty = models.DecimalField(max_digits=12, decimal_places=2, default=D0)

    class Meta:
        indexes = [
            models.Index(fields=["purchase_order"]),
            models.Index(fields=["item"]),
        ]
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["purchase_order", "item"],
                name="uniq_po_item_per_purchase_order",
            ),
        ]

    def clean(self):
        super().clean()
        if self.purchase_order_id and self.item_id and self.purchase_order.hotel_id != self.item.hotel_id:
            raise ValidationError("Item must belong to the same hotel as the purchase order.")
        if self.qty_ordered <= D0:
            raise ValidationError("Ordered quantity must be greater than 0.")
        if self.unit_cost < D0:
            raise ValidationError("Unit cost cannot be negative.")
        if self.received_qty < D0:
            raise ValidationError("Received quantity cannot be negative.")
        if self.received_qty > self.qty_ordered:
            raise ValidationError("Received quantity cannot exceed ordered quantity.")

    @property
    def pending_qty(self):
        pending = Decimal(self.qty_ordered or 0) - Decimal(self.received_qty or 0)
        return pending if pending > D0 else D0

    @property
    def line_total(self):
        return Decimal(self.qty_ordered or 0) * Decimal(self.unit_cost or 0)

    def save(self, *args, **kwargs):
        if self.item_id and (self.unit_cost is None or Decimal(str(self.unit_cost or 0)) <= D0):
            self.unit_cost = self.item.cost_price
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.purchase_order.po_number} - {self.item.name}"


class StoreGoodsReceipt(models.Model):
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="store_goods_receipts")
    purchase_order = models.ForeignKey(
        StorePurchaseOrder,
        on_delete=models.PROTECT,
        related_name="receipts",
    )

    receipt_number = models.CharField(max_length=60, blank=True, null=True)
    supplier_invoice_number = models.CharField(max_length=120, blank=True, null=True)
    received_date = models.DateField(default=timezone.localdate)
    note = models.TextField(blank=True, null=True)

    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="received_store_goods_receipts",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["hotel", "receipt_number"]),
            models.Index(fields=["hotel", "received_date"]),
        ]
        ordering = ["-created_at"]

    def clean(self):
        super().clean()
        if self.purchase_order_id and self.hotel_id and self.purchase_order.hotel_id != self.hotel_id:
            raise ValidationError("Purchase order must belong to the same hotel.")

    def generate_receipt_number(self):
        prefix = "GRN"
        d = timezone.localdate().strftime("%Y%m%d")
        last = StoreGoodsReceipt.objects.filter(
            hotel=self.hotel,
            receipt_number__startswith=f"{prefix}-{d}-"
        ).aggregate(m=Max("receipt_number"))["m"]

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
    def total_amount(self):
        total = sum((item.line_total for item in self.items.all()), D0)
        return Decimal(total or D0)

    def save(self, *args, **kwargs):
        if not self.receipt_number:
            self.receipt_number = self.generate_receipt_number()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.receipt_number or f"GRN #{self.pk}"


class StoreGoodsReceiptItem(models.Model):
    goods_receipt = models.ForeignKey(
        StoreGoodsReceipt,
        on_delete=models.CASCADE,
        related_name="items",
    )
    purchase_order_item = models.ForeignKey(
        StorePurchaseOrderItem,
        on_delete=models.PROTECT,
        related_name="receipt_items",
    )
    qty_received = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=D0)

    class Meta:
        indexes = [
            models.Index(fields=["goods_receipt"]),
            models.Index(fields=["purchase_order_item"]),
        ]
        ordering = ["id"]

    def clean(self):
        super().clean()
        if self.qty_received <= D0:
            raise ValidationError("Received quantity must be greater than 0.")
        if self.unit_cost < D0:
            raise ValidationError("Unit cost cannot be negative.")

        if self.goods_receipt_id and self.purchase_order_item_id:
            if self.goods_receipt.purchase_order_id != self.purchase_order_item.purchase_order_id:
                raise ValidationError("Receipt item must belong to the same purchase order.")

        if self.purchase_order_item_id:
            pending_qty = Decimal(self.purchase_order_item.pending_qty or 0)
            if self.pk:
                old = StoreGoodsReceiptItem.objects.filter(pk=self.pk).first()
                old_qty = Decimal(old.qty_received or 0) if old else D0
                pending_qty += old_qty

            if Decimal(self.qty_received or 0) > pending_qty:
                raise ValidationError("Received quantity cannot exceed pending quantity.")

    @property
    def item(self):
        return self.purchase_order_item.item

    @property
    def line_total(self):
        return Decimal(self.qty_received or 0) * Decimal(self.unit_cost or 0)

    def save(self, *args, **kwargs):
        if self.purchase_order_item_id and (self.unit_cost is None or Decimal(str(self.unit_cost or 0)) <= D0):
            self.unit_cost = self.purchase_order_item.unit_cost
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.goods_receipt.receipt_number} - {self.purchase_order_item.item.name}"