from __future__ import annotations

from decimal import Decimal
from django import forms

from .models import (
    DiningArea, Table,
    MenuCategory, MenuItem,
    RestaurantOrder, RestaurantOrderItem,
    RestaurantPayment,
)

TW_INPUT = "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-900"
TW_SELECT = "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-slate-900"
TW_TEXTAREA = "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-900"


def apply_tailwind(form: forms.Form):
    for _, f in form.fields.items():
        w = f.widget
        css = w.attrs.get("class", "")
        if isinstance(w, forms.Select):
            w.attrs["class"] = (css + " " + TW_SELECT).strip()
        elif isinstance(w, forms.Textarea):
            w.attrs["class"] = (css + " " + TW_TEXTAREA).strip()
        else:
            w.attrs["class"] = (css + " " + TW_INPUT).strip()


class DiningAreaForm(forms.ModelForm):
    class Meta:
        model = DiningArea
        fields = ["name"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind(self)


class TableForm(forms.ModelForm):
    class Meta:
        model = Table
        fields = ["area", "number", "seats", "is_active"]

    def __init__(self, *args, hotel=None, **kwargs):
        super().__init__(*args, **kwargs)
        if hotel is not None:
            self.fields["area"].queryset = DiningArea.objects.filter(hotel=hotel).order_by("name")
        apply_tailwind(self)


class MenuCategoryForm(forms.ModelForm):
    class Meta:
        model = MenuCategory
        fields = ["name", "sort_order", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind(self)


class MenuItemForm(forms.ModelForm):
    class Meta:
        model = MenuItem
        fields = ["category", "name", "price", "is_active", "track_stock", "stock_qty"]

    def __init__(self, *args, hotel=None, **kwargs):
        super().__init__(*args, **kwargs)
        if hotel is not None:
            self.fields["category"].queryset = MenuCategory.objects.filter(hotel=hotel).order_by("name")
        apply_tailwind(self)


class RestaurantOrderForm(forms.ModelForm):
    class Meta:
        model = RestaurantOrder
        fields = ["table", "customer_name", "customer_phone", "discount", "tax", "status"]

    def __init__(self, *args, hotel=None, **kwargs):
        super().__init__(*args, **kwargs)
        if hotel is not None:
            self.fields["table"].queryset = Table.objects.filter(hotel=hotel, is_active=True).order_by("number")
        apply_tailwind(self)

    def clean_discount(self):
        v = self.cleaned_data.get("discount") or Decimal("0")
        if v < 0:
            raise forms.ValidationError("Discount cannot be negative.")
        return v

    def clean_tax(self):
        v = self.cleaned_data.get("tax") or Decimal("0")
        if v < 0:
            raise forms.ValidationError("Tax cannot be negative.")
        return v


class RestaurantOrderItemForm(forms.ModelForm):
    class Meta:
        model = RestaurantOrderItem
        fields = ["item", "qty", "note"]

    def __init__(self, *args, hotel=None, **kwargs):
        super().__init__(*args, **kwargs)
        if hotel is not None:
            self.fields["item"].queryset = MenuItem.objects.filter(hotel=hotel, is_active=True).order_by("name")
        apply_tailwind(self)

    def clean_qty(self):
        qty = self.cleaned_data.get("qty") or 0
        if qty <= 0:
            raise forms.ValidationError("Quantity must be at least 1.")
        return qty


class OrderStatusForm(forms.Form):
    status = forms.ChoiceField(choices=RestaurantOrder.Status.choices)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind(self)


class PaymentForm(forms.Form):
    method = forms.ChoiceField(choices=RestaurantPayment.Method.choices)
    amount = forms.DecimalField(min_value=Decimal("0.01"), decimal_places=2, max_digits=12)
    reference = forms.CharField(required=False, max_length=120)

    def __init__(self, *args, order=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.order = order
        apply_tailwind(self)
        if order is not None and not self.is_bound:
            self.initial["amount"] = order.total

    def clean(self):
        cleaned = super().clean()
        if self.order is None:
            return cleaned

        amt = cleaned.get("amount")
        if amt is None:
            return cleaned

        if amt != self.order.total:
            self.add_error("amount", f"Amount must equal order total ({self.order.total}).")
        return cleaned