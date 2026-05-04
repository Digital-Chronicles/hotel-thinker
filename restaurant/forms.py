from __future__ import annotations

from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import (
    DiningArea, Table,
    MenuCategory, MenuItem,
    RestaurantOrder, RestaurantOrderItem,
    RestaurantPayment, RestaurantInvoice,
)

# Tailwind CSS classes
TW_INPUT = "w-full rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-200"
TW_SELECT = "w-full rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent appearance-none transition-all duration-200"
TW_TEXTAREA = "w-full rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-y min-h-[80px] transition-all duration-200"
TW_CHECKBOX = "w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-2 focus:ring-blue-500 focus:ring-offset-0 transition-all duration-200"
TW_FILE = "w-full rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 cursor-pointer transition-all duration-200"


def apply_tailwind(form: forms.Form):
    """Apply Tailwind CSS classes to all form fields"""
    for field_name, field in form.fields.items():
        widget = field.widget
        css = widget.attrs.get("class", "")
        
        if isinstance(widget, forms.CheckboxInput):
            widget.attrs["class"] = (css + " " + TW_CHECKBOX).strip()
        elif isinstance(widget, forms.Select):
            widget.attrs["class"] = (css + " " + TW_SELECT).strip()
        elif isinstance(widget, forms.Textarea):
            widget.attrs["class"] = (css + " " + TW_TEXTAREA).strip()
        elif isinstance(widget, forms.FileInput):
            widget.attrs["class"] = (css + " " + TW_FILE).strip()
        elif isinstance(widget, (forms.TextInput, forms.EmailInput, forms.NumberInput, forms.DateInput, forms.TimeInput, forms.PasswordInput)):
            widget.attrs["class"] = (css + " " + TW_INPUT).strip()
        else:
            widget.attrs["class"] = (css + " " + TW_INPUT).strip()


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


# ============================================================================
# Dining Area Forms
# ============================================================================

class DiningAreaForm(forms.ModelForm):
    """Form for creating and editing dining areas"""
    
    class Meta:
        model = DiningArea
        fields = ["name", "description", "is_active"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "Optional description of the dining area"}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind(self)
        
        # Add help texts
        self.fields["name"].help_text = "e.g., Main Hall, Terrace, VIP Room"
        self.fields["is_active"].help_text = "Inactive areas won't appear in table selection"
    
    def clean_name(self):
        name = self.cleaned_data.get("name", "").strip()
        if not name:
            raise forms.ValidationError("Dining area name is required.")
        return name


class DiningAreaFilterForm(BaseHotelFilterForm):
    """Form for filtering dining areas"""
    is_active = forms.ChoiceField(
        choices=[("", "All Status"), ("true", "Active"), ("false", "Inactive")],
        required=False,
        widget=forms.Select(attrs={"class": "w-36"})
    )
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Search areas...", "class": "w-64"})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind(self)


# ============================================================================
# Table Forms
# ============================================================================

class TableForm(forms.ModelForm):
    """Form for creating and editing restaurant tables"""
    
    class Meta:
        model = Table
        fields = ["area", "number", "seats", "is_active", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2, "placeholder": "Optional notes about the table (location, view, etc.)"}),
        }
    
    def __init__(self, *args, hotel=None, **kwargs):
        super().__init__(*args, **kwargs)
        if hotel is not None:
            self.fields["area"].queryset = DiningArea.objects.filter(hotel=hotel, is_active=True).order_by("name")
        apply_tailwind(self)
        
        # Add help texts
        self.fields["number"].help_text = "Table number or identifier"
        self.fields["seats"].help_text = "Maximum number of seats at this table"
        self.fields["is_active"].help_text = "Inactive tables won't be available for new orders"
    
    def clean_number(self):
        number = self.cleaned_data.get("number", "").strip()
        if not number:
            raise forms.ValidationError("Table number is required.")
        return number
    
    def clean_seats(self):
        seats = self.cleaned_data.get("seats")
        if seats and seats < 1:
            raise forms.ValidationError("Table must have at least 1 seat.")
        return seats


class TableFilterForm(BaseHotelFilterForm):
    """Form for filtering tables"""
    area = forms.ModelChoiceField(
        queryset=None,
        required=False,
        empty_label="All Areas",
        widget=forms.Select(attrs={"class": "w-44"})
    )
    is_active = forms.ChoiceField(
        choices=[("", "All Status"), ("true", "Active"), ("false", "Inactive")],
        required=False,
        widget=forms.Select(attrs={"class": "w-36"})
    )
    min_seats = forms.IntegerField(
        required=False,
        min_value=1,
        widget=forms.NumberInput(attrs={"placeholder": "Min seats", "class": "w-28"})
    )
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Search table number...", "class": "w-48"})
    )
    
    def __init__(self, *args, hotel=None, **kwargs):
        super().__init__(*args, **kwargs)
        if hotel:
            self.fields["area"].queryset = DiningArea.objects.filter(hotel=hotel, is_active=True)
        apply_tailwind(self)


# ============================================================================
# Menu Category Forms
# ============================================================================

class MenuCategoryForm(forms.ModelForm):
    """Form for creating and editing menu categories"""
    
    class Meta:
        model = MenuCategory
        fields = ["name", "description", "sort_order", "is_active"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2, "placeholder": "Optional category description"}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind(self)
        
        # Add help texts
        self.fields["name"].help_text = "e.g., Appetizers, Main Course, Desserts"
        self.fields["sort_order"].help_text = "Lower numbers appear first in the menu"
        self.fields["is_active"].help_text = "Inactive categories won't appear in item selection"
    
    def clean_name(self):
        name = self.cleaned_data.get("name", "").strip()
        if not name:
            raise forms.ValidationError("Category name is required.")
        return name


class MenuCategoryFilterForm(BaseHotelFilterForm):
    """Form for filtering menu categories"""
    is_active = forms.ChoiceField(
        choices=[("", "All Status"), ("true", "Active"), ("false", "Inactive")],
        required=False,
        widget=forms.Select(attrs={"class": "w-36"})
    )
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Search categories...", "class": "w-48"})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind(self)


# ============================================================================
# Menu Item Forms
# ============================================================================

class MenuItemForm(forms.ModelForm):
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
        super().__init__(*args, **kwargs)
        if hotel is not None:
            self.fields["category"].queryset = MenuCategory.objects.filter(hotel=hotel, is_active=True).order_by("sort_order", "name")
        apply_tailwind(self)
        
        # Add help texts
        self.fields["name"].help_text = "Name of the dish or beverage"
        self.fields["price"].help_text = "Selling price to customers"
        self.fields["cost_price"].help_text = "Cost price for profit calculation"
        self.fields["track_stock"].help_text = "Enable to automatically track inventory levels"
        self.fields["reorder_level"].help_text = "Stock level that triggers low stock alert"
        self.fields["preparation_time"].help_text = "Estimated time in minutes"
        self.fields["is_vegetarian"].help_text = "Suitable for vegetarians"
        self.fields["is_vegan"].help_text = "Suitable for vegans"
        self.fields["is_gluten_free"].help_text = "Gluten-free option"
        self.fields["is_spicy"].help_text = "Contains spicy ingredients"
        self.fields["is_featured"].help_text = "Featured on the menu"
        self.fields["is_recommended"].help_text = "Chef's recommendation"
    
    def clean(self):
        cleaned_data = super().clean()
        track_stock = cleaned_data.get("track_stock")
        stock_qty = cleaned_data.get("stock_qty", 0)
        reorder_level = cleaned_data.get("reorder_level", 0)
        
        if track_stock and stock_qty < 0:
            self.add_error("stock_qty", "Stock quantity cannot be negative when tracking is enabled.")
        
        if track_stock and reorder_level < 0:
            self.add_error("reorder_level", "Reorder level cannot be negative.")
        
        price = cleaned_data.get("price")
        if price and price < 0:
            self.add_error("price", "Price cannot be negative.")
        
        return cleaned_data


class MenuItemFilterForm(BaseHotelFilterForm):
    """Form for filtering menu items"""
    category = forms.ModelChoiceField(
        queryset=None,
        required=False,
        empty_label="All Categories",
        widget=forms.Select(attrs={"class": "w-44"})
    )
    is_active = forms.ChoiceField(
        choices=[("", "All Status"), ("true", "Active"), ("false", "Inactive")],
        required=False,
        widget=forms.Select(attrs={"class": "w-36"})
    )
    low_stock = forms.ChoiceField(
        choices=[("", "All Stock"), ("true", "Low Stock"), ("out", "Out of Stock")],
        required=False,
        widget=forms.Select(attrs={"class": "w-36"})
    )
    dietary = forms.ChoiceField(
        choices=[("", "All"), ("vegetarian", "Vegetarian"), ("vegan", "Vegan"), ("gluten_free", "Gluten Free")],
        required=False,
        widget=forms.Select(attrs={"class": "w-40"})
    )
    featured = forms.ChoiceField(
        choices=[("", "All"), ("featured", "Featured"), ("recommended", "Recommended")],
        required=False,
        widget=forms.Select(attrs={"class": "w-40"})
    )
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Search items...", "class": "w-48"})
    )
    
    def __init__(self, *args, hotel=None, **kwargs):
        super().__init__(*args, **kwargs)
        if hotel:
            self.fields["category"].queryset = MenuCategory.objects.filter(hotel=hotel, is_active=True)
        apply_tailwind(self)


# ============================================================================
# Order Forms
# ============================================================================

class RestaurantOrderForm(forms.ModelForm):
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
            "status": forms.Select(attrs={"class": TW_SELECT}),
        }
    
    def __init__(self, *args, hotel=None, **kwargs):
        super().__init__(*args, **kwargs)
        if hotel is not None:
            # Filter tables by hotel
            self.fields["table"].queryset = Table.objects.filter(
                hotel=hotel, is_active=True
            ).select_related("area").order_by("area__name", "number")
            self.fields["table"].label_from_instance = lambda obj: f"Table {obj.number} - {obj.area.name if obj.area else 'No area'} ({obj.seats} seats)"
            
            # Filter bookings for room charge (only active/checked-in bookings)
            from bookings.models import Booking
            self.fields["booking"].queryset = Booking.objects.filter(
                hotel=hotel, 
                status__in=['confirmed', 'checked_in']
            ).select_related('guest').order_by('-created_at')
            self.fields["booking"].label_from_instance = lambda obj: f"{obj.booking_number} - {obj.guest.full_name if obj.guest else 'Guest'}"
        
        apply_tailwind(self)
        
        # Set default values
        self.fields["status"].initial = RestaurantOrder.Status.OPEN
        self.fields["discount"].initial = Decimal("0.00")
        self.fields["discount_percent"].initial = Decimal("0.00")
        self.fields["tax"].initial = Decimal("0.00")
        self.fields["tax_percent"].initial = Decimal("0.00")
        self.fields["service_charge"].initial = Decimal("0.00")
        self.fields["room_charge"].initial = False
        
        # Add help texts
        self.fields["table"].help_text = "Select table for dine-in orders (leave empty for walk-ins)"
        self.fields["booking"].help_text = "Link to registered hotel guest"
        self.fields["room_charge"].help_text = "Charge to guest's room account (only available when guest is selected)"
        self.fields["status"].help_text = "Open status allows adding items; moves to Kitchen automatically when items are added"
        self.fields["discount_percent"].help_text = "Apply percentage discount (overrides fixed discount)"
        self.fields["tax_percent"].help_text = "Apply percentage tax (overrides fixed tax)"
        self.fields["kitchen_notes"].help_text = "Internal notes visible only to kitchen staff"
    
    def clean(self):
        cleaned_data = super().clean()
        discount = cleaned_data.get("discount", 0)
        discount_percent = cleaned_data.get("discount_percent", 0)
        tax = cleaned_data.get("tax", 0)
        tax_percent = cleaned_data.get("tax_percent", 0)
        booking = cleaned_data.get("booking")
        room_charge = cleaned_data.get("room_charge", False)
        
        if discount < 0:
            self.add_error("discount", "Discount cannot be negative.")
        
        if discount_percent < 0 or discount_percent > 100:
            self.add_error("discount_percent", "Discount percentage must be between 0 and 100.")
        
        if tax < 0:
            self.add_error("tax", "Tax cannot be negative.")
        
        if tax_percent < 0 or tax_percent > 100:
            self.add_error("tax_percent", "Tax percentage must be between 0 and 100.")
        
        if discount > 0 and discount_percent > 0:
            self.add_error(None, "Please use either fixed discount OR percentage discount, not both.")
        
        if tax > 0 and tax_percent > 0:
            self.add_error(None, "Please use either fixed tax OR percentage tax, not both.")
        
        if room_charge and not booking:
            self.add_error("room_charge", "Room charge requires selecting a hotel guest first.")
        
        return cleaned_data


class RestaurantOrderItemForm(forms.ModelForm):
    """Form for adding/editing order items"""
    
    class Meta:
        model = RestaurantOrderItem
        fields = ["item", "qty", "note"]
        widgets = {
            "qty": forms.NumberInput(attrs={"min": "1", "step": "1", "value": "1", "class": "w-24"}),
            "note": forms.TextInput(attrs={"placeholder": "Special instructions (e.g., no onions, extra spicy)", "class": "w-full"}),
        }
    
    def __init__(self, *args, hotel=None, order=None, **kwargs):
        super().__init__(*args, **kwargs)
        if hotel is not None:
            self.fields["item"].queryset = MenuItem.objects.filter(
                hotel=hotel, is_active=True
            ).select_related("category").order_by("category__sort_order", "name")
            self.fields["item"].label_from_instance = lambda obj: f"{obj.name} - ${obj.price}"
        
        self.order = order
        apply_tailwind(self)
        
        # Add help text
        self.fields["item"].help_text = "Select a menu item"
        self.fields["qty"].help_text = "Quantity to order"
        self.fields["note"].help_text = "Any special requests for this specific item"
    
    def clean_qty(self):
        qty = self.cleaned_data.get("qty") or 0
        if qty <= 0:
            raise forms.ValidationError("Quantity must be at least 1.")
        return qty
    
    def clean_item(self):
        item = self.cleaned_data.get("item")
        if self.order and item and self.order.items.filter(item=item).exists():
            raise forms.ValidationError("This item is already in the order. Please update the quantity instead.")
        return item


# Create inline formset factory
from django.forms import inlineformset_factory

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
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind(self)
        
        # Add status descriptions
        status_descriptions = {
            RestaurantOrder.Status.OPEN: "Order is open, items can be added",
            RestaurantOrder.Status.KITCHEN: "Order sent to kitchen for preparation",
            RestaurantOrder.Status.SERVED: "Food has been served to customer",
            RestaurantOrder.Status.BILLED: "Invoice generated, awaiting payment",
            RestaurantOrder.Status.PAID: "Payment received, order complete",
            RestaurantOrder.Status.CANCELLED: "Order cancelled",
        }
        
        # Add help text to status field
        self.fields["status"].help_text = "Current order status"
    
    def clean_status(self):
        status = self.cleaned_data.get("status")
        if status not in dict(RestaurantOrder.Status.choices):
            raise forms.ValidationError("Invalid status selected.")
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
    
    def __init__(self, *args, order=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.order = order
        apply_tailwind(self)
        
        if order is not None and not self.is_bound:
            self.initial["amount"] = order.total
        
        # Add help texts based on method
        self.fields["method"].help_text = "Select payment method"
        self.fields["reference"].help_text = "Transaction ID or reference number (required for mobile/card payments)"
        self.fields["amount"].help_text = f"Total amount due: {order.total if order else '0.00'}"
    
    def clean(self):
        cleaned_data = super().clean()
        
        if self.order is None:
            return cleaned_data
        
        amount = cleaned_data.get("amount")
        if amount is None:
            return cleaned_data
        
        # Validate amount matches order total
        if amount != self.order.total:
            self.add_error("amount", f"Payment amount must equal order total ({self.order.total}).")
        
        method = cleaned_data.get("method")
        reference = cleaned_data.get("reference")
        
        # Require reference for mobile money and card payments
        if method in [RestaurantPayment.Method.MOMO, RestaurantPayment.Method.CARD]:
            if not reference:
                self.add_error("reference", f"Transaction reference is required for {dict(RestaurantPayment.Method.choices).get(method, method)} payments.")
        
        return cleaned_data


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
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind(self)
        
        # Set default dates to last 30 days if not provided
        if not self.is_bound:
            today = timezone.localdate()
            self.initial["date_from"] = today - timezone.timedelta(days=30)
            self.initial["date_to"] = today
    
    def clean(self):
        cleaned_data = super().clean()
        date_from = cleaned_data.get("date_from")
        date_to = cleaned_data.get("date_to")
        
        if date_from and date_to and date_from > date_to:
            self.add_error("date_to", "End date must be after start date.")
        
        return cleaned_data


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
            self.fields["category"].queryset = MenuCategory.objects.filter(hotel=hotel, is_active=True)
        apply_tailwind(self)
        
        # Add help text
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
            self.fields["table"].queryset = Table.objects.filter(hotel=hotel, is_active=True)
        apply_tailwind(self)
    
    def clean_items(self):
        items_data = self.cleaned_data.get("items", "")
        parsed_items = []
        
        for line in items_data.strip().split("\n"):
            if not line.strip():
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 1:
                raise forms.ValidationError(f"Invalid line format: {line}. Expected 'Item Name, Quantity'")
            
            item_name = parts[0]
            quantity = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
            
            parsed_items.append({
                "name": item_name,
                "quantity": quantity
            })
        
        if not parsed_items:
            raise forms.ValidationError("At least one menu item is required.")
        
        return parsed_items