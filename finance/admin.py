# finance/admin.py
from __future__ import annotations

from decimal import Decimal
from .models import CashMovement
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html

from .models import (
    Account,
    Vendor,
    CashAccount,
    Asset,
    Liability,
    JournalEntry,
    JournalLine,
    Invoice,
    InvoiceLineItem,
    InvoiceAuditLog,
    Payment,
    Refund,
    Expense,
    ExpenseAuditLog,
    FinancialPeriod,
)


# ----------------------------
# Helpers
# ----------------------------
def badge(text: str, kind: str = "gray"):
    colors = {
        "gray": ("#334155", "#f1f5f9", "#e2e8f0"),
        "green": ("#166534", "#dcfce7", "#86efac"),
        "yellow": ("#854d0e", "#fef9c3", "#fde047"),
        "red": ("#991b1b", "#fee2e2", "#fca5a5"),
        "blue": ("#1e40af", "#dbeafe", "#93c5fd"),
        "purple": ("#6b21a8", "#f3e8ff", "#d8b4fe"),
    }
    fg, bg, border = colors.get(kind, colors["gray"])
    return format_html(
        '<span style="display:inline-block; padding:2px 8px; border-radius:999px; '
        'font-size:12px; font-weight:600; color:{}; background:{}; border:1px solid {};">{}</span>',
        fg,
        bg,
        border,
        text,
    )


# ----------------------------
# Inlines
# ----------------------------
class InvoiceLineItemInline(admin.TabularInline):
    model = InvoiceLineItem
    extra = 0
    fields = ("description", "quantity", "unit_price", "discount", "tax_rate", "total", "booking", "charge")
    readonly_fields = ("total",)
    autocomplete_fields = ("booking", "charge")


class InvoiceAuditLogInline(admin.TabularInline):
    model = InvoiceAuditLog
    extra = 0
    fields = ("created_at", "action", "user", "description", "ip_address")
    readonly_fields = ("created_at", "action", "user", "description", "ip_address")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    fields = (
        "payment_id",
        "method",
        "amount",
        "currency",
        "status",
        "cash_account",
        "reference",
        "received_by",
        "received_at",
    )
    readonly_fields = ("payment_id", "received_at")
    can_delete = False
    autocomplete_fields = ("received_by", "cash_account")


class ExpenseAuditLogInline(admin.TabularInline):
    model = ExpenseAuditLog
    extra = 0
    fields = ("created_at", "action", "user", "description")
    readonly_fields = ("created_at", "action", "user", "description")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class JournalLineInline(admin.TabularInline):
    model = JournalLine
    extra = 0
    fields = ("account", "description", "debit", "credit")
    autocomplete_fields = ("account",)


# ----------------------------
# Account Admin
# ----------------------------
@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = (
        "account_code",
        "name",
        "hotel",
        "account_type_badge",
        "account_subtype",
        "parent",
        "balance_value",
        "active_badge",
        "is_system",
    )
    list_filter = ("hotel", "account_type", "account_subtype", "is_active", "is_system")
    search_fields = ("account_code", "name", "description")
    ordering = ("hotel", "account_code", "name")
    autocomplete_fields = ("hotel", "parent")
    readonly_fields = ("created_at", "updated_at", "balance_value")
    fieldsets = (
        (_("Account"), {"fields": ("hotel", "account_code", "name", "account_type", "account_subtype", "parent")}),
        (_("Details"), {"fields": ("description", "is_active", "is_system", "balance_value")}),
        (_("Audit"), {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description=_("Type"), ordering="account_type")
    def account_type_badge(self, obj: Account):
        mapping = {
            Account.AccountType.ASSET: ("ASSET", "green"),
            Account.AccountType.LIABILITY: ("LIABILITY", "red"),
            Account.AccountType.EQUITY: ("EQUITY", "purple"),
            Account.AccountType.REVENUE: ("REVENUE", "blue"),
            Account.AccountType.EXPENSE: ("EXPENSE", "yellow"),
        }
        text, kind = mapping.get(obj.account_type, (obj.account_type, "gray"))
        return badge(text, kind)

    @admin.display(description=_("Balance"))
    def balance_value(self, obj: Account):
        return obj.balance

    @admin.display(description=_("Active"), ordering="is_active")
    def active_badge(self, obj: Account):
        return badge(_("ACTIVE"), "green") if obj.is_active else badge(_("INACTIVE"), "gray")


# ----------------------------
# Vendor Admin
# ----------------------------
@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("vendor_code", "name", "hotel", "phone", "email", "payable_balance_value", "active_badge")
    list_filter = ("hotel", "is_active")
    search_fields = ("vendor_code", "name", "contact_person", "phone", "email", "tin_number")
    ordering = ("hotel", "name")
    autocomplete_fields = ("hotel",)
    readonly_fields = ("created_at", "updated_at", "payable_balance_value")
    fieldsets = (
        (_("Vendor"), {"fields": ("hotel", "vendor_code", "name", "contact_person")}),
        (_("Contacts"), {"fields": ("phone", "email", "address", "tin_number")}),
        (_("Finance"), {"fields": ("opening_balance", "payable_balance_value", "is_active")}),
        (_("Notes"), {"fields": ("notes",)}),
        (_("Audit"), {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description=_("Payable Balance"))
    def payable_balance_value(self, obj: Vendor):
        return obj.payable_balance

    @admin.display(description=_("Active"), ordering="is_active")
    def active_badge(self, obj: Vendor):
        return badge(_("ACTIVE"), "green") if obj.is_active else badge(_("INACTIVE"), "gray")


# ----------------------------
# Cash Account Admin
# ----------------------------
@admin.register(CashAccount)
class CashAccountAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "hotel",
        "account_type_badge",
        "currency",
        "opening_balance",
        "current_balance",
        "gl_account",
        "active_badge",
    )
    list_filter = ("hotel", "account_type", "currency", "is_active")
    search_fields = ("name", "account_number", "gl_account__name", "gl_account__account_code")
    ordering = ("hotel", "name")
    autocomplete_fields = ("hotel", "gl_account")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (_("Cash / Bank Account"), {"fields": ("hotel", "name", "account_type", "account_number", "currency")}),
        (_("Balances"), {"fields": ("opening_balance", "current_balance", "gl_account", "is_active")}),
        (_("Notes"), {"fields": ("notes",)}),
        (_("Audit"), {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description=_("Type"), ordering="account_type")
    def account_type_badge(self, obj: CashAccount):
        mapping = {
            CashAccount.AccountType.CASH: ("CASH", "green"),
            CashAccount.AccountType.BANK: ("BANK", "blue"),
            CashAccount.AccountType.MOBILE_MONEY: ("MOBILE MONEY", "yellow"),
        }
        text, kind = mapping.get(obj.account_type, (obj.account_type, "gray"))
        return badge(text, kind)

    @admin.display(description=_("Active"), ordering="is_active")
    def active_badge(self, obj: CashAccount):
        return badge(_("ACTIVE"), "green") if obj.is_active else badge(_("INACTIVE"), "gray")


# ----------------------------
# Asset Admin
# ----------------------------
@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = (
        "asset_number",
        "name",
        "hotel",
        "asset_type",
        "purchase_date",
        "purchase_cost",
        "current_value",
        "status_badge",
        "vendor",
    )
    list_filter = ("hotel", "asset_type", "status", "purchase_date")
    search_fields = ("asset_number", "name", "description", "location", "vendor__name")
    ordering = ("-purchase_date", "name")
    autocomplete_fields = (
        "hotel",
        "vendor",
        "asset_account",
        "depreciation_account",
        "expense_account",
        "created_by",
    )
    readonly_fields = ("asset_number", "created_at", "updated_at")
    fieldsets = (
        (_("Asset"), {"fields": ("hotel", "asset_number", "asset_type", "name", "description", "status")}),
        (_("Valuation"), {"fields": ("purchase_date", "purchase_cost", "current_value", "salvage_value")}),
        (_("Depreciation"), {"fields": ("useful_life_months", "accumulated_depreciation", "depreciation_method")}),
        (_("Accounts"), {"fields": ("asset_account", "depreciation_account", "expense_account")}),
        (_("Links"), {"fields": ("vendor", "location", "created_by")}),
        (_("Audit"), {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description=_("Status"), ordering="status")
    def status_badge(self, obj: Asset):
        mapping = {
            Asset.Status.ACTIVE: ("ACTIVE", "green"),
            Asset.Status.DISPOSED: ("DISPOSED", "gray"),
            Asset.Status.DAMAGED: ("DAMAGED", "red"),
            Asset.Status.INACTIVE: ("INACTIVE", "yellow"),
        }
        text, kind = mapping.get(obj.status, (obj.status, "gray"))
        return badge(text, kind)


# ----------------------------
# Liability Admin
# ----------------------------
@admin.register(Liability)
class LiabilityAdmin(admin.ModelAdmin):
    list_display = (
        "liability_number",
        "name",
        "hotel",
        "liability_type",
        "vendor",
        "original_amount",
        "paid_amount",
        "balance",
        "due_date",
        "status_badge",
    )
    list_filter = ("hotel", "liability_type", "status", "due_date")
    search_fields = ("liability_number", "name", "reference", "vendor__name")
    ordering = ("-created_at",)
    autocomplete_fields = ("hotel", "vendor", "payable_account", "created_by")
    readonly_fields = ("liability_number", "balance", "created_at", "updated_at")
    fieldsets = (
        (_("Liability"), {"fields": ("hotel", "liability_number", "liability_type", "name", "reference", "status")}),
        (_("Amounts"), {"fields": ("original_amount", "paid_amount", "balance")}),
        (_("Dates"), {"fields": ("start_date", "due_date")}),
        (_("Accounts"), {"fields": ("vendor", "payable_account", "created_by")}),
        (_("Notes"), {"fields": ("notes",)}),
        (_("Audit"), {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description=_("Status"), ordering="status")
    def status_badge(self, obj: Liability):
        mapping = {
            Liability.Status.OPEN: ("OPEN", "yellow"),
            Liability.Status.PARTIAL: ("PARTIAL", "blue"),
            Liability.Status.SETTLED: ("SETTLED", "green"),
            Liability.Status.OVERDUE: ("OVERDUE", "red"),
            Liability.Status.CANCELLED: ("CANCELLED", "gray"),
        }
        text, kind = mapping.get(obj.status, (obj.status, "gray"))
        return badge(text, kind)


# ----------------------------
# Journal Admin
# ----------------------------
@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = (
        "entry_number",
        "hotel",
        "entry_date",
        "reference_type",
        "reference_id",
        "description_short",
        "status_badge",
        "total_debits_value",
        "total_credits_value",
        "balanced_badge",
    )
    list_filter = ("hotel", "status", "entry_date", "reference_type")
    search_fields = ("entry_number", "description", "reference_type")
    ordering = ("-entry_date", "-created_at")
    autocomplete_fields = ("hotel", "created_by", "approved_by")
    readonly_fields = (
        "entry_number",
        "posted_at",
        "created_at",
        "updated_at",
        "total_debits_value",
        "total_credits_value",
        "balanced_badge",
    )
    inlines = (JournalLineInline,)
    actions = ("action_post_entries",)

    fieldsets = (
        (_("Journal"), {"fields": ("hotel", "entry_number", "entry_date", "status")}),
        (_("Reference"), {"fields": ("reference_type", "reference_id", "description")}),
        (_("Totals"), {"fields": ("total_debits_value", "total_credits_value", "balanced_badge")}),
        (_("Audit"), {"fields": ("created_by", "approved_by", "posted_at", "created_at", "updated_at")}),
    )

    @admin.display(description=_("Description"))
    def description_short(self, obj: JournalEntry):
        return (obj.description[:60] + "...") if obj.description and len(obj.description) > 60 else obj.description

    @admin.display(description=_("Status"), ordering="status")
    def status_badge(self, obj: JournalEntry):
        mapping = {
            JournalEntry.Status.DRAFT: ("DRAFT", "yellow"),
            JournalEntry.Status.POSTED: ("POSTED", "green"),
            JournalEntry.Status.REVERSED: ("REVERSED", "gray"),
        }
        text, kind = mapping.get(obj.status, (obj.status, "gray"))
        return badge(text, kind)

    @admin.display(description=_("Debits"))
    def total_debits_value(self, obj: JournalEntry):
        return obj.total_debits

    @admin.display(description=_("Credits"))
    def total_credits_value(self, obj: JournalEntry):
        return obj.total_credits

    @admin.display(description=_("Balanced"))
    def balanced_badge(self, obj: JournalEntry):
        return badge(_("YES"), "green") if obj.is_balanced else badge(_("NO"), "red")

    @admin.action(description=_("Post selected journal entries"))
    def action_post_entries(self, request, queryset):
        ok = 0
        for entry in queryset:
            try:
                if entry.status == JournalEntry.Status.DRAFT:
                    entry.post(request.user)
                    ok += 1
            except ValidationError as e:
                self.message_user(request, f"{entry.entry_number}: {', '.join(e.messages)}", level=messages.ERROR)
        if ok:
            self.message_user(request, _(f"Posted {ok} journal entr(y/ies)."), level=messages.SUCCESS)


@admin.register(JournalLine)
class JournalLineAdmin(admin.ModelAdmin):
    list_display = ("journal_entry", "account", "description", "debit", "credit")
    list_filter = ("journal_entry__hotel", "account__account_type", "account__account_subtype")
    search_fields = ("journal_entry__entry_number", "account__name", "description")
    autocomplete_fields = ("journal_entry", "account")
    ordering = ("-journal_entry__entry_date", "id")


# ----------------------------
# Invoice Admin
# ----------------------------
@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "invoice_number",
        "hotel",
        "customer_name",
        "invoice_date",
        "due_date",
        "status_badge",
        "payment_badge",
        "total_amount",
        "amount_paid",
        "balance_due_value",
        "overdue_badge",
    )
    list_filter = ("hotel", "status", "invoice_date", "due_date", "tax_scheme", "currency")
    search_fields = ("invoice_number", "customer_name", "customer_email", "order_number", "booking__booking_number")
    date_hierarchy = "invoice_date"
    ordering = ("-invoice_date", "-created_at")
    autocomplete_fields = (
        "hotel",
        "booking",
        "created_by",
        "voided_by",
        "receivable_account",
        "revenue_account",
        "tax_account",
    )
    inlines = (InvoiceLineItemInline, PaymentInline, InvoiceAuditLogInline)

    readonly_fields = (
        "invoice_uuid",
        "subtotal",
        "tax_amount",
        "total_amount",
        "amount_paid",
        "created_at",
        "updated_at",
        "issued_at",
        "paid_at",
        "voided_at",
        "balance_due_value",
        "overdue_badge",
    )

    fieldsets = (
        (_("Invoice Identification"), {"fields": ("hotel", "booking", "invoice_number", "invoice_uuid", "order_number")}),
        (_("Customer Details"), {"fields": ("customer_name", "customer_email", "customer_phone", "customer_address", "customer_vat")}),
        (_("Invoice Details"), {"fields": ("status", "invoice_date", "due_date")}),
        (_("Tax"), {"fields": ("tax_scheme", "tax_rate", "tax_number", "tax_account")}),
        (_("Amounts"), {"fields": ("subtotal", "discount", "discount_type", "tax_amount", "total_amount", "amount_paid", "balance_due_value", "currency", "exchange_rate")}),
        (_("Accounting"), {"fields": ("receivable_account", "revenue_account")}),
        (_("Notes"), {"fields": ("notes", "terms_conditions", "internal_notes")}),
        (_("Voiding"), {"fields": ("voided_by", "voided_at", "void_reason")}),
        (_("Audit"), {"fields": ("created_by", "created_at", "updated_at", "issued_at", "paid_at", "overdue_badge")}),
    )

    actions = ("action_issue", "action_mark_paid_force")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("hotel", "booking")

    @admin.display(description=_("Balance Due"), ordering="total_amount")
    def balance_due_value(self, obj: Invoice):
        return obj.balance_due

    @admin.display(description=_("Overdue"))
    def overdue_badge(self, obj: Invoice):
        return badge(_("OVERDUE"), "red") if obj.is_overdue else badge(_("OK"), "green")

    @admin.display(description=_("Status"), ordering="status")
    def status_badge(self, obj: Invoice):
        mapping = {
            Invoice.Status.DRAFT: ("DRAFT", "gray"),
            Invoice.Status.PROFORMA: ("PROFORMA", "blue"),
            Invoice.Status.ISSUED: ("ISSUED", "blue"),
            Invoice.Status.SENT: ("SENT", "blue"),
            Invoice.Status.PARTIALLY_PAID: ("PART PAID", "yellow"),
            Invoice.Status.PAID: ("PAID", "green"),
            Invoice.Status.OVERDUE: ("OVERDUE", "red"),
            Invoice.Status.VOID: ("VOID", "gray"),
            Invoice.Status.CREDIT_NOTE: ("CREDIT", "gray"),
        }
        text, kind = mapping.get(obj.status, (obj.status, "gray"))
        return badge(text, kind)

    @admin.display(description=_("Payment"))
    def payment_badge(self, obj: Invoice):
        if obj.balance_due <= 0:
            return badge(_("FULLY PAID"), "green")
        if obj.amount_paid > 0:
            return badge(_("PARTIAL"), "yellow")
        return badge(_("UNPAID"), "gray")

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.action(description=_("Issue selected invoices"))
    def action_issue(self, request, queryset):
        ok = 0
        for inv in queryset:
            try:
                inv.issue(request.user)
                ok += 1
            except ValidationError as e:
                self.message_user(request, f"{inv.invoice_number}: {', '.join(e.messages)}", level=messages.ERROR)
        if ok:
            self.message_user(request, _(f"Issued {ok} invoice(s)."), level=messages.SUCCESS)

    @admin.action(description=_("Mark selected invoices as paid (force)"))
    def action_mark_paid_force(self, request, queryset):
        updated = queryset.update(status=Invoice.Status.PAID, paid_at=timezone.now())
        self.message_user(request, _(f"Marked {updated} invoice(s) as paid."), level=messages.SUCCESS)


@admin.register(InvoiceLineItem)
class InvoiceLineItemAdmin(admin.ModelAdmin):
    list_display = ("invoice", "description", "quantity", "unit_price", "discount", "tax_rate", "total")
    list_filter = ("invoice__hotel",)
    search_fields = ("description", "invoice__invoice_number")
    autocomplete_fields = ("invoice", "booking", "charge")
    readonly_fields = ("total",)
    ordering = ("-id",)


@admin.register(InvoiceAuditLog)
class InvoiceAuditLogAdmin(admin.ModelAdmin):
    list_display = ("invoice", "action", "user", "created_at")
    list_filter = ("action", "created_at")
    search_fields = ("invoice__invoice_number", "description", "user__username")
    autocomplete_fields = ("invoice", "user")
    readonly_fields = ("invoice", "action", "user", "description", "ip_address", "created_at")
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ----------------------------
# Payment Admin
# ----------------------------
@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "payment_id",
        "hotel",
        "invoice",
        "method",
        "amount",
        "currency",
        "cash_account",
        "status_badge",
        "received_by",
        "received_at",
    )
    list_filter = ("hotel", "method", "status", "received_at", "currency")
    search_fields = ("payment_id", "transaction_id", "reference", "invoice__invoice_number")
    date_hierarchy = "received_at"
    ordering = ("-received_at",)
    autocomplete_fields = ("hotel", "invoice", "received_by", "cash_account")
    readonly_fields = ("payment_id", "received_at", "updated_at")

    fieldsets = (
        (_("Links"), {"fields": ("hotel", "invoice", "cash_account")}),
        (_("Payment IDs"), {"fields": ("payment_id", "transaction_id")}),

        (_("Payment Details"), {"fields": ("method", "amount", "currency", "exchange_rate", "status")}),
        (_("References"), {"fields": ("reference", "authorization_code", "card_last_four", "card_type", "bank_name", "check_number")}),
        (_("Audit"), {"fields": ("received_by", "received_at", "updated_at")}),
        (_("Notes"), {"fields": ("notes",)}),
    )

    @admin.display(description=_("Status"), ordering="status")
    def status_badge(self, obj: Payment):
        mapping = {
            Payment.PaymentStatus.PENDING: ("PENDING", "yellow"),
            Payment.PaymentStatus.PROCESSING: ("PROCESSING", "blue"),
            Payment.PaymentStatus.COMPLETED: ("COMPLETED", "green"),
            Payment.PaymentStatus.FAILED: ("FAILED", "red"),
            Payment.PaymentStatus.REFUNDED: ("REFUNDED", "gray"),
            Payment.PaymentStatus.PARTIALLY_REFUNDED: ("PART REF", "gray"),
            Payment.PaymentStatus.CANCELLED: ("CANCELLED", "gray"),
        }
        text, kind = mapping.get(obj.status, (obj.status, "gray"))
        return badge(text, kind)

    def save_model(self, request, obj, form, change):
        if not change and not obj.received_by:
            obj.received_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ("refund_id", "hotel", "payment", "amount", "status", "processed_by", "processed_at")
    list_filter = ("hotel", "status", "processed_at")
    search_fields = ("refund_id", "payment__payment_id", "reason")
    ordering = ("-processed_at",)
    autocomplete_fields = ("hotel", "payment", "processed_by")
    readonly_fields = ("refund_id", "processed_at", "completed_at")

    def save_model(self, request, obj, form, change):
        if not change and not obj.processed_by:
            obj.processed_by = request.user
        super().save_model(request, obj, form, change)


# ----------------------------
# Expense Admin
# ----------------------------
@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = (
        "expense_number",
        "hotel",
        "title",
        "expense_date",
        "category",
        "expense_type",
        "department",
        "total_amount",
        "paid_amount",
        "balance_due",
        "approval_badge",
    )
    list_filter = ("hotel", "category", "expense_type", "department", "approval_status", "payment_method", "expense_date")
    search_fields = ("expense_number", "title", "description", "vendor__name", "payee", "invoice_reference")
    date_hierarchy = "expense_date"
    ordering = ("-expense_date", "-created_at")
    autocomplete_fields = (
        "hotel",
        "vendor",
        "expense_account",
        "payable_account",
        "prepaid_account",
        "asset_account",
        "cash_account",
        "linked_asset",
        "linked_liability",
        "requested_by",
        "approved_by",
        "created_by",
    )
    readonly_fields = (
        "expense_number",
        "total_amount",
        "paid_amount",
        "balance_due",
        "created_at",
        "updated_at",
        "approved_at",
    )
    inlines = (ExpenseAuditLogInline,)
    actions = ("action_approve", "action_reject", "action_mark_paid")

    fieldsets = (
        (_("Expense Information"), {"fields": ("hotel", "expense_number", "category", "expense_type", "department", "title", "description")}),
        (_("Financial"), {"fields": ("amount", "tax_amount", "total_amount", "paid_amount", "balance_due", "currency")}),
        (_("Dates & Payment"), {"fields": ("expense_date", "due_date", "payment_date", "payment_method", "cash_account")}),
        (_("Vendor / Reference"), {"fields": ("payee", "vendor", "invoice_reference")}),
        (_("Accounting"), {"fields": ("expense_account", "payable_account", "prepaid_account", "asset_account")}),
        (_("Linked Records"), {"fields": ("linked_asset", "linked_liability")}),
        (_("Receipt"), {"fields": ("receipt", "receipt_number")}),
        (_("Approval Workflow"), {"fields": ("approval_status", "requested_by", "approved_by", "approved_at", "rejection_reason")}),
        (_("Audit"), {"fields": ("created_by", "created_at", "updated_at", "notes")}),
    )

    @admin.display(description=_("Approval"), ordering="approval_status")
    def approval_badge(self, obj: Expense):
        mapping = {
            Expense.ApprovalStatus.DRAFT: ("DRAFT", "gray"),
            Expense.ApprovalStatus.PENDING: ("PENDING", "yellow"),
            Expense.ApprovalStatus.APPROVED: ("APPROVED", "blue"),
            Expense.ApprovalStatus.REJECTED: ("REJECTED", "red"),
            Expense.ApprovalStatus.PAID: ("PAID", "green"),
            Expense.ApprovalStatus.PARTIAL: ("PARTIAL", "yellow"),
        }
        text, kind = mapping.get(obj.approval_status, (obj.approval_status, "gray"))
        return badge(text, kind)

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.action(description=_("Approve selected expenses"))
    def action_approve(self, request, queryset):
        ok = 0
        for exp in queryset:
            try:
                if exp.approval_status == Expense.ApprovalStatus.PENDING:
                    exp.approve(request.user)
                    ok += 1
            except ValidationError as e:
                self.message_user(request, f"{exp.expense_number}: {', '.join(e.messages)}", level=messages.ERROR)
        if ok:
            self.message_user(request, _(f"Approved {ok} expense(s)."), level=messages.SUCCESS)

    @admin.action(description=_("Reject selected expenses"))
    def action_reject(self, request, queryset):
        ok = 0
        for exp in queryset:
            try:
                if exp.approval_status == Expense.ApprovalStatus.PENDING:
                    exp.reject(request.user, "Rejected via admin action")
                    ok += 1
            except ValidationError as e:
                self.message_user(request, f"{exp.expense_number}: {', '.join(e.messages)}", level=messages.ERROR)
        if ok:
            self.message_user(request, _(f"Rejected {ok} expense(s)."), level=messages.SUCCESS)

    @admin.action(description=_("Mark selected expenses as paid"))
    def action_mark_paid(self, request, queryset):
        ok = 0
        for exp in queryset:
            try:
                if exp.approval_status in [Expense.ApprovalStatus.APPROVED, Expense.ApprovalStatus.PARTIAL]:
                    exp.mark_paid(request.user)
                    ok += 1
            except ValidationError as e:
                self.message_user(request, f"{exp.expense_number}: {', '.join(e.messages)}", level=messages.ERROR)
        if ok:
            self.message_user(request, _(f"Marked {ok} expense(s) as paid."), level=messages.SUCCESS)


@admin.register(ExpenseAuditLog)
class ExpenseAuditLogAdmin(admin.ModelAdmin):
    list_display = ("expense", "action", "user", "created_at")
    list_filter = ("action", "created_at")
    search_fields = ("expense__expense_number", "description", "user__username")
    autocomplete_fields = ("expense", "user")
    readonly_fields = ("expense", "action", "user", "description", "created_at")
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ----------------------------
# Financial Periods
# ----------------------------
@admin.register(FinancialPeriod)
class FinancialPeriodAdmin(admin.ModelAdmin):
    list_display = ("name", "hotel", "start_date", "end_date", "status_badge", "total_revenue", "total_expenses", "net_profit", "closed_at")
    list_filter = ("hotel", "status", "start_date", "end_date")
    search_fields = ("name", "notes")
    ordering = ("-start_date",)
    autocomplete_fields = ("hotel", "closed_by")
    readonly_fields = ("total_revenue", "total_expenses", "net_profit", "created_at", "updated_at", "closed_at")
    actions = ("action_close_periods",)

    fieldsets = (
        (_("Period"), {"fields": ("hotel", "name", "start_date", "end_date", "status")}),
        (_("Closing"), {"fields": ("closed_by", "closed_at")}),
        (_("Summary"), {"fields": ("total_revenue", "total_expenses", "net_profit")}),
        (_("Notes"), {"fields": ("notes",)}),
        (_("Audit"), {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description=_("Status"), ordering="status")
    def status_badge(self, obj: FinancialPeriod):
        mapping = {
            FinancialPeriod.Status.OPEN: ("OPEN", "green"),
            FinancialPeriod.Status.CLOSING: ("CLOSING", "yellow"),
            FinancialPeriod.Status.CLOSED: ("CLOSED", "gray"),
            FinancialPeriod.Status.LOCKED: ("LOCKED", "gray"),
        }
        text, kind = mapping.get(obj.status, (obj.status, "gray"))
        return badge(text, kind)

    @admin.action(description=_("Close selected periods"))
    def action_close_periods(self, request, queryset):
        ok = 0
        for period in queryset:
            try:
                if period.status != FinancialPeriod.Status.CLOSED:
                    period.close(request.user)
                    ok += 1
            except ValidationError as e:
                self.message_user(request, f"{period.name}: {', '.join(e.messages)}", level=messages.ERROR)

        if ok:
            self.message_user(request, _(f"Closed {ok} period(s)."), level=messages.SUCCESS)


@admin.register(CashMovement)
class CashMovementAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "hotel",
        "direction",
        "amount",
        "cash_account",
        "balance_after",
        "source_type",
        "reference",
    )
    list_filter = ("hotel", "direction", "source_type", "cash_account", "created_at")
    search_fields = ("reference", "description", "source_type")
    readonly_fields = ("created_at", "balance_after")
    autocomplete_fields = ("hotel", "cash_account", "created_by")
    ordering = ("-created_at",)