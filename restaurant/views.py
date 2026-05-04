from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Prefetch, Sum, F
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import ListView, CreateView, DetailView, TemplateView, UpdateView, DeleteView

from hotel_thinker.utils import get_active_hotel_for_user, require_hotel_role

from .models import (
    DiningArea, Table, MenuCategory, MenuItem,
    RestaurantOrder, RestaurantOrderItem, RestaurantPayment,
)
from .forms import (
    DiningAreaForm, TableForm, MenuCategoryForm, MenuItemForm,
    RestaurantOrderForm, RestaurantOrderItemForm,
    OrderStatusForm, PaymentForm,
)


# ============================================================================
# Helpers
# ============================================================================

def get_hotel(request: HttpRequest):
    """Get active hotel for the current request"""
    return get_active_hotel_for_user(request.user, request=request)


def require_staff_role(request: HttpRequest):
    """Require staff level access (server, manager, admin)"""
    require_hotel_role(request.user, {"admin", "restaurant_manager", "server", "general_manager"})


def require_manager_role(request: HttpRequest):
    """Require manager level access"""
    require_hotel_role(request.user, {"admin", "restaurant_manager", "general_manager"})


def get_order_or_404(request: HttpRequest, pk: int) -> RestaurantOrder:
    """Get order belonging to current hotel or 404"""
    return get_object_or_404(RestaurantOrder, pk=pk, hotel=get_hotel(request))


def render_order_items_response(order: RestaurantOrder, request: HttpRequest) -> Dict[str, Any]:
    """Helper to render order items HTML and totals for AJAX responses"""
    items = order.items.select_related("item").order_by("-id")
    html = render_to_string(
        "restaurant/partials/order_items_table.html",
        {"order": order, "items": items},
        request=request
    )
    
    return {
        "ok": True,
        "items_html": html,
        "subtotal": str(order.subtotal),
        "discount": str(order.discount or 0),
        "tax": str(order.tax or 0),
        "total": str(order.total),
        "status": order.status,
    }


class HotelScopedQuerysetMixin:
    """Mixin to filter querysets by current hotel"""
    
    def get_hotel(self):
        return get_hotel(self.request)
    
    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(hotel=self.get_hotel())


# ============================================================================
# Order Views
# ============================================================================
@method_decorator(login_required, name="dispatch")
class OrderListView(HotelScopedQuerysetMixin, ListView):
    """List and filter restaurant orders"""
    model = RestaurantOrder
    template_name = "restaurant/order_list.html"
    context_object_name = "orders"
    paginate_by = 50

    def dispatch(self, request, *args, **kwargs):
        require_staff_role(request)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        # Start with base queryset - DO NOT slice here
        qs = super().get_queryset().select_related(
            "table", "table__area"
        ).prefetch_related(
            # Remove the slice [:5] from here - it breaks filtering
            Prefetch("items", queryset=RestaurantOrderItem.objects.select_related("item"))
        ).order_by("-created_at")
        
        # Apply filters
        q = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status", "").strip()
        
        if q:
            qs = qs.filter(
                Q(order_number__icontains=q) |
                Q(customer_name__icontains=q) |
                Q(table__number__icontains=q)
            )
        if status:
            qs = qs.filter(status=status)
            
        return qs
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hotel = self.get_hotel()
        
        # Add status choices
        ctx["status_choices"] = RestaurantOrder.Status.choices
        ctx["current_status"] = self.request.GET.get("status", "")
        ctx["search_query"] = self.request.GET.get("q", "")
        
        # Add stats for the dashboard cards
        from django.utils import timezone
        
        today = timezone.localdate()
        
        # Calculate today's revenue from paid orders
        today_paid_orders = RestaurantOrder.objects.filter(
            hotel=hotel,
            status=RestaurantOrder.Status.PAID,
            closed_at__date=today
        )
        
        # Sum the total from invoices (iterate since total is a property)
        today_revenue = 0
        for order in today_paid_orders:
            today_revenue += order.total
        
        ctx["stats"] = {
            "active_orders": RestaurantOrder.objects.filter(
                hotel=hotel,
                status__in=[RestaurantOrder.Status.OPEN, RestaurantOrder.Status.KITCHEN]
            ).count(),
            "kitchen_orders": RestaurantOrder.objects.filter(
                hotel=hotel,
                status=RestaurantOrder.Status.KITCHEN
            ).count(),
            "ready_orders": RestaurantOrder.objects.filter(
                hotel=hotel,
                status=RestaurantOrder.Status.SERVED
            ).count(),
            "today_revenue": today_revenue,
        }
        
        return ctx
        
          
@method_decorator(login_required, name="dispatch")
class OrderDetailView(HotelScopedQuerysetMixin, DetailView):
    """View order details with items and actions"""
    model = RestaurantOrder
    template_name = "restaurant/order_detail.html"
    context_object_name = "order"

    def dispatch(self, request, *args, **kwargs):
        require_staff_role(request)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        # Remove the problematic Prefetch - you don't need it here
        return super().get_queryset().select_related(
            "table", "table__area", "booking", "created_by", "updated_by"
        ).prefetch_related(
            "items__item"  # This is correct - prefetch items with their related menu items
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        order = self.object
        hotel = self.get_hotel()
        
        # Get the invoice safely - use try/except to avoid DoesNotExist
        invoice = None
        try:
            invoice = order.invoice
        except RestaurantOrder.invoice.RelatedObjectDoesNotExist:
            pass
        
        ctx.update({
            "hotel": hotel,
            "items": order.items.select_related("item").order_by("-id"),
            "invoice": invoice,
            "item_form": RestaurantOrderItemForm(hotel=hotel),
            "status_form": OrderStatusForm(initial={"status": order.status}),
            "payment_form": PaymentForm(order=order),
            "can_edit": order.status not in {
                RestaurantOrder.Status.PAID,
                RestaurantOrder.Status.CANCELLED
            },
            "can_bill": order.status == RestaurantOrder.Status.SERVED and order.items.exists(),
            "can_pay": order.status in {RestaurantOrder.Status.BILLED, RestaurantOrder.Status.SERVED},
        })
        return ctx
      

@method_decorator(login_required, name="dispatch")
class OrderCreateView(CreateView):
    """Create a new restaurant order"""
    model = RestaurantOrder
    form_class = RestaurantOrderForm
    template_name = "restaurant/order_form.html"

    def dispatch(self, request, *args, **kwargs):
        require_staff_role(request)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["hotel"] = get_hotel(self.request)
        return kwargs

    def form_valid(self, form):
        form.instance.hotel = get_hotel(self.request)
        form.instance.created_by = self.request.user
        form.instance.status = RestaurantOrder.Status.OPEN
        
        with transaction.atomic():
            response = super().form_valid(form)
            
        messages.success(self.request, f"Order #{self.object.order_number} created successfully.")
        return response

    def get_success_url(self):
        return reverse("restaurant:order_detail", kwargs={"pk": self.object.pk})


# ============================================================================
# AJAX Endpoints for Order Items
# ============================================================================

@login_required
@require_GET
def menu_items_api(request: HttpRequest) -> JsonResponse:
    """API endpoint for menu item autocomplete/search"""
    hotel = get_hotel(request)
    query = request.GET.get("q", "").strip()
    category_id = request.GET.get("category", "").strip()
    
    qs = MenuItem.objects.filter(hotel=hotel, is_active=True).select_related("category")
    
    if query:
        qs = qs.filter(name__icontains=query)
    if category_id:
        qs = qs.filter(category_id=category_id)
    
    data = [
        {
            "id": item.id,
            "name": item.name,
            "price": str(item.price),
            "category": item.category.name if item.category else "",
            "stock_available": str(item.stock_qty) if item.track_stock else None,
        }
        for item in qs[:50]
    ]
    
    return JsonResponse({"results": data, "count": len(data)})


@login_required
@require_POST
def order_add_item_ajax(request: HttpRequest, pk: int) -> JsonResponse:
    """Add item to order via AJAX"""
    require_staff_role(request)
    order = get_order_or_404(request, pk)
    
    # Check if order can be modified
    if order.status in {RestaurantOrder.Status.PAID, RestaurantOrder.Status.CANCELLED}:
        return JsonResponse(
            {"ok": False, "errors": {"__all__": ["Order is closed and cannot be modified."]}},
            status=400
        )
    
    form = RestaurantOrderItemForm(request.POST, hotel=order.hotel)
    if not form.is_valid():
        return JsonResponse({"ok": False, "errors": form.errors}, status=400)
    
    try:
        with transaction.atomic():
            order_item = form.save(commit=False)
            order_item.order = order
            order_item.unit_price = order_item.item.price  # Lock in current price
            order_item.save()
            
            # Auto-advance from OPEN to KITCHEN when first item added
            if order.status == RestaurantOrder.Status.OPEN:
                order.status = RestaurantOrder.Status.KITCHEN
                order.save(update_fields=["status", "updated_at"])
        
        messages.success(request, f"Added {order_item.qty} x {order_item.item.name} to order.")
        return JsonResponse(render_order_items_response(order, request))
        
    except ValidationError as e:
        return JsonResponse({"ok": False, "errors": {"__all__": list(e.messages)}}, status=400)


@login_required
@require_POST
def order_remove_item_ajax(request: HttpRequest, pk: int, item_id: int) -> JsonResponse:
    """Remove item from order via AJAX"""
    require_staff_role(request)
    order = get_order_or_404(request, pk)
    
    if order.status in {RestaurantOrder.Status.PAID, RestaurantOrder.Status.CANCELLED}:
        return JsonResponse(
            {"ok": False, "errors": {"__all__": ["Order is closed and cannot be modified."]}},
            status=400
        )
    
    order_item = get_object_or_404(RestaurantOrderItem, pk=item_id, order=order)
    item_name = order_item.item.name
    
    with transaction.atomic():
        order_item.delete()
    
    messages.success(request, f"Removed {item_name} from order.")
    return JsonResponse(render_order_items_response(order, request))


@login_required
@require_POST
def order_update_item_qty_ajax(request: HttpRequest, pk: int, item_id: int) -> JsonResponse:
    """Update item quantity via AJAX"""
    require_staff_role(request)
    order = get_order_or_404(request, pk)
    
    if order.status in {RestaurantOrder.Status.PAID, RestaurantOrder.Status.CANCELLED}:
        return JsonResponse(
            {"ok": False, "errors": {"__all__": ["Order is closed and cannot be modified."]}},
            status=400
        )
    
    try:
        qty = int(request.POST.get("qty", "0"))
    except ValueError:
        return JsonResponse({"ok": False, "errors": {"qty": ["Invalid quantity value."]}}, status=400)
    
    if qty <= 0:
        return JsonResponse({"ok": False, "errors": {"qty": ["Quantity must be at least 1."]}}, status=400)
    
    order_item = get_object_or_404(RestaurantOrderItem, pk=item_id, order=order)
    order_item.qty = qty
    order_item.save(update_fields=["qty", "updated_at"])
    
    return JsonResponse(render_order_items_response(order, request))


# ============================================================================
# Order Workflow Views
# ============================================================================

@login_required
@require_POST
def order_set_status(request: HttpRequest, pk: int) -> HttpResponse:
    """Change order status"""
    require_staff_role(request)
    order = get_order_or_404(request, pk)
    
    form = OrderStatusForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Invalid status selected.")
        return redirect("restaurant:order_detail", pk=pk)
    
    new_status = form.cleaned_data["status"]
    status_display = dict(RestaurantOrder.Status.choices).get(new_status, new_status)
    
    try:
        with transaction.atomic():
            order.set_status(new_status, user=request.user)
        messages.success(request, f"Order {order.order_number} updated to {status_display}.")
    except ValidationError as e:
        for error in getattr(e, "messages", [str(e)]):
            messages.error(request, error)
    
    # Redirect to list if coming from there, otherwise back to detail
    next_url = request.POST.get("next") or reverse("restaurant:order_detail", kwargs={"pk": pk})
    return redirect(next_url)



@login_required
@require_POST
def order_bill(request: HttpRequest, pk: int) -> HttpResponse:
    """Generate invoice for order"""
    require_staff_role(request)
    order = get_order_or_404(request, pk)
    
    if not order.items.exists():
        messages.error(request, "Cannot bill an empty order.")
        return redirect("restaurant:order_detail", pk=pk)
    
    try:
        with transaction.atomic():
            from finance.models import Invoice, InvoiceLineItem
            
            # Check if invoice already exists
            invoice, created = Invoice.objects.get_or_create(
                order_number=order.order_number,
                defaults={
                    "hotel": order.hotel,
                    "booking": order.booking,
                    "customer_name": order.customer_name or "Restaurant Customer",
                    "customer_phone": order.customer_phone or "",
                    "customer_email": order.customer_email or "",
                    "subtotal": order.subtotal,
                    "discount": order.discount or 0,
                    "tax_amount": order.tax or 0,  # Use tax_amount
                    "total_amount": order.total,
                    "status": Invoice.Status.ISSUED,
                    "issued_at": timezone.now(),
                }
            )
            
            if created:
                # Create invoice line items
                for order_item in order.items.all():
                    InvoiceLineItem.objects.create(
                        invoice=invoice,
                        description=order_item.item.name,
                        quantity=order_item.qty,
                        unit_price=order_item.unit_price,
                        discount=0,
                        tax_rate=0,
                        total=order_item.line_total,
                        booking=order.booking,
                    )
                messages.success(request, f"Invoice #{invoice.invoice_number} generated successfully.")
            else:
                messages.info(request, f"Invoice #{invoice.invoice_number} already exists.")
            
            # Update order status
            if order.status not in [RestaurantOrder.Status.BILLED, RestaurantOrder.Status.PAID]:
                order.status = RestaurantOrder.Status.BILLED
                order.save(update_fields=["status", "updated_at"])
                
    except ImportError as e:
        messages.error(request, "Finance module not available. Cannot create invoice.")
    except Exception as e:
        messages.error(request, f"Error creating invoice: {str(e)}")
        return redirect("restaurant:order_detail", pk=pk)
    
    return redirect("restaurant:order_detail", pk=pk)


@login_required
def order_pay(request: HttpRequest, pk: int) -> HttpResponse:
    """Process payment for order"""
    require_staff_role(request)
    order = get_order_or_404(request, pk)
    
    # GET request - show payment form
    if request.method == "GET":
        if order.status in {RestaurantOrder.Status.PAID, RestaurantOrder.Status.CANCELLED}:
            messages.warning(request, "This order is already closed.")
            return redirect("restaurant:order_detail", pk=pk)
        
        if not order.items.exists():
            messages.error(request, "Cannot process payment for an empty order.")
            return redirect("restaurant:order_detail", pk=pk)
        
        # Auto-bill if not already billed
        if order.status not in {RestaurantOrder.Status.BILLED, RestaurantOrder.Status.PAID}:
            try:
                with transaction.atomic():
                    from finance.models import Invoice, InvoiceLineItem
                    
                    # Check if invoice already exists
                    invoice, created = Invoice.objects.get_or_create(
                        order_number=order.order_number,
                        defaults={
                            "hotel": order.hotel,
                            "booking": order.booking,
                            "customer_name": order.customer_name or "Restaurant Customer",
                            "customer_phone": order.customer_phone or "",
                            "customer_email": order.customer_email or "",
                            "subtotal": order.subtotal,
                            "discount": order.discount or 0,
                            "tax_amount": order.tax or 0,  # Changed from tax to tax_amount
                            "total_amount": order.total,
                            "status": Invoice.Status.ISSUED,
                            "issued_at": timezone.now(),
                        }
                    )
                    
                    if created:
                        # Create invoice line items
                        for order_item in order.items.all():
                            InvoiceLineItem.objects.create(
                                invoice=invoice,
                                description=order_item.item.name,
                                quantity=order_item.qty,
                                unit_price=order_item.unit_price,
                                discount=0,
                                tax_rate=0,
                                total=order_item.line_total,
                                booking=order.booking,
                            )
                        messages.info(request, "Invoice created.")
                    
                    order.status = RestaurantOrder.Status.BILLED
                    order.save(update_fields=["status"])
                    
            except Exception as e:
                print(f"Invoice creation error: {e}")
                # Continue without invoice if finance module fails
                order.status = RestaurantOrder.Status.BILLED
                order.save(update_fields=["status"])
        
        form = PaymentForm(order=order)
        return render(request, "restaurant/payment_form.html", {
            "order": order,
            "form": form,
            "invoice": None,
        })
    
    # POST request - process payment
    form = PaymentForm(request.POST, order=order)
    if not form.is_valid():
        return render(request, "restaurant/payment_form.html", {
            "order": order,
            "form": form,
        })
    
    try:
        with transaction.atomic():
            from finance.models import Invoice, InvoiceLineItem, Payment
            
            # Get or create invoice (without service_charge)
            invoice, created = Invoice.objects.get_or_create(
                order_number=order.order_number,
                defaults={
                    "hotel": order.hotel,
                    "booking": order.booking,
                    "customer_name": order.customer_name or "Restaurant Customer",
                    "customer_phone": order.customer_phone or "",
                    "customer_email": order.customer_email or "",
                    "subtotal": order.subtotal,
                    "discount": order.discount or 0,
                    "tax_amount": order.tax or 0,  # Use tax_amount, not tax
                    "total_amount": order.total,
                    "status": Invoice.Status.ISSUED,
                    "issued_at": timezone.now(),
                }
            )
            
            if created:
                # Create invoice line items
                for order_item in order.items.all():
                    InvoiceLineItem.objects.create(
                        invoice=invoice,
                        description=order_item.item.name,
                        quantity=order_item.qty,
                        unit_price=order_item.unit_price,
                        discount=0,
                        tax_rate=0,
                        total=order_item.line_total,
                        booking=order.booking,
                    )
            
            # Record payment
            payment = Payment.objects.create(
                hotel=order.hotel,
                invoice=invoice,
                method=form.cleaned_data["method"],
                amount=form.cleaned_data["amount"],
                reference=form.cleaned_data.get("reference") or None,
                received_by=request.user,
                status=Payment.PaymentStatus.COMPLETED,
                notes=form.cleaned_data.get("notes", ""),
            )
            
            # Update invoice status
            invoice.amount_paid = form.cleaned_data["amount"]
            if invoice.amount_paid >= invoice.total_amount:
                invoice.status = Invoice.Status.PAID
                invoice.paid_at = timezone.now()
            else:
                invoice.status = Invoice.Status.PARTIALLY_PAID
            invoice.save(update_fields=["amount_paid", "status", "paid_at"])
            
            # Update order status
            order.status = RestaurantOrder.Status.PAID
            order.closed_at = timezone.now()
            order.save(update_fields=["status", "closed_at", "updated_at"])
            
        messages.success(request, f"Payment of {payment.amount} received via {payment.get_method_display()}.")
        return redirect("restaurant:receipt_print", pk=pk)
        
    except ValidationError as e:
        for error in getattr(e, "messages", [str(e)]):
            messages.error(request, error)
        return render(request, "restaurant/payment_form.html", {
            "order": order,
            "form": form,
        })
    except Exception as e:
        messages.error(request, f"Error processing payment: {str(e)}")
        return redirect("restaurant:order_detail", pk=pk)


@login_required
def receipt_print(request: HttpRequest, pk: int) -> HttpResponse:
    """Print receipt view (optimized for printing)"""
    require_staff_role(request)
    order = get_order_or_404(request, pk)
    
    invoice = getattr(order, "invoice", None)
    payments = []
    if invoice:
        payments = list(invoice.payments.select_related("received_by").order_by("-received_at"))
    
    items = order.items.select_related("item").order_by("id")
    
    return render(request, "restaurant/receipt_print.html", {
        "hotel": get_hotel(request),
        "order": order,
        "invoice": invoice,
        "payments": payments,
        "items": items,
        "is_print_view": True,
    })


# ============================================================================
# Manager Dashboard
# ============================================================================

@method_decorator(login_required, name="dispatch")
class RestaurantManageDashboardView(TemplateView):
    """Restaurant management dashboard with quick actions"""
    template_name = "restaurant/manage/dashboard.html"

    def dispatch(self, request, *args, **kwargs):
        require_manager_role(request)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hotel = get_hotel(self.request)
        
        # Counts for overview cards
        ctx.update({
            "hotel": hotel,
            "areas_count": DiningArea.objects.filter(hotel=hotel).count(),
            "tables_count": Table.objects.filter(hotel=hotel).count(),
            "categories_count": MenuCategory.objects.filter(hotel=hotel).count(),
            "items_count": MenuItem.objects.filter(hotel=hotel).count(),
            "active_orders": RestaurantOrder.objects.filter(
                hotel=hotel, status__in=[RestaurantOrder.Status.OPEN, RestaurantOrder.Status.KITCHEN]
            ).count(),
            "low_stock_items": MenuItem.objects.filter(
                hotel=hotel, track_stock=True
            ).filter(
                Q(stock_qty__lte=F("reorder_level")) & Q(reorder_level__gt=0)
            ).count(),
        })
        
        # Recent orders
        ctx["recent_orders"] = RestaurantOrder.objects.filter(
            hotel=hotel
        ).select_related("table", "table__area").order_by("-created_at")[:10]
        
        # Forms for quick create
        ctx.update({
            "area_form": DiningAreaForm(),
            "table_form": TableForm(hotel=hotel),
            "category_form": MenuCategoryForm(),
            "item_form": MenuItemForm(hotel=hotel),
        })
        
        # Popular items (last 7 days)
        week_ago = timezone.now() - timezone.timedelta(days=7)
        popular_items = RestaurantOrderItem.objects.filter(
            order__hotel=hotel,
            order__created_at__gte=week_ago,
            order__status__in=[RestaurantOrder.Status.PAID, RestaurantOrder.Status.SERVED]
        ).values("item__id", "item__name").annotate(
            total_qty=Sum("qty")
        ).order_by("-total_qty")[:5]
        
        ctx["popular_items"] = popular_items
        
        return ctx

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        """Handle quick create forms from dashboard"""
        hotel = get_hotel(request)
        action = request.POST.get("action", "").strip()
        
        actions_map = {
            "add_area": (DiningAreaForm, DiningArea, "Dining area"),
            "add_category": (MenuCategoryForm, MenuCategory, "Menu category"),
        }
        
        # Handle area and category (no hotel needed in form)
        if action in actions_map:
            form_class, model_class, name = actions_map[action]
            form = form_class(request.POST)
            if form.is_valid():
                obj = form.save(commit=False)
                obj.hotel = hotel
                obj.save()
                messages.success(request, f"{name} '{obj.name}' added successfully.")
            else:
                messages.error(request, f"Failed to add {name.lower()}. Please check the form.")
        
        # Handle table (needs hotel for area filtering)
        elif action == "add_table":
            form = TableForm(request.POST, hotel=hotel)
            if form.is_valid():
                obj = form.save(commit=False)
                obj.hotel = hotel
                obj.save()
                messages.success(request, f"Table '{obj.number}' added successfully.")
            else:
                messages.error(request, "Failed to add table. Please check the form.")
        
        # Handle menu item (needs hotel for category filtering)
        elif action == "add_item":
            form = MenuItemForm(request.POST, hotel=hotel)
            if form.is_valid():
                obj = form.save(commit=False)
                obj.hotel = hotel
                obj.save()
                messages.success(request, f"Menu item '{obj.name}' added successfully.")
            else:
                messages.error(request, "Failed to add menu item. Please check the form.")
        
        else:
            messages.error(request, "Invalid action.")
        
        return redirect("restaurant:manage_dashboard")


# ============================================================================
# Dining Area CRUD
# ============================================================================

class DiningAreaBaseMixin:
    model = DiningArea
    form_class = DiningAreaForm
    success_message = None
    
    def get_queryset(self):
        return DiningArea.objects.filter(hotel=get_hotel(self.request))
    
    def form_valid(self, form):
        if not hasattr(form.instance, 'hotel') or not form.instance.hotel_id:
            form.instance.hotel = get_hotel(self.request)
        messages.success(self.request, self.success_message)
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
class DiningAreaListView(DiningAreaBaseMixin, ListView):
    template_name = "restaurant/manage/area_list.html"
    context_object_name = "areas"
    paginate_by = 50
    success_message = None

    def dispatch(self, request, *args, **kwargs):
        require_manager_role(request)
        return super().dispatch(request, *args, **kwargs)


@method_decorator(login_required, name="dispatch")
class DiningAreaCreateView(DiningAreaBaseMixin, CreateView):
    template_name = "restaurant/manage/area_form.html"
    success_message = "Dining area created successfully."

    def dispatch(self, request, *args, **kwargs):
        require_manager_role(request)
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse("restaurant:area_list")


@method_decorator(login_required, name="dispatch")
class DiningAreaUpdateView(DiningAreaBaseMixin, UpdateView):
    template_name = "restaurant/manage/area_form.html"
    context_object_name = "area"
    success_message = "Dining area updated successfully."

    def dispatch(self, request, *args, **kwargs):
        require_manager_role(request)
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse("restaurant:area_list")


# ============================================================================
# Table CRUD
# ============================================================================

class TableBaseMixin:
    model = Table
    form_class = TableForm
    success_message = None
    
    def get_queryset(self):
        return Table.objects.filter(hotel=get_hotel(self.request)).select_related("area")
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["hotel"] = get_hotel(self.request)
        return kwargs
    
    def form_valid(self, form):
        if not hasattr(form.instance, 'hotel') or not form.instance.hotel_id:
            form.instance.hotel = get_hotel(self.request)
        messages.success(self.request, self.success_message)
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
class TableListView(TableBaseMixin, ListView):
    template_name = "restaurant/manage/table_list.html"
    context_object_name = "tables"
    paginate_by = 50
    success_message = None

    def dispatch(self, request, *args, **kwargs):
        require_manager_role(request)
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        return super().get_queryset().order_by("area__name", "number")


@method_decorator(login_required, name="dispatch")
class TableCreateView(TableBaseMixin, CreateView):
    template_name = "restaurant/manage/table_form.html"
    success_message = "Table created successfully."

    def dispatch(self, request, *args, **kwargs):
        require_manager_role(request)
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse("restaurant:table_list")


@method_decorator(login_required, name="dispatch")
class TableUpdateView(TableBaseMixin, UpdateView):
    template_name = "restaurant/manage/table_form.html"
    context_object_name = "table"
    success_message = "Table updated successfully."

    def dispatch(self, request, *args, **kwargs):
        require_manager_role(request)
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse("restaurant:table_list")


# ============================================================================
# Menu Category CRUD
# ============================================================================

class MenuCategoryBaseMixin:
    model = MenuCategory
    form_class = MenuCategoryForm
    success_message = None
    
    def get_queryset(self):
        return MenuCategory.objects.filter(hotel=get_hotel(self.request))
    
    def form_valid(self, form):
        if not hasattr(form.instance, 'hotel') or not form.instance.hotel_id:
            form.instance.hotel = get_hotel(self.request)
        messages.success(self.request, self.success_message)
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
class MenuCategoryListView(MenuCategoryBaseMixin, ListView):
    template_name = "restaurant/manage/category_list.html"
    context_object_name = "categories"
    paginate_by = 50
    success_message = None

    def dispatch(self, request, *args, **kwargs):
        require_manager_role(request)
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        return super().get_queryset().order_by("sort_order", "name")


@method_decorator(login_required, name="dispatch")
class MenuCategoryCreateView(MenuCategoryBaseMixin, CreateView):
    template_name = "restaurant/manage/category_form.html"
    success_message = "Menu category created successfully."

    def dispatch(self, request, *args, **kwargs):
        require_manager_role(request)
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse("restaurant:category_list")


@method_decorator(login_required, name="dispatch")
class MenuCategoryUpdateView(MenuCategoryBaseMixin, UpdateView):
    template_name = "restaurant/manage/category_form.html"
    context_object_name = "category"
    success_message = "Menu category updated successfully."

    def dispatch(self, request, *args, **kwargs):
        require_manager_role(request)
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse("restaurant:category_list")


# ============================================================================
# Menu Item CRUD
# ============================================================================

class MenuItemBaseMixin:
    model = MenuItem
    form_class = MenuItemForm
    success_message = None
    
    def get_queryset(self):
        return MenuItem.objects.filter(hotel=get_hotel(self.request)).select_related("category")
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["hotel"] = get_hotel(self.request)
        return kwargs
    
    def form_valid(self, form):
        if not hasattr(form.instance, 'hotel') or not form.instance.hotel_id:
            form.instance.hotel = get_hotel(self.request)
        messages.success(self.request, self.success_message)
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
class MenuItemListView(MenuItemBaseMixin, ListView):
    template_name = "restaurant/manage/item_list.html"
    context_object_name = "items"
    paginate_by = 50
    success_message = None

    def dispatch(self, request, *args, **kwargs):
        require_manager_role(request)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        
        # Apply filters
        query = self.request.GET.get("q", "").strip()
        category_id = self.request.GET.get("category", "").strip()
        low_stock = self.request.GET.get("low_stock", "").strip()
        
        if query:
            qs = qs.filter(name__icontains=query)
        if category_id:
            qs = qs.filter(category_id=category_id)
        if low_stock == "true":
            qs = qs.filter(track_stock=True, stock_qty__lte=F("reorder_level"))
        
        return qs.order_by("category__sort_order", "name")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hotel = get_hotel(self.request)
        ctx["categories"] = MenuCategory.objects.filter(hotel=hotel, is_active=True).order_by("name")
        ctx["current_category"] = self.request.GET.get("category", "")
        ctx["search_query"] = self.request.GET.get("q", "")
        return ctx


@method_decorator(login_required, name="dispatch")
class MenuItemCreateView(MenuItemBaseMixin, CreateView):
    template_name = "restaurant/manage/item_form.html"
    success_message = "Menu item created successfully."

    def dispatch(self, request, *args, **kwargs):
        require_manager_role(request)
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse("restaurant:item_list")


@method_decorator(login_required, name="dispatch")
class MenuItemUpdateView(MenuItemBaseMixin, UpdateView):
    template_name = "restaurant/manage/item_form.html"
    context_object_name = "item"
    success_message = "Menu item updated successfully."

    def dispatch(self, request, *args, **kwargs):
        require_manager_role(request)
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse("restaurant:item_list")
    

# Add these to your views.py if you want the delete functionality

@method_decorator(login_required, name="dispatch")
class DiningAreaDeleteView(HotelScopedQuerysetMixin, DeleteView):
    """Delete dining area"""
    model = DiningArea
    template_name = "restaurant/manage/confirm_delete.html"
    success_url = reverse_lazy("restaurant:area_list")
    success_message = "Dining area deleted successfully."

    def dispatch(self, request, *args, **kwargs):
        require_manager_role(request)
        return super().dispatch(request, *args, **kwargs)
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, self.success_message)
        return super().delete(request, *args, **kwargs)


@method_decorator(login_required, name="dispatch")
class TableDeleteView(HotelScopedQuerysetMixin, DeleteView):
    """Delete table"""
    model = Table
    success_url = reverse_lazy("restaurant:table_list")
    success_message = "Table deleted successfully."

    def dispatch(self, request, *args, **kwargs):
        require_manager_role(request)
        return super().dispatch(request, *args, **kwargs)
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, self.success_message)
        return super().delete(request, *args, **kwargs)


@method_decorator(login_required, name="dispatch")
class MenuCategoryDeleteView(HotelScopedQuerysetMixin, DeleteView):
    """Delete menu category"""
    model = MenuCategory
    success_url = reverse_lazy("restaurant:category_list")
    success_message = "Menu category deleted successfully."

    def dispatch(self, request, *args, **kwargs):
        require_manager_role(request)
        return super().dispatch(request, *args, **kwargs)
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, self.success_message)
        return super().delete(request, *args, **kwargs)


@method_decorator(login_required, name="dispatch")
class MenuItemDeleteView(HotelScopedQuerysetMixin, DeleteView):
    """Delete menu item"""
    model = MenuItem
    success_url = reverse_lazy("restaurant:item_list")
    success_message = "Menu item deleted successfully."

    def dispatch(self, request, *args, **kwargs):
        require_manager_role(request)
        return super().dispatch(request, *args, **kwargs)
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, self.success_message)
        return super().delete(request, *args, **kwargs)


@login_required
@require_POST
def menu_item_toggle_status(request: HttpRequest, pk: int) -> JsonResponse:
    """Quick toggle menu item active status"""
    require_manager_role(request)
    hotel = get_hotel(request)
    item = get_object_or_404(MenuItem, pk=pk, hotel=hotel)
    
    item.is_active = not item.is_active
    item.save(update_fields=["is_active", "updated_at"])
    
    return JsonResponse({
        "ok": True,
        "is_active": item.is_active,
        "message": f"{item.name} is now {'active' if item.is_active else 'inactive'}"
    })


@login_required
@require_GET
def order_stats_api(request: HttpRequest) -> JsonResponse:
    """API endpoint for order statistics"""
    require_staff_role(request)
    hotel = get_hotel(request)
    
    stats = {
        "active_orders": RestaurantOrder.objects.filter(
            hotel=hotel,
            status__in=[RestaurantOrder.Status.OPEN, RestaurantOrder.Status.KITCHEN]
        ).count(),
        "today_orders": RestaurantOrder.objects.filter(
            hotel=hotel,
            created_at__date=timezone.localdate()
        ).count(),
        "today_revenue": RestaurantOrder.objects.filter(
            hotel=hotel,
            status=RestaurantOrder.Status.PAID,
            closed_at__date=timezone.localdate()
        ).aggregate(total=Sum("invoice__total"))["total"] or 0,
    }
    
    return JsonResponse(stats)