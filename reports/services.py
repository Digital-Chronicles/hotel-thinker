from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import Coalesce

from finance.models import Expense
from store.models import StoreSale
from restaurant.models import RestaurantOrder
from bookings.models import Booking

D0 = Decimal("0.00")


def _to_decimal(value) -> Decimal:
    """
    Safely convert values to Decimal.
    """
    if value is None:
        return D0
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return D0


def _booking_total(booking) -> Decimal:
    """
    Try to read a total from Booking safely without assuming one exact field name.
    """
    possible_fields = [
        "total_amount",
        "total",
        "amount",
        "grand_total",
        "net_amount",
    ]

    for field in possible_fields:
        if hasattr(booking, field):
            return _to_decimal(getattr(booking, field, D0))

    return D0


def _restaurant_item_total(item) -> Decimal:
    """
    Calculate a restaurant order item's total safely.
    Supports different field naming styles.
    """
    # Best case: item already exposes a total/line total property
    possible_total_fields = [
        "line_total",
        "total",
        "subtotal",
        "amount",
    ]
    for field in possible_total_fields:
        if hasattr(item, field):
            return _to_decimal(getattr(item, field, D0))

    # Fallback: derive from qty x unit price using common field names
    qty = None
    price = None

    for field in ["qty", "quantity", "count"]:
        if hasattr(item, field):
            qty = getattr(item, field, None)
            break

    for field in ["unit_price", "price", "selling_price", "rate"]:
        if hasattr(item, field):
            price = getattr(item, field, None)
            break

    return _to_decimal(qty) * _to_decimal(price)


def _restaurant_order_total(order) -> Decimal:
    """
    Calculate a restaurant order total safely.
    """
    possible_total_fields = [
        "total_amount",
        "total",
        "grand_total",
        "subtotal",
        "amount",
    ]
    for field in possible_total_fields:
        if hasattr(order, field):
            value = getattr(order, field, None)
            if value is not None:
                return _to_decimal(value)

    total = D0
    items_manager = getattr(order, "items", None)
    if items_manager is not None:
        for item in items_manager.all():
            total += _restaurant_item_total(item)
    return total


def get_profit_and_loss_data(start_date=None, end_date=None) -> dict:
    """
    Build a profit and loss summary from Store, Bookings, Restaurant, and Expenses.
    This version is defensive and works with mixed model naming.
    """
    store_sales_qs = StoreSale.objects.filter(status=StoreSale.Status.PAID)
    booking_qs = Booking.objects.all()
    restaurant_qs = RestaurantOrder.objects.all().prefetch_related("items")
    expense_qs = Expense.objects.all()

    # Date filters
    if start_date:
        store_sales_qs = store_sales_qs.filter(created_at__date__gte=start_date)

        if hasattr(Booking, "created_at"):
            booking_qs = booking_qs.filter(created_at__date__gte=start_date)
        elif hasattr(Booking, "check_in"):
            booking_qs = booking_qs.filter(check_in__gte=start_date)

        if hasattr(RestaurantOrder, "created_at"):
            restaurant_qs = restaurant_qs.filter(created_at__date__gte=start_date)

        if hasattr(Expense, "expense_date"):
            expense_qs = expense_qs.filter(expense_date__gte=start_date)
        elif hasattr(Expense, "date"):
            expense_qs = expense_qs.filter(date__gte=start_date)
        elif hasattr(Expense, "created_at"):
            expense_qs = expense_qs.filter(created_at__date__gte=start_date)

    if end_date:
        store_sales_qs = store_sales_qs.filter(created_at__date__lte=end_date)

        if hasattr(Booking, "created_at"):
            booking_qs = booking_qs.filter(created_at__date__lte=end_date)
        elif hasattr(Booking, "check_in"):
            booking_qs = booking_qs.filter(check_in__lte=end_date)

        if hasattr(RestaurantOrder, "created_at"):
            restaurant_qs = restaurant_qs.filter(created_at__date__lte=end_date)

        if hasattr(Expense, "expense_date"):
            expense_qs = expense_qs.filter(expense_date__lte=end_date)
        elif hasattr(Expense, "date"):
            expense_qs = expense_qs.filter(date__lte=end_date)
        elif hasattr(Expense, "created_at"):
            expense_qs = expense_qs.filter(created_at__date__lte=end_date)

    # Store revenue
    store_revenue = sum((_to_decimal(sale.total) for sale in store_sales_qs), D0)

    # Booking revenue
    booking_revenue = D0
    for booking in booking_qs:
        booking_revenue += _booking_total(booking)

    # Restaurant revenue
    restaurant_revenue = D0
    for order in restaurant_qs:
        restaurant_revenue += _restaurant_order_total(order)

    # Expenses
    if hasattr(Expense, "amount"):
        total_expenses = expense_qs.aggregate(
            total=Coalesce(Sum("amount"), D0)
        )["total"] or D0
    else:
        total_expenses = D0
        for expense in expense_qs:
            total_expenses += _to_decimal(getattr(expense, "amount", D0))

    total_revenue = store_revenue + booking_revenue + restaurant_revenue
    gross_profit = total_revenue - total_expenses
    net_profit = gross_profit

    return {
        "store_revenue": store_revenue,
        "booking_revenue": booking_revenue,
        "restaurant_revenue": restaurant_revenue,
        "total_revenue": total_revenue,
        "total_expenses": total_expenses,
        "gross_profit": gross_profit,
        "net_profit": net_profit,
    }


def get_store_stock_valuation_data() -> dict:
    """
    Optional helper for stock valuation report.
    """
    from store.models import StoreItem

    items = StoreItem.objects.select_related("hotel", "category").all()

    rows = []
    grand_total = D0

    for item in items:
        qty = _to_decimal(item.stock_qty)
        cost = _to_decimal(item.cost_price)
        total_value = qty * cost
        grand_total += total_value

        rows.append({
            "item": item,
            "qty": qty,
            "cost_price": cost,
            "total_value": total_value,
        })

    return {
        "items": rows,
        "grand_total": grand_total,
    }


def get_store_sales_report_data(start_date=None, end_date=None) -> dict:
    """
    Optional helper for store sales report.
    """
    qs = StoreSale.objects.prefetch_related("items").all()

    if start_date:
        qs = qs.filter(created_at__date__gte=start_date)
    if end_date:
        qs = qs.filter(created_at__date__lte=end_date)

    paid_sales = qs.filter(status=StoreSale.Status.PAID)
    open_sales = qs.filter(status=StoreSale.Status.OPEN)
    cancelled_sales = qs.filter(status=StoreSale.Status.CANCELLED)

    paid_total = sum((_to_decimal(sale.total) for sale in paid_sales), D0)
    open_total = sum((_to_decimal(sale.total) for sale in open_sales), D0)
    cancelled_total = sum((_to_decimal(sale.total) for sale in cancelled_sales), D0)

    return {
        "sales": qs.order_by("-created_at"),
        "paid_total": paid_total,
        "open_total": open_total,
        "cancelled_total": cancelled_total,
        "total_count": qs.count(),
    }