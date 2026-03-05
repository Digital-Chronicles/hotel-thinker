from __future__ import annotations

from django import forms

from .models import Profile, HotelMember


BASE_INPUT = "w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
BASE_SELECT = "w-full rounded-lg border border-gray-300 bg-white px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
BASE_TEXTAREA = "w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = [
            "phone",
            "alternative_phone",
            "gender",
            "date_of_birth",
            "job_title",
            "department",
            "employee_id",
            "address_line1",
            "address_line2",
            "city",
            "state",
            "postal_code",
            "country",
            "language",
            "timezone",
            "notification_email",
            "notification_sms",
            "notification_push",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for name, field in self.fields.items():
            widget = field.widget

            # Add consistent Tailwind classes
            if isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("class", BASE_TEXTAREA)
                widget.attrs.setdefault("rows", 3)
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", BASE_SELECT)
            elif isinstance(widget, (forms.TextInput, forms.EmailInput, forms.NumberInput, forms.DateInput)):
                widget.attrs.setdefault("class", BASE_INPUT)
            elif isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "h-4 w-4 rounded border-gray-300")

            # Helpful placeholders for some fields
            if name in {"phone", "alternative_phone"} and not widget.attrs.get("placeholder"):
                widget.attrs["placeholder"] = "+2567XXXXXXXX"


class HotelMemberForm(forms.ModelForm):
    class Meta:
        model = HotelMember
        fields = [
            "role",
            "permission_level",
            "can_access_front_desk",
            "can_access_housekeeping",
            "can_access_restaurant",
            "can_access_finance",
            "can_access_maintenance",
            "can_access_reports",
            "is_active",
            "is_primary_contact",
            "notes",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for name, field in self.fields.items():
            widget = field.widget

            if isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("class", BASE_TEXTAREA)
                widget.attrs.setdefault("rows", 3)
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", BASE_SELECT)
            elif isinstance(widget, (forms.TextInput, forms.EmailInput, forms.NumberInput, forms.DateInput)):
                widget.attrs.setdefault("class", BASE_INPUT)
            elif isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "h-4 w-4 rounded border-gray-300")