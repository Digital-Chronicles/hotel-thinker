# finance/models.py
from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Sum, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from hotels.models import Hotel
from bookings.models import Booking


D0 = Decimal("0")
D001 = Decimal("0.01")
D100 = Decimal("100")


class Invoice(models.Model):
    """Professional invoice management with tax compliance"""

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

    # Invoice identification
    # FIX: do NOT set unique=True globally; we enforce uniqueness per hotel in Meta.
    invoice_number = models.CharField(max_length=60)
    invoice_uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    order_number = models.CharField(max_length=60, blank=True, null=True)

    # Customer details (denormalized for historical accuracy)
    customer_name = models.CharField(max_length=255)
    customer_email = models.EmailField(blank=True, null=True)
    customer_phone = models.CharField(max_length=30, blank=True, null=True)
    customer_address = models.TextField(blank=True, null=True)
    customer_vat = models.CharField(max_length=50, blank=True, null=True)

    # Invoice details
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    invoice_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(blank=True, null=True)

    # Tax information
    tax_scheme = models.CharField(
        max_length=20,
        choices=TaxScheme.choices,
        default=TaxScheme.STANDARD,
    )
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=D0)
    tax_number = models.CharField(max_length=50, blank=True, null=True)

    # Financial breakdown
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    discount_type = models.CharField(
        max_length=20,
        choices=[
            ("percentage", _("Percentage")),
            ("fixed", _("Fixed Amount")),
        ],
        default="fixed",
    )
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=D0)

    # Currency
    currency = models.CharField(max_length=3, default="USD")
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=4, default=Decimal("1.0"))

    # Notes
    notes = models.TextField(blank=True, null=True)
    terms_conditions = models.TextField(blank=True, null=True)
    internal_notes = models.TextField(blank=True, null=True)

    # Metadata
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
        # Ensure invoice number
        if not self.invoice_number:
            self.invoice_number = self.generate_invoice_number()

        # Ensure due date (default 30 days)
        if not self.due_date:
            self.due_date = self.invoice_date + timezone.timedelta(days=30)

        # Recalculate totals
        self.calculate_totals()

        super().save(*args, **kwargs)

    def generate_invoice_number(self) -> str:
        """Generate unique invoice number per hotel + month: INV-YYYYMM-0001"""
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
        """
        If line items exist, sum their totals; otherwise use the stored subtotal field.
        """
        if self.pk and self.line_items.exists():
            s = self.line_items.aggregate(t=Sum("total"))["t"]
            return Decimal(s or D0)
        return Decimal(self.subtotal or D0)

    def calculate_totals(self):
        """Calculate all invoice totals safely using Decimals."""
        subtotal = self._subtotal_from_line_items()
        self.subtotal = subtotal

        discount_value = Decimal(self.discount or D0)

        # Apply discount
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

        # Keep amount_paid safe
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

    def mark_sent(self, user):
        if self.status not in [self.Status.ISSUED, self.Status.DRAFT]:
            raise ValidationError(_("Invoice cannot be marked as sent."))

        self.status = self.Status.SENT
        self.save()

        InvoiceAuditLog.objects.create(
            invoice=self,
            action=InvoiceAuditLog.Action.SEND,
            user=user,
            description=f"Invoice marked as sent by {user.get_full_name() or user.username}",
        )

    def record_payment(self, amount, method, user, reference=None):
        """Record a payment against this invoice"""
        if self.status == self.Status.VOID:
            raise ValidationError(_("Cannot pay a voided invoice."))

        amount = Decimal(amount or D0)
        if amount <= D0:
            raise ValidationError(_("Payment amount must be positive."))

        # Create payment (COMPLETED by default)
        payment = Payment.objects.create(
            hotel=self.hotel,
            invoice=self,
            method=method,
            amount=amount,
            reference=reference,
            received_by=user,
            status=Payment.PaymentStatus.COMPLETED,
        )

        # Update invoice amounts/status
        self.amount_paid = Decimal(self.amount_paid or D0) + amount

        if self.amount_paid >= Decimal(self.total_amount or D0):
            self.status = self.Status.PAID
            self.paid_at = timezone.now()
        elif self.amount_paid > D0:
            self.status = self.Status.PARTIALLY_PAID

        # If invoice is late and still not paid, mark overdue
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

    def void(self, user, reason):
        if self.status == self.Status.PAID:
            raise ValidationError(_("Cannot void a paid invoice. Create a credit note instead."))

        self.status = self.Status.VOID
        self.voided_at = timezone.now()
        self.voided_by = user
        self.void_reason = reason
        self.save()

        InvoiceAuditLog.objects.create(
            invoice=self,
            action=InvoiceAuditLog.Action.VOID,
            user=user,
            description=f"Invoice voided by {user.get_full_name() or user.username}. Reason: {reason}",
        )

    def create_credit_note(self, user, reason):
        if self.status != self.Status.PAID:
            raise ValidationError(_("Credit notes can only be created for paid invoices."))

        credit_note = Invoice.objects.create(
            hotel=self.hotel,
            booking=self.booking,
            invoice_number=f"CN-{self.invoice_number}",
            customer_name=self.customer_name,
            customer_email=self.customer_email,
            customer_phone=self.customer_phone,
            status=Invoice.Status.CREDIT_NOTE,
            invoice_date=timezone.localdate(),
            due_date=timezone.localdate(),
            subtotal=-Decimal(self.subtotal or D0),
            discount=-Decimal(self.discount or D0),
            tax_amount=-Decimal(self.tax_amount or D0),
            total_amount=-Decimal(self.total_amount or D0),
            notes=f"Credit note for invoice {self.invoice_number}. Reason: {reason}",
            created_by=user,
        )
        return credit_note


class InvoiceLineItem(models.Model):
    """Detailed line items for invoices"""

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="line_items")
    description = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=D0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=D0)

    # Reference to source
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
    """Audit trail for invoice actions"""

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
        indexes = [
            models.Index(fields=["invoice", "-created_at"]),
        ]
        ordering = ["-created_at"]
        verbose_name = _("Invoice Audit Log")
        verbose_name_plural = _("Invoice Audit Logs")

    def __str__(self):
        return f"{self.invoice.invoice_number} - {self.action} at {self.created_at}"


class Payment(models.Model):
    """Comprehensive payment tracking"""

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
        verbose_name = _("Payment")
        verbose_name_plural = _("Payments")

    def __str__(self):
        return f"Payment {self.payment_id} - {self.amount} {self.currency} ({self.get_method_display()})"

    def save(self, *args, **kwargs):
        if not self.payment_id:
            self.payment_id = self.generate_payment_id()
        super().save(*args, **kwargs)

    def generate_payment_id(self):
        prefix = "PAY"
        date_part = timezone.now().strftime("%y%m%d")
        random_part = uuid.uuid4().hex[:6].upper()
        return f"{prefix}{date_part}{random_part}"

    def clean(self):
        super().clean()

        if self.invoice_id and self.hotel_id and self.invoice.hotel_id != self.hotel_id:
            raise ValidationError(_("Invoice does not belong to this hotel."))

        # For new payments only, prevent over-paying invoice
        if not self.pk and self.invoice_id:
            if Decimal(self.amount or D0) > Decimal(self.invoice.balance_due or D0):
                raise ValidationError(
                    _("Payment amount ({amount}) exceeds invoice balance due ({balance})").format(
                        amount=self.amount,
                        balance=self.invoice.balance_due,
                    )
                )

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

        # Update invoice
        self.invoice.amount_paid = max(Decimal(self.invoice.amount_paid or D0) - refund_amount, D0)
        self.invoice.save()

        InvoiceAuditLog.objects.create(
            invoice=self.invoice,
            action=InvoiceAuditLog.Action.UPDATE,
            user=user,
            description=f"Refund processed ({refund_amount} {self.currency}). Reason: {reason or 'N/A'}",
        )

        return refund


class Refund(models.Model):
    """Refund tracking"""

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
        indexes = [
            models.Index(fields=["hotel", "status"]),
        ]
        verbose_name = _("Refund")
        verbose_name_plural = _("Refunds")

    def __str__(self):
        return f"Refund {self.refund_id} - {self.amount}"

    def save(self, *args, **kwargs):
        if not self.refund_id:
            self.refund_id = f"REF-{uuid.uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)


class Expense(models.Model):
    """Professional expense tracking with approval workflow"""

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

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="expenses")

    # FIX: make expense_number unique per hotel (not globally)
    expense_number = models.CharField(max_length=100)

    category = models.CharField(max_length=30, choices=Category.choices, default=Category.OTHER, db_index=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(D001)])
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    currency = models.CharField(max_length=3, default="USD")

    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    payment_date = models.DateField()
    payee = models.CharField(max_length=255, blank=True, null=True)
    vendor = models.CharField(max_length=255, blank=True, null=True)
    invoice_reference = models.CharField(max_length=100, blank=True, null=True)

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
            models.Index(fields=["hotel", "payment_date", "category"]),
            models.Index(fields=["hotel", "approval_status"]),
            models.Index(fields=["hotel", "payment_date"]),
            models.Index(fields=["expense_number"]),
        ]
        ordering = ["-payment_date", "-created_at"]
        verbose_name = _("Expense")
        verbose_name_plural = _("Expenses")

    def __str__(self):
        return f"{self.expense_number} - {self.title} ({self.amount} {self.currency})"

    def save(self, *args, **kwargs):
        if not self.expense_number:
            self.expense_number = self.generate_expense_number()
        self.total_amount = Decimal(self.amount or D0) + Decimal(self.tax_amount or D0)
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

    def mark_paid(self, user):
        if self.approval_status != self.ApprovalStatus.APPROVED:
            raise ValidationError(_("Only approved expenses can be marked as paid."))

        self.approval_status = self.ApprovalStatus.PAID
        self.save()

        ExpenseAuditLog.objects.create(
            expense=self,
            action=ExpenseAuditLog.Action.PAID,
            user=user,
            description=f"Expense marked as paid by {user.get_full_name() or user.username}",
        )


class ExpenseAuditLog(models.Model):
    """Audit trail for expense actions"""

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
        indexes = [
            models.Index(fields=["expense", "-created_at"]),
        ]
        ordering = ["-created_at"]
        verbose_name = _("Expense Audit Log")
        verbose_name_plural = _("Expense Audit Logs")

    def __str__(self):
        return f"{self.expense.expense_number} - {self.action} at {self.created_at}"


class FinancialPeriod(models.Model):
    """Financial periods for closing accounting cycles"""

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
        verbose_name = _("Financial Period")
        verbose_name_plural = _("Financial Periods")

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
            )
            .exclude(pk=self.pk)
        )

        if overlapping.exists():
            raise ValidationError(_("Period overlaps with existing financial period."))

    def close(self, user):
        if self.status == self.Status.CLOSED:
            raise ValidationError(_("Period already closed."))

        self.total_revenue = (
            Payment.objects.filter(
                hotel=self.hotel,
                status=Payment.PaymentStatus.COMPLETED,
                received_at__date__gte=self.start_date,
                received_at__date__lte=self.end_date,
            ).aggregate(total=Sum("amount"))["total"]
            or D0
        )

        self.total_expenses = (
            Expense.objects.filter(
                hotel=self.hotel,
                payment_date__gte=self.start_date,
                payment_date__lte=self.end_date,
                approval_status=Expense.ApprovalStatus.PAID,
            ).aggregate(total=Sum("total_amount"))["total"]
            or D0
        )

        self.net_profit = Decimal(self.total_revenue or D0) - Decimal(self.total_expenses or D0)

        self.status = self.Status.CLOSED
        self.closed_by = user
        self.closed_at = timezone.now()
        self.save()