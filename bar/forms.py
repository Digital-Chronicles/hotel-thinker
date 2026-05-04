from __future__ import annotations

from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory
from .models import BarCategory, BarItem, BarOrder, BarOrderItem


class BaseTailwindFormMixin:
    """Mixin to apply Tailwind CSS classes to form fields."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_classes()
    
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
        fields = ["name", "sort_order", "is_active"]
        widgets = {
            "sort_order": forms.NumberInput(attrs={"min": 0, "step": 1}),
        }
    
    def __init__(self, *args, **kwargs):
        kwargs.pop('hotel', None)
        super().__init__(*args, **kwargs)
        
        self.fields["sort_order"].help_text = "Lower numbers appear first"
        self.fields["is_active"].help_text = "Inactive categories won't appear in item selection"


class BarItemForm(BaseTailwindFormMixin, forms.ModelForm):
    """Form for Bar Item."""
    
    class Meta:
        model = BarItem
        fields = [
            "category", "name", "sku", "unit", "selling_price",
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
        self.hotel = kwargs.pop('hotel', None)
        super().__init__(*args, **kwargs)
        
        self.fields["sku"].help_text = "Optional unique identifier for inventory tracking"
        self.fields["track_stock"].help_text = "Enable to track inventory levels automatically"
        self.fields["reorder_level"].help_text = "Stock level that triggers low stock alert"
        
        if self.hotel:
            self.fields["category"].queryset = BarCategory.objects.filter(
                hotel=self.hotel, is_active=True
            )
        elif self.instance and self.instance.hotel_id:
            self.fields["category"].queryset = BarCategory.objects.filter(
                hotel_id=self.instance.hotel_id, is_active=True
            )
        else:
            self.fields["category"].queryset = BarCategory.objects.none()
    
    def clean(self):
        cleaned_data = super().clean()
        track_stock = cleaned_data.get("track_stock")
        stock_qty = cleaned_data.get("stock_qty", 0)
        
        if track_stock and stock_qty < 0:
            raise ValidationError("Stock quantity cannot be negative when stock tracking is enabled.")
        
        selling_price = cleaned_data.get("selling_price")
        if selling_price is not None and selling_price < 0:
            raise ValidationError({"selling_price": "Selling price cannot be negative."})
        
        cost_price = cleaned_data.get("cost_price")
        if cost_price is not None and cost_price < 0:
            raise ValidationError({"cost_price": "Cost price cannot be negative."})
        
        reorder_level = cleaned_data.get("reorder_level")
        if reorder_level is not None and reorder_level < 0:
            raise ValidationError({"reorder_level": "Reorder level cannot be negative."})
        
        return cleaned_data


class BarOrderForm(BaseTailwindFormMixin, forms.ModelForm):
    """Form for Bar Order."""
    
    class Meta:
        model = BarOrder
        fields = ["booking", "guest_name", "room_charge", "status", "discount", "tax"]
        widgets = {
            "discount": forms.NumberInput(attrs={"step": "0.01", "min": "0", "placeholder": "0.00"}),
            "tax": forms.NumberInput(attrs={"step": "0.01", "min": "0", "placeholder": "0.00"}),
        }
    
    def __init__(self, *args, **kwargs):
        self.hotel = kwargs.pop('hotel', None)
        super().__init__(*args, **kwargs)
        
        self.fields["guest_name"].help_text = "For walk-in customers or if different from booking"
        self.fields["room_charge"].help_text = "Post to guest's room bill for checkout settlement"
        self.fields["discount"].help_text = "Discount amount to apply to the subtotal"
        self.fields["tax"].help_text = "Tax amount to add to the subtotal after discount"
        
        if self.hotel:
            from bookings.models import Booking
            self.fields["booking"].queryset = Booking.objects.filter(
                hotel=self.hotel, 
                status__in=['confirmed', 'checked_in']
            ).select_related('guest')
            self.fields["booking"].label_from_instance = lambda obj: f"{obj.booking_number} - {obj.guest.full_name if obj.guest else 'Guest'}"
        elif self.instance and self.instance.hotel_id:
            from bookings.models import Booking
            self.fields["booking"].queryset = Booking.objects.filter(
                hotel_id=self.instance.hotel_id, 
                status__in=['confirmed', 'checked_in']
            ).select_related('guest')
        else:
            self.fields["booking"].queryset = Booking.objects.none()
        
        if not self.instance.pk:
            self.fields["status"].choices = [
                (BarOrder.Status.OPEN, "Open"),
                (BarOrder.Status.SERVED, "Served"),
            ]
        else:
            if self.instance.status == BarOrder.Status.PAID or self.instance.status == BarOrder.Status.CANCELLED:
                self.fields["status"].disabled = True
    
    def clean(self):
        cleaned_data = super().clean()
        discount = cleaned_data.get("discount", 0)
        tax = cleaned_data.get("tax", 0)
        booking = cleaned_data.get("booking")
        room_charge = cleaned_data.get("room_charge", False)
        guest_name = cleaned_data.get("guest_name", "").strip()
        status = cleaned_data.get("status")
        
        if discount < 0:
            raise ValidationError({"discount": "Discount cannot be negative."})
        
        if tax < 0:
            raise ValidationError({"tax": "Tax cannot be negative."})
        
        if room_charge and not booking:
            raise ValidationError({"room_charge": "A booking is required for room charge orders."})
        
        if not self.instance.pk and not booking and not guest_name:
            raise ValidationError({"guest_name": "Guest name is required for walk-in orders."})
        
        if self.instance.pk and status and status != self.instance.status:
            if self.instance.status == BarOrder.Status.PAID:
                raise ValidationError({"status": "Cannot change status of a paid order."})
            if self.instance.status == BarOrder.Status.CANCELLED:
                raise ValidationError({"status": "Cannot change status of a cancelled order."})
        
        return cleaned_data


class BarOrderItemForm(BaseTailwindFormMixin, forms.ModelForm):
    """Form for Bar Order Item (used in formsets)."""
    
    class Meta:
        model = BarOrderItem
        fields = ["item", "qty", "unit_price", "note"]
        widgets = {
            "qty": forms.NumberInput(attrs={"step": "1", "min": "1"}),
            "unit_price": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "note": forms.TextInput(attrs={"placeholder": "Special instructions (optional)"}),
        }
    
    def __init__(self, *args, **kwargs):
        # Don't try to access order if it doesn't exist
        hotel = kwargs.pop("hotel", None)
        super().__init__(*args, **kwargs)
        
        # Try to get hotel from various sources
        if hotel:
            self.fields["item"].queryset = BarItem.objects.filter(
                hotel=hotel, is_active=True
            ).select_related("category")
        elif (hasattr(self, 'instance') and 
              self.instance and 
              hasattr(self.instance, 'order') and 
              self.instance.order and 
              self.instance.order.hotel_id):
            self.fields["item"].queryset = BarItem.objects.filter(
                hotel_id=self.instance.order.hotel_id, is_active=True
            ).select_related("category")
        elif 'initial' in kwargs and kwargs['initial'] and 'hotel_id' in kwargs['initial']:
            self.fields["item"].queryset = BarItem.objects.filter(
                hotel_id=kwargs['initial']['hotel_id'], is_active=True
            ).select_related("category")
        else:
            # Return empty queryset initially, will be populated when hotel is known
            self.fields["item"].queryset = BarItem.objects.none()
        
        self.fields["qty"].help_text = "Quantity to order"
        self.fields["unit_price"].help_text = "Price per unit (auto-filled from item if left blank)"
    
    def clean(self):
        cleaned_data = super().clean()
        item = cleaned_data.get("item")
        qty = cleaned_data.get("qty", 1)
        unit_price = cleaned_data.get("unit_price")
        
        if not item:
            # This form is empty, mark it for deletion
            if not self.instance.pk:
                self.cleaned_data['DELETE'] = True
            return cleaned_data
        
        if qty <= 0:
            raise ValidationError({"qty": "Quantity must be at least 1."})
        
        if unit_price is not None and unit_price < 0:
            raise ValidationError({"unit_price": "Unit price cannot be negative."})
        
        # Only check stock for new items
        if item and item.track_stock and not self.instance.pk:
            if qty > item.stock_qty:
                raise ValidationError({
                    "qty": f"Not enough stock. Available: {item.stock_qty} {item.unit}"
                })
        
        return cleaned_data
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        if instance.item_id and (instance.unit_price is None or instance.unit_price <= 0):
            instance.unit_price = instance.item.selling_price
        
        if commit:
            instance.save()
        return instance
    

class BarOrderItemFormSet(forms.BaseInlineFormSet):
    """Custom formset for order items that filters out empty forms."""
    
    def __init__(self, *args, **kwargs):
        # Remove hotel if passed
        kwargs.pop('hotel', None)
        super().__init__(*args, **kwargs)
        
        # For new orders without an instance, we need to set a flag
        self.is_new_order = self.instance is None or not self.instance.pk
    
    def _construct_form(self, i, **kwargs):
        """Override to handle new orders without an instance."""
        # For new orders, we don't have an instance to bind to
        if self.is_new_order and self.instance is None:
            kwargs['auto_id'] = self.auto_id
            return self.form(**kwargs)
        return super()._construct_form(i, **kwargs)
    
    def clean(self):
        """Validate that we have valid items."""
        super().clean()
        has_valid_items = False
        
        for form in self.forms:
            if form.cleaned_data and not form.cleaned_data.get("DELETE", False):
                item = form.cleaned_data.get("item")
                qty = form.cleaned_data.get("qty")
                
                if item and qty and qty > 0:
                    has_valid_items = True
        
        # For new orders, require at least one valid item
        if self.is_new_order and self.instance is None and not has_valid_items:
            # Don't raise validation error on GET, only on POST
            if hasattr(self, 'data') and self.data:
                raise ValidationError("Please add at least one item to the order.")
    
    def save(self, commit=True):
        """Save only forms that have valid items."""
        saved_instances = []
        
        # If this is a new order without an instance, we can't save
        if self.instance is None or not self.instance.pk:
            return saved_instances
        
        for form in self.forms:
            # Skip empty forms
            if not form.cleaned_data:
                continue
            
            # Skip deleted forms
            if form.cleaned_data.get("DELETE", False):
                if form.instance.pk:
                    form.instance.delete()
                continue
            
            # Skip forms without an item
            item = form.cleaned_data.get("item")
            if not item:
                continue
            
            # Skip forms with invalid quantity
            qty = form.cleaned_data.get("qty")
            if not qty or qty <= 0:
                continue
            
            # Set the order on the instance
            form.instance.order = self.instance
            
            # Save the valid form
            instance = form.save(commit=commit)
            saved_instances.append(instance)
        
        return saved_instances


# Update the inlineformset_factory to include can_delete_extra
BarOrderItemFormSet = inlineformset_factory(
    BarOrder,
    BarOrderItem,
    form=BarOrderItemForm,
    formset=BarOrderItemFormSet,
    extra=1,
    can_delete=True,
    can_delete_extra=True,  # Add this
    min_num=0,
    validate_min=False,
    fields=["item", "qty", "unit_price", "note"]
)# Inline formset factory
