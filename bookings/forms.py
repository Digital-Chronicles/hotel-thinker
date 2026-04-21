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
        fields = ['full_name', 'phone', 'email', 'id_number']
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
        }
    
    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if phone:
            import re
            clean_phone = re.sub(r'\D', '', phone)
            if len(clean_phone) < 9:
                raise ValidationError(_("Phone number must be at least 9 digits."))
        return phone


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
            'special_requests': forms.Textarea(attrs={'rows': 2, 'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm'}),
            'guest_notes': forms.Textarea(attrs={'rows': 2, 'class': 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm'}),
        }

    def __init__(self, *args, **kwargs):
        self.hotel = kwargs.pop('hotel', None)
        super().__init__(*args, **kwargs)
        
        if self.hotel:
            # Filter guests by hotel
            self.fields['guest'].queryset = Guest.objects.filter(hotel=self.hotel).order_by('full_name')
            # Filter rooms by hotel
            self.fields['room'].queryset = Room.objects.filter(hotel=self.hotel, is_active=True).select_related('room_type')
            
            # Add help text and styling to all fields
            for field_name, field in self.fields.items():
                if 'class' not in field.widget.attrs:
                    field.widget.attrs['class'] = 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-300'
    
    def clean(self):
        cleaned_data = super().clean()
        check_in = cleaned_data.get('check_in')
        check_out = cleaned_data.get('check_out')
        room = cleaned_data.get('room')
        
        if check_in and check_out and check_out <= check_in:
            self.add_error('check_out', _("Check-out must be after check-in."))
        
        if room and check_in and check_out:
            # Check for overlapping bookings
            overlapping = Booking.objects.filter(
                room=room,
                status__in=[Booking.Status.RESERVED, Booking.Status.CONFIRMED, Booking.Status.CHECKED_IN],
                check_in__lt=check_out,
                check_out__gt=check_in,
            )
            if self.instance and self.instance.pk:
                overlapping = overlapping.exclude(pk=self.instance.pk)
            
            if overlapping.exists():
                self.add_error('room', _("Room is not available for the selected dates."))
        
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
        }

    def __init__(self, *args, **kwargs):
        self.hotel = kwargs.pop('hotel', None)
        super().__init__(*args, **kwargs)
        
        if self.hotel:
            self.fields['guest'].queryset = Guest.objects.filter(hotel=self.hotel).order_by('full_name')
            self.fields['room'].queryset = Room.objects.filter(hotel=self.hotel, is_active=True).select_related('room_type')
        
        for field_name, field in self.fields.items():
            if 'class' not in field.widget.attrs:
                field.widget.attrs['class'] = 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-300'
    
    def clean(self):
        cleaned_data = super().clean()
        check_in = cleaned_data.get('check_in')
        check_out = cleaned_data.get('check_out')
        room = cleaned_data.get('room')
        
        if check_in and check_out and check_out <= check_in:
            self.add_error('check_out', _("Check-out must be after check-in."))
        
        if room and check_in and check_out:
            overlapping = Booking.objects.filter(
                room=room,
                status__in=[Booking.Status.RESERVED, Booking.Status.CONFIRMED, Booking.Status.CHECKED_IN],
                check_in__lt=check_out,
                check_out__gt=check_in,
            ).exclude(pk=self.instance.pk if self.instance else None)
            
            if overlapping.exists():
                self.add_error('room', _("Room is not available for the selected dates."))
        
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
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from finance.models import Payment
        self.fields['method'].choices = Payment.Method.choices
    
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
    
    def clean(self):
        cleaned_data = super().clean()
        date_from = cleaned_data.get('date_from')
        date_to = cleaned_data.get('date_to')
        
        if date_from and date_to and date_to < date_from:
            self.add_error('date_to', _("End date must be after start date."))
        
        return cleaned_data