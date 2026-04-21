from django.contrib import admin

from .models import (
    StoreCategory,
    StoreGoodsReceipt,
    StoreGoodsReceiptItem,
    StoreItem,
    StorePurchaseOrder,
    StorePurchaseOrderItem,
    StoreSale,
    StoreSaleItem,
    StoreStockMovement,
    StoreSupplier,
)


class StoreSaleItemInline(admin.TabularInline):
    model = StoreSaleItem
    extra = 1
    fields = ("item", "qty", "unit_price", "line_total_display")
    readonly_fields = ("line_total_display",)

    def line_total_display(self, obj):
        if obj.pk:
            return obj.line_total
        return "0.00"
    line_total_display.short_description = "Line Total"


class StorePurchaseOrderItemInline(admin.TabularInline):
    model = StorePurchaseOrderItem
    extra = 1
    fields = ("item", "qty_ordered", "unit_cost", "received_qty", "pending_qty_display", "line_total_display")
    readonly_fields = ("received_qty", "pending_qty_display", "line_total_display")

    def pending_qty_display(self, obj):
        if obj.pk:
            return obj.pending_qty
        return "0.00"
    pending_qty_display.short_description = "Pending Qty"

    def line_total_display(self, obj):
        if obj.pk:
            return obj.line_total
        return "0.00"
    line_total_display.short_description = "Line Total"


class StoreGoodsReceiptItemInline(admin.TabularInline):
    model = StoreGoodsReceiptItem
    extra = 1
    fields = ("purchase_order_item", "qty_received", "unit_cost", "line_total_display")
    readonly_fields = ("line_total_display",)

    def line_total_display(self, obj):
        if obj.pk:
            return obj.line_total
        return "0.00"
    line_total_display.short_description = "Line Total"


@admin.register(StoreCategory)
class StoreCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "hotel", "is_active")
    list_filter = ("hotel", "is_active")
    search_fields = ("name", "hotel__name")
    ordering = ("hotel__name", "name")


@admin.register(StoreItem)
class StoreItemAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "hotel",
        "category",
        "sku",
        "unit",
        "cost_price",
        "selling_price",
        "stock_qty",
        "reorder_level",
        "is_low_stock_display",
        "is_active",
    )
    list_filter = ("hotel", "category", "is_active")
    search_fields = ("name", "sku", "hotel__name", "category__name")
    ordering = ("hotel__name", "category__name", "name")
    list_editable = ("cost_price", "selling_price", "reorder_level", "is_active")

    def is_low_stock_display(self, obj):
        return obj.is_low_stock
    is_low_stock_display.boolean = True
    is_low_stock_display.short_description = "Low Stock"


@admin.register(StoreSupplier)
class StoreSupplierAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "hotel",
        "contact_person",
        "phone",
        "email",
        "tin_number",
        "is_active",
        "created_at",
    )
    list_filter = ("hotel", "is_active", "created_at")
    search_fields = ("name", "contact_person", "phone", "email", "tin_number")
    ordering = ("hotel__name", "name")


@admin.register(StorePurchaseOrder)
class StorePurchaseOrderAdmin(admin.ModelAdmin):
    list_display = (
        "po_number",
        "hotel",
        "supplier",
        "order_date",
        "expected_date",
        "status",
        "subtotal_display",
        "total_received_qty_display",
        "created_by",
        "approved_by",
        "approved_at",
        "created_at",
    )
    list_filter = ("hotel", "status", "order_date", "expected_date", "created_at")
    search_fields = ("po_number", "supplier__name", "hotel__name")
    ordering = ("-created_at",)
    inlines = [StorePurchaseOrderItemInline]
    readonly_fields = ("po_number", "approved_at", "created_at", "updated_at")

    fieldsets = (
        ("Purchase Order Details", {
            "fields": ("hotel", "supplier", "po_number", "status", "order_date", "expected_date")
        }),
        ("Approval", {
            "fields": ("created_by", "approved_by", "approved_at")
        }),
        ("Notes", {
            "fields": ("note",)
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at")
        }),
    )

    def subtotal_display(self, obj):
        return obj.subtotal
    subtotal_display.short_description = "Subtotal"

    def total_received_qty_display(self, obj):
        return obj.total_received_qty
    total_received_qty_display.short_description = "Received Qty"


@admin.register(StoreGoodsReceipt)
class StoreGoodsReceiptAdmin(admin.ModelAdmin):
    list_display = (
        "receipt_number",
        "hotel",
        "purchase_order",
        "supplier_invoice_number",
        "received_date",
        "total_amount_display",
        "received_by",
        "created_at",
    )
    list_filter = ("hotel", "received_date", "created_at")
    search_fields = ("receipt_number", "purchase_order__po_number", "supplier_invoice_number", "hotel__name")
    ordering = ("-created_at",)
    inlines = [StoreGoodsReceiptItemInline]
    readonly_fields = ("receipt_number", "created_at")

    fieldsets = (
        ("Receipt Details", {
            "fields": ("hotel", "purchase_order", "receipt_number", "supplier_invoice_number", "received_date")
        }),
        ("Notes", {
            "fields": ("note",)
        }),
        ("Audit", {
            "fields": ("received_by", "created_at")
        }),
    )

    def total_amount_display(self, obj):
        return obj.total_amount
    total_amount_display.short_description = "Total Amount"


@admin.register(StoreSale)
class StoreSaleAdmin(admin.ModelAdmin):
    list_display = (
        "sale_number",
        "hotel",
        "customer_name",
        "customer_phone",
        "status",
        "subtotal_display",
        "discount",
        "tax",
        "total_display",
        "created_by",
        "created_at",
        "closed_at",
    )
    list_filter = ("hotel", "status", "created_at", "closed_at")
    search_fields = ("sale_number", "customer_name", "customer_phone", "hotel__name")
    ordering = ("-created_at",)
    inlines = [StoreSaleItemInline]
    readonly_fields = ("sale_number", "created_at", "closed_at")

    fieldsets = (
        ("Sale Details", {
            "fields": ("hotel", "sale_number", "customer_name", "customer_phone", "status")
        }),
        ("Amounts", {
            "fields": ("discount", "tax")
        }),
        ("Audit", {
            "fields": ("created_by", "created_at", "closed_at")
        }),
    )

    def subtotal_display(self, obj):
        return obj.subtotal
    subtotal_display.short_description = "Subtotal"

    def total_display(self, obj):
        return obj.total
    total_display.short_description = "Total"


@admin.register(StoreStockMovement)
class StoreStockMovementAdmin(admin.ModelAdmin):
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
    search_fields = ("item__name", "reference", "note", "hotel__name")
    ordering = ("-created_at",)
    readonly_fields = (
        "hotel",
        "item",
        "movement_type",
        "quantity",
        "balance_after",
        "reference",
        "note",
        "created_by",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False