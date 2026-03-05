# finance/views.py
from __future__ import annotations

from datetime import datetime, time

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q, Sum, F
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView, ListView, DetailView, CreateView

from hotel_thinker.utils import get_active_hotel_for_user, require_hotel_role
from .forms import ExpenseForm, PaymentForm
from .models import Invoice, Expense, FinancialPeriod, Payment


# -------------------------
# Optional: Restaurant payments (safe import)
# -------------------------
# If you have a restaurant app with a model that records payments, import it here.
# Adjust names/fields if yours differ.
try:
    # Example expected model names (change to match your restaurant app):
    # - RestaurantPayment or OrderPayment or Payment
    # - fields: hotel, amount, status, paid_at/created_at, order (optional)
    from restaurant.models import RestaurantPayment  # type: ignore
except Exception:
    RestaurantPayment = None  # noqa: N816


# -------------------------
# Helpers / Mixins
# -------------------------
def _hotel(request):
    # IMPORTANT: pass request so your "active hotel" logic works correctly
    return get_active_hotel_for_user(request.user, request=request)


class HotelScopedQuerysetMixin:
    """Ensures every queryset is scoped to the active hotel"""

    def get_hotel(self):
        return get_active_hotel_for_user(self.request.user, request=self.request)

    def get_queryset(self):
        return super().get_queryset().filter(hotel=self.get_hotel())


def _aware_start_of_day(d):
    tz = timezone.get_current_timezone()
    return timezone.make_aware(datetime.combine(d, time.min), tz)


def _aware_end_of_day(d):
    tz = timezone.get_current_timezone()
    return timezone.make_aware(datetime.combine(d, time.max), tz)


# -------------------------
# Dashboard
# -------------------------
@method_decorator(login_required, name="dispatch")
class DashboardView(TemplateView):
    template_name = "finance/dashboard.html"

    def dispatch(self, request, *args, **kwargs):
        require_hotel_role(request.user, {"admin", "accountant", "general_manager"})
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hotel = _hotel(self.request)

        today = timezone.localdate()
        month_start = today.replace(day=1)

        # ---- Finance revenue: from COMPLETED payments ----
        finance_today_revenue = (
            Payment.objects.filter(
                hotel=hotel,
                status=Payment.PaymentStatus.COMPLETED,
                received_at__date=today,
            ).aggregate(total=Sum("amount"))["total"]
            or 0
        )

        finance_monthly_revenue = (
            Payment.objects.filter(
                hotel=hotel,
                status=Payment.PaymentStatus.COMPLETED,
                received_at__date__gte=month_start,
                received_at__date__lte=today,
            ).aggregate(total=Sum("amount"))["total"]
            or 0
        )

        # ---- Optional: Restaurant revenue (if model exists) ----
        restaurant_today_revenue = 0
        restaurant_monthly_revenue = 0

        if RestaurantPayment is not None:
            # Adjust these fields if your restaurant payment model differs
            # Common patterns: status="paid" OR is_paid=True OR PaymentStatus.PAID
            qs = RestaurantPayment.objects.filter(hotel=hotel)

            # Try to detect status field style
            if hasattr(RestaurantPayment, "Status"):
                # e.g. RestaurantPayment.Status.PAID
                paid_value = getattr(RestaurantPayment.Status, "PAID", None)
                if paid_value is not None:
                    qs = qs.filter(status=paid_value)
            elif "status" in [f.name for f in RestaurantPayment._meta.fields]:
                qs = qs.filter(status__in=["paid", "PAID", "completed", "COMPLETED"])
            elif "is_paid" in [f.name for f in RestaurantPayment._meta.fields]:
                qs = qs.filter(is_paid=True)

            date_field = "paid_at" if "paid_at" in [f.name for f in RestaurantPayment._meta.fields] else "created_at"

            restaurant_today_revenue = qs.filter(**{f"{date_field}__date": today}).aggregate(total=Sum("amount"))[
                "total"
            ] or 0

            restaurant_monthly_revenue = qs.filter(
                **{
                    f"{date_field}__date__gte": month_start,
                    f"{date_field}__date__lte": today,
                }
            ).aggregate(total=Sum("amount"))["total"] or 0

        # ---- Combined revenue shown on dashboard ----
        today_revenue = finance_today_revenue + restaurant_today_revenue
        monthly_revenue = finance_monthly_revenue + restaurant_monthly_revenue

        # ---- Pending invoices: not fully paid ----
        pending_payments = (
            Invoice.objects.filter(
                hotel=hotel,
                status__in=[
                    Invoice.Status.ISSUED,
                    Invoice.Status.SENT,
                    Invoice.Status.PARTIALLY_PAID,
                    Invoice.Status.OVERDUE,
                ],
            )
            .filter(total_amount__gt=F("amount_paid"))
            .count()
        )

        # ---- Expenses (PAID this month) ----
        expenses = (
            Expense.objects.filter(
                hotel=hotel,
                approval_status=Expense.ApprovalStatus.PAID,
                payment_date__gte=month_start,
                payment_date__lte=today,
            ).aggregate(total=Sum("total_amount"))["total"]
            or 0
        )

        # ---- Recent Transactions (merge income + expenses) ----
        transactions = []

        # Finance payments
        recent_finance_payments = (
            Payment.objects.filter(hotel=hotel, status=Payment.PaymentStatus.COMPLETED)
            .select_related("invoice")
            .order_by("-received_at")[:15]
        )
        for p in recent_finance_payments:
            inv_no = p.invoice.invoice_number if getattr(p, "invoice_id", None) else "N/A"
            transactions.append(
                {
                    "date": p.received_at,
                    "description": f"Payment received (Invoice {inv_no})",
                    "amount": p.amount,
                    "type": "Income",
                }
            )

        # Restaurant payments (optional)
        if RestaurantPayment is not None:
            qs = RestaurantPayment.objects.filter(hotel=hotel)

            if hasattr(RestaurantPayment, "Status"):
                paid_value = getattr(RestaurantPayment.Status, "PAID", None)
                if paid_value is not None:
                    qs = qs.filter(status=paid_value)
            elif "status" in [f.name for f in RestaurantPayment._meta.fields]:
                qs = qs.filter(status__in=["paid", "PAID", "completed", "COMPLETED"])
            elif "is_paid" in [f.name for f in RestaurantPayment._meta.fields]:
                qs = qs.filter(is_paid=True)

            date_field = "paid_at" if "paid_at" in [f.name for f in RestaurantPayment._meta.fields] else "created_at"

            recent_restaurant_payments = qs.order_by(f"-{date_field}")[:15]
            for rp in recent_restaurant_payments:
                dt = getattr(rp, date_field)
                label = "Restaurant payment"
                if hasattr(rp, "order_id") and getattr(rp, "order_id"):
                    label = f"Restaurant payment (Order #{rp.order_id})"

                transactions.append(
                    {
                        "date": dt,
                        "description": label,
                        "amount": rp.amount,
                        "type": "Income",
                    }
                )

        # Expenses
        recent_expenses = (
            Expense.objects.filter(hotel=hotel, approval_status=Expense.ApprovalStatus.PAID)
            .order_by("-payment_date", "-created_at")[:15]
        )
        for e in recent_expenses:
            # convert date to datetime for proper sorting
            dt = timezone.make_aware(datetime.combine(e.payment_date, time.min), timezone.get_current_timezone())
            transactions.append(
                {
                    "date": dt,
                    "description": f"Expense: {e.title}",
                    "amount": e.total_amount,
                    "type": "Expense",
                }
            )

        transactions = sorted(transactions, key=lambda x: x["date"], reverse=True)[:12]

        # Your template prints date; keep it date-only
        for t in transactions:
            t["date"] = t["date"].date() if hasattr(t["date"], "date") else t["date"]

        ctx.update(
            {
                "hotel": hotel,
                "today_revenue": today_revenue,
                "monthly_revenue": monthly_revenue,
                "pending_payments": pending_payments,
                "expenses": expenses,
                "transactions": transactions,
            }
        )
        return ctx


# -------------------------
# Invoices
# -------------------------
@method_decorator(login_required, name="dispatch")
class InvoiceListView(HotelScopedQuerysetMixin, ListView):
    model = Invoice
    template_name = "finance/invoice_list.html"
    context_object_name = "invoices"
    paginate_by = 50

    def dispatch(self, request, *args, **kwargs):
        require_hotel_role(request.user, {"admin", "accountant", "general_manager"})
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset().select_related("booking")
        q = (self.request.GET.get("q") or "").strip()
        status = (self.request.GET.get("status") or "").strip()

        if q:
            qs = qs.filter(Q(invoice_number__icontains=q) | Q(customer_name__icontains=q))

        if status:
            qs = qs.filter(status=status)

        return qs.order_by("-invoice_date", "-created_at")


@method_decorator(login_required, name="dispatch")
class InvoiceDetailView(HotelScopedQuerysetMixin, DetailView):
    model = Invoice
    template_name = "finance/invoice_detail.html"
    context_object_name = "invoice"

    def dispatch(self, request, *args, **kwargs):
        require_hotel_role(request.user, {"admin", "accountant", "general_manager"})
        return super().dispatch(request, *args, **kwargs)


@login_required
@require_POST
def invoice_issue(request, pk: int):
    require_hotel_role(request.user, {"admin", "accountant", "general_manager"})
    hotel = _hotel(request)
    invoice = get_object_or_404(Invoice, pk=pk, hotel=hotel)

    try:
        invoice.issue(request.user)
        messages.success(request, "Invoice issued.")
    except ValidationError as e:
        messages.error(request, ", ".join(getattr(e, "messages", [str(e)])))

    return redirect("finance:invoice_detail", pk=pk)


@login_required
@require_POST
def invoice_mark_sent(request, pk: int):
    require_hotel_role(request.user, {"admin", "accountant", "general_manager"})
    hotel = _hotel(request)
    invoice = get_object_or_404(Invoice, pk=pk, hotel=hotel)

    try:
        invoice.mark_sent(request.user)
        messages.success(request, "Invoice marked as sent.")
    except ValidationError as e:
        messages.error(request, ", ".join(getattr(e, "messages", [str(e)])))

    return redirect("finance:invoice_detail", pk=pk)


@login_required
def invoice_record_payment(request, pk: int):
    """
    Records payment via invoice.record_payment(...) which creates a Payment
    and updates invoice status (partial/paid).
    """
    require_hotel_role(request.user, {"admin", "accountant", "general_manager"})
    hotel = _hotel(request)
    invoice = get_object_or_404(Invoice, pk=pk, hotel=hotel)

    if request.method == "POST":
        form = PaymentForm(request.POST, invoice=invoice)
        if form.is_valid():
            amount = form.cleaned_data["amount"]
            method = form.cleaned_data["method"]
            reference = form.cleaned_data.get("reference")

            try:
                invoice.record_payment(amount=amount, method=method, user=request.user, reference=reference)
                messages.success(request, "Payment recorded.")
                return redirect("finance:invoice_detail", pk=pk)
            except ValidationError as e:
                messages.error(request, ", ".join(getattr(e, "messages", [str(e)])))
    else:
        form = PaymentForm(invoice=invoice)

    return render(request, "finance/payment_form.html", {"invoice": invoice, "form": form})


# -------------------------
# Expenses
# -------------------------
@method_decorator(login_required, name="dispatch")
class ExpenseListView(HotelScopedQuerysetMixin, ListView):
    model = Expense
    template_name = "finance/expense_list.html"
    context_object_name = "expenses"
    paginate_by = 50

    def dispatch(self, request, *args, **kwargs):
        require_hotel_role(request.user, {"admin", "accountant", "general_manager"})
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        q = (self.request.GET.get("q") or "").strip()
        status = (self.request.GET.get("status") or "").strip()

        if q:
            qs = qs.filter(
                Q(title__icontains=q)
                | Q(expense_number__icontains=q)
                | Q(payee__icontains=q)
                | Q(vendor__icontains=q)
            )

        if status:
            qs = qs.filter(approval_status=status)

        return qs.order_by("-payment_date", "-created_at")


@method_decorator(login_required, name="dispatch")
class ExpenseCreateView(CreateView):
    model = Expense
    form_class = ExpenseForm
    template_name = "finance/expense_form.html"

    def dispatch(self, request, *args, **kwargs):
        require_hotel_role(request.user, {"admin", "accountant", "general_manager"})
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        hotel = _hotel(self.request)
        form.instance.hotel = hotel
        form.instance.created_by = self.request.user
        form.instance.requested_by = self.request.user
        messages.success(self.request, "Expense created and submitted for approval.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("finance:expense_list")


@login_required
@require_POST
def expense_approve(request, pk: int):
    require_hotel_role(request.user, {"admin", "general_manager"})
    hotel = _hotel(request)
    expense = get_object_or_404(Expense, pk=pk, hotel=hotel)

    try:
        expense.approve(request.user)
        messages.success(request, "Expense approved.")
    except ValidationError as e:
        messages.error(request, ", ".join(getattr(e, "messages", [str(e)])))

    return redirect("finance:expense_list")


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
    require_hotel_role(request.user, {"admin", "accountant", "general_manager"})
    hotel = _hotel(request)
    expense = get_object_or_404(Expense, pk=pk, hotel=hotel)

    try:
        expense.mark_paid(request.user)
        messages.success(request, "Expense marked as paid.")
    except ValidationError as e:
        messages.error(request, ", ".join(getattr(e, "messages", [str(e)])))

    return redirect("finance:expense_list")


# -------------------------
# Financial Periods
# -------------------------
@method_decorator(login_required, name="dispatch")
class PeriodListView(HotelScopedQuerysetMixin, ListView):
    model = FinancialPeriod
    template_name = "finance/period_list.html"
    context_object_name = "periods"
    paginate_by = 50

    def dispatch(self, request, *args, **kwargs):
        require_hotel_role(request.user, {"admin", "accountant", "general_manager"})
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return super().get_queryset().order_by("-start_date")


@method_decorator(login_required, name="dispatch")
class PeriodDetailView(HotelScopedQuerysetMixin, DetailView):
    model = FinancialPeriod
    template_name = "finance/period_detail.html"
    context_object_name = "period"

    def dispatch(self, request, *args, **kwargs):
        require_hotel_role(request.user, {"admin", "accountant", "general_manager"})
        return super().dispatch(request, *args, **kwargs)


@login_required
@require_POST
def period_close(request, pk: int):
    require_hotel_role(request.user, {"admin", "accountant", "general_manager"})
    hotel = _hotel(request)
    period = get_object_or_404(FinancialPeriod, pk=pk, hotel=hotel)

    try:
        period.close(request.user)
        period.save(update_fields=["status", "closed_by", "closed_at", "total_revenue", "total_expenses", "net_profit"])
        messages.success(request, f"Period '{period.name}' closed.")
    except ValidationError as e:
        messages.error(request, ", ".join(getattr(e, "messages", [str(e)])))

    return redirect("finance:period_detail", pk=pk)