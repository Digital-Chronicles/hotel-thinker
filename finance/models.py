# finance/models.py
from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from hotels.models import Hotel
from bookings.models import Booking


D0 = Decimal("0")
D001 = Decimal("0.01")
D100 = Decimal("100")


# =========================================================
# CORE ACCOUNTING STRUCTURE
# =========================================================

class Account(models.Model):
    class AccountType(models.TextChoices):
        ASSET = "asset", _("Asset")
        LIABILITY = "liability", _("Liability")
        EQUITY = "equity", _("Equity")
        REVENUE = "revenue", _("Revenue")
        EXPENSE = "expense", _("Expense")

    class SubType(models.TextChoices):
        CASH = "cash", _("Cash")
        BANK = "bank", _("Bank")
        RECEIVABLE = "receivable", _("Accounts Receivable")
        INVENTORY = "inventory", _("Inventory")
        PREPAID = "prepaid", _("Prepaid Expense")
        FIXED_ASSET = "fixed_asset", _("Fixed Asset")
        ACCUMULATED_DEPRECIATION = "accumulated_depreciation", _("Accumulated Depreciation")
        PAYABLE = "payable", _("Accounts Payable")
        TAX_PAYABLE = "tax_payable", _("Tax Payable")
        SALARY_PAYABLE = "salary_payable", _("Salary Payable")
        CUSTOMER_DEPOSIT = "customer_deposit", _("Customer Deposit")
        LOAN_PAYABLE = "loan_payable", _("Loan Payable")
        CAPITAL = "capital", _("Capital")
        RETAINED_EARNINGS = "retained_earnings", _("Retained Earnings")
        SALES = "sales", _("Sales Revenue")
        SERVICE_REVENUE = "service_revenue", _("Service Revenue")
        COGS = "cogs", _("Cost of Goods Sold")
        OPERATING_EXPENSE = "operating_expense", _("Operating Expense")
        DEPRECIATION_EXPENSE = "depreciation_expense", _("Depreciation Expense")
        OTHER = "other", _("Other")

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="finance_accounts")
    account_code = models.CharField(max_length=30)
    name = models.CharField(max_length=150)
    account_type = models.CharField(max_length=20, choices=AccountType.choices, db_index=True)
    account_subtype = models.CharField(max_length=40, choices=SubType.choices, default=SubType.OTHER, db_index=True)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
    )
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_system = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hotel", "account_code"], name="uniq_account_code_per_hotel"),
            models.UniqueConstraint(fields=["hotel", "name"], name="uniq_account_name_per_hotel"),
        ]
        indexes = [
            models.Index(fields=["hotel", "account_type"]),
            models.Index(fields=["hotel", "account_subtype"]),
        ]
        ordering = ["account_code", "name"]
        verbose_name = _("Account")
        verbose_name_plural = _("Accounts")

    def __str__(self):
        return f"{self.account_code} - {self.name}"

    @property
    def balance(self) -> Decimal:
        totals = self.journal_lines.aggregate(
            debit_total=Sum("debit"),
            credit_total=Sum("credit"),
        )
        debit_total = Decimal(totals["debit_total"] or D0)
        credit_total = Decimal(totals["credit_total"] or D0)

        if self.account_type in [self.AccountType.ASSET, self.AccountType.EXPENSE]:
            return debit_total - credit_total
        return credit_total - debit_total


class Vendor(models.Model):
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="vendors")
    vendor_code = models.CharField(max_length=30)
    name = models.CharField(max_length=255)
    contact_person = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=30, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    tin_number = models.CharField(max_length=50, blank=True, null=True)
    opening_balance = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hotel", "vendor_code"], name="uniq_vendor_code_per_hotel"),
            models.UniqueConstraint(fields=["hotel", "name"], name="uniq_vendor_name_per_hotel"),
        ]
        indexes = [
            models.Index(fields=["hotel", "name"]),
            models.Index(fields=["hotel", "is_active"]),
        ]
        ordering = ["name"]
        verbose_name = _("Vendor")
        verbose_name_plural = _("Vendors")

    def __str__(self):
        return self.name

    @property
    def payable_balance(self) -> Decimal:
        total = self.liabilities.filter(
            status__in=[Liability.Status.OPEN, Liability.Status.PARTIAL, Liability.Status.OVERDUE]
        ).aggregate(t=Sum("balance"))["t"]
        return Decimal(total or D0)


class CashAccount(models.Model):
    class AccountType(models.TextChoices):
        CASH = "cash", _("Cash")
        BANK = "bank", _("Bank")
        MOBILE_MONEY = "mobile_money", _("Mobile Money")

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="cash_accounts")
    name = models.CharField(max_length=100)
    account_type = models.CharField(max_length=20, choices=AccountType.choices, default=AccountType.CASH)
    account_number = models.CharField(max_length=100, blank=True, null=True)
    currency = models.CharField(max_length=3, default="USD")
    opening_balance = models.DecimalField(max_digits=14, decimal_places=2, default=D0)
    current_balance = models.DecimalField(max_digits=14, decimal_places=2, default=D0)
    gl_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="cash_accounts",
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hotel", "name"], name="uniq_cash_account_name_per_hotel"),
        ]
        indexes = [
            models.Index(fields=["hotel", "account_type"]),
            models.Index(fields=["hotel", "is_active"]),
        ]
        ordering = ["name"]
        verbose_name = _("Cash Account")
        verbose_name_plural = _("Cash Accounts")

    def __str__(self):
        return f"{self.name} ({self.get_account_type_display()})"

    def adjust_balance(self, amount: Decimal, increase: bool = True):
        amount = Decimal(amount or D0)
        if amount < D0:
            raise ValidationError(_("Amount cannot be negative."))
        self.current_balance = Decimal(self.current_balance or D0) + amount if increase else Decimal(self.current_balance or D0) - amount
        self.save(update_fields=["current_balance", "updated_at"])


class Asset(models.Model):
    class AssetType(models.TextChoices):
        FIXED_ASSET = "fixed_asset", _("Fixed Asset")
        PREPAID = "prepaid", _("Prepaid Expense")
        INVENTORY = "inventory", _("Inventory")
        DEPOSIT = "deposit", _("Deposit")
        OTHER = "other", _("Other")

    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        DISPOSED = "disposed", _("Disposed")
        DAMAGED = "damaged", _("Damaged")
        INACTIVE = "inactive", _("Inactive")

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="assets")
    asset_number = models.CharField(max_length=50)
    asset_type = models.CharField(max_length=20, choices=AssetType.choices, default=AssetType.FIXED_ASSET)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    purchase_date = models.DateField(default=timezone.localdate)
    purchase_cost = models.DecimalField(max_digits=14, decimal_places=2, default=D0)
    current_value = models.DecimalField(max_digits=14, decimal_places=2, default=D0)
    useful_life_months = models.PositiveIntegerField(default=0)
    salvage_value = models.DecimalField(max_digits=14, decimal_places=2, default=D0)
    accumulated_depreciation = models.DecimalField(max_digits=14, decimal_places=2, default=D0)
    depreciation_method = models.CharField(max_length=30, default="straight_line")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True, related_name="assets")
    asset_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="asset_items",
    )
    depreciation_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="depreciating_assets",
        null=True,
        blank=True,
    )
    expense_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="asset_expense_items",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hotel", "asset_number"], name="uniq_asset_number_per_hotel"),
        ]
        indexes = [
            models.Index(fields=["hotel", "asset_type"]),
            models.Index(fields=["hotel", "status"]),
        ]
        ordering = ["-purchase_date", "name"]
        verbose_name = _("Asset")
        verbose_name_plural = _("Assets")

    def __str__(self):
        return f"{self.asset_number} - {self.name}"

    def save(self, *args, **kwargs):
        if not self.asset_number:
            self.asset_number = f"AST-{timezone.now().strftime('%Y%m')}-{uuid.uuid4().hex[:6].upper()}"
        if not self.current_value:
            self.current_value = Decimal(self.purchase_cost or D0)
        super().save(*args, **kwargs)


class Liability(models.Model):
    class LiabilityType(models.TextChoices):
        SUPPLIER_PAYABLE = "supplier_payable", _("Supplier Payable")
        TAX_PAYABLE = "tax_payable", _("Tax Payable")
        SALARY_PAYABLE = "salary_payable", _("Salary Payable")
        CUSTOMER_DEPOSIT = "customer_deposit", _("Customer Deposit")
        LOAN = "loan", _("Loan")
        ACCRUAL = "accrual", _("Accrual")
        OTHER = "other", _("Other")

    class Status(models.TextChoices):
        OPEN = "open", _("Open")
        PARTIAL = "partial", _("Partial")
        SETTLED = "settled", _("Settled")
        OVERDUE = "overdue", _("Overdue")
        CANCELLED = "cancelled", _("Cancelled")

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="liabilities")
    liability_number = models.CharField(max_length=50)
    liability_type = models.CharField(max_length=30, choices=LiabilityType.choices, default=LiabilityType.OTHER)
    name = models.CharField(max_length=255)
    reference = models.CharField(max_length=100, blank=True, null=True)
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True, related_name="liabilities")
    payable_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="liability_items")
    original_amount = models.DecimalField(max_digits=14, decimal_places=2, default=D0)
    paid_amount = models.DecimalField(max_digits=14, decimal_places=2, default=D0)
    balance = models.DecimalField(max_digits=14, decimal_places=2, default=D0)
    start_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hotel", "liability_number"], name="uniq_liability_number_per_hotel"),
        ]
        indexes = [
            models.Index(fields=["hotel", "liability_type"]),
            models.Index(fields=["hotel", "status"]),
            models.Index(fields=["hotel", "due_date"]),
        ]
        ordering = ["-created_at"]
        verbose_name = _("Liability")
        verbose_name_plural = _("Liabilities")

    def __str__(self):
        return f"{self.liability_number} - {self.name}"

    def save(self, *args, **kwargs):
        if not self.liability_number:
            self.liability_number = f"LIB-{timezone.now().strftime('%Y%m')}-{uuid.uuid4().hex[:6].upper()}"
        self.original_amount = Decimal(self.original_amount or D0)
        self.paid_amount = Decimal(self.paid_amount or D0)
        self.balance = max(self.original_amount - self.paid_amount, D0)

        if self.balance <= D0:
            self.status = self.Status.SETTLED
        elif self.paid_amount > D0:
            self.status = self.Status.PARTIAL
        elif self.due_date and self.due_date < timezone.localdate():
            self.status = self.Status.OVERDUE
        else:
            self.status = self.Status.OPEN

        super().save(*args, **kwargs)

    def apply_payment(self, amount: Decimal):
        amount = Decimal(amount or D0)
        if amount <= D0:
            raise ValidationError(_("Payment amount must be positive."))
        if amount > self.balance:
            raise ValidationError(_("Payment amount exceeds liability balance."))
        self.paid_amount = Decimal(self.paid_amount or D0) + amount
        self.save()


class JournalEntry(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        POSTED = "posted", _("Posted")
        REVERSED = "reversed", _("Reversed")

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="journal_entries")
    entry_number = models.CharField(max_length=50)
    entry_date = models.DateField(default=timezone.localdate)
    reference_type = models.CharField(max_length=50, blank=True, null=True)
    reference_id = models.PositiveBigIntegerField(blank=True, null=True)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_journal_entries",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_journal_entries",
    )
    posted_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hotel", "entry_number"], name="uniq_journal_entry_number_per_hotel"),
        ]
        indexes = [
            models.Index(fields=["hotel", "entry_date"]),
            models.Index(fields=["hotel", "status"]),
            models.Index(fields=["hotel", "reference_type", "reference_id"]),
        ]
        ordering = ["-entry_date", "-created_at"]
        verbose_name = _("Journal Entry")
        verbose_name_plural = _("Journal Entries")

    def __str__(self):
        return self.entry_number

    def save(self, *args, **kwargs):
        if not self.entry_number:
            self.entry_number = f"JE-{timezone.now().strftime('%Y%m')}-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)

    @property
    def total_debits(self) -> Decimal:
        return Decimal(self.lines.aggregate(t=Sum("debit"))["t"] or D0)

    @property
    def total_credits(self) -> Decimal:
        return Decimal(self.lines.aggregate(t=Sum("credit"))["t"] or D0)

    @property
    def is_balanced(self) -> bool:
        return self.total_debits == self.total_credits

    def post(self, user=None):
        if not self.lines.exists():
            raise ValidationError(_("Cannot post a journal entry without lines."))
        if not self.is_balanced:
            raise ValidationError(_("Journal entry is not balanced."))
        self.status = self.Status.POSTED
        self.approved_by = user
        self.posted_at = timezone.now()
        self.save(update_fields=["status", "approved_by", "posted_at", "updated_at"])


class JournalLine(models.Model):
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="journal_lines")
    description = models.CharField(max_length=255, blank=True, null=True)
    debit = models.DecimalField(max_digits=14, decimal_places=2, default=D0)
    credit = models.DecimalField(max_digits=14, decimal_places=2, default=D0)

    class Meta:
        indexes = [
            models.Index(fields=["account"]),
        ]
        verbose_name = _("Journal Line")
        verbose_name_plural = _("Journal Lines")

    def __str__(self):
        return f"{self.account.name}: Dr {self.debit} / Cr {self.credit}"

    def clean(self):
        super().clean()
        debit = Decimal(self.debit or D0)
        credit = Decimal(self.credit or D0)
        if debit < D0 or credit < D0:
            raise ValidationError(_("Debit and credit cannot be negative."))
        if debit == D0 and credit == D0:
            raise ValidationError(_("Either debit or credit must be greater than zero."))
        if debit > D0 and credit > D0:
            raise ValidationError(_("A journal line cannot have both debit and credit values."))


# =========================================================
# INVOICE MANAGEMENT
# =========================================================

class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        PROFORMA = "proforma", _("Proforma")
        ISSUED = "issued", _("Issued")
        SENT = "sent", _("Sent")
        PARTIALLY_PAID = "partially_paid", _("Partially Paid")
        PAID = "paid", _("Paid")
        OVERDUE = "overdue", _("Overdue")
        VOID = "void", _("Void")
        CREDIT_NOTE = "credit_note", _("Credit Note")

    class TaxScheme(models.TextChoices):
        STANDARD = "standard", _("Standard VAT")
        REDUCED = "reduced", _("Reduced VAT")
        ZERO = "zero", _("Zero Rated")
        EXEMPT = "exempt", _("Exempt")

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="invoices")
    booking = models.OneToOneField(
        Booking,
        on_delete=models.PROTECT,
        related_name="invoice",
        null=True,
        blank=True,
    )

    invoice_number = models.CharField(max_length=60)
    invoice_uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    order_number = models.CharField(max_length=60, blank=True, null=True)

    customer_name = models.CharField(max_length=255)
    customer_email = models.EmailField(blank=True, null=True)
    customer_phone = models.CharField(max_length=30, blank=True, null=True)
    customer_address = models.TextField(blank=True, null=True)
    customer_vat = models.CharField(max_length=50, blank=True, null=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    invoice_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(blank=True, null=True)

    tax_scheme = models.CharField(max_length=20, choices=TaxScheme.choices, default=TaxScheme.STANDARD)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=D0)
    tax_number = models.CharField(max_length=50, blank=True, null=True)

    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    discount_type = models.CharField(
        max_length=20,
        choices=[("percentage", _("Percentage")), ("fixed", _("Fixed Amount"))],
        default="fixed",
    )
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=D0)

    currency = models.CharField(max_length=3, default="USD")
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=4, default=Decimal("1.0"))

    # accounting hooks
    receivable_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="invoice_receivables",
        null=True,
        blank=True,
    )
    revenue_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="invoice_revenues",
        null=True,
        blank=True,
    )
    tax_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="invoice_tax_accounts",
        null=True,
        blank=True,
    )

    notes = models.TextField(blank=True, null=True)
    terms_conditions = models.TextField(blank=True, null=True)
    internal_notes = models.TextField(blank=True, null=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_invoices",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    issued_at = models.DateTimeField(blank=True, null=True)
    paid_at = models.DateTimeField(blank=True, null=True)
    voided_at = models.DateTimeField(blank=True, null=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="voided_invoices",
    )
    void_reason = models.TextField(blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hotel", "invoice_number"], name="uniq_invoice_number_per_hotel"),
        ]
        indexes = [
            models.Index(fields=["hotel", "status", "due_date"]),
            models.Index(fields=["hotel", "invoice_date"]),
            models.Index(fields=["customer_email"]),
            models.Index(fields=["invoice_number"]),
        ]
        ordering = ["-invoice_date", "-created_at"]
        verbose_name = _("Invoice")
        verbose_name_plural = _("Invoices")

    def __str__(self):
        return f"Invoice {self.invoice_number} - {self.customer_name}"

    def clean(self):
        super().clean()
        if self.due_date and self.invoice_date and self.due_date <= self.invoice_date:
            raise ValidationError({"due_date": _("Due date must be after invoice date.")})
        if self.discount_type == "percentage" and self.discount < D0:
            raise ValidationError({"discount": _("Discount cannot be negative.")})

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = self.generate_invoice_number()
        if not self.due_date:
            self.due_date = self.invoice_date + timezone.timedelta(days=30)
        self.calculate_totals()
        super().save(*args, **kwargs)

    def generate_invoice_number(self) -> str:
        prefix = "INV"
        inv_date = self.invoice_date or timezone.localdate()
        year = inv_date.strftime("%Y")
        month = inv_date.strftime("%m")

        last_invoice = (
            Invoice.objects.filter(hotel=self.hotel, invoice_number__startswith=f"{prefix}-{year}{month}-")
            .order_by("invoice_number")
            .last()
        )

        if last_invoice and last_invoice.invoice_number:
            try:
                last_num = int(last_invoice.invoice_number.split("-")[-1])
            except Exception:
                last_num = 0
            new_num = last_num + 1
        else:
            new_num = 1

        return f"{prefix}-{year}{month}-{new_num:04d}"

    def _subtotal_from_line_items(self) -> Decimal:
        if self.pk and self.line_items.exists():
            s = self.line_items.aggregate(t=Sum("total"))["t"]
            return Decimal(s or D0)
        return Decimal(self.subtotal or D0)

    def calculate_totals(self):
        subtotal = self._subtotal_from_line_items()
        self.subtotal = subtotal

        discount_value = Decimal(self.discount or D0)

        if self.discount_type == "percentage":
            discount_amount = subtotal * (discount_value / D100)
        else:
            discount_amount = discount_value

        if discount_amount < D0:
            discount_amount = D0
        if discount_amount > subtotal:
            discount_amount = subtotal

        after_discount = subtotal - discount_amount

        tax_rate = Decimal(self.tax_rate or D0)
        if tax_rate < D0:
            tax_rate = D0

        self.tax_amount = after_discount * (tax_rate / D100)
        self.total_amount = after_discount + self.tax_amount

        self.amount_paid = Decimal(self.amount_paid or D0)
        if self.amount_paid < D0:
            self.amount_paid = D0

    @property
    def balance_due(self) -> Decimal:
        return max(Decimal(self.total_amount or D0) - Decimal(self.amount_paid or D0), D0)

    @property
    def is_overdue(self) -> bool:
        return (
            self.status in [self.Status.ISSUED, self.Status.SENT, self.Status.PARTIALLY_PAID, self.Status.OVERDUE]
            and self.due_date is not None
            and self.due_date < timezone.localdate()
            and self.balance_due > D0
        )

    @property
    def is_fully_paid(self) -> bool:
        return self.balance_due <= D0

    def issue(self, user):
        if self.status != self.Status.DRAFT:
            raise ValidationError(_("Only draft invoices can be issued."))

        self.status = self.Status.ISSUED
        self.issued_at = timezone.now()
        self.save()

        InvoiceAuditLog.objects.create(
            invoice=self,
            action=InvoiceAuditLog.Action.ISSUE,
            user=user,
            description=f"Invoice issued by {user.get_full_name() or user.username}",
        )

    def record_payment(self, amount, method, user, reference=None, cash_account=None):
        if self.status == self.Status.VOID:
            raise ValidationError(_("Cannot pay a voided invoice."))

        amount = Decimal(amount or D0)
        if amount <= D0:
            raise ValidationError(_("Payment amount must be positive."))

        payment = Payment.objects.create(
            hotel=self.hotel,
            invoice=self,
            method=method,
            amount=amount,
            reference=reference,
            received_by=user,
            status=Payment.PaymentStatus.COMPLETED,
            cash_account=cash_account,
        )

        self.amount_paid = Decimal(self.amount_paid or D0) + amount

        if self.amount_paid >= Decimal(self.total_amount or D0):
            self.status = self.Status.PAID
            self.paid_at = timezone.now()
        elif self.amount_paid > D0:
            self.status = self.Status.PARTIALLY_PAID

        if self.is_overdue and self.status != self.Status.PAID:
            self.status = self.Status.OVERDUE

        self.save()

        InvoiceAuditLog.objects.create(
            invoice=self,
            action=InvoiceAuditLog.Action.PAYMENT,
            user=user,
            description=f"Payment recorded ({amount} {self.currency}) by {user.get_full_name() or user.username}",
        )
        return payment


class InvoiceLineItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="line_items")
    description = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=D0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=D0)

    booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, null=True, blank=True)
    charge = models.ForeignKey("bookings.AdditionalCharge", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["id"]
        verbose_name = _("Invoice Line Item")
        verbose_name_plural = _("Invoice Line Items")

    def __str__(self):
        return f"{self.description} - {self.total}"

    def clean(self):
        super().clean()
        if self.quantity <= 0:
            raise ValidationError({"quantity": _("Quantity must be at least 1.")})
        if self.unit_price is not None and self.unit_price < D0:
            raise ValidationError({"unit_price": _("Unit price cannot be negative.")})
        if self.discount is not None and self.discount < D0:
            raise ValidationError({"discount": _("Discount cannot be negative.")})

    def save(self, *args, **kwargs):
        qty = Decimal(self.quantity or 0)
        unit = Decimal(self.unit_price or D0)
        disc = Decimal(self.discount or D0)
        line = (qty * unit) - disc
        if line < D0:
            line = D0
        self.total = line
        super().save(*args, **kwargs)


class InvoiceAuditLog(models.Model):
    class Action(models.TextChoices):
        CREATE = "create", _("Created")
        UPDATE = "update", _("Updated")
        ISSUE = "issue", _("Issued")
        SEND = "send", _("Sent")
        PAYMENT = "payment", _("Payment Received")
        VOID = "void", _("Voided")
        EMAIL = "email", _("Email Sent")
        DOWNLOAD = "download", _("Downloaded")

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="audit_logs")
    action = models.CharField(max_length=20, choices=Action.choices)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    description = models.TextField()
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["invoice", "-created_at"])]
        ordering = ["-created_at"]


# =========================================================
# PAYMENTS / REFUNDS
# =========================================================

class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = "cash", _("Cash")
        CREDIT_CARD = "credit_card", _("Credit Card")
        DEBIT_CARD = "debit_card", _("Debit Card")
        MOBILE_MONEY = "mobile_money", _("Mobile Money")
        BANK_TRANSFER = "bank_transfer", _("Bank Transfer")
        CHECK = "check", _("Check")
        ONLINE = "online", _("Online Payment")
        CRYPTO = "crypto", _("Cryptocurrency")
        LOYALTY_POINTS = "loyalty_points", _("Loyalty Points")
        OTHER = "other", _("Other")

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        PROCESSING = "processing", _("Processing")
        COMPLETED = "completed", _("Completed")
        FAILED = "failed", _("Failed")
        REFUNDED = "refunded", _("Refunded")
        PARTIALLY_REFUNDED = "partially_refunded", _("Partially Refunded")
        CANCELLED = "cancelled", _("Cancelled")

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="payments")
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")

    payment_id = models.CharField(max_length=100, unique=True, editable=False)
    transaction_id = models.CharField(max_length=200, blank=True, null=True)

    method = models.CharField(max_length=20, choices=Method.choices, default=Method.CASH)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(D001)])
    currency = models.CharField(max_length=3, default="USD")
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=4, default=Decimal("1.0"))
    status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING, db_index=True)

    cash_account = models.ForeignKey(
        CashAccount,
        on_delete=models.PROTECT,
        related_name="payments",
        null=True,
        blank=True,
    )

    reference = models.CharField(max_length=120, blank=True, null=True)
    authorization_code = models.CharField(max_length=200, blank=True, null=True)
    card_last_four = models.CharField(max_length=4, blank=True, null=True)
    card_type = models.CharField(max_length=50, blank=True, null=True)
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    check_number = models.CharField(max_length=50, blank=True, null=True)

    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="received_payments",
    )
    received_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    notes = models.TextField(blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=["hotel", "received_at", "method"]),
            models.Index(fields=["hotel", "status"]),
            models.Index(fields=["transaction_id"]),
            models.Index(fields=["payment_id"]),
        ]
        ordering = ["-received_at"]

    def __str__(self):
        return f"Payment {self.payment_id} - {self.amount} {self.currency} ({self.get_method_display()})"

    def save(self, *args, **kwargs):
        if not self.payment_id:
            self.payment_id = self.generate_payment_id()
        super().save(*args, **kwargs)

    def generate_payment_id(self):
        return f"PAY{timezone.now().strftime('%y%m%d')}{uuid.uuid4().hex[:6].upper()}"

    def clean(self):
        super().clean()
        if self.invoice_id and self.hotel_id and self.invoice.hotel_id != self.hotel_id:
            raise ValidationError(_("Invoice does not belong to this hotel."))
        if not self.pk and self.invoice_id:
            if Decimal(self.amount or D0) > Decimal(self.invoice.balance_due or D0):
                raise ValidationError(
                    _("Payment amount ({amount}) exceeds invoice balance due ({balance})").format(
                        amount=self.amount,
                        balance=self.invoice.balance_due,
                    )
                )
        if self.cash_account and self.cash_account.hotel_id != self.hotel_id:
            raise ValidationError(_("Cash account does not belong to this hotel."))

    def process_refund(self, amount=None, user=None, reason=None):
        refund_amount = Decimal(amount or self.amount or D0)
        if refund_amount <= D0:
            raise ValidationError(_("Refund amount must be positive."))
        if refund_amount > Decimal(self.amount or D0):
            raise ValidationError(_("Refund amount cannot exceed original payment."))

        if refund_amount == Decimal(self.amount or D0):
            self.status = self.PaymentStatus.REFUNDED
        else:
            self.status = self.PaymentStatus.PARTIALLY_REFUNDED

        self.save()

        refund = Refund.objects.create(
            hotel=self.hotel,
            payment=self,
            amount=refund_amount,
            reason=reason or "Refund processed",
            processed_by=user,
            status=Refund.RefundStatus.COMPLETED,
        )

        self.invoice.amount_paid = max(Decimal(self.invoice.amount_paid or D0) - refund_amount, D0)
        self.invoice.save()

        return refund


class Refund(models.Model):
    class RefundStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        PROCESSING = "processing", _("Processing")
        COMPLETED = "completed", _("Completed")
        FAILED = "failed", _("Failed")

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="refunds")
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="refunds")

    refund_id = models.CharField(max_length=100, unique=True, editable=False)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(D001)])
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=RefundStatus.choices, default=RefundStatus.PENDING, db_index=True)

    processed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    processed_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    notes = models.TextField(blank=True, null=True)

    class Meta:
        indexes = [models.Index(fields=["hotel", "status"])]

    def __str__(self):
        return f"Refund {self.refund_id} - {self.amount}"

    def save(self, *args, **kwargs):
        if not self.refund_id:
            self.refund_id = f"REF-{uuid.uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)


# =========================================================
# EXPENSES
# =========================================================

class Expense(models.Model):
    class Category(models.TextChoices):
        UTILITIES = "utilities", _("Utilities")
        SALARY = "salary", _("Salary")
        MAINTENANCE = "maintenance", _("Maintenance")
        SUPPLIES = "supplies", _("Supplies")
        FOOD_BEVERAGE = "food_beverage", _("Food & Beverage")
        MARKETING = "marketing", _("Marketing")
        INSURANCE = "insurance", _("Insurance")
        RENT = "rent", _("Rent")
        EQUIPMENT = "equipment", _("Equipment")
        SOFTWARE = "software", _("Software")
        TRAINING = "training", _("Training")
        TRAVEL = "travel", _("Travel")
        OTHER = "other", _("Other")

    class PaymentMethod(models.TextChoices):
        CASH = "cash", _("Cash")
        BANK_TRANSFER = "bank_transfer", _("Bank Transfer")
        CREDIT_CARD = "credit_card", _("Credit Card")
        CHECK = "check", _("Check")

    class ApprovalStatus(models.TextChoices):
        DRAFT = "draft", _("Draft")
        PENDING = "pending", _("Pending Approval")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")
        PAID = "paid", _("Paid")
        PARTIAL = "partial", _("Partially Paid")

    class ExpenseType(models.TextChoices):
        OPERATIONAL = "operational", _("Operational Expense")
        CAPITAL = "capital", _("Capital Expenditure")
        PREPAID = "prepaid", _("Prepaid Expense")
        ACCRUAL = "accrual", _("Accrued Expense")

    class Department(models.TextChoices):
        FRONT_OFFICE = "front_office", _("Front Office")
        HOUSEKEEPING = "housekeeping", _("Housekeeping")
        RESTAURANT = "restaurant", _("Restaurant")
        BAR = "bar", _("Bar")
        KITCHEN = "kitchen", _("Kitchen")
        MAINTENANCE = "maintenance", _("Maintenance")
        LAUNDRY = "laundry", _("Laundry")
        ADMIN = "admin", _("Admin")
        SECURITY = "security", _("Security")
        STORE = "store", _("Store")
        SPA = "spa", _("Spa / Services")
        OTHER = "other", _("Other")

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="expenses")
    expense_number = models.CharField(max_length=100)

    category = models.CharField(max_length=30, choices=Category.choices, default=Category.OTHER, db_index=True)
    expense_type = models.CharField(max_length=20, choices=ExpenseType.choices, default=ExpenseType.OPERATIONAL)
    department = models.CharField(max_length=30, choices=Department.choices, default=Department.OTHER, db_index=True)

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(D001)])
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    balance_due = models.DecimalField(max_digits=12, decimal_places=2, default=D0)

    currency = models.CharField(max_length=3, default="USD")

    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    expense_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(blank=True, null=True)
    payment_date = models.DateField(blank=True, null=True)

    payee = models.CharField(max_length=255, blank=True, null=True)
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True, related_name="expenses")
    invoice_reference = models.CharField(max_length=100, blank=True, null=True)

    expense_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="expenses",
        null=True,
        blank=True,
    )
    payable_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="expense_payables",
        null=True,
        blank=True,
    )
    prepaid_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="prepaid_expenses",
        null=True,
        blank=True,
    )
    asset_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="capital_expenses",
        null=True,
        blank=True,
    )
    cash_account = models.ForeignKey(
        CashAccount,
        on_delete=models.PROTECT,
        related_name="expenses",
        null=True,
        blank=True,
    )

    linked_asset = models.ForeignKey(
        Asset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_expenses",
    )
    linked_liability = models.ForeignKey(
        Liability,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_expenses",
    )

    receipt = models.FileField(upload_to="expense_receipts/%Y/%m/", blank=True, null=True)
    receipt_number = models.CharField(max_length=100, blank=True, null=True)

    approval_status = models.CharField(max_length=20, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING, db_index=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expense_requests",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_expenses",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, null=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_expenses",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    notes = models.TextField(blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hotel", "expense_number"], name="uniq_expense_number_per_hotel"),
        ]
        indexes = [
            models.Index(fields=["hotel", "expense_date", "category"]),
            models.Index(fields=["hotel", "approval_status"]),
            models.Index(fields=["hotel", "expense_date"]),
            models.Index(fields=["hotel", "department"]),
            models.Index(fields=["expense_number"]),
        ]
        ordering = ["-expense_date", "-created_at"]
        verbose_name = _("Expense")
        verbose_name_plural = _("Expenses")

    def __str__(self):
        return f"{self.expense_number} - {self.title} ({self.total_amount} {self.currency})"

    def clean(self):
        super().clean()
        if self.vendor and self.vendor.hotel_id != self.hotel_id:
            raise ValidationError(_("Vendor does not belong to this hotel."))
        if self.cash_account and self.cash_account.hotel_id != self.hotel_id:
            raise ValidationError(_("Cash account does not belong to this hotel."))
        for fld in ["expense_account", "payable_account", "prepaid_account", "asset_account"]:
            acc = getattr(self, fld)
            if acc and acc.hotel_id != self.hotel_id:
                raise ValidationError(_("%(field)s does not belong to this hotel.") % {"field": fld})

    def save(self, *args, **kwargs):
        if not self.expense_number:
            self.expense_number = self.generate_expense_number()

        self.total_amount = Decimal(self.amount or D0) + Decimal(self.tax_amount or D0)
        self.paid_amount = Decimal(self.paid_amount or D0)
        self.balance_due = max(Decimal(self.total_amount or D0) - Decimal(self.paid_amount or D0), D0)

        if self.balance_due <= D0 and self.approval_status == self.ApprovalStatus.APPROVED:
            self.approval_status = self.ApprovalStatus.PAID
        elif self.paid_amount > D0 and self.balance_due > D0 and self.approval_status == self.ApprovalStatus.APPROVED:
            self.approval_status = self.ApprovalStatus.PARTIAL

        super().save(*args, **kwargs)

    def generate_expense_number(self):
        prefix = "EXP"
        year = timezone.now().strftime("%Y")
        month = timezone.now().strftime("%m")

        last_expense = (
            Expense.objects.filter(hotel=self.hotel, expense_number__startswith=f"{prefix}{year}{month}")
            .order_by("expense_number")
            .last()
        )

        if last_expense and last_expense.expense_number:
            try:
                last_num = int(last_expense.expense_number[-4:])
            except Exception:
                last_num = 0
            new_num = last_num + 1
        else:
            new_num = 1

        return f"{prefix}{year}{month}{new_num:04d}"

    def approve(self, user):
        if self.approval_status != self.ApprovalStatus.PENDING:
            raise ValidationError(_("Only pending expenses can be approved."))

        self.approval_status = self.ApprovalStatus.APPROVED
        self.approved_by = user
        self.approved_at = timezone.now()
        self.save()

        ExpenseAuditLog.objects.create(
            expense=self,
            action=ExpenseAuditLog.Action.APPROVE,
            user=user,
            description=f"Expense approved by {user.get_full_name() or user.username}",
        )

    def reject(self, user, reason):
        if self.approval_status != self.ApprovalStatus.PENDING:
            raise ValidationError(_("Only pending expenses can be rejected."))

        self.approval_status = self.ApprovalStatus.REJECTED
        self.rejection_reason = reason
        self.save()

        ExpenseAuditLog.objects.create(
            expense=self,
            action=ExpenseAuditLog.Action.REJECT,
            user=user,
            description=f"Expense rejected by {user.get_full_name() or user.username}. Reason: {reason}",
        )

    @transaction.atomic
    def mark_paid(self, user, amount=None, cash_account=None):
        if self.approval_status not in [self.ApprovalStatus.APPROVED, self.ApprovalStatus.PARTIAL]:
            raise ValidationError(_("Only approved or partially paid expenses can be paid."))

        amount = Decimal(amount or self.balance_due or D0)
        if amount <= D0:
            raise ValidationError(_("Payment amount must be positive."))
        if amount > self.balance_due:
            raise ValidationError(_("Payment exceeds expense balance."))

        if cash_account:
            if cash_account.hotel_id != self.hotel_id:
                raise ValidationError(_("Cash account does not belong to this hotel."))
            self.cash_account = cash_account

        self.paid_amount = Decimal(self.paid_amount or D0) + amount
        self.payment_date = timezone.localdate()

        if self.linked_liability:
            self.linked_liability.apply_payment(amount)

        self.save()

        ExpenseAuditLog.objects.create(
            expense=self,
            action=ExpenseAuditLog.Action.PAID,
            user=user,
            description=f"Expense payment recorded: {amount} {self.currency}",
        )


class ExpenseAuditLog(models.Model):
    class Action(models.TextChoices):
        CREATE = "create", _("Created")
        UPDATE = "update", _("Updated")
        SUBMIT = "submit", _("Submitted for Approval")
        APPROVE = "approve", _("Approved")
        REJECT = "reject", _("Rejected")
        PAID = "paid", _("Marked Paid")
        RECEIPT = "receipt", _("Receipt Uploaded")

    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name="audit_logs")
    action = models.CharField(max_length=20, choices=Action.choices)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["expense", "-created_at"])]
        ordering = ["-created_at"]


# =========================================================
# PERIODS
# =========================================================

class FinancialPeriod(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", _("Open")
        CLOSING = "closing", _("Closing")
        CLOSED = "closed", _("Closed")
        LOCKED = "locked", _("Locked")

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="financial_periods")

    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)

    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="closed_periods",
    )
    closed_at = models.DateTimeField(null=True, blank=True)

    total_revenue = models.DecimalField(max_digits=14, decimal_places=2, default=D0)
    total_expenses = models.DecimalField(max_digits=14, decimal_places=2, default=D0)
    net_profit = models.DecimalField(max_digits=14, decimal_places=2, default=D0)

    notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hotel", "name"], name="uniq_period_name_per_hotel"),
        ]
        indexes = [
            models.Index(fields=["hotel", "start_date", "end_date"]),
            models.Index(fields=["hotel", "status"]),
        ]
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.name} - {self.hotel.name}"

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            raise ValidationError(_("End date must be after start date."))

        overlapping = (
            FinancialPeriod.objects.filter(
                hotel=self.hotel,
                start_date__lt=self.end_date,
                end_date__gt=self.start_date,
            ).exclude(pk=self.pk)
        )

        if overlapping.exists():
            raise ValidationError(_("Period overlaps with existing financial period."))

    def close(self, user):
        if self.status == self.Status.CLOSED:
            raise ValidationError(_("Period already closed."))

        revenue_total = JournalLine.objects.filter(
            journal_entry__hotel=self.hotel,
            journal_entry__status=JournalEntry.Status.POSTED,
            journal_entry__entry_date__gte=self.start_date,
            journal_entry__entry_date__lte=self.end_date,
            account__account_type=Account.AccountType.REVENUE,
        ).aggregate(t=Sum("credit"))["t"] or D0

        expense_total = JournalLine.objects.filter(
            journal_entry__hotel=self.hotel,
            journal_entry__status=JournalEntry.Status.POSTED,
            journal_entry__entry_date__gte=self.start_date,
            journal_entry__entry_date__lte=self.end_date,
            account__account_type=Account.AccountType.EXPENSE,
        ).aggregate(t=Sum("debit"))["t"] or D0

        self.total_revenue = Decimal(revenue_total or D0)
        self.total_expenses = Decimal(expense_total or D0)
        self.net_profit = self.total_revenue - self.total_expenses

        self.status = self.Status.CLOSED
        self.closed_by = user
        self.closed_at = timezone.now()
        self.save()