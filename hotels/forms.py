# hotels/forms.py
from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _
from .models import (
    Hotel, HotelChain, HotelCategory, HotelSetting, 
    HotelImage, HotelDocument, HotelReview, 
    HotelContactPerson, HotelBankDetail, HotelAmenity,
    HotelAmenityMapping, HotelExperience, HotelExperienceImage
)


# Tailwind CSS classes
TW_INPUT = (
    "w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm "
    "placeholder-gray-400 shadow-sm "
    "focus:outline-none focus:ring-2 focus:ring-blue-600 focus:border-blue-600"
)
TW_SELECT = TW_INPUT
TW_TEXTAREA = (
    "w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm "
    "placeholder-gray-400 shadow-sm "
    "focus:outline-none focus:ring-2 focus:ring-blue-600 focus:border-blue-600"
)
TW_CHECKBOX = "h-4 w-4 rounded border-gray-300 text-blue-800 focus:ring-2 focus:ring-blue-600"
TW_FILE = (
    "block w-full text-sm text-gray-700 "
    "file:mr-4 file:py-2 file:px-4 file:rounded-lg "
    "file:border-0 file:text-sm file:font-semibold "
    "file:bg-gray-100 file:text-gray-800 hover:file:bg-gray-200"
)
TW_RADIO = "h-4 w-4 border-gray-300 text-blue-800 focus:ring-2 focus:ring-blue-600"

COMMON_CURRENCIES = [
    ("UGX", "UGX - Ugandan Shilling"),
    ("USD", "USD - United States Dollar"),
    ("EUR", "EUR - Euro"),
    ("GBP", "GBP - British Pound"),
    ("KES", "KES - Kenyan Shilling"),
    ("TZS", "TZS - Tanzanian Shilling"),
    ("RWF", "RWF - Rwandan Franc"),
    ("CDF", "CDF - Congolese Franc"),
]

CURRENCY_SYMBOLS = {
    "UGX": "UGX",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "KES": "KSh",
    "TZS": "TSh",
    "RWF": "FRw",
    "CDF": "FC",
}


def apply_tailwind(form: forms.Form) -> None:
    """Apply Tailwind CSS classes to all form fields"""
    for _, field in form.fields.items():
        w = field.widget
        if isinstance(w, forms.HiddenInput):
            continue
        if isinstance(w, forms.CheckboxInput):
            w.attrs.setdefault("class", TW_CHECKBOX)
            continue
        if isinstance(w, forms.RadioSelect):
            w.attrs.setdefault("class", TW_RADIO)
            continue
        if isinstance(w, forms.ClearableFileInput):
            w.attrs.setdefault("class", TW_FILE)
            continue
        if isinstance(w, forms.Textarea):
            w.attrs.setdefault("class", TW_TEXTAREA)
            continue
        if isinstance(w, (forms.Select, forms.SelectMultiple)):
            w.attrs.setdefault("class", TW_SELECT)
            continue
        w.attrs.setdefault("class", TW_INPUT)


# ==================== HOTEL CHAIN FORM ====================
class HotelChainForm(forms.ModelForm):
    class Meta:
        model = HotelChain
        fields = [
            'name', 'logo', 'website', 'description', 
            'headquarters_address', 'is_active'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'headquarters_address': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind(self)


# ==================== HOTEL CATEGORY FORM ====================
class HotelCategoryForm(forms.ModelForm):
    class Meta:
        model = HotelCategory
        fields = ['name', 'description', 'star_rating_min', 'star_rating_max', 'icon']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind(self)
    
    def clean(self):
        cleaned_data = super().clean()
        star_min = cleaned_data.get('star_rating_min')
        star_max = cleaned_data.get('star_rating_max')
        
        if star_min is not None and star_max is not None:
            if star_min > star_max:
                self.add_error('star_rating_min', _('Minimum rating cannot exceed maximum rating'))
        
        return cleaned_data


# ==================== HOTEL MAIN FORM ====================
class HotelForm(forms.ModelForm):
    class Meta:
        model = Hotel
        fields = [
            # Basic Information
            'name', 'hotel_chain', 'category',
            
            # Contact
            'email', 'phone', 'phone_alt', 'whatsapp', 'website',
            
            # Address
            'address_line1', 'address_line2', 'city', 'state', 
            'postal_code', 'country',
            
            # Geographic Coordinates
            'latitude', 'longitude',
            
            # Business details
            'tax_number', 'business_registration', 'year_established',
            'number_of_employees',
            
            # Hotel Details
            'star_rating', 'total_rooms', 'total_floors',
            'default_currency', 'default_currency_symbol', 'supported_currencies',
            
            # Descriptions
            'short_description', 'description', 'meta_description', 'meta_keywords',
            
            # Branding
            'logo', 'logo_light', 'favicon', 'cover_image',
            'brand_color_primary', 'brand_color_secondary',
            
            # Status
            'is_active', 'is_featured', 'is_verified', 'is_published',
            
            # Social Media
            'facebook_url', 'instagram_url', 'twitter_url', 
            'linkedin_url', 'youtube_url', 'tripadvisor_url',
            
            # Business Hours
            'check_in_time', 'check_out_time', 
            'reception_open_time', 'reception_close_time',
            
            # Policies
            'cancellation_policy', 'payment_policy', 'house_rules',
            'child_policy', 'pet_policy',
        ]
        widgets = {
            'short_description': forms.Textarea(attrs={'rows': 2}),
            'description': forms.Textarea(attrs={'rows': 6}),
            'meta_description': forms.Textarea(attrs={'rows': 2}),
            'cancellation_policy': forms.Textarea(attrs={'rows': 4}),
            'payment_policy': forms.Textarea(attrs={'rows': 3}),
            'house_rules': forms.Textarea(attrs={'rows': 4}),
            'child_policy': forms.Textarea(attrs={'rows': 2}),
            'pet_policy': forms.Textarea(attrs={'rows': 2}),
            'supported_currencies': forms.CheckboxSelectMultiple(choices=COMMON_CURRENCIES),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind(self)

        if 'default_currency' in self.fields:
            self.fields['default_currency'].widget = forms.Select(choices=COMMON_CURRENCIES, attrs={'class': TW_SELECT})
        if 'default_currency_symbol' in self.fields:
            self.fields['default_currency_symbol'].widget.attrs.setdefault('placeholder', 'UGX')
        if 'supported_currencies' in self.fields:
            self.fields['supported_currencies'].required = False
            self.fields['supported_currencies'].help_text = _('Select all currencies this hotel accepts. The default currency is added automatically.')
            if self.instance and self.instance.pk and self.instance.supported_currencies:
                self.initial['supported_currencies'] = self.instance.supported_currencies
            else:
                self.initial.setdefault('supported_currencies', ['UGX'])
        
        # Add placeholders and input types
        if 'latitude' in self.fields:
            self.fields['latitude'].widget.attrs.update({
                'step': 'any',
                'placeholder': 'e.g., 40.7128'
            })
        
        if 'longitude' in self.fields:
            self.fields['longitude'].widget.attrs.update({
                'step': 'any',
                'placeholder': 'e.g., -74.0060'
            })
        
        if 'star_rating' in self.fields:
            self.fields['star_rating'].widget.attrs.update({
                'step': '0.5',
                'min': '0',
                'max': '5'
            })
        
        # Time pickers
        time_fields = ['check_in_time', 'check_out_time', 'reception_open_time', 'reception_close_time']
        for field_name in time_fields:
            if field_name in self.fields:
                self.fields[field_name].widget = forms.TimeInput(
                    attrs={'type': 'time', 'class': TW_INPUT}
                )

    def clean_supported_currencies(self):
        values = self.cleaned_data.get('supported_currencies') or []
        cleaned = []
        for code in values:
            code = str(code or '').strip().upper()[:3]
            if len(code) == 3 and code not in cleaned:
                cleaned.append(code)
        return cleaned

    def clean(self):
        cleaned = super().clean()
        default = (cleaned.get('default_currency') or 'UGX').strip().upper()[:3]
        currencies = cleaned.get('supported_currencies') or []
        if default and default not in currencies:
            currencies.insert(0, default)
        cleaned['default_currency'] = default
        cleaned['supported_currencies'] = currencies
        if not cleaned.get('default_currency_symbol'):
            cleaned['default_currency_symbol'] = CURRENCY_SYMBOLS.get(default, default)
        return cleaned


# ==================== HOTEL SETTING FORM ====================
class HotelSettingForm(forms.ModelForm):
    class Meta:
        model = HotelSetting
        fields = [
            # About
            "short_description",
            "about_description",

            # Contact
            "address",
            "phone_number",
            "email",
            "emergency_contact",

            # Branding
            "brand_color",
            "logo",
            "logo_light",
            "favicon",

            # Business hours
            "check_in_time",
            "check_out_time",
            "reception_open_time",
            "reception_close_time",

            # Policies
            "cancellation_policy",
            "payment_policy",
            "house_rules",

            # Tax & currency
            "default_tax_rate",
            "tax_number",
            "currency",
            "currency_symbol",

            # Social media
            "instagram",
            "twitter",
            "facebook",
            "linkedin",
            "youtube",

            # API keys
            "google_maps_api_key",
            "payment_gateway_key",
            "payment_gateway_secret",
            "sms_api_key",
            "email_api_key",

            # Features
            "enable_online_booking",
            "enable_restaurant_ordering",
            "enable_loyalty_program",
            
            # Notifications
            "send_booking_confirmation_email",
            "send_booking_confirmation_sms",
            "send_checkin_reminder",
            "send_checkout_reminder",
        ]
        widgets = {
            "about_description": forms.Textarea(attrs={"rows": 4}),
            "short_description": forms.Textarea(attrs={"rows": 2}),
            "cancellation_policy": forms.Textarea(attrs={"rows": 3}),
            "payment_policy": forms.Textarea(attrs={"rows": 3}),
            "house_rules": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind(self)

        # Placeholders
        if "brand_color" in self.fields:
            self.fields["brand_color"].widget.attrs.setdefault("placeholder", "#1D4ED8")
        
        if "currency" in self.fields:
            self.fields["currency"].widget.attrs.setdefault("placeholder", "USD")
        
        if "currency_symbol" in self.fields:
            self.fields["currency_symbol"].widget.attrs.setdefault("placeholder", "$")
        
        if "default_tax_rate" in self.fields:
            self.fields["default_tax_rate"].widget.attrs.setdefault("inputmode", "decimal")
            self.fields["default_tax_rate"].widget.attrs.setdefault("placeholder", "0.00")

        # Time pickers
        for f in ["check_in_time", "check_out_time", "reception_open_time", "reception_close_time"]:
            if f in self.fields:
                self.fields[f].widget = forms.TimeInput(attrs={"type": "time", "class": TW_INPUT})


# ==================== HOTEL IMAGE FORM ====================
class HotelImageForm(forms.ModelForm):
    class Meta:
        model = HotelImage
        fields = ['image', 'category', 'title', 'alt_text', 'caption', 'order', 'is_primary', 'is_featured']
        widgets = {
            'caption': forms.Textarea(attrs={'rows': 2}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind(self)
        
        # Add help text
        self.fields['order'].help_text = _("Lower numbers appear first")
        self.fields['alt_text'].help_text = _("SEO optimization - describe the image")


# Removed HotelImageGalleryForm due to Django's limitations with multiple file uploads
# Use HotelImageForm for individual uploads instead


# ==================== HOTEL DOCUMENT FORM ====================
class HotelDocumentForm(forms.ModelForm):
    class Meta:
        model = HotelDocument
        fields = ['document_type', 'title', 'file', 'description', 'issue_date', 'expiry_date']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'issue_date': forms.DateInput(attrs={'type': 'date'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind(self)
    
    def clean(self):
        cleaned_data = super().clean()
        issue_date = cleaned_data.get('issue_date')
        expiry_date = cleaned_data.get('expiry_date')
        
        if issue_date and expiry_date and expiry_date < issue_date:
            self.add_error('expiry_date', _('Expiry date cannot be before issue date'))
        
        return cleaned_data


# ==================== HOTEL REVIEW FORM ====================
class HotelReviewForm(forms.ModelForm):
    class Meta:
        model = HotelReview
        fields = [
            'guest_name', 'guest_email', 'overall_rating',
            'cleanliness_rating', 'comfort_rating', 'location_rating',
            'staff_rating', 'facilities_rating', 'value_rating',
            'title', 'review_text', 'pros', 'cons',
            'stay_date_from', 'stay_date_to', 'room_number'
        ]
        widgets = {
            'review_text': forms.Textarea(attrs={'rows': 5}),
            'pros': forms.Textarea(attrs={'rows': 3}),
            'cons': forms.Textarea(attrs={'rows': 3}),
            'stay_date_from': forms.DateInput(attrs={'type': 'date'}),
            'stay_date_to': forms.DateInput(attrs={'type': 'date'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind(self)
        
        # Add rating attributes
        rating_fields = [
            'overall_rating', 'cleanliness_rating', 'comfort_rating',
            'location_rating', 'staff_rating', 'facilities_rating', 'value_rating'
        ]
        for field_name in rating_fields:
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.update({
                    'step': '0.5',
                    'min': '1',
                    'max': '5'
                })
    
    def clean(self):
        cleaned_data = super().clean()
        stay_from = cleaned_data.get('stay_date_from')
        stay_to = cleaned_data.get('stay_date_to')
        
        if stay_from and stay_to and stay_to < stay_from:
            self.add_error('stay_date_to', _('Check-out date cannot be before check-in date'))
        
        return cleaned_data


class HotelReviewResponseForm(forms.ModelForm):
    """Form for hotel staff to respond to reviews"""
    
    class Meta:
        model = HotelReview
        fields = ['hotel_response']
        widgets = {
            'hotel_response': forms.Textarea(attrs={'rows': 4, 'placeholder': _('Write your response here...')}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind(self)


class HotelReviewFilterForm(forms.Form):
    """Form for filtering reviews"""
    
    rating = forms.ChoiceField(
        choices=[('', _('All Ratings'))] + [(str(i), f'{i} ★') for i in range(1, 6)],
        required=False
    )
    sort_by = forms.ChoiceField(
        choices=[
            ('-created_at', _('Newest First')),
            ('created_at', _('Oldest First')),
            ('-overall_rating', _('Highest Rated')),
            ('overall_rating', _('Lowest Rated')),
        ],
        required=False
    )
    is_verified = forms.ChoiceField(
        choices=[
            ('', _('All Reviews')),
            ('true', _('Verified Only')),
            ('false', _('Unverified Only')),
        ],
        required=False
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind(self)


# ==================== CONTACT PERSON FORM ====================
class HotelContactPersonForm(forms.ModelForm):
    class Meta:
        model = HotelContactPerson
        fields = ['name', 'position', 'email', 'phone', 'phone_alt', 'is_primary']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind(self)


# ==================== BANK DETAIL FORM ====================
class HotelBankDetailForm(forms.ModelForm):
    class Meta:
        model = HotelBankDetail
        fields = ['bank_name', 'account_holder_name', 'account_number', 
                 'routing_number', 'swift_code', 'iban', 'is_primary']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind(self)


# ==================== AMENITY FORMS ====================
class HotelAmenityForm(forms.ModelForm):
    class Meta:
        model = HotelAmenity
        fields = ['name', 'category', 'icon', 'is_paid', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind(self)


class HotelAmenityMappingForm(forms.ModelForm):
    class Meta:
        model = HotelAmenityMapping
        fields = ['amenity', 'is_available', 'additional_info', 'charge_amount']
        widgets = {
            'additional_info': forms.Textarea(attrs={'rows': 2}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind(self)
        
        if 'charge_amount' in self.fields:
            self.fields['charge_amount'].widget.attrs.update({
                'step': '0.01',
                'placeholder': '0.00'
            })


class HotelBulkAmenityForm(forms.Form):
    """Form for bulk assigning amenities to a hotel"""
    
    amenities = forms.ModelMultipleChoiceField(
        queryset=HotelAmenity.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False
    )
    
    def __init__(self, hotel=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.hotel = hotel
        apply_tailwind(self)
        
        # Pre-select existing amenities
        if hotel:
            existing_amenities = HotelAmenityMapping.objects.filter(
                hotel=hotel, 
                is_available=True
            ).values_list('amenity_id', flat=True)
            self.fields['amenities'].initial = existing_amenities


# ==================== BULK UPLOAD FORM ====================
class HotelBulkUploadForm(forms.Form):
    """Form for bulk uploading hotel data via CSV"""
    
    csv_file = forms.FileField(
        label=_('CSV File'),
        help_text=_('Upload CSV file with hotel data. Required columns: name, email, phone, city, country')
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind(self)
    
    def clean_csv_file(self):
        csv_file = self.cleaned_data['csv_file']
        
        if not csv_file.name.endswith('.csv'):
            raise forms.ValidationError(_('File must be CSV format'))
        
        # Check file size (max 5MB)
        if csv_file.size > 5 * 1024 * 1024:
            raise forms.ValidationError(_('File size must be less than 5MB'))
        
        return csv_file


# ==================== SEARCH AND FILTER FORMS ====================
class HotelSearchForm(forms.Form):
    """Form for searching and filtering hotels"""
    
    query = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': _('Search by name, city, or country...'),
            'class': TW_INPUT
        })
    )
    
    city = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': TW_INPUT}))
    country = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': TW_INPUT}))
    
    star_rating = forms.ChoiceField(
        choices=[('', _('Any Star'))] + [(str(i), f'{i} ★') for i in range(1, 6)],
        required=False
    )
    
    min_rating = forms.DecimalField(
        required=False,
        min_value=0,
        max_value=5,
        widget=forms.NumberInput(attrs={'step': '0.5', 'class': TW_INPUT})
    )
    
    is_active = forms.ChoiceField(
        choices=[('', _('All')), ('true', _('Active')), ('false', _('Inactive'))],
        required=False
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Apply tailwind to all fields except those with custom widget classes
        for field_name, field in self.fields.items():
            if not hasattr(field.widget, 'attrs') or 'class' not in field.widget.attrs:
                field.widget.attrs.setdefault('class', TW_INPUT)


class HotelExperienceForm(forms.ModelForm):
    """Form for guests to submit hotel experiences"""
    class Meta:
        model = HotelExperience
        fields = [
            'hotel', 'guest_name', 'guest_email',
            'place_visited', 'activity', 'rating', 'experience_text'
        ]
        widgets = {
            'experience_text': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind(self)
        
        if 'rating' in self.fields:
            self.fields['rating'].widget.attrs.update({
                'min': '1',
                'max': '5',
                'class': TW_INPUT
            })
        
        # Make hotel choice dropdown cleaner
        if 'hotel' in self.fields:
            self.fields['hotel'].queryset = Hotel.objects.filter(is_active=True, is_published=True).order_by('name')
            self.fields['hotel'].empty_label = "Select the Hotel you stayed at"