from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional, Type, Union

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import QuerySet
from django.forms import inlineformset_factory
from django.utils import timezone

from .models import (
    DiningArea, Table,
    MenuCategory, MenuItem,
    RestaurantOrder, RestaurantOrderItem,
    RestaurantPayment, RestaurantInvoice,
)

# ============================================================================
# Tailwind CSS Classes
# ============================================================================

TW_INPUT = "w-full rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-200"
TW_INPUT_ERROR = "w-full rounded-xl border border-red-500 bg-red-50 px-4 py-2.5 text-sm text-red-900 placeholder-red-400 focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent transition-all duration-200"
TW_SELECT = "w-full rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent appearance-none transition-all duration-200"
TW_SELECT_ERROR = "w-full rounded-xl border border-red-500 bg-red-50 px-4 py-2.5 text-sm text-red-900 focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent appearance-none transition-all duration-200"
TW_TEXTAREA = "w-full rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-y min-h-[80px] transition-all duration-200"
TW_CHECKBOX = "w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-2 focus:ring-blue-500 focus:ring-offset-0 transition-all duration-200"
TW_FILE = "w-full rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 cursor-pointer transition-all duration-200"


def apply_tailwind(form: forms.Form, has_errors: bool = False) -> None:
    """
    Apply Tailwind CSS classes to all form fields.
    
    Args:
        form: The form instance to style
        has_errors: If True, apply error styling to fields with errors
    """
    for field_name, field in form.fields.items():
        widget = field.widget
        css = widget.attrs.get("class", "")
        has_field_error = has_errors and field_name in form.errors
        
        if isinstance(widget, forms.CheckboxInput):
            widget.attrs["class"] = (css + " " + TW_CHECKBOX).strip()
        elif isinstance(widget, forms.Select):
            base_class = TW_SELECT_ERROR if has_field_error else TW_SELECT
            widget.attrs["class"] = (css + " " + base_class).strip()
        elif isinstance(widget, forms.Textarea):
            widget.attrs["class"] = (css + " " + TW_TEXTAREA).strip()
        elif isinstance(widget, forms.FileInput):
            widget.attrs["class"] = (css + " " + TW_FILE).strip()
        elif isinstance(widget, (forms.TextInput, forms.EmailInput, forms.NumberInput, 
                                  forms.DateInput, forms.TimeInput, forms.PasswordInput)):
            base_class = TW_INPUT_ERROR if has_field_error else TW_INPUT
            widget.attrs["class"] = (css + " " + base_class).strip()
        else:
            base_class = TW_INPUT_ERROR if has_field_error else TW_INPUT
            widget.attrs["class"] = (css + " " + base_class).strip()


# ============================================================================
# Base Classes
# ============================================================================

class BaseHotelFilterForm(forms.Form):
    """Base form for filtering by hotel"""
    hotel = forms.ModelChoiceField(
        queryset=None,
        required=False,
        empty_label="All Hotels",
        widget=forms.Select(attrs={"class": "w-48"})
    )
    
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and hasattr(user, 'hotels'):
            self.fields["hotel"].queryset = user.hotels.all()
        apply_tailwind(self)


class BaseModelForm(forms.ModelForm):
    """Base ModelForm with Tailwind styling and common functionality"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_styling()
    
    def _apply_styling(self) -> None:
        """Apply Tailwind styling to all fields"""
        has_errors = bool(self.errors)
        apply_tailwind(self, has_errors)
    
    def add_form_error(self, message: str) -> None:
        """Add a non-field error to the form"""
        self.add_error(None, message)
    
    def clean_positive_decimal(self, field_name: str, allow_zero: bool = False) -> Decimal:
        """Validate a decimal field is positive"""
        value = self.cleaned_data.get(field_name)
        if value is not None:
            if value < 0:
                raise ValidationError(f"{field_name.replace('_', ' ').title()} cannot be negative.")
            if not allow_zero and value == 0:
                raise ValidationError(f"{field_name.replace('_', ' ').title()} must be greater than zero.")
        return value


class BaseFilterForm(BaseHotelFilterForm):
    """Base filter form with common filter fields"""
    
    is_active = forms.ChoiceField(
        choices=[("", "All Status"), ("true", "Active"), ("false", "Inactive")],
        required=False,
        widget=forms.Select(attrs={"class": "w-36"})
    )
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Search...", "class": "w-48"})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind(self)
    
    def get_active_filter(self) -> Optional[bool]:
        """Convert is_active string to boolean or None"""
        val = self.cleaned_data.get("is_active")
        if val == "true":
            return True
        if val == "false":
            return False
        return None


# ============================================================================
# Dining Area Forms
# ============================================================================

class DiningAreaForm(BaseModelForm):
    """Form for creating and editing dining areas"""
    
    class Meta:
        model = DiningArea
        fields = ["name", "description", "is_active"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "Optional description of the dining area"}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.fields["name"].help_text = "e.g., Main Hall, Terrace, VIP Room"
        self.fields["is_active"].help_text = "Inactive areas won't appear in table selection"
    
    def clean_name(self) -> str:
        name = self.cleaned_data.get("name", "").strip()
        if not name:
            raise ValidationError("Dining area name is required.")
        if len(name) < 2:
            raise ValidationError("Dining area name must be at least 2 characters.")
        return name


class DiningAreaFilterForm(BaseFilterForm):
    """Form for filtering dining areas"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["search"].widget.attrs["placeholder"] = "Search areas..."


# ============================================================================
# Table Forms
# ============================================================================

class TableForm(BaseModelForm):
    """Form for creating and editing restaurant tables"""
    
    class Meta:
        model = Table
        fields = ["area", "number", "seats", "is_active", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2, "placeholder": "Optional notes about the table (location, view, etc.)"}),
        }
    
    def __init__(self, *args, hotel=None, **kwargs):
        self.hotel = hotel
        super().__init__(*args, **kwargs)
        
        if hotel is not None:
            self.fields["area"].queryset = DiningArea.objects.filter(
                hotel=hotel, is_active=True
            ).order_by("name")
        
        self.fields["number"].help_text = "Table number or identifier"
        self.fields["seats"].help_text = "Maximum number of seats at this table"
        self.fields["is_active"].help_text = "Inactive tables won't be available for new orders"
    
    def clean_number(self) -> str:
        number = self.cleaned_data.get("number", "").strip()
        if not number:
            raise ValidationError("Table number is required.")
        return number
    
    def clean_seats(self) -> int:
        seats = self.cleaned_data.get("seats")
        if seats and seats < 1:
            raise ValidationError("Table must have at least 1 seat.")
        if seats and seats > 50:
            raise ValidationError("Table cannot have more than 50 seats.")
        return seats
    
    def clean(self) -> Dict[str, Any]:
        cleaned_data = super().clean()
        area = cleaned_data.get("area")
        
        # Check uniqueness within the hotel
        if self.hotel and cleaned_data.get("number"):
            exists = Table.objects.filter(
                hotel=self.hotel,
                number=cleaned_data["number"]
            ).exclude(pk=self.instance.pk if self.instance else None).exists()
            
            if exists:
                self.add_error("number", f"Table number '{cleaned_data['number']}' already exists in this hotel.")
        
        return cleaned_data


class TableFilterForm(BaseFilterForm):
    """Form for filtering tables"""
    
    area = forms.ModelChoiceField(
        queryset=None,
        required=False,
        empty_label="All Areas",
        widget=forms.Select(attrs={"class": "w-44"})
    )
    min_seats = forms.IntegerField(
        required=False,
        min_value=1,
        widget=forms.NumberInput(attrs={"placeholder": "Min seats", "class": "w-28"})
    )
    
    def __init__(self, *args, hotel=None, **kwargs):
        super().__init__(*args, **kwargs)
        if hotel:
            self.fields["area"].queryset = DiningArea.objects.filter(
                hotel=hotel, is_active=True
            ).order_by("name")
        self.fields["search"].widget.attrs["placeholder"] = "Search table number..."


# ============================================================================
# Menu Category Forms
# ============================================================================

class MenuCategoryForm(BaseModelForm):
    """Form for creating and editing menu categories"""
    
    class Meta:
        model = MenuCategory
        fields = ["name", "description", "sort_order", "is_active"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2, "placeholder": "Optional category description"}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.fields["name"].help_text = "e.g., Appetizers, Main Course, Desserts"
        self.fields["sort_order"].help_text = "Lower numbers appear first in the menu"
        self.fields["is_active"].help_text = "Inactive categories won't appear in item selection"
    
    def clean_name(self) -> str:
        name = self.cleaned_data.get("name", "").strip()
        if not name:
            raise ValidationError("Category name is required.")
        return name
    
    def clean_sort_order(self) -> int:
        sort_order = self.cleaned_data.get("sort_order", 0)
        if sort_order < 0:
            raise ValidationError("Sort order cannot be negative.")
        return sort_order


class MenuCategoryFilterForm(BaseFilterForm):
    """Form for filtering menu categories"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["search"].widget.attrs["placeholder"] = "Search categories..."


# ============================================================================
# Menu Item Forms
# ============================================================================

class MenuItemForm(BaseModelForm):
    """Form for creating and editing menu items"""
    
    class Meta:
        model = MenuItem
        fields = [
            "category", "name", "description", "ingredients", "price", "cost_price",
            "track_stock", "stock_qty", "reorder_level", "preparation_time",
            "is_vegetarian", "is_vegan", "is_gluten_free", "is_spicy",
            "is_featured", "is_recommended", "is_active"
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "Detailed description of the dish"}),
            "ingredients": forms.Textarea(attrs={"rows": 2, "placeholder": "List of main ingredients"}),
            "price": forms.NumberInput(attrs={"step": "0.01", "min": "0", "placeholder": "0.00"}),
            "cost_price": forms.NumberInput(attrs={"step": "0.01", "min": "0", "placeholder": "0.00"}),
            "stock_qty": forms.NumberInput(attrs={"step": "0.01", "min": "0", "placeholder": "0"}),
            "reorder_level": forms.NumberInput(attrs={"step": "0.01", "min": "0", "placeholder": "0"}),
            "preparation_time": forms.NumberInput(attrs={"min": "0", "placeholder": "15"}),
        }
    
    def __init__(self, *args, hotel=None, **kwargs):
        self.hotel = hotel
        super().__init__(*args, **kwargs)
        
        if hotel is not None:
            self.fields["category"].queryset = MenuCategory.objects.filter(
                hotel=hotel, is_active=True
            ).order_by("sort_order", "name")
        
        self._add_help_texts()
    
    def _add_help_texts(self) -> None:
        """Add help texts to all fields"""
        help_texts = {
            "name": "Name of the dish or beverage",
            "price": "Selling price to customers",
            "cost_price": "Cost price for profit calculation",
            "track_stock": "Enable to automatically track inventory levels",
            "reorder_level": "Stock level that triggers low stock alert",
            "preparation_time": "Estimated time in minutes",
            "is_vegetarian": "Suitable for vegetarians",
            "is_vegan": "Suitable for vegans",
            "is_gluten_free": "Gluten-free option",
            "is_spicy": "Contains spicy ingredients",
            "is_featured": "Featured on the menu",
            "is_recommended": "Chef's recommendation",
        }
        
        for field, help_text in help_texts.items():
            self.fields[field].help_text = help_text
    
    def clean_name(self) -> str:
        name = self.cleaned_data.get("name", "").strip()
        if not name:
            raise ValidationError("Menu item name is required.")
        if len(name) < 2:
            raise ValidationError("Menu item name must be at least 2 characters.")
        return name
    
    def clean_price(self) -> Decimal:
        price = self.cleaned_data.get("price")
        if price is not None and price < 0:
            raise ValidationError("Price cannot be negative.")
        return price or Decimal("0.00")
    
    def clean_cost_price(self) -> Decimal:
        cost_price = self.cleaned_data.get("cost_price")
        if cost_price is not None and cost_price < 0:
            raise ValidationError("Cost price cannot be negative.")
        return cost_price or Decimal("0.00")
    
    def clean(self) -> Dict[str, Any]:
        cleaned_data = super().clean()
        track_stock = cleaned_data.get("track_stock")
        stock_qty = cleaned_data.get("stock_qty", 0)
        reorder_level = cleaned_data.get("reorder_level", 0)
        price = cleaned_data.get("price", 0)
        cost_price = cleaned_data.get("cost_price", 0)
        
        # Stock validation
        if track_stock:
            if stock_qty < 0:
                self.add_error("stock_qty", "Stock quantity cannot be negative when tracking is enabled.")
            if reorder_level < 0:
                self.add_error("reorder_level", "Reorder level cannot be negative.")
        
        # Profitability warning (not an error, but could be shown to user)
        if price > 0 and cost_price >= price:
            self.add_form_error(f"Warning: Cost price (${cost_price}) is greater than or equal to selling price (${price}). This item will not be profitable.")
        
        # Check uniqueness within hotel
        if self.hotel and cleaned_data.get("name"):
            exists = MenuItem.objects.filter(
                hotel=self.hotel,
                name__iexact=cleaned_data["name"]
            ).exclude(pk=self.instance.pk if self.instance else None).exists()
            
            if exists:
                self.add_error("name", f"Menu item '{cleaned_data['name']}' already exists in this hotel.")
        
        return cleaned_data


class MenuItemFilterForm(BaseFilterForm):
    """Form for filtering menu items"""
    
    category = forms.ModelChoiceField(
        queryset=None,
        required=False,
        empty_label="All Categories",
        widget=forms.Select(attrs={"class": "w-44"})
    )
    low_stock = forms.ChoiceField(
        choices=[("", "All Stock"), ("true", "Low Stock"), ("out", "Out of Stock")],
        required=False,
        widget=forms.Select(attrs={"class": "w-36"})
    )
    dietary = forms.ChoiceField(
        choices=[
            ("", "All"), 
            ("vegetarian", "Vegetarian"), 
            ("vegan", "Vegan"), 
            ("gluten_free", "Gluten Free")
        ],
        required=False,
        widget=forms.Select(attrs={"class": "w-40"})
    )
    featured = forms.ChoiceField(
        choices=[("", "All"), ("featured", "Featured"), ("recommended", "Recommended")],
        required=False,
        widget=forms.Select(attrs={"class": "w-40"})
    )
    
    def __init__(self, *args, hotel=None, **kwargs):
        super().__init__(*args, **kwargs)
        if hotel:
            self.fields["category"].queryset = MenuCategory.objects.filter(
                hotel=hotel, is_active=True
            ).order_by("name")
        self.fields["search"].widget.attrs["placeholder"] = "Search items..."
    
    def get_low_stock_filter(self) -> Optional[str]:
        """Get low stock filter value"""
        return self.cleaned_data.get("low_stock")
    
    def get_dietary_filter(self) -> Optional[str]:
        """Get dietary filter value"""
        return self.cleaned_data.get("dietary")
    
    def get_featured_filter(self) -> Optional[str]:
        """Get featured filter value"""
        return self.cleaned_data.get("featured")


# ============================================================================
# Order Forms
# ============================================================================

class RestaurantOrderForm(BaseModelForm):
    """Form for creating and editing restaurant orders"""
    
    class Meta:
        model = RestaurantOrder
        fields = [
            "table", "customer_name", "customer_phone", "customer_email",
            "booking", "room_charge", "status",
            "discount", "discount_percent", "tax", "tax_percent", 
            "service_charge", "special_instructions", "kitchen_notes"
        ]
        widgets = {
            "customer_name": forms.TextInput(attrs={"placeholder": "Guest name (for walk-ins)"}),
            "customer_phone": forms.TextInput(attrs={"placeholder": "Contact number"}),
            "customer_email": forms.EmailInput(attrs={"placeholder": "Email for digital receipt"}),
            "special_instructions": forms.Textarea(attrs={"rows": 2, "placeholder": "Special requests or instructions for kitchen"}),
            "kitchen_notes": forms.Textarea(attrs={"rows": 2, "placeholder": "Internal notes for kitchen staff"}),
            "discount": forms.NumberInput(attrs={"step": "0.01", "min": "0", "placeholder": "0.00"}),
            "discount_percent": forms.NumberInput(attrs={"step": "0.01", "min": "0", "max": "100", "placeholder": "0"}),
            "tax": forms.NumberInput(attrs={"step": "0.01", "min": "0", "placeholder": "0.00"}),
            "tax_percent": forms.NumberInput(attrs={"step": "0.01", "min": "0", "max": "100", "placeholder": "0"}),
            "service_charge": forms.NumberInput(attrs={"step": "0.01", "min": "0", "placeholder": "0.00"}),
        }
    
    def __init__(self, *args, hotel=None, **kwargs):
        self.hotel = hotel
        super().__init__(*args, **kwargs)
        
        if hotel is not None:
            self._configure_table_field(hotel)
            self._configure_booking_field(hotel)
        
        self._set_defaults()
        self._add_help_texts()
    
    def _configure_table_field(self, hotel: Hotel) -> None:
        """Configure the table field with proper queryset and labels"""
        self.fields["table"].queryset = Table.objects.filter(
            hotel=hotel, is_active=True
        ).select_related("area").order_by("area__name", "number")
        self.fields["table"].label_from_instance = lambda obj: (
            f"Table {obj.number} - {obj.area.name if obj.area else 'No area'} ({obj.seats} seats)"
        )
    
    def _configure_booking_field(self, hotel: Hotel) -> None:
        """Configure the booking field with proper queryset and labels"""
        try:
            from bookings.models import Booking
            self.fields["booking"].queryset = Booking.objects.filter(
                hotel=hotel, 
                status__in=['confirmed', 'checked_in']
            ).select_related('guest').order_by('-created_at')
            self.fields["booking"].label_from_instance = lambda obj: (
                f"{obj.booking_number} - {obj.guest.full_name if obj.guest else 'Guest'}"
            )
        except ImportError:
            self.fields["booking"].queryset = self.fields["booking"].queryset.none()
    
    def _set_defaults(self) -> None:
        """Set default values for numeric fields"""
        defaults = {
            "status": RestaurantOrder.Status.OPEN,
            "discount": Decimal("0.00"),
            "discount_percent": Decimal("0.00"),
            "tax": Decimal("0.00"),
            "tax_percent": Decimal("0.00"),
            "service_charge": Decimal("0.00"),
            "room_charge": False,
        }
        for field, value in defaults.items():
            self.fields[field].initial = value
    
    def _add_help_texts(self) -> None:
        """Add help texts to all fields"""
        help_texts = {
            "table": "Select table for dine-in orders (leave empty for walk-ins)",
            "booking": "Link to registered hotel guest",
            "room_charge": "Charge to guest's room account (only available when guest is selected)",
            "status": "Open status allows adding items; moves to Kitchen automatically when items are added",
            "discount_percent": "Apply percentage discount (overrides fixed discount)",
            "tax_percent": "Apply percentage tax (overrides fixed tax)",
            "kitchen_notes": "Internal notes visible only to kitchen staff",
        }
        for field, help_text in help_texts.items():
            if field in self.fields:
                self.fields[field].help_text = help_text
    
    def clean_discount(self) -> Decimal:
        return self.clean_positive_decimal("discount", allow_zero=True)
    
    def clean_discount_percent(self) -> Decimal:
        value = self.cleaned_data.get("discount_percent", 0)
        if value is not None and (value < 0 or value > 100):
            raise ValidationError("Discount percentage must be between 0 and 100.")
        return value or Decimal("0.00")
    
    def clean_tax(self) -> Decimal:
        return self.clean_positive_decimal("tax", allow_zero=True)
    
    def clean_tax_percent(self) -> Decimal:
        value = self.cleaned_data.get("tax_percent", 0)
        if value is not None and (value < 0 or value > 100):
            raise ValidationError("Tax percentage must be between 0 and 100.")
        return value or Decimal("0.00")
    
    def clean(self) -> Dict[str, Any]:
        cleaned_data = super().clean()
        discount = cleaned_data.get("discount", 0)
        discount_percent = cleaned_data.get("discount_percent", 0)
        tax = cleaned_data.get("tax", 0)
        tax_percent = cleaned_data.get("tax_percent", 0)
        booking = cleaned_data.get("booking")
        room_charge = cleaned_data.get("room_charge", False)
        
        # Validate discount methods are mutually exclusive
        if discount > 0 and discount_percent > 0:
            self.add_form_error("Please use either fixed discount OR percentage discount, not both.")
        
        # Validate tax methods are mutually exclusive
        if tax > 0 and tax_percent > 0:
            self.add_form_error("Please use either fixed tax OR percentage tax, not both.")
        
        # Validate room charge requires booking
        if room_charge and not booking:
            self.add_error("room_charge", "Room charge requires selecting a hotel guest first.")
        
        return cleaned_data


class RestaurantOrderItemForm(BaseModelForm):
    """Form for adding/editing order items"""
    
    class Meta:
        model = RestaurantOrderItem
        fields = ["item", "qty", "note"]
        widgets = {
            "qty": forms.NumberInput(attrs={"min": "1", "step": "1", "value": "1", "class": "w-24"}),
            "note": forms.TextInput(attrs={
                "placeholder": "Special instructions (e.g., no onions, extra spicy)", 
                "class": "w-full"
            }),
        }
    
    def __init__(self, *args, hotel=None, order=None, **kwargs):
        self.order = order
        super().__init__(*args, **kwargs)
        
        if hotel is not None:
            self.fields["item"].queryset = MenuItem.objects.filter(
                hotel=hotel, is_active=True
            ).select_related("category").order_by("category__sort_order", "name")
            self.fields["item"].label_from_instance = lambda obj: f"{obj.name} - ${obj.price:.2f}"
        
        self._add_help_texts()
    
    def _add_help_texts(self) -> None:
        """Add help texts to fields"""
        self.fields["item"].help_text = "Select a menu item"
        self.fields["qty"].help_text = "Quantity to order"
        self.fields["note"].help_text = "Any special requests for this specific item"
    
    def clean_qty(self) -> int:
        qty = self.cleaned_data.get("qty")
        if not qty or qty <= 0:
            raise ValidationError("Quantity must be at least 1.")
        if qty > 999:
            raise ValidationError("Quantity cannot exceed 999.")
        return qty
    
    def clean_item(self) -> MenuItem:
        item = self.cleaned_data.get("item")
        
        # Check if item already exists in order
        if self.order and item and self.order.items.filter(item=item).exists():
            raise ValidationError(
                "This item is already in the order. Please update the quantity instead."
            )
        
        # Check stock availability if tracking is enabled
        if item and item.track_stock and self.cleaned_data.get("qty"):
            qty = self.cleaned_data["qty"]
            if item.stock_qty < qty:
                raise ValidationError(
                    f"Insufficient stock for {item.name}. Available: {item.stock_qty}"
                )
        
        return item


# Order Item FormSet
OrderItemFormSet = inlineformset_factory(
    RestaurantOrder,
    RestaurantOrderItem,
    form=RestaurantOrderItemForm,
    extra=1,
    can_delete=True,
    fields=["item", "qty", "note"],
    widgets={
        "note": forms.TextInput(attrs={"placeholder": "Special instructions"}),
    }
)


# ============================================================================
# Order Action Forms
# ============================================================================

class OrderStatusForm(forms.Form):
    """Form for changing order status"""
    
    status = forms.ChoiceField(choices=RestaurantOrder.Status.choices)
    notes = forms.CharField(
        required=False, 
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Optional notes about status change"})
    )
    
    # Status transition validation rules
    STATUS_TRANSITIONS = {
        RestaurantOrder.Status.OPEN: {
            RestaurantOrder.Status.KITCHEN, RestaurantOrder.Status.CANCELLED
        },
        RestaurantOrder.Status.KITCHEN: {
            RestaurantOrder.Status.SERVED, RestaurantOrder.Status.CANCELLED
        },
        RestaurantOrder.Status.SERVED: {
            RestaurantOrder.Status.BILLED, RestaurantOrder.Status.CANCELLED
        },
        RestaurantOrder.Status.BILLED: {
            RestaurantOrder.Status.PAID, RestaurantOrder.Status.CANCELLED
        },
        RestaurantOrder.Status.PAID: set(),
        RestaurantOrder.Status.CANCELLED: set(),
    }
    
    def __init__(self, *args, current_status: Optional[str] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_status = current_status
        apply_tailwind(self)
        
        self._add_status_help_texts()
    
    def _add_status_help_texts(self) -> None:
        """Add descriptive help text for each status"""
        status_descriptions = {
            RestaurantOrder.Status.OPEN: "Order is open, items can be added",
            RestaurantOrder.Status.KITCHEN: "Order sent to kitchen for preparation",
            RestaurantOrder.Status.SERVED: "Food has been served to customer",
            RestaurantOrder.Status.BILLED: "Invoice generated, awaiting payment",
            RestaurantOrder.Status.PAID: "Payment received, order complete",
            RestaurantOrder.Status.CANCELLED: "Order cancelled",
        }
        
        choices = []
        for value, label in RestaurantOrder.Status.choices:
            desc = status_descriptions.get(value, "")
            display = f"{label} - {desc}" if desc else label
            choices.append((value, display))
        
        self.fields["status"].choices = choices
        self.fields["status"].help_text = "Current order status"
    
    def clean_status(self) -> str:
        status = self.cleaned_data.get("status")
        
        if status not in dict(RestaurantOrder.Status.choices):
            raise ValidationError("Invalid status selected.")
        
        # Validate status transition
        if self.current_status and self.current_status != status:
            allowed = self.STATUS_TRANSITIONS.get(self.current_status, set())
            if status not in allowed:
                raise ValidationError(
                    f"Cannot change from '{self.current_status}' to '{status}'. "
                    f"Allowed transitions: {', '.join(allowed) if allowed else 'none'}"
                )
        
        return status


class PaymentForm(forms.Form):
    """Form for processing payments"""
    
    method = forms.ChoiceField(choices=RestaurantPayment.Method.choices)
    amount = forms.DecimalField(min_value=Decimal("0.01"), decimal_places=2, max_digits=12)
    reference = forms.CharField(
        required=False, 
        max_length=120, 
        widget=forms.TextInput(attrs={"placeholder": "Transaction reference (for mobile/card payments)"})
    )
    notes = forms.CharField(
        required=False, 
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Payment notes (optional)"})
    )
    
    # Payment methods that require reference
    REFERENCE_REQUIRED_METHODS = {RestaurantPayment.Method.MOMO, RestaurantPayment.Method.CARD}
    
    def __init__(self, *args, order=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.order = order
        apply_tailwind(self)
        
        if order is not None and not self.is_bound:
            self.initial["amount"] = order.total
        
        self._add_help_texts()
    
    def _add_help_texts(self) -> None:
        """Add help texts to fields"""
        self.fields["method"].help_text = "Select payment method"
        self.fields["reference"].help_text = "Transaction ID or reference number (required for mobile/card payments)"
        self.fields["amount"].help_text = f"Total amount due: {self.order.total if self.order else '0.00'}"
    
    def clean_amount(self) -> Decimal:
        amount = self.cleaned_data.get("amount")
        
        if amount <= 0:
            raise ValidationError("Payment amount must be greater than zero.")
        
        if self.order and amount != self.order.total:
            raise ValidationError(f"Payment amount must equal order total ({self.order.total}).")
        
        return amount
    
    def clean_reference(self) -> str:
        reference = self.cleaned_data.get("reference", "").strip()
        method = self.cleaned_data.get("method")
        
        if method in self.REFERENCE_REQUIRED_METHODS and not reference:
            method_display = dict(RestaurantPayment.Method.choices).get(method, method)
            raise ValidationError(f"Transaction reference is required for {method_display} payments.")
        
        return reference


# ============================================================================
# Report Forms
# ============================================================================

class DateRangeForm(forms.Form):
    """Form for date range filtering in reports"""
    
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "w-40"})
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "w-40"})
    )
    
    DEFAULT_DAYS = 30
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind(self)
        
        if not self.is_bound:
            self._set_default_dates()
    
    def _set_default_dates(self) -> None:
        """Set default date range to last 30 days"""
        today = timezone.localdate()
        self.initial["date_from"] = today - timezone.timedelta(days=self.DEFAULT_DAYS)
        self.initial["date_to"] = today
    
    def clean(self) -> Dict[str, Any]:
        cleaned_data = super().clean()
        date_from = cleaned_data.get("date_from")
        date_to = cleaned_data.get("date_to")
        
        if date_from and date_to and date_from > date_to:
            self.add_error("date_to", "End date must be after start date.")
        
        return cleaned_data
    
    def get_date_range(self) -> tuple:
        """Get validated date range as tuple"""
        return (self.cleaned_data.get("date_from"), self.cleaned_data.get("date_to"))


class SalesReportForm(DateRangeForm):
    """Form for sales report filtering"""
    
    hotel = forms.ModelChoiceField(
        queryset=None,
        required=False,
        empty_label="All Hotels",
        widget=forms.Select(attrs={"class": "w-48"})
    )
    status = forms.ChoiceField(
        choices=[("", "All Orders"), ("paid", "Completed (Paid)"), ("cancelled", "Cancelled")],
        required=False,
        widget=forms.Select(attrs={"class": "w-36"})
    )
    group_by = forms.ChoiceField(
        choices=[
            ("day", "Daily"),
            ("week", "Weekly"),
            ("month", "Monthly"),
            ("category", "By Category"),
            ("item", "By Item"),
        ],
        initial="day",
        widget=forms.Select(attrs={"class": "w-36"})
    )
    payment_method = forms.ChoiceField(
        choices=[("", "All Methods")] + list(RestaurantPayment.Method.choices),
        required=False,
        widget=forms.Select(attrs={"class": "w-44"})
    )
    
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and hasattr(user, 'hotels'):
            self.fields["hotel"].queryset = user.hotels.all()
        apply_tailwind(self)


class StockReportForm(DateRangeForm):
    """Form for stock/inventory reporting"""
    
    category = forms.ModelChoiceField(
        queryset=None,
        required=False,
        empty_label="All Categories",
        widget=forms.Select(attrs={"class": "w-44"})
    )
    low_stock_only = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={"class": TW_CHECKBOX})
    )
    sort_by = forms.ChoiceField(
        choices=[
            ("name", "By Name"),
            ("stock_qty", "By Stock Quantity"),
            ("sales_count", "By Sales Volume"),
        ],
        initial="name",
        widget=forms.Select(attrs={"class": "w-36"})
    )
    
    def __init__(self, *args, hotel=None, **kwargs):
        super().__init__(*args, **kwargs)
        if hotel:
            self.fields["category"].queryset = MenuCategory.objects.filter(
                hotel=hotel, is_active=True
            ).order_by("name")
        apply_tailwind(self)
        
        self.fields["low_stock_only"].help_text = "Show only items below reorder level"


# ============================================================================
# Quick Order Form (for fast POS)
# ============================================================================

class QuickOrderForm(forms.Form):
    """Quick order form for fast POS entry"""
    
    table = forms.ModelChoiceField(
        queryset=None,
        required=False,
        widget=forms.Select(attrs={"class": "w-48"})
    )
    customer_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Customer name", "class": "w-48"})
    )
    items = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={
            "rows": 4,
            "placeholder": "Enter items (one per line)\nFormat: Item Name, Quantity\nExample: Burger, 2\nFries, 1",
            "class": "w-full font-mono"
        })
    )
    
    def __init__(self, *args, hotel=None, **kwargs):
        super().__init__(*args, **kwargs)
        if hotel:
            self.fields["table"].queryset = Table.objects.filter(
                hotel=hotel, is_active=True
            ).select_related("area").order_by("area__name", "number")
        apply_tailwind(self)
    
    def clean_items(self) -> list:
        """Parse and validate items from text input"""
        items_data = self.cleaned_data.get("items", "")
        parsed_items = []
        errors = []
        
        for line_num, line in enumerate(items_data.strip().split("\n"), 1):
            line = line.strip()
            if not line:
                continue
            
            # Parse line: "Item Name, Quantity" or just "Item Name"
            parts = [p.strip() for p in line.split(",")]
            if not parts or not parts[0]:
                errors.append(f"Line {line_num}: Empty item name")
                continue
            
            item_name = parts[0]
            
            # Parse quantity (default to 1)
            try:
                quantity = int(parts[1]) if len(parts) > 1 and parts[1] else 1
                if quantity <= 0:
                    errors.append(f"Line {line_num}: Quantity must be positive (got {quantity})")
                    continue
                if quantity > 99:
                    errors.append(f"Line {line_num}: Quantity cannot exceed 99 (got {quantity})")
                    continue
            except ValueError:
                errors.append(f"Line {line_num}: Invalid quantity format '{parts[1]}'")
                continue
            
            parsed_items.append({
                "name": item_name,
                "quantity": quantity,
                "line": line_num,
            })
        
        if errors:
            raise ValidationError("\n".join(errors))
        
        if not parsed_items:
            raise ValidationError("At least one menu item is required.")
        
        return parsed_items