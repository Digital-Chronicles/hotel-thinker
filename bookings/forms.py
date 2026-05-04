# bookings/forms.py
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import Booking, Guest, AdditionalCharge
from rooms.models import Room, RoomType


# -----------------------------------------------------------------------------
# Guest Forms
# -----------------------------------------------------------------------------

class GuestFullForm(forms.ModelForm):
    """Complete guest form with all fields"""
    
    class Meta:
        model = Guest
        fields = [
            'full_name', 'preferred_name', 'guest_type',
            'phone', 'alternative_phone', 'email',
            'id_type', 'id_number', 'id_issue_date', 'id_expiry_date', 'id_scan',
            'nationality', 'language',
            'address', 'city', 'country', 'postal_code',
            'company_name', 'company_vat', 'company_address',
            'special_requests', 'dietary_restrictions', 'room_preferences',
            'is_vip', 'marketing_consent', 'newsletter_subscribed',
        ]
        widgets = {
            'id_issue_date': forms.DateInput(attrs={'type': 'date', 'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm'}),
            'id_expiry_date': forms.DateInput(attrs={'type': 'date', 'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm'}),
            'special_requests': forms.Textarea(attrs={'rows': 3, 'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm'}),
            'dietary_restrictions': forms.Textarea(attrs={'rows': 2, 'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm'}),
            'room_preferences': forms.Textarea(attrs={'rows': 2, 'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm'}),
            'company_address': forms.Textarea(attrs={'rows': 2, 'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm'}),
            'address': forms.Textarea(attrs={'rows': 2, 'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add styling to all fields
        for field_name, field in self.fields.items():
            if 'class' not in field.widget.attrs:
                field.widget.attrs['class'] = 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-300'

    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if phone:
            # Remove any non-digit characters for validation
            import re
            clean_phone = re.sub(r'\D', '', phone)
            if len(clean_phone) < 9:
                raise ValidationError(_("Phone number must be at least 9 digits."))
        return phone


class GuestQuickCreateForm(forms.ModelForm):
    """Minimal guest form for quick creation during booking"""
    
    class Meta:
        model = Guest
        fields = ['full_name', 'phone', 'email', 'id_number', 'guest_type']
        widgets = {
            'full_name': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-300',
                'placeholder': 'John Doe'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-300',
                'placeholder': '+256 XXX XXX XXX'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-300',
                'placeholder': 'guest@example.com'
            }),
            'id_number': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-300',
                'placeholder': 'ID/Passport Number'
            }),
            'guest_type': forms.Select(attrs={
                'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-300'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['guest_type'].initial = 'individual'
    
    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if phone:
            import re
            clean_phone = re.sub(r'\D', '', phone)
            if len(clean_phone) < 9:
                raise ValidationError(_("Phone number must be at least 9 digits."))
        return phone
    
    def clean_full_name(self):
        full_name = self.cleaned_data.get('full_name', '').strip()
        if not full_name:
            raise ValidationError(_("Full name is required."))
        return full_name


# -----------------------------------------------------------------------------
# Booking Forms
# -----------------------------------------------------------------------------
class BookingForm(forms.ModelForm):
    """Form for creating new bookings"""
    
    class Meta:
        model = Booking
        fields = [
            'guest', 'room', 'check_in', 'check_out',
            'adults', 'children', 'infants',
            'source', 'source_reference',
            'special_requests', 'guest_notes',
            'discount', 'discount_type', 'tax_rate',
        ]
        widgets = {
            'check_in': forms.DateInput(attrs={'type': 'date', 'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm'}),
            'check_out': forms.DateInput(attrs={'type': 'date', 'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm'}),
            'special_requests': forms.Textarea(attrs={'rows': 2, 'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm', 'placeholder': 'Any special requests from the guest'}),
            'guest_notes': forms.Textarea(attrs={'rows': 2, 'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm', 'placeholder': 'Notes visible to front desk staff'}),
            'source_reference': forms.TextInput(attrs={'placeholder': 'Booking reference from external source'}),
        }

    def __init__(self, *args, **kwargs):
        self.hotel = kwargs.pop('hotel', None)
        super().__init__(*args, **kwargs)
        
        # Make room required and show error if not selected
        self.fields['room'].required = True
        self.fields['guest'].required = True
        self.fields['check_in'].required = True
        self.fields['check_out'].required = True
        self.fields['adults'].required = True
        
        if self.hotel:
            # Filter guests by hotel
            self.fields['guest'].queryset = Guest.objects.filter(hotel=self.hotel).order_by('full_name')
            self.fields['guest'].empty_label = "Select a guest"
            
            # Filter rooms by hotel and ensure they are active
            rooms = Room.objects.filter(
                hotel=self.hotel, 
                is_active=True
            ).select_related('room_type')
            
            self.fields['room'].queryset = rooms
            self.fields['room'].empty_label = "Select a room"
            
            # Set default values
            self.fields['adults'].initial = 1
            self.fields['children'].initial = 0
            self.fields['infants'].initial = 0
            self.fields['discount'].initial = 0
            self.fields['discount_type'].initial = 'fixed'
            self.fields['tax_rate'].initial = 0
            
            # Make discount and tax optional
            self.fields['discount'].required = False
            self.fields['discount_type'].required = False
            self.fields['tax_rate'].required = False
            
            # Add help texts
            self.fields['source'].help_text = "How did the guest make this booking?"
            self.fields['discount'].help_text = "Enter discount amount (fixed amount only for now)"
            self.fields['tax_rate'].help_text = "Enter tax percentage (e.g., 18 for 18%)"
        
        # Add styling to all fields
        for field_name, field in self.fields.items():
            if 'class' not in field.widget.attrs:
                field.widget.attrs['class'] = 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-300'
            
            # Add required star for required fields
            if field.required:
                existing_label = field.label or field_name.replace('_', ' ').title()
                field.label = f"{existing_label} *"
    
    def clean_room(self):
        room = self.cleaned_data.get('room')
        if not room:
            raise ValidationError(_("Room is required. Please select a room."))
        return room
    
    def clean_guest(self):
        guest = self.cleaned_data.get('guest')
        if not guest:
            raise ValidationError(_("Guest is required. Please select a guest or create one."))
        return guest
    
    def clean_check_in(self):
        check_in = self.cleaned_data.get('check_in')
        if not check_in:
            raise ValidationError(_("Check-in date is required."))
        if check_in and check_in < timezone.now().date():
            raise ValidationError(_("Check-in date cannot be in the past."))
        return check_in
    
    def clean_check_out(self):
        check_out = self.cleaned_data.get('check_out')
        if not check_out:
            raise ValidationError(_("Check-out date is required."))
        return check_out
    
    def clean_discount(self):
        discount = self.cleaned_data.get('discount')
        if discount is None:
            return 0
        if discount < 0:
            raise ValidationError(_("Discount cannot be negative."))
        return discount
    
    def clean_tax_rate(self):
        tax_rate = self.cleaned_data.get('tax_rate')
        if tax_rate is None:
            return 0
        if tax_rate < 0 or tax_rate > 100:
            raise ValidationError(_("Tax rate must be between 0 and 100."))
        return tax_rate
    
    def clean(self):
        cleaned_data = super().clean()
        check_in = cleaned_data.get('check_in')
        check_out = cleaned_data.get('check_out')
        room = cleaned_data.get('room')
        
        # Validate check-out is after check-in
        if check_in and check_out:
            if check_out <= check_in:
                self.add_error('check_out', _("Check-out must be after check-in."))
                return cleaned_data
        
        # Validate room availability
        if room and check_in and check_out:
            overlapping = Booking.objects.filter(
                room=room,
                status__in=[Booking.Status.RESERVED, Booking.Status.CONFIRMED, Booking.Status.CHECKED_IN],
                check_in__lt=check_out,
                check_out__gt=check_in,
            )
            
            # If this is an existing booking, exclude it from the check
            if self.instance and self.instance.pk:
                overlapping = overlapping.exclude(pk=self.instance.pk)
            
            if overlapping.exists():
                self.add_error('room', _("Room is not available for the selected dates."))
        
        # Ensure adults count is at least 1
        adults = cleaned_data.get('adults')
        if adults is not None and adults < 1:
            self.add_error('adults', _("There must be at least 1 adult."))
        
        return cleaned_data


class BookingUpdateForm(forms.ModelForm):
    """Form for updating existing bookings"""
    
    class Meta:
        model = Booking
        fields = [
            'guest', 'room', 'check_in', 'check_out',
            'adults', 'children', 'infants',
            'status', 'payment_status',
            'source', 'source_reference',
            'special_requests', 'guest_notes', 'internal_notes',
            'nightly_rate', 'extra_bed_charge',
            'discount', 'discount_type', 'tax_rate',
        ]
        widgets = {
            'check_in': forms.DateInput(attrs={'type': 'date', 'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm'}),
            'check_out': forms.DateInput(attrs={'type': 'date', 'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm'}),
            'special_requests': forms.Textarea(attrs={'rows': 2, 'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm'}),
            'guest_notes': forms.Textarea(attrs={'rows': 2, 'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm'}),
            'internal_notes': forms.Textarea(attrs={'rows': 2, 'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm'}),
            'nightly_rate': forms.NumberInput(attrs={'step': '0.01', 'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm'}),
            'extra_bed_charge': forms.NumberInput(attrs={'step': '0.01', 'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm'}),
        }

    def __init__(self, *args, **kwargs):
        self.hotel = kwargs.pop('hotel', None)
        super().__init__(*args, **kwargs)
        
        # Make discount and tax fields optional
        self.fields['discount'].required = False
        self.fields['discount_type'].required = False
        self.fields['tax_rate'].required = False
        
        if self.hotel:
            self.fields['guest'].queryset = Guest.objects.filter(hotel=self.hotel).order_by('full_name')
            self.fields['room'].queryset = Room.objects.filter(hotel=self.hotel, is_active=True).select_related('room_type')
        
        # Add styling to all fields
        for field_name, field in self.fields.items():
            if 'class' not in field.widget.attrs:
                field.widget.attrs['class'] = 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-300'
    
    def clean_discount(self):
        discount = self.cleaned_data.get('discount')
        if discount is None:
            return 0
        if discount < 0:
            raise ValidationError(_("Discount cannot be negative."))
        return discount
    
    def clean_tax_rate(self):
        tax_rate = self.cleaned_data.get('tax_rate')
        if tax_rate is None:
            return 0
        if tax_rate < 0 or tax_rate > 100:
            raise ValidationError(_("Tax rate must be between 0 and 100."))
        return tax_rate
    
    def clean(self):
        cleaned_data = super().clean()
        check_in = cleaned_data.get('check_in')
        check_out = cleaned_data.get('check_out')
        room = cleaned_data.get('room')
        
        if check_in and check_out and check_out <= check_in:
            self.add_error('check_out', _("Check-out must be after check-in."))
            return cleaned_data
        
        if room and check_in and check_out:
            overlapping = Booking.objects.filter(
                room=room,
                status__in=[Booking.Status.RESERVED, Booking.Status.CONFIRMED, Booking.Status.CHECKED_IN],
                check_in__lt=check_out,
                check_out__gt=check_in,
            ).exclude(pk=self.instance.pk if self.instance else None)
            
            if overlapping.exists():
                self.add_error('room', _("Room is not available for the selected dates."))
        
        # Set default discount_type if not provided
        if not cleaned_data.get('discount_type'):
            cleaned_data['discount_type'] = 'fixed'
        
        return cleaned_data
    

# -----------------------------------------------------------------------------
# Payment Form
# -----------------------------------------------------------------------------

class BookingPaymentForm(forms.Form):
    """Form for recording payments against a booking"""
    
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0.01,
        widget=forms.NumberInput(attrs={
            'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-300',
            'placeholder': '0.00',
            'step': '0.01'
        })
    )
    method = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={
            'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-300'
        })
    )
    reference = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-300',
            'placeholder': 'Transaction/Cheque reference (optional)'
        })
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 2,
            'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-300',
            'placeholder': 'Payment notes (optional)'
        })
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from finance.models import Payment
        self.fields['method'].choices = Payment.Method.choices
        self.fields['method'].initial = Payment.Method.CASH
    
    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount and amount <= 0:
            raise ValidationError(_("Payment amount must be greater than zero."))
        return amount


# -----------------------------------------------------------------------------
# Additional Charge Form
# -----------------------------------------------------------------------------

class AdditionalChargeForm(forms.ModelForm):
    """Form for adding additional charges to a booking"""
    
    class Meta:
        model = AdditionalCharge
        fields = ['category', 'description', 'quantity', 'unit_price']
        widgets = {
            'category': forms.Select(attrs={
                'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-300'
            }),
            'description': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-300',
                'placeholder': 'e.g., Mini Bar items, Laundry service...'
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-300',
                'min': 1,
                'value': 1
            }),
            'unit_price': forms.NumberInput(attrs={
                'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-300',
                'placeholder': '0.00',
                'step': '0.01'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-300'
    
    def clean_quantity(self):
        quantity = self.cleaned_data.get('quantity')
        if quantity and quantity < 1:
            raise ValidationError(_("Quantity must be at least 1."))
        return quantity
    
    def clean_unit_price(self):
        unit_price = self.cleaned_data.get('unit_price')
        if unit_price and unit_price <= 0:
            raise ValidationError(_("Unit price must be greater than zero."))
        return unit_price


# -----------------------------------------------------------------------------
# Report Forms
# -----------------------------------------------------------------------------

class BookingReportForm(forms.Form):
    """Form for generating booking reports"""
    
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-300'
        })
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-300'
        })
    )
    status = forms.ChoiceField(
        required=False,
        choices=[('', 'All')] + list(Booking.Status.choices),
        widget=forms.Select(attrs={
            'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-300'
        })
    )
    payment_status = forms.ChoiceField(
        required=False,
        choices=[('', 'All')] + list(Booking.PaymentStatus.choices),
        widget=forms.Select(attrs={
            'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-300'
        })
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-300'
    
    def clean(self):
        cleaned_data = super().clean()
        date_from = cleaned_data.get('date_from')
        date_to = cleaned_data.get('date_to')
        
        if date_from and date_to and date_to < date_from:
            self.add_error('date_to', _("End date must be after start date."))
        
        return cleaned_data