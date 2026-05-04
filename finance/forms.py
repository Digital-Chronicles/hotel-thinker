# finance/forms.py
from __future__ import annotations

from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import (
    Account, Vendor, CashAccount, Asset, Liability, 
    JournalEntry, JournalLine, Invoice, InvoiceLineItem, 
    Expense, FinancialPeriod, Payment
)

D0 = Decimal("0.00")
D100 = Decimal("100")


# =========================================================
# Base Form with Tailwind Styling
# =========================================================

class BaseFinanceForm(forms.ModelForm):
    """Base form with Tailwind CSS styling"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_tailwind_classes()
    
    def _apply_tailwind_classes(self):
        """Apply Tailwind CSS classes to all form fields"""
        for field_name, field in self.fields.items():
            widget = field.widget
            existing_class = widget.attrs.get('class', '')
            
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs['class'] = f"{existing_class} w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-2 focus:ring-blue-500".strip()
            elif isinstance(widget, forms.Select):
                widget.attrs['class'] = f"{existing_class} w-full rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-300 appearance-none".strip()
            elif isinstance(widget, forms.Textarea):
                widget.attrs['class'] = f"{existing_class} w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-300 resize-y min-h-[80px]".strip()
            elif isinstance(widget, forms.FileInput):
                widget.attrs['class'] = f"{existing_class} w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100".strip()
            else:
                widget.attrs['class'] = f"{existing_class} w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-300".strip()


# =========================================================
# Account Forms
# =========================================================

class AccountForm(BaseFinanceForm):
    """Form for creating/editing accounts"""
    
    class Meta:
        model = Account
        fields = [
            'account_code', 'name', 'account_type', 'account_subtype',
            'parent', 'description', 'is_active', 'is_system'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Optional description of the account'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.hotel = kwargs.pop('hotel', None)
        super().__init__(*args, **kwargs)
        
        if self.hotel:
            self.fields['parent'].queryset = Account.objects.filter(
                hotel=self.hotel, is_active=True
            ).order_by('account_code')
        
        # Add help texts
        self.fields['account_code'].help_text = "Unique code for this account (e.g., 1000, 2000)"
        self.fields['account_type'].help_text = "The type determines how balances are calculated"
        self.fields['account_subtype'].help_text = "More specific classification for reporting"
        self.fields['is_system'].help_text = "System accounts are protected from deletion"
    
    def clean_account_code(self):
        code = self.cleaned_data.get('account_code', '').strip().upper()
        if not code:
            raise ValidationError(_("Account code is required."))
        
        if self.hotel:
            existing = Account.objects.filter(
                hotel=self.hotel, 
                account_code=code
            ).exclude(pk=self.instance.pk if self.instance else None)
            if existing.exists():
                raise ValidationError(_("Account code must be unique within this hotel."))
        
        return code
    
    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        if not name:
            raise ValidationError(_("Account name is required."))
        
        if self.hotel:
            existing = Account.objects.filter(
                hotel=self.hotel, 
                name=name
            ).exclude(pk=self.instance.pk if self.instance else None)
            if existing.exists():
                raise ValidationError(_("Account name must be unique within this hotel."))
        
        return name


# =========================================================
# Vendor Forms
# =========================================================

class VendorForm(BaseFinanceForm):
    """Form for creating/editing vendors"""
    
    class Meta:
        model = Vendor
        fields = [
            'vendor_code', 'name', 'contact_person', 'phone', 'email',
            'address', 'tin_number', 'opening_balance', 'is_active', 'notes'
        ]
        widgets = {
            'address': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Physical address'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Additional notes about the vendor'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.hotel = kwargs.pop('hotel', None)
        super().__init__(*args, **kwargs)
        
        if not self.instance.pk:
            self.fields['vendor_code'].required = False
        
        self.fields['vendor_code'].help_text = "Auto-generated if left blank"
        self.fields['tin_number'].help_text = "Tax Identification Number"
        self.fields['opening_balance'].help_text = "Initial balance owed to this vendor"
    
    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        if not name:
            raise ValidationError(_("Vendor name is required."))
        
        if self.hotel:
            existing = Vendor.objects.filter(
                hotel=self.hotel, 
                name=name
            ).exclude(pk=self.instance.pk if self.instance else None)
            if existing.exists():
                raise ValidationError(_("Vendor name must be unique within this hotel."))
        
        return name
    
    def clean_phone(self):
        phone = self.cleaned_data.get('phone', '').strip()
        if phone:
            import re
            clean_phone = re.sub(r'\D', '', phone)
            if len(clean_phone) < 9:
                raise ValidationError(_("Phone number must be at least 9 digits."))
        return phone


# =========================================================
# Cash Account Forms
# =========================================================

class CashAccountForm(BaseFinanceForm):
    """Form for creating/editing cash accounts"""
    
    class Meta:
        model = CashAccount
        fields = [
            'name', 'account_type', 'account_number', 'opening_balance',
            'gl_account', 'is_active', 'notes'
        ]
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Optional notes'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.hotel = kwargs.pop('hotel', None)
        super().__init__(*args, **kwargs)
        
        if self.hotel:
            self.fields['gl_account'].queryset = Account.objects.filter(
                hotel=self.hotel,
                account_type=Account.AccountType.ASSET,
                account_subtype__in=[Account.SubType.CASH, Account.SubType.BANK],
                is_active=True
            ).order_by('account_code')
        
        self.fields['opening_balance'].help_text = "Initial balance for this account"
        self.fields['gl_account'].help_text = "Linked General Ledger account"
    
    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        if not name:
            raise ValidationError(_("Cash account name is required."))
        
        if self.hotel:
            existing = CashAccount.objects.filter(
                hotel=self.hotel, 
                name=name
            ).exclude(pk=self.instance.pk if self.instance else None)
            if existing.exists():
                raise ValidationError(_("Cash account name must be unique within this hotel."))
        
        return name


# =========================================================
# Asset Forms
# =========================================================

class AssetForm(BaseFinanceForm):
    """Form for creating/editing assets"""
    
    class Meta:
        model = Asset
        fields = [
            'asset_type', 'name', 'description', 'purchase_date', 'purchase_cost',
            'useful_life_months', 'salvage_value', 'depreciation_method', 'status',
            'location', 'vendor', 'asset_account', 'depreciation_account', 'expense_account'
        ]
        widgets = {
            'purchase_date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Detailed description of the asset'}),
            'location': forms.TextInput(attrs={'placeholder': 'Physical location of the asset'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.hotel = kwargs.pop('hotel', None)
        super().__init__(*args, **kwargs)
        
        if self.hotel:
            self.fields['vendor'].queryset = Vendor.objects.filter(hotel=self.hotel, is_active=True).order_by('name')
            self.fields['asset_account'].queryset = Account.objects.filter(
                hotel=self.hotel, 
                account_type=Account.AccountType.ASSET,
                is_active=True
            ).order_by('account_code')
            self.fields['depreciation_account'].queryset = Account.objects.filter(
                hotel=self.hotel,
                account_type=Account.AccountType.EXPENSE,
                is_active=True
            ).order_by('account_code')
            self.fields['expense_account'].queryset = Account.objects.filter(
                hotel=self.hotel,
                account_type=Account.AccountType.EXPENSE,
                is_active=True
            ).order_by('account_code')
        
        self.fields['useful_life_months'].help_text = "Expected useful life in months"
        self.fields['salvage_value'].help_text = "Estimated value at end of useful life"
        self.fields['depreciation_method'].help_text = "Method used to calculate depreciation"
    
    def clean_purchase_cost(self):
        cost = self.cleaned_data.get('purchase_cost', D0)
        if cost <= D0:
            raise ValidationError(_("Purchase cost must be greater than zero."))
        return cost
    
    def clean_useful_life_months(self):
        months = self.cleaned_data.get('useful_life_months', 0)
        if months < 0:
            raise ValidationError(_("Useful life cannot be negative."))
        return months


# =========================================================
# Liability Forms
# =========================================================

class LiabilityForm(BaseFinanceForm):
    """Form for creating/editing liabilities"""
    
    class Meta:
        model = Liability
        fields = [
            'liability_type', 'name', 'reference', 'vendor', 'payable_account',
            'original_amount', 'start_date', 'due_date', 'notes'
        ]
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Optional notes'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.hotel = kwargs.pop('hotel', None)
        super().__init__(*args, **kwargs)
        
        if self.hotel:
            self.fields['vendor'].queryset = Vendor.objects.filter(hotel=self.hotel, is_active=True).order_by('name')
            self.fields['payable_account'].queryset = Account.objects.filter(
                hotel=self.hotel,
                account_type=Account.AccountType.LIABILITY,
                is_active=True
            ).order_by('account_code')
        
        self.fields['start_date'].initial = timezone.now().date()
    
    def clean_original_amount(self):
        amount = self.cleaned_data.get('original_amount', D0)
        if amount <= D0:
            raise ValidationError(_("Original amount must be greater than zero."))
        return amount
    
    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        due_date = cleaned_data.get('due_date')
        
        if start_date and due_date and due_date < start_date:
            self.add_error('due_date', _("Due date cannot be before start date."))
        
        return cleaned_data


# =========================================================
# Journal Entry Forms
# =========================================================

class JournalEntryForm(BaseFinanceForm):
    """Form for creating journal entries"""
    
    class Meta:
        model = JournalEntry
        fields = ['entry_date', 'description', 'reference_type', 'reference_id']
        widgets = {
            'entry_date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Description of the journal entry'}),
            'reference_id': forms.NumberInput(attrs={'placeholder': 'Reference ID number'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.hotel = kwargs.pop('hotel', None)
        super().__init__(*args, **kwargs)
        
        self.fields['entry_date'].initial = timezone.now().date()
        self.fields['reference_type'].help_text = "Type of source document (e.g., invoice, payment)"
        self.fields['reference_id'].help_text = "ID of the source document"


class JournalLineForm(BaseFinanceForm):
    """Form for adding journal lines"""
    
    class Meta:
        model = JournalLine
        fields = ['account', 'description', 'debit', 'credit']
        widgets = {
            'description': forms.TextInput(attrs={'placeholder': 'Optional line description'}),
            'debit': forms.NumberInput(attrs={'step': '0.01', 'placeholder': '0.00'}),
            'credit': forms.NumberInput(attrs={'step': '0.01', 'placeholder': '0.00'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.hotel = kwargs.pop('hotel', None)
        super().__init__(*args, **kwargs)
        
        if self.hotel:
            self.fields['account'].queryset = Account.objects.filter(
                hotel=self.hotel, is_active=True
            ).order_by('account_code')
        
        self.fields['debit'].help_text = "Amount to debit (increase asset/expense)"
        self.fields['credit'].help_text = "Amount to credit (increase liability/equity/revenue)"
    
    def clean(self):
        cleaned_data = super().clean()
        debit = cleaned_data.get('debit', D0)
        credit = cleaned_data.get('credit', D0)
        
        if debit == D0 and credit == D0:
            raise ValidationError(_("Either debit or credit must be greater than zero."))
        
        if debit > D0 and credit > D0:
            raise ValidationError(_("Cannot have both debit and credit values."))
        
        if debit < D0 or credit < D0:
            raise ValidationError(_("Debit and credit cannot be negative."))
        
        return cleaned_data


# =========================================================
# Invoice Forms
# =========================================================

class InvoiceForm(BaseFinanceForm):
    """Form for creating/editing invoices"""
    
    class Meta:
        model = Invoice
        fields = [
            'customer_name', 'customer_email', 'customer_phone', 'customer_address',
            'customer_vat', 'invoice_date', 'due_date', 'tax_scheme', 'tax_rate',
            'tax_number', 'discount', 'discount_type', 'notes', 'terms_conditions',
            'internal_notes', 'receivable_account', 'revenue_account', 'tax_account'
        ]
        widgets = {
            'invoice_date': forms.DateInput(attrs={'type': 'date'}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
            'customer_address': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Customer billing address'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Notes visible to customer'}),
            'terms_conditions': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Payment terms and conditions'}),
            'internal_notes': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Internal notes (staff only)'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.hotel = kwargs.pop('hotel', None)
        super().__init__(*args, **kwargs)
        
        if self.hotel:
            self.fields['receivable_account'].queryset = Account.objects.filter(
                hotel=self.hotel,
                account_type=Account.AccountType.ASSET,
                account_subtype=Account.SubType.RECEIVABLE,
                is_active=True
            ).order_by('account_code')
            self.fields['revenue_account'].queryset = Account.objects.filter(
                hotel=self.hotel,
                account_type=Account.AccountType.REVENUE,
                is_active=True
            ).order_by('account_code')
            self.fields['tax_account'].queryset = Account.objects.filter(
                hotel=self.hotel,
                account_type=Account.AccountType.LIABILITY,
                account_subtype=Account.SubType.TAX_PAYABLE,
                is_active=True
            ).order_by('account_code')
        
        self.fields['invoice_date'].initial = timezone.now().date()
        self.fields['discount'].initial = D0
        self.fields['tax_rate'].initial = D0
        self.fields['discount_type'].initial = 'fixed'
        self.fields['tax_rate'].help_text = "Tax percentage (e.g., 18 for 18%)"
        self.fields['discount'].help_text = "Discount amount or percentage based on type"
    
    def clean_invoice_date(self):
        date = self.cleaned_data.get('invoice_date')
        if date and date < timezone.now().date():
            raise ValidationError(_("Invoice date cannot be in the past."))
        return date
    
    def clean_tax_rate(self):
        rate = self.cleaned_data.get('tax_rate', D0)
        if rate < D0 or rate > D100:
            raise ValidationError(_("Tax rate must be between 0 and 100."))
        return rate


class InvoiceLineItemForm(BaseFinanceForm):
    """Form for adding items to an invoice"""
    
    class Meta:
        model = InvoiceLineItem
        fields = ['description', 'quantity', 'unit_price', 'discount', 'tax_rate']
        widgets = {
            'description': forms.TextInput(attrs={'placeholder': 'Item description'}),
            'quantity': forms.NumberInput(attrs={'min': 1, 'step': 1, 'value': 1}),
            'unit_price': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'placeholder': '0.00'}),
            'discount': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'placeholder': '0.00'}),
            'tax_rate': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'max': '100', 'placeholder': '0'}),
        }
    
    def clean_quantity(self):
        qty = self.cleaned_data.get('quantity', 1)
        if qty < 1:
            raise ValidationError(_("Quantity must be at least 1."))
        return qty
    
    def clean_unit_price(self):
        price = self.cleaned_data.get('unit_price', D0)
        if price < D0:
            raise ValidationError(_("Unit price cannot be negative."))
        return price
    
    def clean_discount(self):
        discount = self.cleaned_data.get('discount', D0)
        if discount < D0:
            raise ValidationError(_("Discount cannot be negative."))
        return discount


# =========================================================
# Payment Forms
# =========================================================

class PaymentForm(BaseFinanceForm):
    """Form for recording payments"""
    
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=D0,
        widget=forms.NumberInput(attrs={
            'step': '0.01',
            'placeholder': '0.00',
        })
    )
    method = forms.ChoiceField(
        choices=Payment.Method.choices,
        widget=forms.Select()
    )
    reference = forms.CharField(
        required=False,
        max_length=120,
        widget=forms.TextInput(attrs={
            'placeholder': 'Transaction reference number',
        })
    )
    cash_account = forms.ModelChoiceField(
        queryset=None,
        required=False,
        widget=forms.Select()
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 2,
            'placeholder': 'Payment notes (optional)',
        })
    )
    
    def __init__(self, *args, invoice=None, **kwargs):
        self.invoice = invoice
        super().__init__(*args, **kwargs)
        
        if invoice and invoice.hotel:
            self.fields['cash_account'].queryset = CashAccount.objects.filter(
                hotel=invoice.hotel, is_active=True
            ).order_by('name')
        
        if invoice and not self.is_bound:
            self.initial['amount'] = invoice.balance_due
        
        self.fields['amount'].help_text = f"Amount to pay (Balance due: {invoice.balance_due if invoice else 'N/A'})"
        self.fields['reference'].help_text = "Transaction ID, cheque number, or reference"
        self.fields['cash_account'].help_text = "Cash/Bank account to record this payment"
        
        self._apply_tailwind_classes()
    
    def clean_amount(self):
        amount = self.cleaned_data.get('amount', D0)
        if amount <= D0:
            raise ValidationError(_("Payment amount must be greater than zero."))
        
        if self.invoice and amount > self.invoice.balance_due:
            raise ValidationError(_("Payment amount cannot exceed invoice balance due."))
        
        return amount
    
    def clean(self):
        cleaned_data = super().clean()
        method = cleaned_data.get('method')
        reference = cleaned_data.get('reference')
        
        if method in [Payment.Method.MOBILE_MONEY, Payment.Method.CREDIT_CARD, Payment.Method.DEBIT_CARD]:
            if not reference:
                self.add_error('reference', _("Transaction reference is required for this payment method."))
        
        return cleaned_data


# =========================================================
# Expense Forms
# =========================================================

class ExpenseForm(BaseFinanceForm):
    """Form for creating/editing expenses"""
    
    class Meta:
        model = Expense
        fields = [
            'category', 'expense_type', 'department', 'title', 'description',
            'amount', 'tax_amount', 'payment_method', 'expense_date', 'due_date',
            'payee', 'vendor', 'invoice_reference', 'expense_account',
            'payable_account', 'prepaid_account', 'asset_account', 'cash_account',
            'receipt', 'notes'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Detailed description of the expense'}),
            'expense_date': forms.DateInput(attrs={'type': 'date'}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
            'receipt': forms.FileInput(),
            'notes': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Additional notes'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.hotel = kwargs.pop('hotel', None)
        super().__init__(*args, **kwargs)
        
        if self.hotel:
            self.fields['vendor'].queryset = Vendor.objects.filter(hotel=self.hotel, is_active=True).order_by('name')
            self.fields['cash_account'].queryset = CashAccount.objects.filter(hotel=self.hotel, is_active=True).order_by('name')
            self.fields['expense_account'].queryset = Account.objects.filter(
                hotel=self.hotel,
                account_type=Account.AccountType.EXPENSE,
                is_active=True
            ).order_by('account_code')
            self.fields['payable_account'].queryset = Account.objects.filter(
                hotel=self.hotel,
                account_type=Account.AccountType.LIABILITY,
                account_subtype=Account.SubType.PAYABLE,
                is_active=True
            ).order_by('account_code')
            self.fields['prepaid_account'].queryset = Account.objects.filter(
                hotel=self.hotel,
                account_type=Account.AccountType.ASSET,
                account_subtype=Account.SubType.PREPAID,
                is_active=True
            ).order_by('account_code')
            self.fields['asset_account'].queryset = Account.objects.filter(
                hotel=self.hotel,
                account_type=Account.AccountType.ASSET,
                account_subtype__in=[Account.SubType.FIXED_ASSET, Account.SubType.EQUIPMENT],
                is_active=True
            ).order_by('account_code')
        
        self.fields['expense_date'].initial = timezone.now().date()
        self.fields['amount'].initial = D0
        self.fields['tax_amount'].initial = D0
        self.fields['amount'].help_text = "Base amount before tax"
        self.fields['tax_amount'].help_text = "Tax amount"
        self.fields['invoice_reference'].help_text = "Vendor invoice or receipt number"
    
    def clean_amount(self):
        amount = self.cleaned_data.get('amount', D0)
        if amount <= D0:
            raise ValidationError(_("Expense amount must be greater than zero."))
        return amount
    
    def clean(self):
        cleaned_data = super().clean()
        expense_type = cleaned_data.get('expense_type')
        asset_account = cleaned_data.get('asset_account')
        
        if expense_type == Expense.ExpenseType.CAPITAL and not asset_account:
            self.add_error('asset_account', _("Asset account is required for capital expenditures."))
        
        return cleaned_data


# =========================================================
# Financial Period Forms
# =========================================================

class FinancialPeriodForm(BaseFinanceForm):
    """Form for creating financial periods"""
    
    class Meta:
        model = FinancialPeriod
        fields = ['name', 'start_date', 'end_date', 'notes']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Optional notes about this period'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.hotel = kwargs.pop('hotel', None)
        super().__init__(*args, **kwargs)
        
        self.fields['name'].help_text = "e.g., Q1 2024, January 2024"
        self.fields['start_date'].help_text = "First day of the period"
        self.fields['end_date'].help_text = "Last day of the period"
    
    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date:
            if start_date >= end_date:
                self.add_error('end_date', _("End date must be after start date."))
            
            if self.hotel:
                overlapping = FinancialPeriod.objects.filter(
                    hotel=self.hotel,
                    start_date__lt=end_date,
                    end_date__gt=start_date
                ).exclude(pk=self.instance.pk if self.instance else None)
                
                if overlapping.exists():
                    self.add_error(None, _("Period overlaps with an existing financial period."))
        
        return cleaned_data


# =========================================================
# Report Forms
# =========================================================

class DateRangeForm(forms.Form):
    """Form for date range filtering in reports"""
    
    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        today = timezone.now().date()
        
        if not self.is_bound:
            self.initial['start_date'] = today.replace(day=1)
            self.initial['end_date'] = today
        
        self._apply_tailwind_classes()
    
    def _apply_tailwind_classes(self):
        for field in self.fields.values():
            if hasattr(field.widget, 'attrs'):
                field.widget.attrs['class'] = 'w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500'
    
    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date and start_date > end_date:
            self.add_error('end_date', _("End date must be after start date."))
        
        return cleaned_data


class TrialBalanceForm(DateRangeForm):
    """Form for trial balance report"""
    
    account_type = forms.ChoiceField(
        choices=[('', 'All Types')] + list(Account.AccountType.choices),
        required=False,
        widget=forms.Select()
    )
    
    include_zero_balances = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput()
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['account_type'].widget.attrs['class'] = 'w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500'
        self.fields['include_zero_balances'].widget.attrs['class'] = 'w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-2 focus:ring-blue-500'