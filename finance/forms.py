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
            "booking": forms.Select(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all bg-white",
            }),
            "customer_name": forms.TextInput(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all",
                "placeholder": "Enter customer name",
            }),
            "customer_email": forms.EmailInput(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all",
                "placeholder": "customer@example.com",
            }),
            "customer_phone": forms.TextInput(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all",
                "placeholder": "+1234567890",
            }),
            "customer_address": forms.Textarea(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all",
                "rows": 2,
                "placeholder": "Customer address",
            }),
            "invoice_date": forms.DateInput(attrs={
                "type": "date",
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all",
            }),
            "due_date": forms.DateInput(attrs={
                "type": "date",
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all",
            }),
            "tax_scheme": forms.Select(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all bg-white",
            }),
            "tax_rate": forms.NumberInput(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all",
                "placeholder": "0.00",
                "step": "0.01",
            }),
            "tax_number": forms.TextInput(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all",
                "placeholder": "Tax/VAT number",
            }),
            "subtotal": forms.NumberInput(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all",
                "placeholder": "0.00",
                "step": "0.01",
            }),
            "discount": forms.NumberInput(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all",
                "placeholder": "0.00",
                "step": "0.01",
            }),
            "discount_type": forms.Select(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all bg-white",
            }),
            "currency": forms.TextInput(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all",
                "placeholder": "USD",
                "maxlength": 3,
            }),
            "exchange_rate": forms.NumberInput(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all",
                "placeholder": "1.0000",
                "step": "0.0001",
            }),
            "notes": forms.Textarea(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all",
                "rows": 3,
                "placeholder": "Additional notes...",
            }),
            "terms_conditions": forms.Textarea(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all",
                "rows": 3,
                "placeholder": "Terms and conditions...",
            }),
            "status": forms.Select(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all bg-white",
            }),
        }

    def __init__(self, *args, hotel=None, **kwargs):
        super().__init__(*args, **kwargs)
        if hotel is not None:
            self.fields["booking"].queryset = Booking.objects.filter(hotel=hotel).order_by("-check_in")
        
        # Add common classes to all form fields
        for field_name, field in self.fields.items():
            if field.widget.__class__ in [forms.TextInput, forms.EmailInput, forms.NumberInput, forms.DateInput, forms.PasswordInput]:
                if 'class' not in field.widget.attrs:
                    field.widget.attrs['class'] = 'w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all'
            elif isinstance(field.widget, forms.Select):
                if 'class' not in field.widget.attrs:
                    field.widget.attrs['class'] = 'w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all bg-white'
            elif isinstance(field.widget, forms.Textarea):
                if 'class' not in field.widget.attrs:
                    field.widget.attrs['class'] = 'w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all'

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
        widgets = {
            "method": forms.Select(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all bg-white",
            }),
            "amount": forms.NumberInput(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all",
                "placeholder": "0.00",
                "step": "0.01",
                "min": "0.01",
            }),
            "currency": forms.TextInput(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all",
                "placeholder": "USD",
                "maxlength": 3,
            }),
            "exchange_rate": forms.NumberInput(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all",
                "placeholder": "1.0000",
                "step": "0.0001",
            }),
            "reference": forms.TextInput(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all",
                "placeholder": "Transaction reference",
            }),
            "notes": forms.Textarea(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all",
                "rows": 2,
                "placeholder": "Payment notes...",
            }),
        }

    def __init__(self, *args, invoice=None, **kwargs):
        self.invoice = invoice
        super().__init__(*args, **kwargs)
        
        # Add cash_account field if needed
        from .models import CashAccount
        if invoice and hasattr(invoice, 'hotel'):
            self.fields['cash_account'] = forms.ModelChoiceField(
                queryset=CashAccount.objects.filter(hotel=invoice.hotel, is_active=True),
                required=False,
                widget=forms.Select(attrs={
                    "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all bg-white",
                })
            )

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
            "category": forms.Select(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all bg-white",
            }),
            "title": forms.TextInput(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all",
                "placeholder": "Expense title",
            }),
            "description": forms.Textarea(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all",
                "rows": 3,
                "placeholder": "Detailed description...",
            }),
            "amount": forms.NumberInput(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all",
                "placeholder": "0.00",
                "step": "0.01",
                "min": "0.01",
            }),
            "tax_amount": forms.NumberInput(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all",
                "placeholder": "0.00",
                "step": "0.01",
                "min": "0",
            }),
            "currency": forms.TextInput(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all",
                "placeholder": "USD",
                "maxlength": 3,
            }),
            "payment_method": forms.Select(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all bg-white",
            }),
            "payment_date": forms.DateInput(attrs={
                "type": "date",
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all",
            }),
            "payee": forms.TextInput(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all",
                "placeholder": "Payee name",
            }),
            "vendor": forms.Select(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all bg-white",
            }),
            "invoice_reference": forms.TextInput(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all",
                "placeholder": "Supplier invoice number",
            }),
            "receipt": forms.ClearableFileInput(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all file:mr-2 file:rounded-lg file:border-0 file:bg-blue-50 file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-blue-700 hover:file:bg-blue-100",
            }),
            "receipt_number": forms.TextInput(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all",
                "placeholder": "Receipt number",
            }),
            "notes": forms.Textarea(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all",
                "rows": 2,
                "placeholder": "Additional notes...",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Make vendor field optional and add empty choice
        self.fields['vendor'].required = False
        self.fields['vendor'].empty_label = "Select vendor (optional)"
        
        # Add help texts
        self.fields['receipt'].help_text = "Upload receipt image or PDF (max 5MB)"
        self.fields['receipt'].widget.attrs['accept'] = 'image/*,.pdf'

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
            "name": forms.TextInput(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all",
                "placeholder": "e.g., Q1 2024, January 2024",
            }),
            "start_date": forms.DateInput(attrs={
                "type": "date",
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all",
            }),
            "end_date": forms.DateInput(attrs={
                "type": "date",
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all",
            }),
            "status": forms.Select(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all bg-white",
            }),
            "notes": forms.Textarea(attrs={
                "class": "w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all",
                "rows": 3,
                "placeholder": "Additional notes about this financial period...",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add help text for status field
        self.fields['status'].help_text = "Closed periods cannot be modified"

    def clean(self):
        data = super().clean()
        s = data.get("start_date")
        e = data.get("end_date")
        if s and e and s >= e:
            raise ValidationError({"end_date": "End date must be after start date."})
        return data