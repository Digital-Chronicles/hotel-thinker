# finance/forms.py
from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from bookings.models import Booking
from .models import Invoice, Payment, Expense, FinancialPeriod


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = [
            "booking",
            "customer_name", "customer_email", "customer_phone", "customer_address",
            "invoice_date", "due_date",
            "tax_scheme", "tax_rate", "tax_number",
            "subtotal", "discount", "discount_type",
            "currency", "exchange_rate",
            "notes", "terms_conditions",
            "status",
        ]
        widgets = {
            "invoice_date": forms.DateInput(attrs={"type": "date"}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "terms_conditions": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, hotel=None, **kwargs):
        super().__init__(*args, **kwargs)
        if hotel is not None:
            self.fields["booking"].queryset = Booking.objects.filter(hotel=hotel).order_by("-check_in")

    def clean(self):
        data = super().clean()
        invoice_date = data.get("invoice_date")
        due_date = data.get("due_date")

        if invoice_date and due_date and due_date <= invoice_date:
            raise ValidationError({"due_date": "Due date must be after invoice date."})
        return data


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ["method", "amount", "currency", "exchange_rate", "reference", "notes"]

    def __init__(self, *args, invoice=None, **kwargs):
        self.invoice = invoice
        super().__init__(*args, **kwargs)

    def clean_amount(self):
        amt = self.cleaned_data.get("amount")
        if amt is None or amt <= 0:
            raise forms.ValidationError("Amount must be greater than 0.")
        if self.invoice is not None and amt > self.invoice.balance_due:
            raise forms.ValidationError("Payment exceeds invoice balance due.")
        return amt


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = [
            "category", "title", "description",
            "amount", "tax_amount", "currency",
            "payment_method", "payment_date",
            "payee", "vendor", "invoice_reference",
            "receipt", "receipt_number",
            "notes",
        ]
        widgets = {
            "payment_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def clean(self):
        data = super().clean()
        amount = data.get("amount") or 0
        tax_amount = data.get("tax_amount") or 0

        if amount <= 0:
            raise ValidationError({"amount": "Expense amount must be greater than zero."})
        if tax_amount < 0:
            raise ValidationError({"tax_amount": "Tax amount cannot be negative."})
        return data


class FinancialPeriodForm(forms.ModelForm):
    class Meta:
        model = FinancialPeriod
        fields = ["name", "start_date", "end_date", "status", "notes"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        data = super().clean()
        s = data.get("start_date")
        e = data.get("end_date")
        if s and e and s >= e:
            raise ValidationError({"end_date": "End date must be after start date."})
        return data