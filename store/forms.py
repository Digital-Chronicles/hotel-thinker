from __future__ import annotations

from django import forms
from django.forms import inlineformset_factory

from .models import (
    StoreCategory,
    StoreGoodsReceipt,
    StoreGoodsReceiptItem,
    StoreItem,
    StorePurchaseOrder,
    StorePurchaseOrderItem,
    StoreSale,
    StoreSupplier,
)


class BaseTailwindFormMixin:
    def _apply_classes(self):
        for name, field in self.fields.items():
            widget = field.widget
            cls = widget.attrs.get("class", "")
            base = "w-full rounded-xl border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = f"{cls} h-4 w-4 rounded border-gray-300".strip()
            elif isinstance(widget, (forms.Select, forms.SelectMultiple, forms.DateInput, forms.TextInput, forms.EmailInput, forms.NumberInput, forms.Textarea)):
                widget.attrs["class"] = f"{cls} {base}".strip()


class StoreCategoryForm(BaseTailwindFormMixin, forms.ModelForm):
    class Meta:
        model = StoreCategory
        fields = ["hotel", "name", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_classes()


class StoreItemForm(BaseTailwindFormMixin, forms.ModelForm):
    class Meta:
        model = StoreItem
        fields = [
            "hotel",
            "category",
            "name",
            "sku",
            "unit",
            "cost_price",
            "selling_price",
            "stock_qty",
            "reorder_level",
            "is_active",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_classes()


class StoreItemUpdateForm(BaseTailwindFormMixin, forms.ModelForm):
    class Meta:
        model = StoreItem
        fields = [
            "hotel",
            "category",
            "name",
            "sku",
            "unit",
            "cost_price",
            "selling_price",
            "reorder_level",
            "is_active",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_classes()


class StoreSupplierForm(BaseTailwindFormMixin, forms.ModelForm):
    class Meta:
        model = StoreSupplier
        fields = ["hotel", "name", "contact_person", "phone", "email", "address", "tin_number", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_classes()


class StorePurchaseOrderForm(BaseTailwindFormMixin, forms.ModelForm):
    class Meta:
        model = StorePurchaseOrder
        fields = ["hotel", "supplier", "order_date", "expected_date", "note"]
        widgets = {
            "order_date": forms.DateInput(attrs={"type": "date"}),
            "expected_date": forms.DateInput(attrs={"type": "date"}),
            "note": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        hotel = kwargs.pop("hotel", None)
        super().__init__(*args, **kwargs)
        self._apply_classes()

        if hotel is not None:
            self.fields["supplier"].queryset = self.fields["supplier"].queryset.filter(hotel=hotel)


class StorePurchaseOrderItemForm(BaseTailwindFormMixin, forms.ModelForm):
    class Meta:
        model = StorePurchaseOrderItem
        fields = ["item", "qty_ordered", "unit_cost"]

    def __init__(self, *args, **kwargs):
        hotel = kwargs.pop("hotel", None)
        super().__init__(*args, **kwargs)
        self._apply_classes()

        if hotel is not None:
            self.fields["item"].queryset = self.fields["item"].queryset.filter(hotel=hotel, is_active=True)


class StoreGoodsReceiptForm(BaseTailwindFormMixin, forms.ModelForm):
    class Meta:
        model = StoreGoodsReceipt
        fields = ["hotel", "purchase_order", "supplier_invoice_number", "received_date", "note"]
        widgets = {
            "received_date": forms.DateInput(attrs={"type": "date"}),
            "note": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        hotel = kwargs.pop("hotel", None)
        super().__init__(*args, **kwargs)
        self._apply_classes()

        if hotel is not None:
            self.fields["purchase_order"].queryset = self.fields["purchase_order"].queryset.filter(
                hotel=hotel,
                status__in=[
                    StorePurchaseOrder.Status.APPROVED,
                    StorePurchaseOrder.Status.PARTIALLY_RECEIVED,
                ],
            )


class StoreGoodsReceiptItemForm(BaseTailwindFormMixin, forms.ModelForm):
    class Meta:
        model = StoreGoodsReceiptItem
        fields = ["purchase_order_item", "qty_received", "unit_cost"]

    def __init__(self, *args, **kwargs):
        purchase_order = kwargs.pop("purchase_order", None)
        super().__init__(*args, **kwargs)
        self._apply_classes()

        if purchase_order is not None:
            self.fields["purchase_order_item"].queryset = self.fields["purchase_order_item"].queryset.filter(
                purchase_order=purchase_order
            ).select_related("item")


class StoreSaleForm(BaseTailwindFormMixin, forms.ModelForm):
    class Meta:
        model = StoreSale
        fields = ["hotel", "customer_name", "customer_phone", "status", "discount", "tax"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_classes()


StorePurchaseOrderItemFormSet = inlineformset_factory(
    StorePurchaseOrder,
    StorePurchaseOrderItem,
    form=StorePurchaseOrderItemForm,
    extra=1,
    can_delete=True,
)

StoreGoodsReceiptItemFormSet = inlineformset_factory(
    StoreGoodsReceipt,
    StoreGoodsReceiptItem,
    form=StoreGoodsReceiptItemForm,
    extra=1,
    can_delete=True,
)