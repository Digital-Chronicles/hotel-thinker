# finance/admin.py
from __future__ import annotations

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html

from .models import (
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
    """
    kind: gray | green | yellow | red | blue
    """
    colors = {
        "gray": ("#334155", "#f1f5f9", "#e2e8f0"),
        "green": ("#166534", "#dcfce7", "#86efac"),
        "yellow": ("#854d0e", "#fef9c3", "#fde047"),
        "red": ("#991b1b", "#fee2e2", "#fca5a5"),
        "blue": ("#1e40af", "#dbeafe", "#93c5fd"),
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
    fields = ("payment_id", "method", "amount", "currency", "status", "reference", "received_by", "received_at")
    readonly_fields = ("payment_id", "received_at")
    can_delete = False
    autocomplete_fields = ("received_by",)


class ExpenseAuditLogInline(admin.TabularInline):
    model = ExpenseAuditLog
    extra = 0
    fields = ("created_at", "action", "user", "description")
    readonly_fields = ("created_at", "action", "user", "description")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


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
    autocomplete_fields = ("hotel", "booking", "created_by", "voided_by")
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
        (_("Tax"), {"fields": ("tax_scheme", "tax_rate", "tax_number")}),
        (_("Amounts"), {"fields": ("subtotal", "discount", "discount_type", "tax_amount", "total_amount", "amount_paid", "balance_due_value", "currency", "exchange_rate")}),
        (_("Notes"), {"fields": ("notes", "terms_conditions", "internal_notes")}),
        (_("Voiding"), {"fields": ("voided_by", "voided_at", "void_reason")}),
        (_("Audit"), {"fields": ("created_by", "created_at", "updated_at", "issued_at", "paid_at", "overdue_badge")}),
    )

    actions = ("action_mark_sent", "action_issue", "action_mark_paid")

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

    @admin.action(description=_("Mark selected invoices as sent"))
    def action_mark_sent(self, request, queryset):
        ok = 0
        for inv in queryset:
            try:
                inv.mark_sent(request.user)
                ok += 1
            except ValidationError as e:
                self.message_user(request, f"{inv.invoice_number}: {', '.join(e.messages)}", level=messages.ERROR)
        if ok:
            self.message_user(request, _(f"Marked {ok} invoice(s) as sent."), level=messages.SUCCESS)

    @admin.action(description=_("Mark selected invoices as paid (force)"))
    def action_mark_paid(self, request, queryset):
        # Force action for admin convenience (does not create Payment records).
        updated = queryset.update(status=Invoice.Status.PAID, paid_at=timezone.now())
        self.message_user(request, _(f"Marked {updated} invoice(s) as paid."), level=messages.SUCCESS)


# ----------------------------
# Invoice Line Items
# ----------------------------
@admin.register(InvoiceLineItem)
class InvoiceLineItemAdmin(admin.ModelAdmin):
    list_display = ("invoice", "description", "quantity", "unit_price", "discount", "tax_rate", "total")
    list_filter = ("invoice__hotel",)
    search_fields = ("description", "invoice__invoice_number")
    autocomplete_fields = ("invoice", "booking", "charge")
    readonly_fields = ("total",)
    ordering = ("-id",)


# ----------------------------
# Invoice Audit Logs
# ----------------------------
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
# Payments
# ----------------------------
@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("payment_id", "hotel", "invoice", "method", "amount", "currency", "status_badge", "received_by", "received_at")
    list_filter = ("hotel", "method", "status", "received_at", "currency")
    search_fields = ("payment_id", "transaction_id", "reference", "invoice__invoice_number")
    date_hierarchy = "received_at"
    ordering = ("-received_at",)
    autocomplete_fields = ("hotel", "invoice", "received_by")
    readonly_fields = ("payment_id", "received_at", "updated_at")

    fieldsets = (
        (_("Links"), {"fields": ("hotel", "invoice")}),
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


# ----------------------------
# Refunds
# ----------------------------
@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ("refund_id", "hotel", "payment", "amount", "status", "processed_by", "processed_at")
    list_filter = ("hotel", "status", "processed_at")
    search_fields = ("refund_id", "payment__payment_id", "reason")
    ordering = ("-processed_at",)
    autocomplete_fields = ("hotel", "payment", "processed_by")
    readonly_fields = ("refund_id", "processed_at")

    def save_model(self, request, obj, form, change):
        if not change and not obj.processed_by:
            obj.processed_by = request.user
        super().save_model(request, obj, form, change)


# ----------------------------
# Expenses
# ----------------------------
@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("expense_number", "hotel", "title", "payment_date", "category", "amount", "tax_amount", "total_amount", "approval_badge", "payment_method")
    list_filter = ("hotel", "category", "approval_status", "payment_method", "payment_date")
    search_fields = ("expense_number", "title", "description", "vendor", "payee", "invoice_reference")
    date_hierarchy = "payment_date"
    ordering = ("-payment_date", "-created_at")
    autocomplete_fields = ("hotel", "requested_by", "approved_by", "created_by")
    readonly_fields = ("expense_number", "total_amount", "created_at", "updated_at", "approved_at")
    inlines = (ExpenseAuditLogInline,)
    actions = ("action_approve", "action_reject", "action_mark_paid")

    fieldsets = (
        (_("Expense Information"), {"fields": ("hotel", "expense_number", "category", "title", "description")}),
        (_("Financial"), {"fields": ("amount", "tax_amount", "total_amount", "currency")}),
        (_("Payment Details"), {"fields": ("payment_method", "payment_date", "payee", "vendor", "invoice_reference")}),
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
                if exp.approval_status == Expense.ApprovalStatus.APPROVED:
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