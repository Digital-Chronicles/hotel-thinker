from __future__ import annotations

from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from .models import BarCategory, BarItem, BarOrder, BarOrderItem


class BaseTailwindFormMixin:
    """Mixin to apply Tailwind CSS classes to form fields."""
    
    def _apply_classes(self):
        for name, field in self.fields.items():
            widget = field.widget
            cls = widget.attrs.get("class", "")
            
            # Base input classes
            base_input = "w-full rounded-xl border border-slate-300 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-200"
            base_checkbox = "h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-2 focus:ring-blue-500"
            base_select = "w-full rounded-xl border border-slate-300 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent appearance-none bg-white"
            
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = f"{cls} {base_checkbox}".strip()
            elif isinstance(widget, forms.Select):
                widget.attrs["class"] = f"{cls} {base_select}".strip()
            elif isinstance(widget, (forms.TextInput, forms.EmailInput, forms.NumberInput, forms.DateInput, forms.TimeInput)):
                widget.attrs["class"] = f"{cls} {base_input}".strip()
            elif isinstance(widget, forms.Textarea):
                widget.attrs["class"] = f"{cls} {base_input} resize-y min-h-[80px]".strip()
            elif isinstance(widget, forms.FileInput):
                widget.attrs["class"] = f"{cls} w-full rounded-xl border border-slate-300 px-4 py-2.5 text-sm file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100".strip()


class BarCategoryForm(BaseTailwindFormMixin, forms.ModelForm):
    """Form for Bar Category."""
    
    class Meta:
        model = BarCategory
        fields = ["hotel", "name", "sort_order", "is_active"]
        widgets = {
            "sort_order": forms.NumberInput(attrs={"min": 0, "step": 1}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_classes()
        
        # Add help texts
        self.fields["sort_order"].help_text = "Lower numbers appear first"
        self.fields["is_active"].help_text = "Inactive categories won't appear in item selection"


class BarItemForm(BaseTailwindFormMixin, forms.ModelForm):
    """Form for Bar Item."""
    
    class Meta:
        model = BarItem
        fields = [
            "hotel", "category", "name", "sku", "unit", "selling_price",
            "cost_price", "track_stock", "stock_qty", "reorder_level", "is_active"
        ]
        widgets = {
            "selling_price": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "cost_price": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "stock_qty": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "reorder_level": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "sku": forms.TextInput(attrs={"placeholder": "e.g., BEER-001"}),
            "unit": forms.TextInput(attrs={"placeholder": "e.g., Bottle, Can, Glass"}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_classes()
        
        # Add help texts
        self.fields["sku"].help_text = "Optional unique identifier for inventory tracking"
        self.fields["track_stock"].help_text = "Enable to track inventory levels automatically"
        self.fields["reorder_level"].help_text = "Stock level that triggers low stock alert"
        
        # Limit category choices based on hotel
        if self.instance and self.instance.hotel_id:
            self.fields["category"].queryset = BarCategory.objects.filter(
                hotel_id=self.instance.hotel_id, is_active=True
            )
    
    def clean(self):
        cleaned_data = super().clean()
        track_stock = cleaned_data.get("track_stock")
        stock_qty = cleaned_data.get("stock_qty", 0)
        
        # Validate stock quantity if tracking is enabled
        if track_stock and stock_qty < 0:
            raise ValidationError("Stock quantity cannot be negative when stock tracking is enabled.")
        
        return cleaned_data


class BarOrderForm(BaseTailwindFormMixin, forms.ModelForm):
    """Form for Bar Order."""
    
    class Meta:
        model = BarOrder
        fields = ["hotel", "booking", "guest_name", "room_charge", "status", "discount", "tax"]
        widgets = {
            "discount": forms.NumberInput(attrs={"step": "0.01", "min": "0", "placeholder": "0.00"}),
            "tax": forms.NumberInput(attrs={"step": "0.01", "min": "0", "placeholder": "0.00"}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_classes()
        
        # Add help texts
        self.fields["guest_name"].help_text = "For walk-in customers or if different from booking"
        self.fields["room_charge"].help_text = "Post to guest's room bill for checkout settlement"
        
        # Customize status choices (remove paid/cancelled from creation)
        if not self.instance.pk:
            self.fields["status"].choices = [
                (BarOrder.Status.OPEN, "Open"),
                (BarOrder.Status.SERVED, "Served"),
            ]
    
    def clean(self):
        cleaned_data = super().clean()
        discount = cleaned_data.get("discount", 0)
        tax = cleaned_data.get("tax", 0)
        
        if discount < 0:
            raise ValidationError({"discount": "Discount cannot be negative."})
        
        if tax < 0:
            raise ValidationError({"tax": "Tax cannot be negative."})
        
        return cleaned_data


class BarOrderItemForm(BaseTailwindFormMixin, forms.ModelForm):
    """Form for Bar Order Item (used in formsets)."""
    
    class Meta:
        model = BarOrderItem
        fields = ["item", "qty", "unit_price", "note"]
        widgets = {
            "qty": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
            "unit_price": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "note": forms.TextInput(attrs={"placeholder": "Special instructions (optional)"}),
        }
    
    def __init__(self, *args, **kwargs):
        hotel = kwargs.pop("hotel", None)
        super().__init__(*args, **kwargs)
        self._apply_classes()
        
        if hotel:
            self.fields["item"].queryset = BarItem.objects.filter(
                hotel=hotel, is_active=True
            ).select_related("category")


class BarOrderItemFormSet(forms.BaseInlineFormSet):
    """Custom formset for order items with validation."""
    
    def clean(self):
        """Validate that all items are unique in the order."""
        super().clean()
        items = []
        
        for form in self.forms:
            if form.cleaned_data and not form.cleaned_data.get("DELETE", False):
                item = form.cleaned_data.get("item")
                if item:
                    if item in items:
                        raise ValidationError("Duplicate items are not allowed. Please combine quantities.")
                    items.append(item)


# Inline formset factory
from django.forms import inlineformset_factory

BarOrderItemFormSet = inlineformset_factory(
    BarOrder,
    BarOrderItem,
    form=BarOrderItemForm,
    formset=BarOrderItemFormSet,
    extra=1,
    can_delete=True,
    fields=["item", "qty", "unit_price", "note"]
)