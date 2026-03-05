# rooms/forms.py
from __future__ import annotations

from django import forms
from .models import RoomType, Room


# Tailwind helper styles
TW_INPUT = (
    "w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm "
    "placeholder-slate-400 shadow-sm "
    "focus:outline-none focus:ring-2 focus:ring-slate-300 focus:border-slate-300"
)
TW_SELECT = TW_INPUT
TW_TEXTAREA = (
    "w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm "
    "placeholder-slate-400 shadow-sm "
    "focus:outline-none focus:ring-2 focus:ring-slate-300 focus:border-slate-300"
)
TW_CHECKBOX = (
    "h-4 w-4 rounded border-slate-300 text-slate-900 "
    "focus:ring-2 focus:ring-slate-300"
)


class RoomTypeForm(forms.ModelForm):
    class Meta:
        model = RoomType
        fields = ["name", "description", "base_price"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Apply Tailwind classes
        self.fields["name"].widget.attrs.update({
            "class": TW_INPUT,
            "placeholder": "e.g. Single, Double, Deluxe",
        })
        self.fields["description"].widget.attrs.update({
            "class": TW_TEXTAREA,
            "placeholder": "Short description (optional)",
        })
        self.fields["base_price"].widget.attrs.update({
            "class": TW_INPUT,
            "placeholder": "0.00",
            "inputmode": "decimal",
        })


class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = ["room_type", "number", "floor", "status", "is_active"]

    def __init__(self, *args, hotel=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Hotel filter
        if hotel is not None:
            self.fields["room_type"].queryset = RoomType.objects.filter(hotel=hotel).order_by("name")

        # Tailwind classes
        self.fields["room_type"].widget.attrs.update({
            "class": TW_SELECT,
        })
        self.fields["number"].widget.attrs.update({
            "class": TW_INPUT,
            "placeholder": "e.g. 101, A-01",
        })
        self.fields["floor"].widget.attrs.update({
            "class": TW_INPUT,
            "placeholder": "e.g. 1st floor (optional)",
        })
        self.fields["status"].widget.attrs.update({
            "class": TW_SELECT,
        })

        # Checkbox styling
        self.fields["is_active"].widget.attrs.update({
            "class": TW_CHECKBOX,
        })

    def clean_number(self):
        number = (self.cleaned_data.get("number") or "").strip()
        if not number:
            raise forms.ValidationError("Room number is required.")
        return number