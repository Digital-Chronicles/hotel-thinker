# bookings/forms.py — UPDATED (supports 50% check-in / 100% check-out payment validation)
from __future__ import annotations

from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator

from rooms.models import Room
from finance.models import Payment
from .models import Guest, Booking


# -------------------------------------------------------------------
# Tailwind helpers (same style you already use)
# -------------------------------------------------------------------
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


def _d(v) -> Decimal:
    try:
        return Decimal(v or 0)
    except Exception:
        return Decimal("0")


# -------------------------------------------------------------------
# Guests
# -------------------------------------------------------------------
class GuestFullForm(forms.ModelForm):
    class Meta:
        model = Guest
        fields = [
            "full_name", "preferred_name", "guest_type",
            "phone", "alternative_phone", "email",
            "id_type", "id_number", "id_issue_date", "id_expiry_date", "id_scan",
            "nationality", "language",
            "address", "city", "country", "postal_code",
            "company_name", "company_vat", "company_address",
            "special_requests", "dietary_restrictions", "room_preferences", "is_vip",
            "marketing_consent", "newsletter_subscribed",
            "is_blacklisted", "blacklist_reason",
        ]
        widgets = {
            "id_issue_date": forms.DateInput(attrs={"type": "date"}),
            "id_expiry_date": forms.DateInput(attrs={"type": "date"}),
            "address": forms.Textarea(attrs={"rows": 2}),
            "company_address": forms.Textarea(attrs={"rows": 2}),
            "special_requests": forms.Textarea(attrs={"rows": 3}),
            "dietary_restrictions": forms.Textarea(attrs={"rows": 2}),
            "room_preferences": forms.Textarea(attrs={"rows": 2}),
            "blacklist_reason": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind(self)

        self.fields["full_name"].widget.attrs.setdefault("placeholder", "Guest full name")
        self.fields["phone"].widget.attrs.setdefault("placeholder", "2567XXXXXXXX")
        self.fields["email"].widget.attrs.setdefault("placeholder", "Optional")
        self.fields["preferred_name"].widget.attrs.setdefault("placeholder", "Optional")
        self.fields["id_scan"].help_text = "Optional ID scan/photo"

    def clean_full_name(self):
        name = (self.cleaned_data.get("full_name") or "").strip()
        if len(name) < 2:
            raise forms.ValidationError("Full name is too short.")
        return name


class GuestQuickCreateForm(forms.ModelForm):
    class Meta:
        model = Guest
        fields = [
            "full_name",
            "phone",
            "guest_type",
            "email",
            "nationality",
            "country",
            "id_type",
            "id_number",
            "is_vip",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind(self)
        self.fields["full_name"].widget.attrs.setdefault("placeholder", "Guest full name")
        self.fields["phone"].widget.attrs.setdefault("placeholder", "2567XXXXXXXX")
        self.fields["email"].widget.attrs.setdefault("placeholder", "Optional")


# -------------------------------------------------------------------
# Bookings (REDUCED fields + AUTO room pricing)
# -------------------------------------------------------------------
class BookingForm(forms.ModelForm):
    """
    Reduced booking form:
    - Staff selects guest, room, dates, people, source, notes, status
    - Price is fetched automatically from Room.room_type.base_price by Booking.save()
    """

    use_room_rate = forms.BooleanField(required=False, initial=True, widget=forms.HiddenInput())

    class Meta:
        model = Booking
        fields = [
            "guest", "room",
            "check_in", "check_out",
            "adults", "children", "infants",
            "source",
            "special_requests", "internal_notes",
            "status",
            "use_room_rate",
        ]
        widgets = {
            "special_requests": forms.Textarea(attrs={"rows": 3}),
            "internal_notes": forms.Textarea(attrs={"rows": 3}),
            "check_in": forms.DateInput(attrs={"type": "date"}),
            "check_out": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, hotel=None, **kwargs):
        super().__init__(*args, **kwargs)

        if hotel is not None:
            self.fields["guest"].queryset = Guest.objects.filter(hotel=hotel).order_by("full_name")
            self.fields["room"].queryset = (
                Room.objects.filter(hotel=hotel, is_active=True)
                .select_related("room_type")
                .order_by("number")
            )

        apply_tailwind(self)

    def clean(self):
        data = super().clean()
        check_in = data.get("check_in")
        check_out = data.get("check_out")
        room = data.get("room")

        if check_in and check_out and check_out <= check_in:
            raise ValidationError({"check_out": "Check-out must be after check-in."})

        # Room availability check
        if room and check_in and check_out:
            qs = Booking.objects.filter(
                room=room,
                status__in=[Booking.Status.RESERVED, Booking.Status.CONFIRMED, Booking.Status.CHECKED_IN],
                check_in__lt=check_out,
                check_out__gt=check_in,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError("Room is not available for the selected dates.")

        return data


class BookingUpdateForm(BookingForm):
    """
    Update form: same reduced fields + optional payment snapshot editing.
    """
    class Meta(BookingForm.Meta):
        fields = BookingForm.Meta.fields + ["payment_status", "amount_paid"]

    def __init__(self, *args, hotel=None, **kwargs):
        super().__init__(*args, hotel=hotel, **kwargs)
        if "amount_paid" in self.fields:
            self.fields["amount_paid"].widget.attrs.setdefault("inputmode", "decimal")
            self.fields["amount_paid"].widget.attrs.setdefault("placeholder", "0.00")


# -------------------------------------------------------------------
# Payments (Receive Payment form) — upgraded for check-in/check-out requirements
# -------------------------------------------------------------------
class BookingPaymentForm(forms.Form):
    """
    Supports 3 targets:
      - (default) normal payment: just requires amount > 0
      - target="checkin": requires that after paying, paid >= 50% of total
      - target="checkout": requires that after paying, balance becomes 0 (100%)
    """

    target = forms.ChoiceField(
        required=False,
        choices=[
            ("", "Payment"),
            ("checkin", "Check-in"),
            ("checkout", "Check-out"),
        ],
        widget=forms.HiddenInput(),
    )

    method = forms.ChoiceField(choices=Payment.Method.choices)
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    reference = forms.CharField(required=False, max_length=120)

    def __init__(self, *args, booking: Booking | None = None, **kwargs):
        """
        Pass booking=... when you want payment validation against booking totals.
        Example:
            form = BookingPaymentForm(request.POST, booking=booking)
        """
        super().__init__(*args, **kwargs)
        self.booking = booking
        apply_tailwind(self)
        self.fields["reference"].widget.attrs.setdefault("placeholder", "Optional")

    def clean_amount(self):
        amt = _d(self.cleaned_data.get("amount"))
        if amt <= 0:
            raise ValidationError("Amount must be greater than 0.")
        return amt

    def clean(self):
        cleaned = super().clean()

        # If no booking passed, behave like a normal payment form.
        if not self.booking:
            return cleaned

        target = (cleaned.get("target") or "").strip()
        amount = _d(cleaned.get("amount"))
        if amount <= 0:
            return cleaned

        total = _d(self.booking.total_amount)
        paid = _d(self.booking.amount_paid)
        after = paid + amount

        # check-in: after payment must reach >= 50%
        if target == "checkin":
            required = _d(getattr(self.booking, "required_checkin_amount", total * Decimal("0.50")))
            if after < required:
                need_more = required - after
                raise ValidationError(
                    f"Check-in requires at least 50% payment. Add at least {need_more:.2f} more."
                )

        # check-out: after payment must clear the full balance
        if target == "checkout":
            balance = max(total - paid, Decimal("0"))
            if amount < balance:
                need_more = balance - amount
                raise ValidationError(
                    f"Check-out requires full payment. Add at least {need_more:.2f} more."
                )

        return cleaned