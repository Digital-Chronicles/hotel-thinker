# hotels/forms.py
from __future__ import annotations

from django import forms
from .models import HotelSetting


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


def apply_tailwind(form: forms.Form) -> None:
    for _, field in form.fields.items():
        w = field.widget
        if isinstance(w, forms.HiddenInput):
            continue
        if isinstance(w, forms.CheckboxInput):
            w.attrs.setdefault("class", TW_CHECKBOX)
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

            # API keys (keep in form but we’ll show in “Advanced” section)
            "google_maps_api_key",
            "payment_gateway_key",
            "payment_gateway_secret",
            "sms_api_key",
            "email_api_key",

            # Features
            "enable_online_booking",
            "enable_restaurant_ordering",
            "enable_loyalty_program",
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

        # Helpful placeholders
        if "brand_color" in self.fields:
            self.fields["brand_color"].widget.attrs.setdefault("placeholder", "#1D4ED8")

        if "currency" in self.fields:
            self.fields["currency"].widget.attrs.setdefault("placeholder", "USD")
        if "currency_symbol" in self.fields:
            self.fields["currency_symbol"].widget.attrs.setdefault("placeholder", "$")

        # Time widgets: use native time pickers
        for f in ["check_in_time", "check_out_time", "reception_open_time", "reception_close_time"]:
            if f in self.fields:
                self.fields[f].widget = forms.TimeInput(attrs={"type": "time", "class": TW_INPUT})

        # Decimal input hints
        if "default_tax_rate" in self.fields:
            self.fields["default_tax_rate"].widget.attrs.setdefault("inputmode", "decimal")
            self.fields["default_tax_rate"].widget.attrs.setdefault("placeholder", "0.00")