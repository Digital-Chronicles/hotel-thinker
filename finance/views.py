# finance/views.py
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum, F, Value, DecimalField
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods, require_POST, require_GET
from django.views.generic import (
    CreateView, DetailView, ListView, TemplateView, UpdateView, DeleteView
)

from hotel_thinker.utils import get_active_hotel_for_user, require_hotel_role

from .forms import (
    AccountForm, AssetForm, CashAccountForm, DateRangeForm, ExpenseForm,
    FinancialPeriodForm, InvoiceForm, InvoiceLineItemForm, JournalEntryForm,
    JournalLineForm, LiabilityForm, PaymentForm, TrialBalanceForm, VendorForm
)
from .models import (
    Account, Asset, CashAccount, CashMovement, Expense, ExpenseAuditLog,
    FinancialPeriod, Invoice, InvoiceAuditLog, InvoiceLineItem,
    JournalEntry, JournalLine, Liability, Payment, Refund, Vendor
)

D0 = Decimal("0.00")
D001 = Decimal("0.01")


# =========================================================
# Helpers
# =========================================================

def _hotel(request):
    """Get active hotel for the current request"""
    return get_active_hotel_for_user(request.user, request=request)


def _require_finance_access(user):
    """Require finance access role"""
    require_hotel_role(user, {"admin", "accountant", "general_manager"})


def _aware_datetime_from_date(d, end=False):
    """Convert date to timezone-aware datetime"""
    tz = timezone.get_current_timezone()
    if end:
        return timezone.make_aware(datetime.combine(d, datetime.max.time()), tz)
    return timezone.make_aware(datetime.combine(d, datetime.min.time()), tz)


class HotelScopedQuerysetMixin:
    """Restrict querysets to the active hotel."""

    def get_hotel(self):
        return get_active_hotel_for_user(self.request.user, request=self.request)

    def get_queryset(self):
        qs = super().get_queryset()
        hotel = self.get_hotel()
        if hotel and hasattr(qs, "filter"):
            return qs.filter(hotel=hotel)
        return qs


# =========================================================
# FINANCE DASHBOARD
# =========================================================

@method_decorator(login_required, name="dispatch")
class DashboardView(TemplateView):
    template_name = "finance/dashboard.html"

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hotel = _hotel(self.request)

        today = timezone.localdate()
        yesterday = today - timedelta(days=1)
        month_start = today.replace(day=1)
        last_month_start = (month_start - timedelta(days=1)).replace(day=1)
        last_month_end = month_start - timedelta(days=1)

        completed_payments = Payment.objects.filter(
            hotel=hotel,
            status=Payment.PaymentStatus.COMPLETED,
        )

        today_revenue = completed_payments.filter(
            received_at__date=today
        ).aggregate(total=Coalesce(Sum("amount"), D0))["total"]

        yesterday_revenue = completed_payments.filter(
            received_at__date=yesterday
        ).aggregate(total=Coalesce(Sum("amount"), D0))["total"]

        monthly_revenue = completed_payments.filter(
            received_at__date__gte=month_start,
            received_at__date__lte=today,
        ).aggregate(total=Coalesce(Sum("amount"), D0))["total"]

        last_month_revenue = completed_payments.filter(
            received_at__date__gte=last_month_start,
            received_at__date__lte=last_month_end,
        ).aggregate(total=Coalesce(Sum("amount"), D0))["total"]

        # Optional restaurant integration
        try:
            from restaurant.models import RestaurantPayment
            restaurant_qs = RestaurantPayment.objects.filter(hotel=hotel)
            restaurant_today = restaurant_qs.filter(received_at__date=today).aggregate(total=Coalesce(Sum("amount"), D0))["total"]
            restaurant_yesterday = restaurant_qs.filter(received_at__date=yesterday).aggregate(total=Coalesce(Sum("amount"), D0))["total"]
            restaurant_monthly = restaurant_qs.filter(received_at__date__gte=month_start, received_at__date__lte=today).aggregate(total=Coalesce(Sum("amount"), D0))["total"]
            restaurant_last_month = restaurant_qs.filter(received_at__date__gte=last_month_start, received_at__date__lte=last_month_end).aggregate(total=Coalesce(Sum("amount"), D0))["total"]
        except ImportError:
            restaurant_today = D0
            restaurant_yesterday = D0
            restaurant_monthly = D0
            restaurant_last_month = D0

        total_today_revenue = today_revenue + restaurant_today
        total_monthly_revenue = monthly_revenue + restaurant_monthly
        yesterday_total = yesterday_revenue + restaurant_yesterday
        last_month_total = last_month_revenue + restaurant_last_month

        daily_change = 0
        if yesterday_total > 0:
            daily_change = round(((total_today_revenue - yesterday_total) / yesterday_total) * 100, 1)

        monthly_change = 0
        if last_month_total > 0:
            monthly_change = round(((total_monthly_revenue - last_month_total) / last_month_total) * 100, 1)

        receivable_statuses = [
            Invoice.Status.ISSUED,
            Invoice.Status.SENT,
            Invoice.Status.PARTIALLY_PAID,
            Invoice.Status.OVERDUE,
        ]

        invoice_qs = Invoice.objects.filter(hotel=hotel)

        pending_payments = invoice_qs.filter(
            status__in=receivable_statuses
        ).exclude(total_amount=F("amount_paid")).count()

        overdue_invoices = invoice_qs.filter(
            status__in=receivable_statuses,
            due_date__lt=today,
            total_amount__gt=F("amount_paid"),
        ).count()

        open_invoices = invoice_qs.filter(status__in=receivable_statuses)
        total_receivables = sum((invoice.balance_due for invoice in open_invoices), D0)

        expense_qs = Expense.objects.filter(hotel=hotel)

        monthly_expenses = expense_qs.filter(
            approval_status__in=[Expense.ApprovalStatus.PAID, Expense.ApprovalStatus.PARTIAL],
            expense_date__gte=month_start,
            expense_date__lte=today,
        ).aggregate(total=Coalesce(Sum("total_amount"), D0))["total"]

        last_month_expenses = expense_qs.filter(
            approval_status__in=[Expense.ApprovalStatus.PAID, Expense.ApprovalStatus.PARTIAL],
            expense_date__gte=last_month_start,
            expense_date__lte=last_month_end,
        ).aggregate(total=Coalesce(Sum("total_amount"), D0))["total"]

        expense_change = 0
        if last_month_expenses > 0:
            expense_change = round(((monthly_expenses - last_month_expenses) / last_month_expenses) * 100, 1)

        approved_unpaid = expense_qs.filter(
            approval_status__in=[Expense.ApprovalStatus.APPROVED, Expense.ApprovalStatus.PARTIAL]
        ).count()

        pending_approvals = expense_qs.filter(
            approval_status=Expense.ApprovalStatus.PENDING
        ).count()

        net_cash_flow = total_monthly_revenue - monthly_expenses

        revenue_labels = []
        revenue_data = []
        expense_data = []

        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            revenue_labels.append(day.strftime("%a"))

            day_revenue = completed_payments.filter(
                received_at__date=day
            ).aggregate(total=Coalesce(Sum("amount"), D0))["total"]

            try:
                from restaurant.models import RestaurantPayment
                day_revenue += RestaurantPayment.objects.filter(
                    hotel=hotel, received_at__date=day
                ).aggregate(total=Coalesce(Sum("amount"), D0))["total"]
            except ImportError:
                pass

            revenue_data.append(float(day_revenue))

            day_expense = expense_qs.filter(
                approval_status__in=[Expense.ApprovalStatus.PAID, Expense.ApprovalStatus.PARTIAL],
                expense_date=day,
            ).aggregate(total=Coalesce(Sum("total_amount"), D0))["total"]

            expense_data.append(float(day_expense))

        expense_by_category = (
            expense_qs.filter(
                approval_status__in=[Expense.ApprovalStatus.PAID, Expense.ApprovalStatus.PARTIAL],
                expense_date__gte=month_start,
                expense_date__lte=today,
            )
            .values("category")
            .annotate(total=Coalesce(Sum("total_amount"), D0))
            .order_by("-total")[:6]
        )

        category_labels = []
        category_values = []

        category_names = {
            "utilities": "Utilities",
            "salary": "Salaries",
            "maintenance": "Maintenance",
            "supplies": "Supplies",
            "food_beverage": "Food & Beverage",
            "marketing": "Marketing",
            "insurance": "Insurance",
            "rent": "Rent",
            "equipment": "Equipment",
            "software": "Software",
            "training": "Training",
            "travel": "Travel",
            "other": "Other",
        }

        for item in expense_by_category:
            category_labels.append(category_names.get(item["category"], item["category"].replace("_", " ").title()))
            category_values.append(float(item["total"]))

        transactions = []

        recent_payments = completed_payments.select_related("invoice").order_by("-received_at")[:10]
        for payment in recent_payments:
            inv_no = payment.invoice.invoice_number if payment.invoice_id else "N/A"
            transactions.append({
                "date": payment.received_at,
                "description": f"Payment received (Invoice {inv_no})",
                "amount": payment.amount,
                "type": "Income",
            })

        try:
            from restaurant.models import RestaurantPayment
            recent_restaurant = RestaurantPayment.objects.filter(
                hotel=hotel
            ).order_by("-received_at")[:10]

            for rp in recent_restaurant:
                transactions.append({
                    "date": rp.received_at,
                    "description": "Restaurant payment",
                    "amount": rp.amount,
                    "type": "Income",
                })
        except ImportError:
            pass

        recent_expenses = expense_qs.filter(
            approval_status__in=[Expense.ApprovalStatus.PAID, Expense.ApprovalStatus.PARTIAL]
        ).order_by("-expense_date", "-created_at")[:10]

        for expense in recent_expenses:
            transactions.append({
                "date": _aware_datetime_from_date(expense.expense_date),
                "description": expense.title,
                "amount": expense.total_amount,
                "type": "Expense",
            })

        transactions = sorted(transactions, key=lambda x: x["date"], reverse=True)[:10]
        for txn in transactions:
            txn["date"] = txn["date"].date() if hasattr(txn["date"], "date") else txn["date"]

        ctx.update({
            "hotel": hotel,
            "today_revenue": total_today_revenue,
            "monthly_revenue": total_monthly_revenue,
            "daily_change": daily_change,
            "monthly_change": monthly_change,
            "pending_payments": pending_payments,
            "overdue_invoices": overdue_invoices,
            "total_receivables": total_receivables,
            "monthly_expenses": monthly_expenses,
            "expense_change": expense_change,
            "approved_unpaid": approved_unpaid,
            "pending_approvals": pending_approvals,
            "net_cash_flow": net_cash_flow,
            "revenue_labels": revenue_labels,
            "revenue_data": revenue_data,
            "expense_data": expense_data,
            "category_labels": category_labels,
            "category_values": category_values,
            "transactions": transactions,
        })

        return ctx


# =========================================================
# Invoices
# =========================================================

@method_decorator(login_required, name="dispatch")
class InvoiceListView(HotelScopedQuerysetMixin, ListView):
    model = Invoice
    template_name = "finance/invoice_list.html"
    context_object_name = "invoices"
    paginate_by = 50

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset().select_related("booking", "hotel")
        q = (self.request.GET.get("q") or "").strip()
        status = (self.request.GET.get("status") or "").strip()

        if q:
            qs = qs.filter(
                Q(invoice_number__icontains=q)
                | Q(customer_name__icontains=q)
                | Q(customer_email__icontains=q)
                | Q(order_number__icontains=q)
            )

        if status:
            qs = qs.filter(status=status)

        return qs.order_by("-invoice_date", "-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        hotel = self.get_hotel()
        all_invoices = Invoice.objects.filter(hotel=hotel)
        today = timezone.localdate()
        
        total_outstanding = D0
        total_overdue = D0
        
        for invoice in all_invoices:
            balance = invoice.total_amount - invoice.amount_paid
            if balance > D0 and invoice.status not in ['paid', 'void', 'credit_note']:
                total_outstanding += balance
                if invoice.due_date and invoice.due_date < today:
                    total_overdue += balance
        
        paid_this_month = all_invoices.filter(
            status='paid',
            paid_at__year=today.year,
            paid_at__month=today.month
        ).aggregate(total=Coalesce(Sum('total_amount'), Value(D0)))['total'] or D0
        
        ctx['status_choices'] = Invoice.Status.choices
        ctx['total_outstanding'] = total_outstanding
        ctx['total_overdue'] = total_overdue
        ctx['paid_this_month'] = paid_this_month
        
        return ctx


@method_decorator(login_required, name="dispatch")
class InvoiceDetailView(HotelScopedQuerysetMixin, DetailView):
    model = Invoice
    template_name = "finance/invoice_detail.html"
    context_object_name = "invoice"

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related(
                "booking", "hotel", "created_by", "voided_by",
                "receivable_account", "revenue_account", "tax_account",
            )
            .prefetch_related("line_items", "payments", "audit_logs")
        )


@method_decorator(login_required, name="dispatch")
class InvoiceCreateView(CreateView):
    model = Invoice
    form_class = InvoiceForm
    template_name = "finance/invoice_form.html"

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['hotel'] = _hotel(self.request)
        return kwargs

    def form_valid(self, form):
        hotel = _hotel(self.request)
        form.instance.hotel = hotel
        form.instance.created_by = self.request.user
        form.instance.status = Invoice.Status.DRAFT
        
        messages.success(self.request, f"Invoice {form.instance.invoice_number} created successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("finance:invoice_detail", kwargs={"pk": self.object.pk})


@method_decorator(login_required, name="dispatch")
class InvoiceUpdateView(HotelScopedQuerysetMixin, UpdateView):
    model = Invoice
    form_class = InvoiceForm
    template_name = "finance/invoice_form.html"
    context_object_name = "invoice"

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['hotel'] = self.get_hotel()
        return kwargs

    def get_queryset(self):
        return super().get_queryset().exclude(status__in=[Invoice.Status.PAID, Invoice.Status.VOID])

    def form_valid(self, form):
        messages.success(self.request, f"Invoice {form.instance.invoice_number} updated successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("finance:invoice_detail", kwargs={"pk": self.object.pk})


@login_required
@require_POST
def invoice_issue(request, pk: int):
    _require_finance_access(request.user)
    hotel = _hotel(request)
    invoice = get_object_or_404(Invoice, pk=pk, hotel=hotel)

    try:
        invoice.issue(request.user)
        messages.success(request, "Invoice issued successfully.")
    except ValidationError as e:
        messages.error(request, ", ".join(getattr(e, "messages", [str(e)])))

    return redirect("finance:invoice_detail", pk=pk)


@login_required
@require_POST
def invoice_send(request, pk: int):
    _require_finance_access(request.user)
    hotel = _hotel(request)
    invoice = get_object_or_404(Invoice, pk=pk, hotel=hotel)

    try:
        invoice.status = Invoice.Status.SENT
        invoice.save()
        InvoiceAuditLog.objects.create(
            invoice=invoice,
            action=InvoiceAuditLog.Action.SEND,
            user=request.user,
            description=f"Invoice marked as sent by {request.user.get_full_name() or request.user.username}",
        )
        messages.success(request, "Invoice marked as sent.")
    except Exception as e:
        messages.error(request, str(e))

    return redirect("finance:invoice_detail", pk=pk)


@login_required
@require_POST
def invoice_void(request, pk: int):
    _require_finance_access(request.user)
    hotel = _hotel(request)
    invoice = get_object_or_404(Invoice, pk=pk, hotel=hotel)

    if invoice.status == Invoice.Status.PAID:
        messages.error(request, "Cannot void a paid invoice.")
        return redirect("finance:invoice_detail", pk=pk)

    reason = request.POST.get("reason", "").strip()
    invoice.status = Invoice.Status.VOID
    invoice.voided_at = timezone.now()
    invoice.voided_by = request.user
    invoice.void_reason = reason
    invoice.save()

    InvoiceAuditLog.objects.create(
        invoice=invoice,
        action=InvoiceAuditLog.Action.VOID,
        user=request.user,
        description=f"Invoice voided. Reason: {reason}",
    )
    messages.success(request, "Invoice voided successfully.")
    return redirect("finance:invoice_list")


@login_required
def invoice_record_payment(request, pk: int):
    _require_finance_access(request.user)
    hotel = _hotel(request)
    invoice = get_object_or_404(Invoice, pk=pk, hotel=hotel)

    if request.method == "POST":
        form = PaymentForm(request.POST, invoice=invoice)
        if form.is_valid():
            amount = form.cleaned_data["amount"]
            method = form.cleaned_data["method"]
            reference = form.cleaned_data.get("reference")
            cash_account = form.cleaned_data.get("cash_account")
            notes = form.cleaned_data.get("notes")

            try:
                invoice.record_payment(
                    amount=amount,
                    method=method,
                    user=request.user,
                    reference=reference,
                    cash_account=cash_account,
                )
                messages.success(request, "Payment recorded successfully.")
                return redirect("finance:invoice_detail", pk=pk)
            except ValidationError as e:
                messages.error(request, ", ".join(getattr(e, "messages", [str(e)])))
    else:
        form = PaymentForm(invoice=invoice)

    return render(
        request,
        "finance/payment_form.html",
        {
            "invoice": invoice,
            "form": form,
        },
    )


# =========================================================
# Expenses
# =========================================================

@method_decorator(login_required, name="dispatch")
class ExpenseListView(HotelScopedQuerysetMixin, ListView):
    model = Expense
    template_name = "finance/expense_list.html"
    context_object_name = "expenses"
    paginate_by = 50

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset().select_related(
            "hotel", "vendor", "cash_account",
            "expense_account", "payable_account",
            "created_by", "requested_by", "approved_by",
        )

        q = (self.request.GET.get("q") or "").strip()
        status = (self.request.GET.get("status") or "").strip()
        category = (self.request.GET.get("category") or "").strip()
        department = (self.request.GET.get("department") or "").strip()
        expense_type = (self.request.GET.get("expense_type") or "").strip()

        if q:
            qs = qs.filter(
                Q(title__icontains=q)
                | Q(expense_number__icontains=q)
                | Q(payee__icontains=q)
                | Q(vendor__name__icontains=q)
                | Q(invoice_reference__icontains=q)
            )

        if status:
            qs = qs.filter(approval_status=status)

        if category:
            qs = qs.filter(category=category)

        if department:
            qs = qs.filter(department=department)

        if expense_type:
            qs = qs.filter(expense_type=expense_type)

        return qs.order_by("-expense_date", "-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        filtered_qs = self.get_queryset()
        
        ctx['status_choices'] = Expense.ApprovalStatus.choices
        ctx['category_choices'] = Expense.Category.choices
        ctx['department_choices'] = Expense.Department.choices
        
        ctx['pending_count'] = filtered_qs.filter(approval_status='pending').count()
        ctx['approved_unpaid_count'] = filtered_qs.filter(approval_status='approved').count()
        
        total_amount = filtered_qs.aggregate(
            total=Coalesce(Sum('total_amount'), Value(D0, output_field=DecimalField()))
        )['total'] or D0
        ctx['total_amount'] = total_amount
        
        return ctx


@method_decorator(login_required, name="dispatch")
class ExpenseDetailView(HotelScopedQuerysetMixin, DetailView):
    model = Expense
    template_name = "finance/expense_detail.html"
    context_object_name = "expense"

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related(
                "hotel", "vendor", "cash_account",
                "expense_account", "payable_account",
                "prepaid_account", "asset_account",
                "linked_asset", "linked_liability",
                "created_by", "requested_by", "approved_by",
            )
            .prefetch_related("audit_logs")
        )


@method_decorator(login_required, name="dispatch")
class ExpenseCreateView(CreateView):
    model = Expense
    form_class = ExpenseForm
    template_name = "finance/expense_form.html"

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        hotel = _hotel(self.request)

        for field_name in [
            "vendor", "cash_account", "expense_account",
            "payable_account", "prepaid_account", "asset_account",
        ]:
            if field_name in form.fields:
                form.fields[field_name].queryset = form.fields[field_name].queryset.filter(hotel=hotel)

        return form

    def form_valid(self, form):
        hotel = _hotel(self.request)
        form.instance.hotel = hotel
        form.instance.created_by = self.request.user
        form.instance.requested_by = self.request.user

        messages.success(self.request, "Expense created and submitted for approval.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("finance:expense_list")


@method_decorator(login_required, name="dispatch")
class ExpenseUpdateView(HotelScopedQuerysetMixin, UpdateView):
    model = Expense
    form_class = ExpenseForm
    template_name = "finance/expense_form.html"
    context_object_name = "expense"

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        hotel = self.get_hotel()

        for field_name in [
            "vendor", "cash_account", "expense_account",
            "payable_account", "prepaid_account", "asset_account",
        ]:
            if field_name in form.fields:
                form.fields[field_name].queryset = form.fields[field_name].queryset.filter(hotel=hotel)

        return form

    def get_queryset(self):
        return super().get_queryset().exclude(approval_status=Expense.ApprovalStatus.PAID)

    def form_valid(self, form):
        if self.object.approval_status == Expense.ApprovalStatus.PAID:
            messages.error(self.request, "Paid expenses cannot be edited.")
            return redirect("finance:expense_detail", pk=self.object.pk)

        messages.success(self.request, "Expense updated successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("finance:expense_detail", kwargs={"pk": self.object.pk})


@login_required
@require_POST
def expense_approve(request, pk: int):
    require_hotel_role(request.user, {"admin", "general_manager"})
    hotel = _hotel(request)
    expense = get_object_or_404(Expense, pk=pk, hotel=hotel)

    try:
        expense.approve(request.user)
        messages.success(request, "Expense approved successfully.")
    except ValidationError as e:
        messages.error(request, ", ".join(getattr(e, "messages", [str(e)])))

    return redirect("finance:expense_detail", pk=pk)


@login_required
@require_POST
def expense_reject(request, pk: int):
    require_hotel_role(request.user, {"admin", "general_manager"})
    hotel = _hotel(request)
    expense = get_object_or_404(Expense, pk=pk, hotel=hotel)

    reason = (request.POST.get("reason") or "").strip() or "Rejected"

    try:
        expense.reject(request.user, reason)
        messages.success(request, "Expense rejected.")
    except ValidationError as e:
        messages.error(request, ", ".join(getattr(e, "messages", [str(e)])))

    return redirect("finance:expense_list")


@login_required
@require_POST
def expense_mark_paid(request, pk: int):
    _require_finance_access(request.user)
    hotel = _hotel(request)
    expense = get_object_or_404(Expense, pk=pk, hotel=hotel)

    amount = request.POST.get("amount")
    cash_account = None

    if amount:
        try:
            amount = Decimal(amount)
        except Exception:
            messages.error(request, "Invalid payment amount.")
            return redirect("finance:expense_detail", pk=pk)
    else:
        amount = None

    if request.POST.get("cash_account"):
        cash_account_id = request.POST.get("cash_account")
        if cash_account_id:
            cash_account = get_object_or_404(CashAccount, pk=cash_account_id, hotel=hotel)

    try:
        expense.mark_paid(request.user, amount=amount, cash_account=cash_account)
        messages.success(request, "Expense payment recorded successfully.")
    except ValidationError as e:
        messages.error(request, ", ".join(getattr(e, "messages", [str(e)])))

    return redirect("finance:expense_detail", pk=pk)


# =========================================================
# Financial Periods
# =========================================================

@method_decorator(login_required, name="dispatch")
class PeriodListView(HotelScopedQuerysetMixin, ListView):
    model = FinancialPeriod
    template_name = "finance/period_list.html"
    context_object_name = "periods"
    paginate_by = 50

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return super().get_queryset().select_related("hotel", "closed_by").order_by("-start_date")


@method_decorator(login_required, name="dispatch")
class PeriodCreateView(CreateView):
    model = FinancialPeriod
    form_class = FinancialPeriodForm
    template_name = "finance/period_form.html"

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['hotel'] = _hotel(self.request)
        return kwargs

    def form_valid(self, form):
        hotel = _hotel(self.request)
        form.instance.hotel = hotel
        messages.success(self.request, f"Period '{form.instance.name}' created successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("finance:period_list")


@method_decorator(login_required, name="dispatch")
class PeriodDetailView(HotelScopedQuerysetMixin, DetailView):
    model = FinancialPeriod
    template_name = "finance/period_detail.html"
    context_object_name = "period"

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)


@login_required
@require_POST
def period_close(request, pk: int):
    _require_finance_access(request.user)
    hotel = _hotel(request)
    period = get_object_or_404(FinancialPeriod, pk=pk, hotel=hotel)

    try:
        period.close(request.user)
        messages.success(request, f"Period '{period.name}' closed successfully.")
    except ValidationError as e:
        messages.error(request, ", ".join(getattr(e, "messages", [str(e)])))

    return redirect("finance:period_detail", pk=pk)


# =========================================================
# Accounts (Chart of Accounts)
# =========================================================

@method_decorator(login_required, name="dispatch")
class AccountListView(HotelScopedQuerysetMixin, ListView):
    model = Account
    template_name = "finance/account_list.html"
    context_object_name = "accounts"
    paginate_by = 50

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset().select_related("hotel", "parent")
        q = (self.request.GET.get("q") or "").strip()
        account_type = (self.request.GET.get("type") or "").strip()
        subtype = (self.request.GET.get("subtype") or "").strip()
        is_active = (self.request.GET.get("active") or "").strip()

        if q:
            qs = qs.filter(
                Q(account_code__icontains=q)
                | Q(name__icontains=q)
                | Q(description__icontains=q)
            )

        if account_type:
            qs = qs.filter(account_type=account_type)

        if subtype:
            qs = qs.filter(account_subtype=subtype)

        if is_active == "yes":
            qs = qs.filter(is_active=True)
        elif is_active == "no":
            qs = qs.filter(is_active=False)

        return qs.order_by("account_code", "name")


@method_decorator(login_required, name="dispatch")
class AccountCreateView(CreateView):
    model = Account
    form_class = AccountForm
    template_name = "finance/account_form.html"

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['hotel'] = _hotel(self.request)
        return kwargs

    def form_valid(self, form):
        hotel = _hotel(self.request)
        form.instance.hotel = hotel
        messages.success(self.request, f"Account '{form.instance.name}' created successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("finance:account_list")


@method_decorator(login_required, name="dispatch")
class AccountDetailView(HotelScopedQuerysetMixin, DetailView):
    model = Account
    template_name = "finance/account_detail.html"
    context_object_name = "account"

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return super().get_queryset().select_related("hotel", "parent").prefetch_related("journal_lines")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        account = self.object
        ctx["recent_lines"] = account.journal_lines.select_related(
            "journal_entry"
        ).order_by("-journal_entry__entry_date", "-id")[:20]
        return ctx


@method_decorator(login_required, name="dispatch")
class AccountUpdateView(HotelScopedQuerysetMixin, UpdateView):
    model = Account
    form_class = AccountForm
    template_name = "finance/account_form.html"
    context_object_name = "account"

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['hotel'] = self.get_hotel()
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, f"Account '{form.instance.name}' updated successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("finance:account_list")


@login_required
@require_POST
def account_delete(request, pk: int):
    _require_finance_access(request.user)
    hotel = _hotel(request)
    account = get_object_or_404(Account, pk=pk, hotel=hotel)

    if account.is_system:
        messages.error(request, "Cannot delete a system account.")
        return redirect("finance:account_detail", pk=pk)

    if account.journal_lines.exists():
        messages.error(request, "Cannot delete account with journal entries. Deactivate instead.")
        return redirect("finance:account_detail", pk=pk)

    account_name = account.name
    account.delete()
    messages.success(request, f"Account '{account_name}' deleted successfully.")
    return redirect("finance:account_list")


# =========================================================
# Cash Accounts
# =========================================================

@method_decorator(login_required, name="dispatch")
class CashAccountListView(HotelScopedQuerysetMixin, ListView):
    model = CashAccount
    template_name = "finance/cash_account_list.html"
    context_object_name = "accounts"
    paginate_by = 50

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)


@method_decorator(login_required, name="dispatch")
class CashAccountCreateView(CreateView):
    model = CashAccount
    form_class = CashAccountForm
    template_name = "finance/cash_account_form.html"

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['hotel'] = _hotel(self.request)
        return kwargs

    def form_valid(self, form):
        hotel = _hotel(self.request)
        form.instance.hotel = hotel
        form.instance.current_balance = form.instance.opening_balance
        messages.success(self.request, f"Cash account '{form.instance.name}' created successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("finance:cash_account_list")


@method_decorator(login_required, name="dispatch")
class CashAccountUpdateView(HotelScopedQuerysetMixin, UpdateView):
    model = CashAccount
    form_class = CashAccountForm
    template_name = "finance/cash_account_form.html"
    context_object_name = "account"

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['hotel'] = self.get_hotel()
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, f"Cash account '{form.instance.name}' updated successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("finance:cash_account_list")


@login_required
@require_POST
def cash_account_delete(request, pk: int):
    _require_finance_access(request.user)
    hotel = _hotel(request)
    account = get_object_or_404(CashAccount, pk=pk, hotel=hotel)

    if account.payments.exists() or account.expenses.exists() or account.movements.exists():
        messages.error(request, "Cannot delete account with transactions. Deactivate instead.")
        return redirect("finance:cash_account_detail", pk=pk)

    account.delete()
    messages.success(request, f"Cash account '{account.name}' deleted successfully.")
    return redirect("finance:cash_account_list")


# =========================================================
# Vendors
# =========================================================

@method_decorator(login_required, name="dispatch")
class VendorListView(HotelScopedQuerysetMixin, ListView):
    model = Vendor
    template_name = "finance/vendor_list.html"
    context_object_name = "vendors"
    paginate_by = 50

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset().select_related("hotel")
        q = (self.request.GET.get("q") or "").strip()
        is_active = (self.request.GET.get("active") or "").strip()

        if q:
            qs = qs.filter(
                Q(vendor_code__icontains=q)
                | Q(name__icontains=q)
                | Q(contact_person__icontains=q)
                | Q(phone__icontains=q)
                | Q(email__icontains=q)
                | Q(tin_number__icontains=q)
            )

        if is_active == "yes":
            qs = qs.filter(is_active=True)
        elif is_active == "no":
            qs = qs.filter(is_active=False)

        return qs.order_by("name")


@method_decorator(login_required, name="dispatch")
class VendorCreateView(CreateView):
    model = Vendor
    form_class = VendorForm
    template_name = "finance/vendor_form.html"

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['hotel'] = _hotel(self.request)
        return kwargs

    def form_valid(self, form):
        hotel = _hotel(self.request)
        form.instance.hotel = hotel

        if not form.instance.vendor_code:
            last_vendor = Vendor.objects.filter(hotel=hotel).order_by("-id").first()
            if last_vendor and last_vendor.vendor_code:
                try:
                    last_num = int(last_vendor.vendor_code.split("-")[-1])
                    new_num = last_num + 1
                except (ValueError, IndexError):
                    new_num = 1
            else:
                new_num = 1
            form.instance.vendor_code = f"VEN-{new_num:04d}"

        messages.success(self.request, f"Vendor '{form.instance.name}' created successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("finance:vendor_detail", kwargs={"pk": self.object.pk})


@method_decorator(login_required, name="dispatch")
class VendorDetailView(HotelScopedQuerysetMixin, DetailView):
    model = Vendor
    template_name = "finance/vendor_detail.html"
    context_object_name = "vendor"

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return super().get_queryset().select_related("hotel")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        vendor = self.object
        hotel = self.get_hotel()

        ctx["recent_expenses"] = vendor.expenses.filter(hotel=hotel).order_by("-expense_date", "-created_at")[:20]
        ctx["recent_liabilities"] = vendor.liabilities.filter(hotel=hotel).order_by("-created_at")[:20]
        return ctx


@method_decorator(login_required, name="dispatch")
class VendorUpdateView(HotelScopedQuerysetMixin, UpdateView):
    model = Vendor
    form_class = VendorForm
    template_name = "finance/vendor_form.html"
    context_object_name = "vendor"

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['hotel'] = self.get_hotel()
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, f"Vendor '{form.instance.name}' updated successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("finance:vendor_detail", kwargs={"pk": self.object.pk})


@login_required
@require_POST
def vendor_delete(request, pk: int):
    _require_finance_access(request.user)
    hotel = _hotel(request)
    vendor = get_object_or_404(Vendor, pk=pk, hotel=hotel)

    if vendor.expenses.exists() or vendor.liabilities.exists() or vendor.assets.exists():
        messages.error(request, "Cannot delete vendor with existing expenses, liabilities, or assets. Deactivate instead.")
        return redirect("finance:vendor_detail", pk=pk)

    vendor_name = vendor.name
    vendor.delete()
    messages.success(request, f"Vendor '{vendor_name}' deleted successfully.")
    return redirect("finance:vendor_list")


# =========================================================
# Assets
# =========================================================

@method_decorator(login_required, name="dispatch")
class AssetListView(HotelScopedQuerysetMixin, ListView):
    model = Asset
    template_name = "finance/asset_list.html"
    context_object_name = "assets"
    paginate_by = 50

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset().select_related(
            "hotel", "vendor", "asset_account",
            "depreciation_account", "expense_account",
        )

        q = (self.request.GET.get("q") or "").strip()
        asset_type = (self.request.GET.get("type") or "").strip()
        status = (self.request.GET.get("status") or "").strip()

        if q:
            qs = qs.filter(
                Q(asset_number__icontains=q)
                | Q(name__icontains=q)
                | Q(description__icontains=q)
                | Q(location__icontains=q)
                | Q(vendor__name__icontains=q)
            )

        if asset_type:
            qs = qs.filter(asset_type=asset_type)

        if status:
            qs = qs.filter(status=status)

        return qs.order_by("-purchase_date", "name")


@method_decorator(login_required, name="dispatch")
class AssetCreateView(CreateView):
    model = Asset
    form_class = AssetForm
    template_name = "finance/asset_form.html"

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['hotel'] = _hotel(self.request)
        return kwargs

    def form_valid(self, form):
        hotel = _hotel(self.request)
        form.instance.hotel = hotel
        form.instance.created_by = self.request.user
        form.instance.current_value = form.instance.purchase_cost

        messages.success(self.request, f"Asset '{form.instance.name}' created successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("finance:asset_detail", kwargs={"pk": self.object.pk})


@method_decorator(login_required, name="dispatch")
class AssetDetailView(HotelScopedQuerysetMixin, DetailView):
    model = Asset
    template_name = "finance/asset_detail.html"
    context_object_name = "asset"

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return super().get_queryset().select_related(
            "hotel", "vendor", "asset_account",
            "depreciation_account", "expense_account", "created_by",
        )


@method_decorator(login_required, name="dispatch")
class AssetUpdateView(HotelScopedQuerysetMixin, UpdateView):
    model = Asset
    form_class = AssetForm
    template_name = "finance/asset_form.html"
    context_object_name = "asset"

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['hotel'] = self.get_hotel()
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, f"Asset '{form.instance.name}' updated successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("finance:asset_detail", kwargs={"pk": self.object.pk})


@login_required
@require_POST
def asset_delete(request, pk: int):
    _require_finance_access(request.user)
    hotel = _hotel(request)
    asset = get_object_or_404(Asset, pk=pk, hotel=hotel)

    asset_name = asset.name
    asset.delete()
    messages.success(request, f"Asset '{asset_name}' deleted successfully.")
    return redirect("finance:asset_list")


# =========================================================
# Liabilities
# =========================================================

@method_decorator(login_required, name="dispatch")
class LiabilityListView(HotelScopedQuerysetMixin, ListView):
    model = Liability
    template_name = "finance/liability_list.html"
    context_object_name = "liabilities"
    paginate_by = 50

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset().select_related(
            "hotel", "vendor", "payable_account", "created_by",
        )

        q = (self.request.GET.get("q") or "").strip()
        liability_type = (self.request.GET.get("type") or "").strip()
        status = (self.request.GET.get("status") or "").strip()

        if q:
            qs = qs.filter(
                Q(liability_number__icontains=q)
                | Q(name__icontains=q)
                | Q(reference__icontains=q)
                | Q(vendor__name__icontains=q)
            )

        if liability_type:
            qs = qs.filter(liability_type=liability_type)

        if status:
            qs = qs.filter(status=status)

        return qs.order_by("-created_at")


@method_decorator(login_required, name="dispatch")
class LiabilityCreateView(CreateView):
    model = Liability
    form_class = LiabilityForm
    template_name = "finance/liability_form.html"

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['hotel'] = _hotel(self.request)
        return kwargs

    def form_valid(self, form):
        hotel = _hotel(self.request)
        form.instance.hotel = hotel
        form.instance.created_by = self.request.user
        form.instance.balance = form.instance.original_amount

        messages.success(self.request, f"Liability '{form.instance.name}' created successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("finance:liability_detail", kwargs={"pk": self.object.pk})


@method_decorator(login_required, name="dispatch")
class LiabilityDetailView(HotelScopedQuerysetMixin, DetailView):
    model = Liability
    template_name = "finance/liability_detail.html"
    context_object_name = "liability"

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return super().get_queryset().select_related(
            "hotel", "vendor", "payable_account", "created_by",
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        liability = self.object
        hotel = self.get_hotel()

        ctx["related_expenses"] = liability.source_expenses.filter(hotel=hotel).order_by("-expense_date", "-created_at")[:20]
        return ctx


@method_decorator(login_required, name="dispatch")
class LiabilityUpdateView(HotelScopedQuerysetMixin, UpdateView):
    model = Liability
    form_class = LiabilityForm
    template_name = "finance/liability_form.html"
    context_object_name = "liability"

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['hotel'] = self.get_hotel()
        return kwargs

    def get_queryset(self):
        return super().get_queryset().exclude(status=Liability.Status.SETTLED)

    def form_valid(self, form):
        messages.success(self.request, f"Liability '{form.instance.name}' updated successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("finance:liability_detail", kwargs={"pk": self.object.pk})


@login_required
@require_POST
def liability_delete(request, pk: int):
    _require_finance_access(request.user)
    hotel = _hotel(request)
    liability = get_object_or_404(Liability, pk=pk, hotel=hotel)

    if liability.status == Liability.Status.SETTLED:
        messages.error(request, "Cannot delete a settled liability.")
        return redirect("finance:liability_detail", pk=pk)

    liability_name = liability.name
    liability.delete()
    messages.success(request, f"Liability '{liability_name}' deleted successfully.")
    return redirect("finance:liability_list")


# =========================================================
# Journal Entries
# =========================================================

@method_decorator(login_required, name="dispatch")
class JournalListView(HotelScopedQuerysetMixin, ListView):
    model = JournalEntry
    template_name = "finance/journal_list.html"
    context_object_name = "journals"
    paginate_by = 50

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset().select_related(
            "hotel", "created_by", "approved_by",
        ).prefetch_related("lines", "lines__account")

        q = (self.request.GET.get("q") or "").strip()
        status = (self.request.GET.get("status") or "").strip()
        reference_type = (self.request.GET.get("reference_type") or "").strip()

        if q:
            qs = qs.filter(
                Q(entry_number__icontains=q)
                | Q(description__icontains=q)
                | Q(reference_type__icontains=q)
            )

        if status:
            qs = qs.filter(status=status)

        if reference_type:
            qs = qs.filter(reference_type=reference_type)

        return qs.order_by("-entry_date", "-created_at")


@method_decorator(login_required, name="dispatch")
class JournalEntryCreateView(CreateView):
    model = JournalEntry
    form_class = JournalEntryForm
    template_name = "finance/journal_form.html"

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['hotel'] = _hotel(self.request)
        return kwargs

    def form_valid(self, form):
        hotel = _hotel(self.request)
        form.instance.hotel = hotel
        form.instance.created_by = self.request.user
        form.instance.status = JournalEntry.Status.DRAFT

        messages.success(self.request, "Journal entry created. Add lines to complete it.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("finance:journal_detail", kwargs={"pk": self.object.pk})


@method_decorator(login_required, name="dispatch")
class JournalDetailView(HotelScopedQuerysetMixin, DetailView):
    model = JournalEntry
    template_name = "finance/journal_detail.html"
    context_object_name = "journal"

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("hotel", "created_by", "approved_by")
            .prefetch_related("lines", "lines__account")
        )


@method_decorator(login_required, name="dispatch")
class JournalEntryUpdateView(HotelScopedQuerysetMixin, UpdateView):
    model = JournalEntry
    form_class = JournalEntryForm
    template_name = "finance/journal_form.html"
    context_object_name = "journal"

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return super().get_queryset().exclude(status=JournalEntry.Status.POSTED)

    def form_valid(self, form):
        messages.success(self.request, f"Journal {form.instance.entry_number} updated successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("finance:journal_detail", kwargs={"pk": self.object.pk})


@login_required
@require_POST
def journal_line_add(request, journal_pk: int):
    _require_finance_access(request.user)
    hotel = _hotel(request)
    journal = get_object_or_404(JournalEntry, pk=journal_pk, hotel=hotel)

    if journal.status != JournalEntry.Status.DRAFT:
        messages.error(request, "Cannot add lines to a non-draft journal.")
        return redirect("finance:journal_detail", pk=journal_pk)

    form = JournalLineForm(request.POST, hotel=hotel)
    if form.is_valid():
        line = form.save(commit=False)
        line.journal_entry = journal
        line.save()
        messages.success(request, "Journal line added.")
    else:
        for error in form.errors.values():
            messages.error(request, ", ".join(error))

    return redirect("finance:journal_detail", pk=journal_pk)


@login_required
@require_POST
def journal_line_delete(request, line_pk: int):
    _require_finance_access(request.user)
    line = get_object_or_404(JournalLine, pk=line_pk)
    journal = line.journal_entry

    if journal.status != JournalEntry.Status.DRAFT:
        messages.error(request, "Cannot delete lines from a non-draft journal.")
        return redirect("finance:journal_detail", pk=journal.pk)

    line.delete()
    messages.success(request, "Journal line deleted.")
    return redirect("finance:journal_detail", pk=journal.pk)


@login_required
@require_POST
def journal_post(request, pk: int):
    _require_finance_access(request.user)
    hotel = _hotel(request)
    journal = get_object_or_404(JournalEntry, pk=pk, hotel=hotel)

    try:
        journal.post(request.user)
        messages.success(request, f"Journal {journal.entry_number} posted successfully.")
    except ValidationError as e:
        messages.error(request, ", ".join(getattr(e, "messages", [str(e)])))

    return redirect("finance:journal_detail", pk=pk)


@login_required
@require_POST
def journal_delete(request, pk: int):
    _require_finance_access(request.user)
    hotel = _hotel(request)
    journal = get_object_or_404(JournalEntry, pk=pk, hotel=hotel)

    if journal.status == JournalEntry.Status.POSTED:
        messages.error(request, "Cannot delete a posted journal entry.")
        return redirect("finance:journal_detail", pk=pk)

    journal.delete()
    messages.success(request, f"Journal {journal.entry_number} deleted successfully.")
    return redirect("finance:journal_list")


# =========================================================
# Financial Reports
# =========================================================

@method_decorator(login_required, name="dispatch")
class ProfitLossView(TemplateView):
    template_name = "finance/reports/profit_loss.html"

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hotel = _hotel(self.request)

        today = timezone.localdate()
        start_date = self.request.GET.get("start_date")
        end_date = self.request.GET.get("end_date")

        if start_date and end_date:
            start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
        else:
            start_date = today.replace(day=1)
            end_date = today

        revenue_lines = (
            JournalLine.objects.filter(
                journal_entry__hotel=hotel,
                journal_entry__status=JournalEntry.Status.POSTED,
                journal_entry__entry_date__gte=start_date,
                journal_entry__entry_date__lte=end_date,
                account__account_type=Account.AccountType.REVENUE,
            )
            .values("account__name")
            .annotate(total=Coalesce(Sum("credit"), D0))
            .order_by("account__name")
        )

        expense_lines = (
            JournalLine.objects.filter(
                journal_entry__hotel=hotel,
                journal_entry__status=JournalEntry.Status.POSTED,
                journal_entry__entry_date__gte=start_date,
                journal_entry__entry_date__lte=end_date,
                account__account_type=Account.AccountType.EXPENSE,
            )
            .values("account__name")
            .annotate(total=Coalesce(Sum("debit"), D0))
            .order_by("account__name")
        )

        total_revenue = sum((item["total"] for item in revenue_lines), D0)
        total_expenses = sum((item["total"] for item in expense_lines), D0)
        net_profit = total_revenue - total_expenses

        ctx.update({
            "hotel": hotel,
            "start_date": start_date,
            "end_date": end_date,
            "revenue_lines": revenue_lines,
            "expense_lines": expense_lines,
            "total_revenue": total_revenue,
            "total_expenses": total_expenses,
            "net_profit": net_profit,
        })
        return ctx


@method_decorator(login_required, name="dispatch")
class CashFlowView(TemplateView):
    template_name = "finance/reports/cash_flow.html"

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hotel = _hotel(self.request)

        today = timezone.localdate()
        start_date = self.request.GET.get("start_date")
        end_date = self.request.GET.get("end_date")

        if start_date and end_date:
            start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
        else:
            start_date = today.replace(day=1)
            end_date = today

        inflows = Payment.objects.filter(
            hotel=hotel,
            status=Payment.PaymentStatus.COMPLETED,
            received_at__date__gte=start_date,
            received_at__date__lte=end_date,
        ).aggregate(total=Coalesce(Sum("amount"), D0))["total"]

        outflows = Expense.objects.filter(
            hotel=hotel,
            approval_status__in=[Expense.ApprovalStatus.PAID, Expense.ApprovalStatus.PARTIAL],
            expense_date__gte=start_date,
            expense_date__lte=end_date,
        ).aggregate(total=Coalesce(Sum("total_amount"), D0))["total"]

        net_cash_flow = inflows - outflows

        cash_accounts = Account.objects.filter(
            hotel=hotel,
            account_type=Account.AccountType.ASSET,
            account_subtype__in=[Account.SubType.CASH, Account.SubType.BANK],
            is_active=True,
        ).order_by("account_code")

        ctx.update({
            "hotel": hotel,
            "start_date": start_date,
            "end_date": end_date,
            "cash_inflows": inflows,
            "cash_outflows": outflows,
            "net_cash_flow": net_cash_flow,
            "cash_accounts": cash_accounts,
        })
        return ctx


@method_decorator(login_required, name="dispatch")
class BalanceSheetView(TemplateView):
    template_name = "finance/reports/balance_sheet.html"

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hotel = _hotel(self.request)

        assets = Account.objects.filter(
            hotel=hotel,
            account_type=Account.AccountType.ASSET,
            is_active=True,
        ).order_by("account_code")

        liabilities = Account.objects.filter(
            hotel=hotel,
            account_type=Account.AccountType.LIABILITY,
            is_active=True,
        ).order_by("account_code")

        equity = Account.objects.filter(
            hotel=hotel,
            account_type=Account.AccountType.EQUITY,
            is_active=True,
        ).order_by("account_code")

        total_assets = sum((acc.balance for acc in assets), D0)
        total_liabilities = sum((acc.balance for acc in liabilities), D0)
        total_equity = sum((acc.balance for acc in equity), D0)

        ctx.update({
            "hotel": hotel,
            "as_of_date": timezone.localdate(),
            "assets": assets,
            "liabilities": liabilities,
            "equity": equity,
            "total_assets": total_assets,
            "total_liabilities": total_liabilities,
            "total_equity": total_equity,
        })
        return ctx


@method_decorator(login_required, name="dispatch")
class TrialBalanceView(TemplateView):
    template_name = "finance/reports/trial_balance.html"

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hotel = _hotel(self.request)

        form = TrialBalanceForm(self.request.GET or None)

        if form.is_valid():
            start_date = form.cleaned_data.get("start_date")
            end_date = form.cleaned_data.get("end_date")
            account_type = form.cleaned_data.get("account_type")
            include_zero = form.cleaned_data.get("include_zero_balances", False)
        else:
            today = timezone.localdate()
            start_date = today.replace(day=1)
            end_date = today
            account_type = None
            include_zero = False

        accounts = Account.objects.filter(hotel=hotel, is_active=True)

        if account_type:
            accounts = accounts.filter(account_type=account_type)

        if not include_zero:
            accounts = accounts.filter(
                Q(journal_lines__debit__gt=0) | Q(journal_lines__credit__gt=0)
            ).distinct()

        accounts = accounts.order_by("account_code")

        trial_balance = []
        total_debits = D0
        total_credits = D0

        for account in accounts:
            if start_date and end_date:
                # Filter journal lines by date range
                lines = account.journal_lines.filter(
                    journal_entry__status=JournalEntry.Status.POSTED,
                    journal_entry__entry_date__gte=start_date,
                    journal_entry__entry_date__lte=end_date,
                )
                debit_total = lines.aggregate(total=Sum("debit"))["total"] or D0
                credit_total = lines.aggregate(total=Sum("credit"))["total"] or D0

                if account.account_type in [Account.AccountType.ASSET, Account.AccountType.EXPENSE]:
                    balance = debit_total - credit_total
                else:
                    balance = credit_total - debit_total
            else:
                balance = account.balance

            if include_zero or balance != D0:
                trial_balance.append({
                    "account_code": account.account_code,
                    "account_name": account.name,
                    "account_type": account.get_account_type_display(),
                    "debit": balance if account.account_type in [Account.AccountType.ASSET, Account.AccountType.EXPENSE] else D0,
                    "credit": balance if account.account_type in [Account.AccountType.LIABILITY, Account.AccountType.EQUITY, Account.AccountType.REVENUE] else D0,
                })

                if account.account_type in [Account.AccountType.ASSET, Account.AccountType.EXPENSE]:
                    total_debits += balance
                else:
                    total_credits += balance

        ctx.update({
            "hotel": hotel,
            "form": form,
            "trial_balance": trial_balance,
            "total_debits": total_debits,
            "total_credits": total_credits,
            "start_date": start_date,
            "end_date": end_date,
        })
        return ctx


# Add this to finance/views.py

@method_decorator(login_required, name="dispatch")
class CashAccountDetailView(HotelScopedQuerysetMixin, DetailView):
    model = CashAccount
    template_name = "finance/cash_account_detail.html"
    context_object_name = "account"

    def dispatch(self, request, *args, **kwargs):
        _require_finance_access(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        account = self.object
        
        ctx["recent_payments"] = account.payments.select_related("invoice").order_by("-received_at")[:20]
        ctx["recent_expenses"] = account.expenses.order_by("-expense_date", "-created_at")[:20]
        ctx["recent_movements"] = account.movements.order_by("-created_at")[:20]
        
        return ctx

        