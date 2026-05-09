from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional, Tuple, Type, Union
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.db.models import Q, Prefetch, Sum, F, Count, Avg, DecimalField
from django.db.models.functions import Coalesce
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.views.generic import ListView, CreateView, DetailView, TemplateView, UpdateView, DeleteView
from django.views.generic.edit import FormView

from hotel_thinker.utils import get_active_hotel_for_user, require_hotel_role

from .models import (
    DiningArea, Table, MenuCategory, MenuItem,
    RestaurantOrder, RestaurantOrderItem, RestaurantPayment,
    RestaurantInvoice,
)
from .forms import (
    DiningAreaForm, TableForm, MenuCategoryForm, MenuItemForm,
    RestaurantOrderForm, RestaurantOrderItemForm,
    OrderStatusForm, PaymentForm, QuickOrderForm,
)


# ============================================================================
# Decorators & Helpers
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
        "items_count": items.count(),
    }


def ajax_login_required(view_func):
    """Decorator that returns JSON response for AJAX login required"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"ok": False, "errors": {"__all__": ["Authentication required."]}}, status=401)
        return view_func(request, *args, **kwargs)
    return wrapper


class HotelScopedQuerysetMixin:
    """Mixin to filter querysets by current hotel"""
    
    def get_hotel(self):
        return get_hotel(self.request)
    
    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(hotel=self.get_hotel())


class StaffRequiredMixin:
    """Mixin to require staff role"""
    
    def dispatch(self, request, *args, **kwargs):
        require_staff_role(request)
        return super().dispatch(request, *args, **kwargs)


class ManagerRequiredMixin:
    """Mixin to require manager role"""
    
    def dispatch(self, request, *args, **kwargs):
        require_manager_role(request)
        return super().dispatch(request, *args, **kwargs)


class BaseCRUDMixin:
    """Base mixin for CRUD operations"""
    success_message = None
    
    def form_valid(self, form):
        response = super().form_valid(form)
        if self.success_message:
            messages.success(self.request, self.success_message)
        return response
    
    def form_invalid(self, form):
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(self.request, f"{field}: {error}" if field != '__all__' else error)
        return super().form_invalid(form)


# ============================================================================
# Order Views
# ============================================================================

@method_decorator([login_required, never_cache], name="dispatch")
class OrderListView(StaffRequiredMixin, HotelScopedQuerysetMixin, ListView):
    """List and filter restaurant orders"""
    model = RestaurantOrder
    template_name = "restaurant/order_list.html"
    context_object_name = "orders"
    paginate_by = 50

    def get_queryset(self):
        qs = super().get_queryset().select_related(
            "table", "table__area"
        ).prefetch_related(
            Prefetch("items", queryset=RestaurantOrderItem.objects.select_related("item")[:5])
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
        today = timezone.localdate()
        
        # Use aggregation for better performance
        today_paid_total = RestaurantOrder.objects.filter(
            hotel=hotel,
            status=RestaurantOrder.Status.PAID,
            closed_at__date=today
        ).aggregate(
            total=Coalesce(Sum("invoice__total"), Decimal("0.00"))
        )["total"]
        
        ctx.update({
            "status_choices": RestaurantOrder.Status.choices,
            "current_status": self.request.GET.get("status", ""),
            "search_query": self.request.GET.get("q", ""),
            "stats": {
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
                "today_revenue": float(today_paid_total),
            },
        })
        
        return ctx


@method_decorator([login_required, never_cache], name="dispatch")
class OrderDetailView(StaffRequiredMixin, HotelScopedQuerysetMixin, DetailView):
    """View order details with items and actions"""
    model = RestaurantOrder
    template_name = "restaurant/order_detail.html"
    context_object_name = "order"

    def get_queryset(self):
        return super().get_queryset().select_related(
            "table", "table__area", "booking", "created_by", "updated_by"
        ).prefetch_related("items__item")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        order = self.object
        hotel = self.get_hotel()
        
        # Safely get invoice
        invoice = getattr(order, "invoice", None)
        
        ctx.update({
            "hotel": hotel,
            "items": order.items.select_related("item").order_by("-id"),
            "invoice": invoice,
            "item_form": RestaurantOrderItemForm(hotel=hotel, order=order),
            "status_form": OrderStatusForm(initial={"status": order.status}, current_status=order.status),
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
class OrderCreateView(StaffRequiredMixin, CreateView):
    """Create a new restaurant order"""
    model = RestaurantOrder
    form_class = RestaurantOrderForm
    template_name = "restaurant/order_form.html"

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
        
        # Redirect to order detail or add items page
        if "_add_items" in self.request.POST:
            return redirect("restaurant:order_detail", pk=self.object.pk)
        return response

    def get_success_url(self):
        return reverse("restaurant:order_detail", kwargs={"pk": self.object.pk})


# ============================================================================
# POS / Quick Order View
# ============================================================================

@method_decorator(login_required, name="dispatch")
class POSView(StaffRequiredMixin, FormView):
    """Point of Sale interface with quick order form"""
    template_name = "restaurant/pos.html"
    form_class = QuickOrderForm
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["hotel"] = get_hotel(self.request)
        return kwargs
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hotel = get_hotel(self.request)
        
        ctx.update({
            "hotel": hotel,
            "menu_categories": MenuCategory.objects.filter(hotel=hotel, is_active=True).prefetch_related(
                Prefetch("items", queryset=MenuItem.objects.filter(hotel=hotel, is_active=True))
            ),
            "active_tables": Table.objects.filter(hotel=hotel, is_active=True).select_related("area"),
            "open_orders": RestaurantOrder.objects.filter(
                hotel=hotel,
                status__in=[RestaurantOrder.Status.OPEN, RestaurantOrder.Status.KITCHEN]
            ).select_related("table", "table__area")[:20],
        })
        return ctx
    
    def form_valid(self, form):
        """Process quick order form"""
        hotel = get_hotel(self.request)
        cleaned_data = form.cleaned_data
        
        try:
            with transaction.atomic():
                # Create order
                order = RestaurantOrder.objects.create(
                    hotel=hotel,
                    table=cleaned_data.get("table"),
                    customer_name=cleaned_data.get("customer_name") or "Walk-in Customer",
                    status=RestaurantOrder.Status.OPEN,
                    created_by=self.request.user,
                )
                
                # Add items
                items_added = 0
                for item_data in cleaned_data["items"]:
                    # Try to find menu item by name
                    menu_item = MenuItem.objects.filter(
                        hotel=hotel,
                        name__iexact=item_data["name"],
                        is_active=True
                    ).first()
                    
                    if not menu_item:
                        # Try partial match
                        menu_item = MenuItem.objects.filter(
                            hotel=hotel,
                            name__icontains=item_data["name"],
                            is_active=True
                        ).first()
                    
                    if menu_item:
                        RestaurantOrderItem.objects.create(
                            order=order,
                            item=menu_item,
                            qty=item_data["quantity"],
                            unit_price=menu_item.price,
                        )
                        items_added += 1
                    else:
                        messages.warning(
                            self.request, 
                            f"Item '{item_data['name']}' not found in menu. Skipped."
                        )
                
                if items_added == 0:
                    raise ValidationError("No valid items found in the order.")
                
                # Update order status if items added
                if items_added > 0:
                    order.status = RestaurantOrder.Status.KITCHEN
                    order.save(update_fields=["status"])
                
                messages.success(
                    self.request, 
                    f"Order #{order.order_number} created with {items_added} item(s)."
                )
                
                return redirect("restaurant:order_detail", pk=order.pk)
                
        except ValidationError as e:
            messages.error(self.request, str(e))
            return self.form_invalid(form)
        except Exception as e:
            messages.error(self.request, f"Error creating order: {str(e)}")
            return self.form_invalid(form)
    
    def form_invalid(self, form):
        for error in form.non_field_errors():
            messages.error(self.request, error)
        return super().form_invalid(form)


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
    if category_id and category_id.isdigit():
        qs = qs.filter(category_id=int(category_id))
    
    # Limit results for performance
    qs = qs[:50]
    
    data = [
        {
            "id": item.id,
            "name": item.name,
            "price": str(item.price),
            "category": item.category.name if item.category else "",
            "stock_available": str(item.stock_qty) if item.track_stock else None,
            "is_low_stock": item.is_low_stock if item.track_stock else False,
        }
        for item in qs
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
    
    form = RestaurantOrderItemForm(request.POST, hotel=order.hotel, order=order)
    if not form.is_valid():
        return JsonResponse({"ok": False, "errors": form.errors}, status=400)
    
    try:
        with transaction.atomic():
            order_item = form.save(commit=False)
            order_item.order = order
            order_item.unit_price = order_item.item.price
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
    
    if qty > 999:
        return JsonResponse({"ok": False, "errors": {"qty": ["Quantity cannot exceed 999."]}}, status=400)
    
    order_item = get_object_or_404(RestaurantOrderItem, pk=item_id, order=order)
    
    # Check stock if tracking is enabled
    if order_item.item.track_stock and order_item.item.stock_qty < qty:
        return JsonResponse({
            "ok": False, 
            "errors": {"qty": [f"Insufficient stock. Available: {order_item.item.stock_qty}"]}
        }, status=400)
    
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
    
    form = OrderStatusForm(request.POST, current_status=order.status)
    if not form.is_valid():
        for error in form.errors.get("status", []):
            messages.error(request, error)
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
            # Use restaurant's own invoice model
            invoice = RestaurantInvoice.objects.filter(order=order).first()
            
            if not invoice:
                invoice = RestaurantInvoice.objects.create(
                    hotel=order.hotel,
                    order=order,
                    subtotal=order.subtotal,
                    discount=order.discount,
                    discount_percent=order.discount_percent,
                    tax=order.tax,
                    tax_percent=order.tax_percent,
                    service_charge=order.service_charge,
                    total=order.total,
                    issued_at=timezone.now(),
                )
                messages.success(request, f"Invoice #{invoice.invoice_number} generated successfully.")
            else:
                messages.info(request, f"Invoice #{invoice.invoice_number} already exists.")
            
            # Update order status
            if order.status not in [RestaurantOrder.Status.BILLED, RestaurantOrder.Status.PAID]:
                order.status = RestaurantOrder.Status.BILLED
                order.save(update_fields=["status", "updated_at"])
                
    except Exception as e:
        messages.error(request, f"Error creating invoice: {str(e)}")
        return redirect("restaurant:order_detail", pk=pk)
    
    return redirect("restaurant:order_detail", pk=pk)


@login_required
@require_http_methods(["GET", "POST"])
def order_pay(request: HttpRequest, pk: int) -> HttpResponse:
    """Process payment for order"""
    require_staff_role(request)
    order = get_order_or_404(request, pk)
    
    # Check if order can be paid
    if order.status == RestaurantOrder.Status.PAID:
        messages.warning(request, "This order is already paid.")
        return redirect("restaurant:order_detail", pk=pk)
    
    if order.status == RestaurantOrder.Status.CANCELLED:
        messages.warning(request, "Cancelled orders cannot be paid.")
        return redirect("restaurant:order_detail", pk=pk)
    
    if not order.items.exists():
        messages.error(request, "Cannot process payment for an empty order.")
        return redirect("restaurant:order_detail", pk=pk)
    
    # Auto-bill if not already billed
    if order.status not in {RestaurantOrder.Status.BILLED, RestaurantOrder.Status.PAID}:
        try:
            with transaction.atomic():
                invoice, created = RestaurantInvoice.objects.get_or_create(
                    order=order,
                    defaults={
                        "hotel": order.hotel,
                        "subtotal": order.subtotal,
                        "discount": order.discount,
                        "discount_percent": order.discount_percent,
                        "tax": order.tax,
                        "tax_percent": order.tax_percent,
                        "service_charge": order.service_charge,
                        "total": order.total,
                        "issued_at": timezone.now(),
                    }
                )
                order.status = RestaurantOrder.Status.BILLED
                order.save(update_fields=["status"])
        except Exception as e:
            messages.error(request, f"Error creating invoice: {str(e)}")
            return redirect("restaurant:order_detail", pk=pk)
    
    # GET request - show payment form
    if request.method == "GET":
        form = PaymentForm(order=order)
        return render(request, "restaurant/payment_form.html", {
            "order": order,
            "form": form,
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
            invoice = order.invoice
            
            # Create payment
            payment = RestaurantPayment.objects.create(
                hotel=order.hotel,
                invoice=invoice,
                method=form.cleaned_data["method"],
                amount=form.cleaned_data["amount"],
                reference=form.cleaned_data.get("reference") or None,
                received_by=request.user,
                notes=form.cleaned_data.get("notes", ""),
            )
            
            # Update invoice status
            invoice.status = RestaurantInvoice.Status.PAID
            invoice.paid_at = timezone.now()
            invoice.save(update_fields=["status", "paid_at"])
            
            # Update order status
            order.status = RestaurantOrder.Status.PAID
            order.closed_at = timezone.now()
            order.save(update_fields=["status", "closed_at", "updated_at"])
            
        messages.success(
            request, 
            f"Payment of {payment.amount} received via {payment.get_method_display()}."
        )
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
# Kitchen Display Views
# ============================================================================

@method_decorator(login_required, name="dispatch")
class KitchenDisplayView(StaffRequiredMixin, HotelScopedQuerysetMixin, ListView):
    """Kitchen display view for food preparation"""
    model = RestaurantOrder
    template_name = "restaurant/kitchen_display.html"
    context_object_name = "orders"
    
    def get_queryset(self):
        return super().get_queryset().filter(
            status=RestaurantOrder.Status.KITCHEN
        ).select_related("table", "table__area").prefetch_related(
            Prefetch("items", queryset=RestaurantOrderItem.objects.select_related("item"))
        ).order_by("created_at")
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # Group orders by priority (preparation time)
        high_priority = []
        normal_priority = []
        
        for order in ctx["orders"]:
            # Orders with items that have preparation time > 20 min are high priority
            has_long_prep = any(
                item.item.preparation_time > 20 for item in order.items.all()
            )
            if has_long_prep:
                high_priority.append(order)
            else:
                normal_priority.append(order)
        
        ctx["high_priority_orders"] = high_priority
        ctx["normal_priority_orders"] = normal_priority
        
        return ctx


@login_required
@require_POST
def kitchen_order_ready(request: HttpRequest, pk: int) -> JsonResponse:
    """Mark order as ready/ served from kitchen display"""
    require_staff_role(request)
    order = get_order_or_404(request, pk)
    
    if order.status != RestaurantOrder.Status.KITCHEN:
        return JsonResponse({
            "ok": False,
            "error": f"Order is not in kitchen. Current status: {order.get_status_display()}"
        }, status=400)
    
    try:
        order.set_status(RestaurantOrder.Status.SERVED, user=request.user)
        return JsonResponse({
            "ok": True,
            "message": f"Order #{order.order_number} marked as served.",
            "order_id": order.pk,
        })
    except ValidationError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)


# ============================================================================
# Manager Dashboard
# ============================================================================

@method_decorator(login_required, name="dispatch")
class RestaurantManageDashboardView(ManagerRequiredMixin, TemplateView):
    """Restaurant management dashboard with quick actions"""
    template_name = "restaurant/manage/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hotel = get_hotel(self.request)
        today = timezone.localdate()
        week_ago = timezone.now() - timezone.timedelta(days=7)
        
        # Dashboard statistics
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
            ).filter(stock_qty__lte=F("reorder_level")).count(),
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
        popular_items = RestaurantOrderItem.objects.filter(
            order__hotel=hotel,
            order__created_at__gte=week_ago,
            order__status__in=[RestaurantOrder.Status.PAID, RestaurantOrder.Status.SERVED]
        ).values("item__id", "item__name", "item__price").annotate(
            total_qty=Sum("qty"),
            total_revenue=Sum(F("qty") * F("unit_price"))
        ).order_by("-total_qty")[:10]
        
        ctx["popular_items"] = popular_items
        
        # Sales summary
        sales_summary = RestaurantOrder.objects.filter(
            hotel=hotel,
            created_at__date=today
        ).aggregate(
            total_orders=Count("id"),
            completed_orders=Count("id", filter=Q(status=RestaurantOrder.Status.PAID)),
            total_revenue=Coalesce(Sum("invoice__total"), Decimal("0.00")),
            avg_order_value=Coalesce(Avg("invoice__total"), Decimal("0.00")),
        )
        
        ctx["sales_summary"] = {
            "total_orders": sales_summary["total_orders"],
            "completed_orders": sales_summary["completed_orders"],
            "total_revenue": float(sales_summary["total_revenue"]),
            "avg_order_value": float(sales_summary["avg_order_value"]),
        }
        
        return ctx

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        """Handle quick create forms from dashboard"""
        hotel = get_hotel(request)
        action = request.POST.get("action", "").strip()
        
        actions_map = {
            "add_area": (DiningAreaForm, DiningArea, "Dining area", "name"),
            "add_category": (MenuCategoryForm, MenuCategory, "Menu category", "name"),
            "add_table": (TableForm, Table, "Table", "number"),
            "add_item": (MenuItemForm, MenuItem, "Menu item", "name"),
        }
        
        if action not in actions_map:
            messages.error(request, "Invalid action.")
            return redirect("restaurant:manage_dashboard")
        
        form_class, model_class, name, name_field = actions_map[action]
        
        # Special handling for forms that need hotel parameter
        if action == "add_table":
            form = form_class(request.POST, hotel=hotel)
        elif action == "add_item":
            form = form_class(request.POST, hotel=hotel)
        else:
            form = form_class(request.POST)
        
        if form.is_valid():
            obj = form.save(commit=False)
            obj.hotel = hotel
            obj.save()
            messages.success(request, f"{name} '{getattr(obj, name_field)}' added successfully.")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}" if field != '__all__' else error)
        
        return redirect("restaurant:manage_dashboard")


# ============================================================================
# Dining Area CRUD
# ============================================================================

class DiningAreaBaseMixin(ManagerRequiredMixin, BaseCRUDMixin):
    model = DiningArea
    form_class = DiningAreaForm
    
    def get_queryset(self):
        return DiningArea.objects.filter(hotel=get_hotel(self.request))
    
    def form_valid(self, form):
        if not form.instance.hotel_id:
            form.instance.hotel = get_hotel(self.request)
        return super().form_valid(form)


class DiningAreaListView(DiningAreaBaseMixin, ListView):
    template_name = "restaurant/manage/area_list.html"
    context_object_name = "areas"
    paginate_by = 50


class DiningAreaCreateView(DiningAreaBaseMixin, CreateView):
    template_name = "restaurant/manage/area_form.html"
    success_message = "Dining area created successfully."
    
    def get_success_url(self):
        return reverse("restaurant:area_list")


class DiningAreaUpdateView(DiningAreaBaseMixin, UpdateView):
    template_name = "restaurant/manage/area_form.html"
    context_object_name = "area"
    success_message = "Dining area updated successfully."
    
    def get_success_url(self):
        return reverse("restaurant:area_list")


class DiningAreaDeleteView(ManagerRequiredMixin, HotelScopedQuerysetMixin, DeleteView):
    model = DiningArea
    success_url = reverse_lazy("restaurant:area_list")
    success_message = "Dining area deleted successfully."
    template_name = "restaurant/manage/confirm_delete.html"
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, self.success_message)
        return super().delete(request, *args, **kwargs)


# ============================================================================
# Table CRUD
# ============================================================================

class TableBaseMixin(ManagerRequiredMixin, BaseCRUDMixin):
    model = Table
    form_class = TableForm
    
    def get_queryset(self):
        return Table.objects.filter(hotel=get_hotel(self.request)).select_related("area")
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["hotel"] = get_hotel(self.request)
        return kwargs
    
    def form_valid(self, form):
        if not form.instance.hotel_id:
            form.instance.hotel = get_hotel(self.request)
        return super().form_valid(form)


class TableListView(TableBaseMixin, ListView):
    template_name = "restaurant/manage/table_list.html"
    context_object_name = "tables"
    paginate_by = 50
    
    def get_queryset(self):
        return super().get_queryset().order_by("area__name", "number")


class TableCreateView(TableBaseMixin, CreateView):
    template_name = "restaurant/manage/table_form.html"
    success_message = "Table created successfully."
    
    def get_success_url(self):
        return reverse("restaurant:table_list")


class TableUpdateView(TableBaseMixin, UpdateView):
    template_name = "restaurant/manage/table_form.html"
    context_object_name = "table"
    success_message = "Table updated successfully."
    
    def get_success_url(self):
        return reverse("restaurant:table_list")


class TableDeleteView(ManagerRequiredMixin, HotelScopedQuerysetMixin, DeleteView):
    model = Table
    success_url = reverse_lazy("restaurant:table_list")
    success_message = "Table deleted successfully."
    template_name = "restaurant/manage/confirm_delete.html"
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, self.success_message)
        return super().delete(request, *args, **kwargs)


# ============================================================================
# Menu Category CRUD
# ============================================================================

class MenuCategoryBaseMixin(ManagerRequiredMixin, BaseCRUDMixin):
    model = MenuCategory
    form_class = MenuCategoryForm
    
    def get_queryset(self):
        return MenuCategory.objects.filter(hotel=get_hotel(self.request))
    
    def form_valid(self, form):
        if not form.instance.hotel_id:
            form.instance.hotel = get_hotel(self.request)
        return super().form_valid(form)


class MenuCategoryListView(MenuCategoryBaseMixin, ListView):
    template_name = "restaurant/manage/category_list.html"
    context_object_name = "categories"
    paginate_by = 50
    
    def get_queryset(self):
        return super().get_queryset().order_by("sort_order", "name")


class MenuCategoryCreateView(MenuCategoryBaseMixin, CreateView):
    template_name = "restaurant/manage/category_form.html"
    success_message = "Menu category created successfully."
    
    def get_success_url(self):
        return reverse("restaurant:category_list")


class MenuCategoryUpdateView(MenuCategoryBaseMixin, UpdateView):
    template_name = "restaurant/manage/category_form.html"
    context_object_name = "category"
    success_message = "Menu category updated successfully."
    
    def get_success_url(self):
        return reverse("restaurant:category_list")


class MenuCategoryDeleteView(ManagerRequiredMixin, HotelScopedQuerysetMixin, DeleteView):
    model = MenuCategory
    success_url = reverse_lazy("restaurant:category_list")
    success_message = "Menu category deleted successfully."
    template_name = "restaurant/manage/confirm_delete.html"
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, self.success_message)
        return super().delete(request, *args, **kwargs)


# ============================================================================
# Menu Item CRUD
# ============================================================================

class MenuItemBaseMixin(ManagerRequiredMixin, BaseCRUDMixin):
    model = MenuItem
    form_class = MenuItemForm
    
    def get_queryset(self):
        return MenuItem.objects.filter(hotel=get_hotel(self.request)).select_related("category")
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["hotel"] = get_hotel(self.request)
        return kwargs
    
    def form_valid(self, form):
        if not form.instance.hotel_id:
            form.instance.hotel = get_hotel(self.request)
        return super().form_valid(form)


class MenuItemListView(MenuItemBaseMixin, ListView):
    template_name = "restaurant/manage/item_list.html"
    context_object_name = "items"
    paginate_by = 50

    def get_queryset(self):
        qs = super().get_queryset()
        
        # Apply filters
        query = self.request.GET.get("q", "").strip()
        category_id = self.request.GET.get("category", "").strip()
        low_stock = self.request.GET.get("low_stock", "").strip()
        is_active = self.request.GET.get("is_active", "").strip()
        
        if query:
            qs = qs.filter(name__icontains=query)
        if category_id and category_id.isdigit():
            qs = qs.filter(category_id=int(category_id))
        if low_stock == "true":
            qs = qs.filter(track_stock=True, stock_qty__lte=F("reorder_level"))
        if low_stock == "out":
            qs = qs.filter(track_stock=True, stock_qty=0)
        if is_active == "true":
            qs = qs.filter(is_active=True)
        elif is_active == "false":
            qs = qs.filter(is_active=False)
        
        return qs.order_by("category__sort_order", "name")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hotel = get_hotel(self.request)
        ctx.update({
            "categories": MenuCategory.objects.filter(hotel=hotel, is_active=True).order_by("name"),
            "current_category": self.request.GET.get("category", ""),
            "search_query": self.request.GET.get("q", ""),
            "low_stock_filter": self.request.GET.get("low_stock", ""),
            "active_filter": self.request.GET.get("is_active", ""),
        })
        return ctx


class MenuItemCreateView(MenuItemBaseMixin, CreateView):
    template_name = "restaurant/manage/item_form.html"
    success_message = "Menu item created successfully."
    
    def get_success_url(self):
        return reverse("restaurant:item_list")


class MenuItemUpdateView(MenuItemBaseMixin, UpdateView):
    template_name = "restaurant/manage/item_form.html"
    context_object_name = "item"
    success_message = "Menu item updated successfully."
    
    def get_success_url(self):
        return reverse("restaurant:item_list")


class MenuItemDeleteView(ManagerRequiredMixin, HotelScopedQuerysetMixin, DeleteView):
    model = MenuItem
    success_url = reverse_lazy("restaurant:item_list")
    success_message = "Menu item deleted successfully."
    template_name = "restaurant/manage/confirm_delete.html"
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, self.success_message)
        return super().delete(request, *args, **kwargs)


# ============================================================================
# AJAX Utilities
# ============================================================================

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
    today = timezone.localdate()
    
    # Use aggregation for better performance
    today_revenue = RestaurantOrder.objects.filter(
        hotel=hotel,
        status=RestaurantOrder.Status.PAID,
        closed_at__date=today
    ).aggregate(
        total=Coalesce(Sum("invoice__total"), Decimal("0.00"))
    )["total"]
    
    stats = {
        "active_orders": RestaurantOrder.objects.filter(
            hotel=hotel,
            status__in=[RestaurantOrder.Status.OPEN, RestaurantOrder.Status.KITCHEN]
        ).count(),
        "today_orders": RestaurantOrder.objects.filter(
            hotel=hotel,
            created_at__date=today
        ).count(),
        "today_revenue": float(today_revenue),
        "kitchen_orders": RestaurantOrder.objects.filter(
            hotel=hotel,
            status=RestaurantOrder.Status.KITCHEN
        ).count(),
        "served_orders": RestaurantOrder.objects.filter(
            hotel=hotel,
            status=RestaurantOrder.Status.SERVED
        ).count(),
    }
    
    return JsonResponse(stats)


@login_required
@require_GET
def table_status_api(request: HttpRequest) -> JsonResponse:
    """API endpoint for table availability status"""
    require_staff_role(request)
    hotel = get_hotel(request)
    
    tables = Table.objects.filter(hotel=hotel, is_active=True).select_related("area")
    
    # Get occupied table IDs
    occupied_table_ids = set(
        RestaurantOrder.objects.filter(
            hotel=hotel,
            table__isnull=False,
            status__in=[RestaurantOrder.Status.OPEN, RestaurantOrder.Status.KITCHEN, RestaurantOrder.Status.SERVED]
        ).values_list("table_id", flat=True)
    )
    
    data = []
    for table in tables:
        data.append({
            "id": table.id,
            "number": table.number,
            "area": table.area.name if table.area else None,
            "seats": table.seats,
            "is_occupied": table.id in occupied_table_ids,
            "status": "occupied" if table.id in occupied_table_ids else "available",
        })
    
    return JsonResponse({"tables": data})

# ============================================================================
# Additional View Functions for URL Patterns
# ============================================================================

@login_required
@require_POST
def dining_area_toggle_status(request: HttpRequest, pk: int) -> JsonResponse:
    """Quick toggle dining area active status"""
    require_manager_role(request)
    hotel = get_hotel(request)
    area = get_object_or_404(DiningArea, pk=pk, hotel=hotel)
    
    area.is_active = not area.is_active
    area.save(update_fields=["is_active", "updated_at"])
    
    return JsonResponse({
        "ok": True,
        "is_active": area.is_active,
        "message": f"{area.name} is now {'active' if area.is_active else 'inactive'}"
    })


@login_required
@require_POST
def table_toggle_status(request: HttpRequest, pk: int) -> JsonResponse:
    """Quick toggle table active status"""
    require_manager_role(request)
    hotel = get_hotel(request)
    table = get_object_or_404(Table, pk=pk, hotel=hotel)
    
    table.is_active = not table.is_active
    table.save(update_fields=["is_active", "updated_at"])
    
    return JsonResponse({
        "ok": True,
        "is_active": table.is_active,
        "message": f"Table {table.number} is now {'active' if table.is_active else 'inactive'}"
    })


@login_required
@require_POST
def category_toggle_status(request: HttpRequest, pk: int) -> JsonResponse:
    """Quick toggle menu category active status"""
    require_manager_role(request)
    hotel = get_hotel(request)
    category = get_object_or_404(MenuCategory, pk=pk, hotel=hotel)
    
    category.is_active = not category.is_active
    category.save(update_fields=["is_active", "updated_at"])
    
    return JsonResponse({
        "ok": True,
        "is_active": category.is_active,
        "message": f"{category.name} is now {'active' if category.is_active else 'inactive'}"
    })


@login_required
@require_POST
def menu_item_bulk_action(request: HttpRequest) -> JsonResponse:
    """Bulk actions for menu items (activate/deactivate/delete)"""
    require_manager_role(request)
    hotel = get_hotel(request)
    
    action = request.POST.get("action", "").strip()
    item_ids = request.POST.getlist("item_ids", [])
    
    if not item_ids:
        return JsonResponse({"ok": False, "error": "No items selected."}, status=400)
    
    # Verify all items belong to the hotel
    items = MenuItem.objects.filter(pk__in=item_ids, hotel=hotel)
    
    if action == "activate":
        count = items.update(is_active=True)
        message = f"{count} item(s) activated."
    elif action == "deactivate":
        count = items.update(is_active=False)
        message = f"{count} item(s) deactivated."
    elif action == "delete":
        count = items.count()
        items.delete()
        message = f"{count} item(s) deleted."
    else:
        return JsonResponse({"ok": False, "error": "Invalid action."}, status=400)
    
    return JsonResponse({"ok": True, "message": message})


@login_required
def table_occupancy_view(request: HttpRequest) -> HttpResponse:
    """Visual table occupancy grid view"""
    require_staff_role(request)
    hotel = get_hotel(request)
    
    areas = DiningArea.objects.filter(hotel=hotel, is_active=True).prefetch_related(
        Prefetch("tables", queryset=Table.objects.filter(hotel=hotel, is_active=True))
    )
    
    # Get current orders for occupancy status
    active_orders = RestaurantOrder.objects.filter(
        hotel=hotel,
        status__in=[RestaurantOrder.Status.OPEN, RestaurantOrder.Status.KITCHEN, RestaurantOrder.Status.SERVED],
        table__isnull=False
    ).select_related("table")
    
    occupied_table_ids = set(order.table_id for order in active_orders)
    
    for area in areas:
        for table in area.tables.all():
            table.is_occupied = table.id in occupied_table_ids
            table.current_order = next(
                (order for order in active_orders if order.table_id == table.id), 
                None
            )
    
    return render(request, "restaurant/table_occupancy.html", {
        "hotel": hotel,
        "areas": areas,
        "active_orders_count": len(active_orders),
    })


@login_required
def print_order(request: HttpRequest, pk: int) -> HttpResponse:
    """Print friendly order view"""
    require_staff_role(request)
    order = get_order_or_404(request, pk)
    
    items = order.items.select_related("item").order_by("id")
    
    return render(request, "restaurant/print_order.html", {
        "hotel": get_hotel(request),
        "order": order,
        "items": items,
        "is_print_view": True,
    })


@login_required
def print_kitchen_ticket(request: HttpRequest, pk: int) -> HttpResponse:
    """Print kitchen ticket for an order"""
    require_staff_role(request)
    order = get_order_or_404(request, pk)
    
    items = order.items.select_related("item").order_by("id")
    
    return render(request, "restaurant/print_kitchen_ticket.html", {
        "hotel": get_hotel(request),
        "order": order,
        "items": items,
        "is_print_view": True,
    })


# ============================================================================
# Report Views
# ============================================================================

@method_decorator(login_required, name="dispatch")
class SalesReportView(ManagerRequiredMixin, TemplateView):
    """Sales report view"""
    template_name = "restaurant/reports/sales_report.html"
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hotel = get_hotel(self.request)
        
        from .forms import SalesReportForm
        form = SalesReportForm(self.request.GET or None, user=self.request.user)
        
        ctx["form"] = form
        ctx["hotel"] = hotel
        
        if form.is_valid():
            ctx.update(self._get_report_data(form, hotel))
        
        return ctx
    
    def _get_report_data(self, form, hotel):
        """Generate report data based on form filters"""
        data = {}
        date_from = form.cleaned_data.get("date_from")
        date_to = form.cleaned_data.get("date_to")
        group_by = form.cleaned_data.get("group_by", "day")
        
        # Base queryset
        orders = RestaurantOrder.objects.filter(
            hotel=hotel,
            status=RestaurantOrder.Status.PAID
        )
        
        if date_from:
            orders = orders.filter(closed_at__date__gte=date_from)
        if date_to:
            orders = orders.filter(closed_at__date__lte=date_to)
        
        data["total_orders"] = orders.count()
        data["total_revenue"] = orders.aggregate(
            total=Coalesce(Sum("invoice__total"), Decimal("0.00"))
        )["total"]
        
        # Group by logic
        if group_by == "day":
            data["chart_data"] = self._group_by_day(orders)
        elif group_by == "category":
            data["chart_data"] = self._group_by_category(orders)
        elif group_by == "item":
            data["chart_data"] = self._group_by_item(orders)
        
        return data
    
    def _group_by_day(self, orders):
        """Group orders by day"""
        from django.db.models.functions import TruncDate
        
        return orders.annotate(
            date=TruncDate("closed_at")
        ).values("date").annotate(
            total=Coalesce(Sum("invoice__total"), Decimal("0.00")),
            count=Count("id")
        ).order_by("date")
    
    def _group_by_category(self, orders):
        """Group sales by menu category"""
        return RestaurantOrderItem.objects.filter(
            order__in=orders
        ).values("item__category__name").annotate(
            total_qty=Sum("qty"),
            total_revenue=Coalesce(Sum(F("qty") * F("unit_price")), Decimal("0.00"))
        ).order_by("-total_revenue")
    
    def _group_by_item(self, orders):
        """Group sales by menu item"""
        return RestaurantOrderItem.objects.filter(
            order__in=orders
        ).values("item__name", "item__price").annotate(
            total_qty=Sum("qty"),
            total_revenue=Coalesce(Sum(F("qty") * F("unit_price")), Decimal("0.00"))
        ).order_by("-total_revenue")[:20]


@method_decorator(login_required, name="dispatch")
class StockReportView(ManagerRequiredMixin, TemplateView):
    """Stock/Inventory report view"""
    template_name = "restaurant/reports/stock_report.html"
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hotel = get_hotel(self.request)
        
        from .forms import StockReportForm
        form = StockReportForm(self.request.GET or None, hotel=hotel)
        
        ctx["form"] = form
        ctx["hotel"] = hotel
        
        if form.is_valid():
            items = MenuItem.objects.filter(hotel=hotel)
            
            category = form.cleaned_data.get("category")
            low_stock_only = form.cleaned_data.get("low_stock_only", False)
            sort_by = form.cleaned_data.get("sort_by", "name")
            
            if category:
                items = items.filter(category=category)
            
            if low_stock_only:
                items = items.filter(track_stock=True, stock_qty__lte=F("reorder_level"))
            
            # Apply sorting
            if sort_by == "name":
                items = items.order_by("name")
            elif sort_by == "stock_qty":
                items = items.order_by("stock_qty")
            elif sort_by == "sales_count":
                items = items.annotate(
                    sales_count=Coalesce(Sum("order_items__qty"), Decimal("0"))
                ).order_by("-sales_count")
            
            ctx["items"] = items
            ctx["low_stock_count"] = items.filter(
                track_stock=True, stock_qty__lte=F("reorder_level")
            ).count()
            ctx["out_of_stock_count"] = items.filter(
                track_stock=True, stock_qty=0
            ).count()
        
        return ctx


@method_decorator(login_required, name="dispatch")
class TaxReportView(ManagerRequiredMixin, TemplateView):
    """Tax report view"""
    template_name = "restaurant/reports/tax_report.html"
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hotel = get_hotel(self.request)
        today = timezone.localdate()
        
        # Get current month range
        from dateutil.relativedelta import relativedelta
        month_start = today.replace(day=1)
        month_end = month_start + relativedelta(months=1) - relativedelta(days=1)
        
        paid_orders = RestaurantOrder.objects.filter(
            hotel=hotel,
            status=RestaurantOrder.Status.PAID,
            closed_at__date__gte=month_start,
            closed_at__date__lte=month_end
        )
        
        # Calculate tax collected
        tax_total = Decimal("0.00")
        for order in paid_orders:
            tax_total += order.tax
        
        ctx.update({
            "hotel": hotel,
            "period_start": month_start,
            "period_end": month_end,
            "total_orders": paid_orders.count(),
            "total_sales": paid_orders.aggregate(
                total=Coalesce(Sum("invoice__total"), Decimal("0.00"))
            )["total"],
            "total_tax": tax_total,
            "tax_rate": 0,  # Configure based on your tax settings
        })
        
        return ctx


@login_required
@require_GET
def export_sales_csv(request: HttpRequest) -> HttpResponse:
    """Export sales report as CSV"""
    require_manager_role(request)
    hotel = get_hotel(request)
    
    import csv
    from django.http import HttpResponse
    
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="sales_report_{timezone.localdate()}.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        "Order Number", "Date", "Table", "Customer", "Subtotal", 
        "Discount", "Tax", "Total", "Status", "Payment Method"
    ])
    
    # Get date range from request
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    
    orders = RestaurantOrder.objects.filter(hotel=hotel, status=RestaurantOrder.Status.PAID)
    
    if date_from:
        orders = orders.filter(closed_at__date__gte=date_from)
    if date_to:
        orders = orders.filter(closed_at__date__lte=date_to)
    
    orders = orders.select_related("table", "invoice").order_by("-closed_at")
    
    for order in orders:
        payment_method = ""
        if hasattr(order, "invoice") and order.invoice:
            payment = order.invoice.payments.first()
            if payment:
                payment_method = payment.get_method_display()
        
        writer.writerow([
            order.order_number,
            order.closed_at.strftime("%Y-%m-%d %H:%M") if order.closed_at else "",
            order.table.number if order.table else "Walk-in",
            order.customer_name or "",
            order.subtotal,
            order.discount,
            order.tax,
            order.total,
            order.get_status_display(),
            payment_method,
        ])
    
    return response

