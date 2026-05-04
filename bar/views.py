from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum, Prefetch, F, Count, Avg, DecimalField, OuterRef, Subquery, ExpressionWrapper
from django.db.models.functions import TruncDate, Coalesce
from django.http import JsonResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_GET, require_POST
from django.views.generic import CreateView, DetailView, ListView, UpdateView, TemplateView, View
from django.views.generic.edit import ModelFormMixin

from .forms import (
    BarCategoryForm, BarItemForm, BarOrderForm, BarOrderItemForm
)
from .models import BarCategory, BarItem, BarOrder, BarOrderItem, BarStockMovement


# ============================================================================
# Decorators & Helpers
# ============================================================================

def hotel_required(view_func):
    """Decorator to ensure user has a valid hotel context."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not get_user_hotel(request.user):
            messages.error(request, "Please select a hotel first.")
            return redirect("hotels:select_hotel")
        return view_func(request, *args, **kwargs)
    return wrapper


def get_user_hotel(user):
    """Get the current active hotel for the user with caching."""
    if not user.is_authenticated:
        return None
    
    if hasattr(user, '_cached_hotel'):
        return user._cached_hotel
    
    try:
        session_hotel_id = getattr(user, 'session', {}).get('active_hotel_id') if hasattr(user, 'session') else None
        
        if session_hotel_id:
            from hotels.models import Hotel
            try:
                hotel = Hotel.objects.get(id=session_hotel_id, is_active=True)
                user._cached_hotel = hotel
                return hotel
            except Hotel.DoesNotExist:
                pass
        
        active_membership = user.hotel_memberships.filter(
            is_active=True, 
            hotel__is_active=True
        ).select_related('hotel').first()
        
        if active_membership and active_membership.hotel:
            user._cached_hotel = active_membership.hotel
            return active_membership.hotel
    except Exception:
        pass
    
    return None


class HotelAutoSelectMixin:
    """Mixin to automatically set the hotel for the user with permission checks."""
    
    def dispatch(self, request, *args, **kwargs):
        self.hotel = self.get_hotel()
        if not self.hotel:
            messages.error(request, "Please select a hotel to continue.")
            return redirect("hotels:select_hotel")
        
        if not request.user.hotel_memberships.filter(hotel=self.hotel, is_active=True).exists():
            messages.error(request, "You don't have access to this hotel.")
            return redirect("hotels:select_hotel")
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_hotel(self):
        return get_user_hotel(self.request.user)
    
    def get_queryset(self):
        qs = super().get_queryset()
        if self.hotel:
            return qs.filter(hotel=self.hotel)
        return qs.none()
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.hotel:
            kwargs['hotel'] = self.hotel
        return kwargs
    
    def form_valid(self, form):
        if self.hotel and hasattr(form.instance, 'hotel'):
            form.instance.hotel = self.hotel
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['hotel'] = self.hotel
        return context


class StaffRequiredMixin(UserPassesTestMixin):
    """Mixin to require staff permissions."""
    
    def test_func(self):
        user = self.request.user
        hotel = getattr(self, 'hotel', None) or get_user_hotel(user)
        return user.is_authenticated and (
            user.is_superuser or 
            user.hotel_memberships.filter(
                hotel=hotel, 
                is_active=True,
                role__in=['admin', 'general_manager', 'restaurant_manager', 'server']
            ).exists()
        )
    
    def handle_no_permission(self):
        messages.error(self.request, "You don't have permission to access this page.")
        return redirect('bar:order_list')


class ManagerRequiredMixin(UserPassesTestMixin):
    """Mixin to require manager permissions."""
    
    def test_func(self):
        user = self.request.user
        hotel = getattr(self, 'hotel', None) or get_user_hotel(user)
        return user.is_authenticated and (
            user.is_superuser or 
            user.hotel_memberships.filter(
                hotel=hotel, 
                is_active=True,
                role__in=['admin', 'general_manager', 'restaurant_manager']
            ).exists()
        )
    
    def handle_no_permission(self):
        messages.error(self.request, "Manager access required for this action.")
        return redirect('bar:order_list')


def require_staff_role(request):
    """Require staff level access (server, manager, admin)"""
    hotel = get_user_hotel(request.user)
    if not request.user.is_authenticated:
        raise ValidationError("Authentication required")
    
    if not request.user.is_superuser and not request.user.hotel_memberships.filter(
        hotel=hotel, 
        is_active=True,
        role__in=['admin', 'general_manager', 'restaurant_manager', 'server']
    ).exists():
        raise ValidationError("Staff access required")


def require_manager_role(request):
    """Require manager level access"""
    hotel = get_user_hotel(request.user)
    if not request.user.is_authenticated:
        raise ValidationError("Authentication required")
    
    if not request.user.is_superuser and not request.user.hotel_memberships.filter(
        hotel=hotel, 
        is_active=True,
        role__in=['admin', 'general_manager', 'restaurant_manager']
    ).exists():
        raise ValidationError("Manager access required")


def render_order_items_response(order: BarOrder, request: HttpRequest) -> Dict[str, Any]:
    """Helper to render order items HTML and totals for AJAX responses"""
    items = order.items.select_related("item").order_by("-id")
    html = render_to_string(
        "bar/partials/order_items_table.html",
        {"order": order, "items": items},
        request=request
    )
    
    return {
        "ok": True,
        "items_html": html,
        "subtotal": str(order.subtotal),
        "total": str(order.total),
        "status": order.status,
    }


# ============================================================================
# Category Views
# ============================================================================

class BarCategoryListView(LoginRequiredMixin, HotelAutoSelectMixin, StaffRequiredMixin, ListView):
    """List all bar categories with filtering and stats."""
    model = BarCategory
    template_name = "bar/category_list.html"
    context_object_name = "categories"
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().prefetch_related(
            Prefetch('items', queryset=BarItem.objects.filter(is_active=True))
        )
        
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q))
        
        active = self.request.GET.get("active", "")
        if active == "true":
            qs = qs.filter(is_active=True)
        elif active == "false":
            qs = qs.filter(is_active=False)
        
        qs = qs.annotate(item_count=Count('items', filter=Q(items__is_active=True)))
        
        return qs.order_by("sort_order", "name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queryset = self.object_list if hasattr(self, 'object_list') else self.get_queryset()
        
        context.update({
            "total_categories": queryset.count(),
            "active_categories": queryset.filter(is_active=True).count(),
            "inactive_categories": queryset.filter(is_active=False).count(),
            "current_filters": {
                "q": self.request.GET.get("q", ""),
                "active": self.request.GET.get("active", ""),
            },
        })
        
        return context


class BarCategoryCreateView(LoginRequiredMixin, HotelAutoSelectMixin, ManagerRequiredMixin, CreateView):
    """Create a new bar category."""
    model = BarCategory
    form_class = BarCategoryForm
    template_name = "bar/category_form.html"
    success_url = reverse_lazy("bar:category_list")

    def form_valid(self, form):
        form.instance.hotel = self.hotel
        messages.success(self.request, f"Category '{form.instance.name}' created successfully.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "title": "Create Category",
            "submit_text": "Create Category",
            "is_edit": False,
        })
        return context


class BarCategoryUpdateView(LoginRequiredMixin, HotelAutoSelectMixin, ManagerRequiredMixin, UpdateView):
    """Update an existing bar category."""
    model = BarCategory
    form_class = BarCategoryForm
    template_name = "bar/category_form.html"

    def get_success_url(self):
        return reverse("bar:category_list")

    def form_valid(self, form):
        messages.success(self.request, f"Category '{form.instance.name}' updated successfully.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "title": "Edit Category",
            "submit_text": "Update Category",
            "is_edit": True,
        })
        return context


# ============================================================================
# Item Views
# ============================================================================

class BarItemListView(LoginRequiredMixin, HotelAutoSelectMixin, StaffRequiredMixin, ListView):
    """List all bar items with advanced filtering and stock alerts."""
    model = BarItem
    template_name = "bar/item_list.html"
    context_object_name = "items"
    paginate_by = 30

    def get_queryset(self):
        qs = super().get_queryset().select_related("category")
        
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(name__icontains=q) | 
                Q(sku__icontains=q) | 
                Q(category__name__icontains=q)
            )
        
        category_id = self.request.GET.get("category", "")
        if category_id and category_id.isdigit():
            qs = qs.filter(category_id=category_id)
        
        low_stock = self.request.GET.get("low_stock", "")
        if low_stock == "true":
            qs = qs.filter(track_stock=True, stock_qty__lte=F("reorder_level"))
        elif low_stock == "out":
            qs = qs.filter(track_stock=True, stock_qty=0)
        
        active = self.request.GET.get("active", "")
        if active == "true":
            qs = qs.filter(is_active=True)
        elif active == "false":
            qs = qs.filter(is_active=False)
        
        track_stock = self.request.GET.get("track_stock", "")
        if track_stock == "true":
            qs = qs.filter(track_stock=True)
        
        qs = qs.annotate(
            total_sold=Coalesce(
                Sum('order_items__qty', output_field=DecimalField(max_digits=12, decimal_places=2)),
                Decimal(0)
            ),
            total_revenue=Coalesce(
                Sum(
                    ExpressionWrapper(
                        F('order_items__qty') * F('order_items__unit_price'),
                        output_field=DecimalField(max_digits=14, decimal_places=2)
                    ),
                    output_field=DecimalField(max_digits=14, decimal_places=2)
                ),
                Decimal(0)
            )
        )
        
        return qs.order_by("category__name", "name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        all_items = BarItem.objects.filter(hotel=self.hotel)
        
        total_value_result = all_items.aggregate(
            total=Coalesce(
                Sum(
                    ExpressionWrapper(
                        F("stock_qty") * F("cost_price"),
                        output_field=DecimalField(max_digits=14, decimal_places=2)
                    )
                ),
                Decimal("0.00")
            )
        )
        
        context.update({
            "total_items": all_items.count(),
            "active_items": all_items.filter(is_active=True).count(),
            "low_stock_items": all_items.filter(
                track_stock=True, stock_qty__lte=F("reorder_level")
            ).count(),
            "out_of_stock_items": all_items.filter(
                track_stock=True, stock_qty=0
            ).count(),
            "total_value": total_value_result["total"],
            "categories": BarCategory.objects.filter(hotel=self.hotel, is_active=True),
            "current_filters": {
                "q": self.request.GET.get("q", ""),
                "category": self.request.GET.get("category", ""),
                "low_stock": self.request.GET.get("low_stock", ""),
                "active": self.request.GET.get("active", ""),
                "track_stock": self.request.GET.get("track_stock", ""),
            },
        })
        
        return context


class BarItemCreateView(LoginRequiredMixin, HotelAutoSelectMixin, ManagerRequiredMixin, CreateView):
    """Create a new bar item with stock tracking."""
    model = BarItem
    form_class = BarItemForm
    template_name = "bar/item_form.html"
    success_url = reverse_lazy("bar:item_list")

    @transaction.atomic
    def form_valid(self, form):
        form.instance.hotel = self.hotel
        response = super().form_valid(form)
        
        if form.instance.track_stock and form.instance.stock_qty > 0:
            BarStockMovement.objects.create(
                hotel=self.hotel,
                item=form.instance,
                movement_type=BarStockMovement.MovementType.OPENING,
                quantity=form.instance.stock_qty,
                balance_after=form.instance.stock_qty,
                note=f"Opening stock for {form.instance.name}",
                created_by=self.request.user
            )
        
        messages.success(self.request, f"Item '{form.instance.name}' created successfully.")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "title": "Create Item",
            "submit_text": "Create Item",
            "is_edit": False,
        })
        return context


class BarItemUpdateView(LoginRequiredMixin, HotelAutoSelectMixin, ManagerRequiredMixin, UpdateView):
    """Update an existing bar item."""
    model = BarItem
    form_class = BarItemForm
    template_name = "bar/item_form.html"

    def get_success_url(self):
        return reverse("bar:item_list")

    def form_valid(self, form):
        messages.success(self.request, f"Item '{form.instance.name}' updated successfully.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "title": "Edit Item",
            "submit_text": "Update Item",
            "is_edit": True,
        })
        return context


# ============================================================================
# Order Views
# ============================================================================

class BarOrderListView(LoginRequiredMixin, HotelAutoSelectMixin, StaffRequiredMixin, ListView):
    """List all bar orders with comprehensive filtering and stats."""
    model = BarOrder
    template_name = "bar/order_list.html"
    context_object_name = "orders"
    paginate_by = 30

    def get_queryset(self):
        qs = super().get_queryset().select_related(
            "booking", "booking__guest", "created_by"
        ).prefetch_related(
            Prefetch("items", queryset=BarOrderItem.objects.select_related("item"))
        )
        
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(order_number__icontains=q) |
                Q(guest_name__icontains=q) |
                Q(booking__guest__first_name__icontains=q) |
                Q(booking__guest__last_name__icontains=q)
            )
        
        status_ = self.request.GET.get("status", "")
        if status_:
            qs = qs.filter(status=status_)
        
        date_from = self.request.GET.get("date_from", "")
        date_to = self.request.GET.get("date_to", "")
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        
        room_charge = self.request.GET.get("room_charge", "")
        if room_charge == "true":
            qs = qs.filter(room_charge=True)
        elif room_charge == "false":
            qs = qs.filter(room_charge=False)
        
        qs = qs.annotate(
            calculated_subtotal=Coalesce(
                Sum(
                    ExpressionWrapper(
                        F('items__qty') * F('items__unit_price'),
                        output_field=DecimalField(max_digits=14, decimal_places=2)
                    ),
                    output_field=DecimalField(max_digits=14, decimal_places=2)
                ),
                Decimal(0)
            )
        )
        
        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queryset = self.object_list if hasattr(self, 'object_list') else self.get_queryset()
        today = timezone.now().date()
        
        context.update({
            "total_orders": queryset.count(),
            "open_orders": queryset.filter(status=BarOrder.Status.OPEN).count(),
            "served_orders": queryset.filter(status=BarOrder.Status.SERVED).count(),
            "billed_orders": queryset.filter(status=BarOrder.Status.BILLED).count(),
            "paid_orders": queryset.filter(status=BarOrder.Status.PAID).count(),
            "cancelled_orders": queryset.filter(status=BarOrder.Status.CANCELLED).count(),
        })
        
        today_orders = queryset.filter(created_at__date=today)
        today_paid = today_orders.filter(status=BarOrder.Status.PAID)
        
        today_revenue_result = BarOrderItem.objects.filter(
            order__in=today_paid,
            order__hotel=self.hotel
        ).aggregate(
            total=Coalesce(
                Sum(
                    ExpressionWrapper(
                        F('qty') * F('unit_price'),
                        output_field=DecimalField(max_digits=14, decimal_places=2)
                    )
                ),
                Decimal("0.00")
            )
        )
        
        context.update({
            "today_orders": today_orders.count(),
            "today_revenue": today_revenue_result["total"],
        })
        
        paid_orders = queryset.filter(status=BarOrder.Status.PAID)
        if paid_orders.exists():
            total_revenue_result = BarOrderItem.objects.filter(
                order__in=paid_orders,
                order__hotel=self.hotel
            ).aggregate(
                total=Coalesce(
                    Sum(
                        ExpressionWrapper(
                            F('qty') * F('unit_price'),
                            output_field=DecimalField(max_digits=14, decimal_places=2)
                        )
                    ),
                    Decimal("0.00")
                )
            )
            total_revenue = total_revenue_result["total"]
            context["avg_order_value"] = total_revenue / paid_orders.count()
        else:
            context["avg_order_value"] = Decimal("0.00")
        
        context.update({
            "status_choices": BarOrder.Status.choices,
            "current_filters": {
                "q": self.request.GET.get("q", ""),
                "status": self.request.GET.get("status", ""),
                "date_from": self.request.GET.get("date_from", ""),
                "date_to": self.request.GET.get("date_to", ""),
                "room_charge": self.request.GET.get("room_charge", ""),
            },
        })
        
        return context


class BarOrderCreateView(LoginRequiredMixin, HotelAutoSelectMixin, StaffRequiredMixin, CreateView):
    """Create a new bar order with basic details (items added later)."""
    model = BarOrder
    form_class = BarOrderForm
    template_name = "bar/order_form.html"

    def get_success_url(self):
        return reverse("bar:order_detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context.update({
            "title": "Create Bar Order",
            "submit_text": "Create Order",
            "is_edit": False,
            "today_orders": BarOrder.objects.filter(
                hotel=self.hotel,
                created_at__date=timezone.now().date()
            ).count() if self.hotel else 0,
        })
        return context

    def form_valid(self, form):
        form.instance.hotel = self.hotel
        form.instance.created_by = self.request.user
        form.instance.status = BarOrder.Status.OPEN
        
        response = super().form_valid(form)
        
        messages.success(
            self.request, 
            f"Bar order {self.object.order_number} created successfully. You can now add items."
        )
        
        return response


class BarOrderUpdateView(LoginRequiredMixin, HotelAutoSelectMixin, StaffRequiredMixin, UpdateView):
    """Update an existing bar order (basic details only - not items)."""
    model = BarOrder
    form_class = BarOrderForm
    template_name = "bar/order_form.html"

    def get_success_url(self):
        return reverse("bar:order_detail", kwargs={"pk": self.object.pk})

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        order = self.get_object()
        
        if order.status in [BarOrder.Status.PAID, BarOrder.Status.CANCELLED]:
            messages.error(request, "Cannot edit a paid or cancelled order.")
            return redirect("bar:order_detail", pk=order.pk)
        
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "title": "Edit Bar Order",
            "submit_text": "Update Order",
            "is_edit": True,
        })
        return context

    def form_valid(self, form):
        messages.success(self.request, f"Bar order {self.object.order_number} updated successfully.")
        return super().form_valid(form)


class BarOrderDetailView(LoginRequiredMixin, HotelAutoSelectMixin, StaffRequiredMixin, DetailView):
    """Display detailed bar order information with item management."""
    model = BarOrder
    template_name = "bar/order_detail.html"
    context_object_name = "order"

    def get_queryset(self):
        return super().get_queryset().select_related(
            "hotel", "booking", "booking__guest", "created_by"
        ).prefetch_related(
            Prefetch("items", queryset=BarOrderItem.objects.select_related("item", "item__category"))
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = self.object
        
        context.update({
            "can_edit": order.status not in [BarOrder.Status.PAID, BarOrder.Status.CANCELLED],
            "can_add_items": order.status in [BarOrder.Status.OPEN, BarOrder.Status.SERVED],
            "can_mark_served": order.status == BarOrder.Status.OPEN and order.items.exists(),
            "can_mark_billed": order.status in [BarOrder.Status.OPEN, BarOrder.Status.SERVED] and order.items.exists(),
            "can_mark_paid": order.status == BarOrder.Status.BILLED,
            "can_cancel": order.status not in [BarOrder.Status.PAID, BarOrder.Status.CANCELLED],
            "item_form": BarOrderItemForm(hotel=order.hotel),
        })
        
        if context["can_add_items"]:
            context["available_items"] = BarItem.objects.filter(
                hotel=order.hotel, 
                is_active=True
            ).select_related("category").order_by("category__name", "name")
        
        return context


# ============================================================================
# AJAX Endpoints for Order Items
# ============================================================================

@login_required
@require_GET
def bar_items_api(request: HttpRequest) -> JsonResponse:
    """API endpoint for bar item autocomplete/search"""
    hotel = get_user_hotel(request.user)
    query = request.GET.get("q", "").strip()
    category_id = request.GET.get("category", "").strip()
    
    qs = BarItem.objects.filter(hotel=hotel, is_active=True).select_related("category")
    
    if query:
        qs = qs.filter(name__icontains=query)
    if category_id:
        qs = qs.filter(category_id=category_id)
    
    data = [
        {
            "id": item.id,
            "name": item.name,
            "price": str(item.selling_price),
            "category": item.category.name if item.category else "",
            "stock_available": str(item.stock_qty) if item.track_stock else None,
            "unit": item.unit,
        }
        for item in qs[:50]
    ]
    
    return JsonResponse({"results": data, "count": len(data)})


@login_required
@require_POST
def bar_order_add_item_ajax(request: HttpRequest, pk: int) -> JsonResponse:
    """Add item to order via AJAX"""
    try:
        require_staff_role(request)
    except ValidationError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=403)
    
    hotel = get_user_hotel(request.user)
    order = get_object_or_404(BarOrder, pk=pk, hotel=hotel)
    
    if order.status in [BarOrder.Status.PAID, BarOrder.Status.CANCELLED]:
        return JsonResponse(
            {"ok": False, "error": "Order is closed and cannot be modified."},
            status=400
        )
    
    # Debug: Log the POST data
    print("POST data:", request.POST)
    print("POST keys:", list(request.POST.keys()))
    
    # Try to get the item ID from different possible field names
    item_id = request.POST.get("item_id") or request.POST.get("item") or request.POST.get("item-id")
    
    if not item_id:
        return JsonResponse({
            "ok": False, 
            "error": "Item ID is required. Received POST data: " + str(dict(request.POST))
        }, status=400)
    
    try:
        item = BarItem.objects.get(pk=item_id, hotel=hotel, is_active=True)
    except BarItem.DoesNotExist:
        return JsonResponse({"ok": False, "error": f"Item with ID {item_id} not found"}, status=400)
    except ValueError:
        return JsonResponse({"ok": False, "error": f"Invalid item ID: {item_id}"}, status=400)
    
    # Get quantity
    try:
        qty = int(request.POST.get("qty", 1))
        if qty <= 0:
            qty = 1
    except ValueError:
        qty = 1
    
    # Check stock if tracking is enabled
    if item.track_stock and qty > item.stock_qty:
        return JsonResponse({
            "ok": False, 
            "error": f"Not enough stock. Available: {item.stock_qty} {item.unit}"
        }, status=400)
    
    try:
        with transaction.atomic():
            # Check if item already exists in the order
            existing_item = order.items.filter(item=item).first()
            
            if existing_item:
                # Update quantity
                existing_item.qty += qty
                existing_item.save(update_fields=["qty"])
                order_item = existing_item
                message = f"Updated {item.name} quantity to {existing_item.qty}"
            else:
                # Add new item
                order_item = BarOrderItem.objects.create(
                    order=order,
                    item=item,
                    qty=qty,
                    unit_price=item.selling_price,
                    note=request.POST.get("note", "")
                )
                message = f"Added {qty} x {item.name} to order"
        
        # Return success response
        items = order.items.select_related("item").order_by("-id")
        
        # For AJAX response, return simple JSON
        return JsonResponse({
            "ok": True,
            "message": message,
            "subtotal": str(order.subtotal),
            "total": str(order.total),
            "item_count": items.count(),
        })
        
    except ValidationError as e:
        return JsonResponse({"ok": False, "error": "; ".join(e.messages)}, status=400)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({"ok": False, "error": str(e)}, status=400)
    


@login_required
@require_POST
def bar_order_remove_item_ajax(request: HttpRequest, pk: int, item_id: int) -> JsonResponse:
    """Remove item from order via AJAX"""
    try:
        require_staff_role(request)
    except ValidationError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=403)
    
    hotel = get_user_hotel(request.user)
    order = get_object_or_404(BarOrder, pk=pk, hotel=hotel)
    
    if order.status in [BarOrder.Status.PAID, BarOrder.Status.CANCELLED]:
        return JsonResponse(
            {"ok": False, "error": "Order is closed and cannot be modified."},
            status=400
        )
    
    order_item = get_object_or_404(BarOrderItem, pk=item_id, order=order)
    item_name = order_item.item.name
    
    with transaction.atomic():
        order_item.delete()
    
    messages.success(request, f"Removed {item_name} from order.")
    return JsonResponse(render_order_items_response(order, request))


@login_required
@require_POST
def bar_order_update_item_qty_ajax(request: HttpRequest, pk: int, item_id: int) -> JsonResponse:
    """Update item quantity via AJAX"""
    try:
        require_staff_role(request)
    except ValidationError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=403)
    
    hotel = get_user_hotel(request.user)
    order = get_object_or_404(BarOrder, pk=pk, hotel=hotel)
    
    if order.status in [BarOrder.Status.PAID, BarOrder.Status.CANCELLED]:
        return JsonResponse(
            {"ok": False, "error": "Order is closed and cannot be modified."},
            status=400
        )
    
    try:
        qty = int(request.POST.get("qty", "0"))
    except ValueError:
        return JsonResponse({"ok": False, "error": "Invalid quantity value."}, status=400)
    
    if qty <= 0:
        return JsonResponse({"ok": False, "error": "Quantity must be at least 1."}, status=400)
    
    order_item = get_object_or_404(BarOrderItem, pk=item_id, order=order)
    
    # Check stock if tracking is enabled
    if order_item.item.track_stock and qty > order_item.item.stock_qty + order_item.qty:
        return JsonResponse({
            "ok": False, 
            "error": f"Not enough stock. Available: {order_item.item.stock_qty + order_item.qty}"
        }, status=400)
    
    order_item.qty = qty
    order_item.save(update_fields=["qty"])
    
    return JsonResponse(render_order_items_response(order, request))


# ============================================================================
# Order Action Views
# ============================================================================

@login_required
@require_http_methods(["POST"])
@hotel_required
@transaction.atomic
def bar_order_mark_served(request: HttpRequest, pk: int) -> HttpResponse:
    """Mark a bar order as served."""
    hotel = get_user_hotel(request.user)
    order = get_object_or_404(BarOrder, pk=pk, hotel=hotel)
    
    if order.status == BarOrder.Status.CANCELLED:
        messages.error(request, "Cannot serve a cancelled order.")
        return redirect("bar:order_detail", pk=order.pk)
    
    if not order.items.exists():
        messages.error(request, "Cannot serve an empty order. Please add items first.")
        return redirect("bar:order_detail", pk=order.pk)
    
    order.status = BarOrder.Status.SERVED
    if not order.closed_at:
        order.closed_at = timezone.now()
    order.save(update_fields=["status", "closed_at"])
    
    messages.success(request, f"Bar order {order.order_number} marked as served.")
    return redirect("bar:order_detail", pk=order.pk)


@login_required
@require_http_methods(["POST"])
@hotel_required
@transaction.atomic
def bar_order_mark_billed(request: HttpRequest, pk: int) -> HttpResponse:
    """Mark a bar order as billed (ready for payment)."""
    hotel = get_user_hotel(request.user)
    order = get_object_or_404(BarOrder, pk=pk, hotel=hotel)
    
    if not order.items.exists():
        messages.error(request, "Cannot bill an empty order. Please add items first.")
        return redirect("bar:order_detail", pk=order.pk)
    
    if order.status == BarOrder.Status.CANCELLED:
        messages.error(request, "Cannot bill a cancelled order.")
        return redirect("bar:order_detail", pk=order.pk)
    
    # Mark order as billed
    order.status = BarOrder.Status.BILLED
    order.save(update_fields=["status"])
    
    # Try to create finance invoice if finance app is installed
    try:
        from finance.models import Invoice, InvoiceLineItem
        
        # Check if invoice already exists
        invoice, created = Invoice.objects.get_or_create(
            bar_order=order,
            defaults={
                "hotel": hotel,
                "customer_name": order.guest_name or "Bar Customer",
                "customer_email": "",
                "subtotal": order.subtotal,
                "discount": order.discount or 0,
                "tax": order.tax or 0,
                "total": order.total,
                "status": "issued",
                "invoice_type": "bar",
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
                    total=order_item.line_total,
                )
        
        messages.success(request, f"Bar order {order.order_number} has been billed. Invoice #{invoice.invoice_number if hasattr(invoice, 'invoice_number') else invoice.id} created.")
        
    except ImportError:
        # Finance app not installed, just mark as billed
        messages.success(request, f"Bar order {order.order_number} has been billed. Ready for payment.")
    except Exception as e:
        # Log error but don't fail the operation
        print(f"Error creating invoice: {e}")
        messages.warning(request, f"Order marked as billed but invoice creation failed: {str(e)}")
    
    return redirect("bar:order_detail", pk=order.pk)


@login_required
@require_http_methods(["POST"])
@hotel_required
@transaction.atomic
def bar_order_mark_billed(request: HttpRequest, pk: int) -> HttpResponse:
    """Mark a bar order as billed and create finance invoice (ready for payment)."""
    hotel = get_user_hotel(request.user)
    order = get_object_or_404(BarOrder, pk=pk, hotel=hotel)
    
    if not order.items.exists():
        messages.error(request, "Cannot bill an empty order. Please add items first.")
        return redirect("bar:order_detail", pk=order.pk)
    
    if order.status == BarOrder.Status.CANCELLED:
        messages.error(request, "Cannot bill a cancelled order.")
        return redirect("bar:order_detail", pk=order.pk)
    
    try:
        from finance.models import Invoice, InvoiceLineItem
        
        # Check if invoice already exists
        existing_invoice = Invoice.objects.filter(
            hotel=hotel,
            order_number=order.order_number,
            status__in=[Invoice.Status.DRAFT, Invoice.Status.ISSUED, Invoice.Status.SENT, Invoice.Status.PARTIALLY_PAID]
        ).first()
        
        if existing_invoice:
            # Use existing invoice
            invoice = existing_invoice
            messages.info(request, f"Using existing invoice #{invoice.invoice_number}")
        else:
            # Create new invoice
            invoice = Invoice.objects.create(
                hotel=hotel,
                booking=order.booking,
                order_number=order.order_number,
                customer_name=order.guest_name or "Bar Customer",
                customer_phone=order.booking.guest.phone if order.booking else "",
                customer_email=order.booking.guest.email if order.booking else "",
                invoice_date=timezone.now().date(),
                due_date=timezone.now().date() + timezone.timedelta(days=30),
                subtotal=order.subtotal,
                discount=order.discount or 0,
                discount_type="fixed",
                tax_amount=order.tax or 0,
                total_amount=order.total,
                currency="UGX",
                status=Invoice.Status.ISSUED,
                issued_at=timezone.now(),
                created_by=request.user,
                notes=f"Bar order #{order.order_number}",
            )
            
            # Create invoice line items for each bar item
            for order_item in order.items.all():
                InvoiceLineItem.objects.create(
                    invoice=invoice,
                    description=order_item.item.name,
                    quantity=order_item.qty,
                    unit_price=order_item.unit_price,  # This is the required field
                    discount=0,
                    tax_rate=0,
                    total=order_item.line_total,
                    booking=order.booking,
                )
            
            messages.success(request, f"Invoice #{invoice.invoice_number} created successfully.")
        
        # Mark order as billed
        order.status = BarOrder.Status.BILLED
        order.save(update_fields=["status"])
        
        messages.success(request, f"Bar order {order.order_number} has been billed. Ready for payment.")
        
    except ImportError as e:
        # Finance app not installed, just mark as billed
        order.status = BarOrder.Status.BILLED
        order.save(update_fields=["status"])
        messages.success(request, f"Bar order {order.order_number} has been billed. Ready for payment.")
        messages.warning(request, "Finance module not available. Invoice not created.")
        
    except Exception as e:
        # Rollback on error
        messages.error(request, f"Error creating invoice: {str(e)}")
        return redirect("bar:order_detail", pk=order.pk)
    
    return redirect("bar:order_detail", pk=order.pk)


@login_required
@require_http_methods(["POST"])
@hotel_required
@transaction.atomic
def bar_order_mark_paid(request: HttpRequest, pk: int) -> HttpResponse:
    """Mark a bar order as paid and update stock."""
    hotel = get_user_hotel(request.user)
    order = get_object_or_404(BarOrder, pk=pk, hotel=hotel)
    
    if order.status != BarOrder.Status.BILLED:
        messages.error(request, "Only billed orders can be marked as paid.")
        return redirect("bar:order_detail", pk=order.pk)
    
    if not order.items.exists():
        messages.error(request, "Cannot pay an empty order.")
        return redirect("bar:order_detail", pk=order.pk)
    
    try:
        # Process stock deductions for items
        for order_item in order.items.all():
            if order_item.item.track_stock:
                if Decimal(order_item.qty) > order_item.item.stock_qty:
                    messages.error(
                        request, 
                        f"Insufficient stock for {order_item.item.name}. Available: {order_item.item.stock_qty}"
                    )
                    return redirect("bar:order_detail", pk=order.pk)
                
                order_item.item.stock_qty -= Decimal(order_item.qty)
                order_item.item.save(update_fields=["stock_qty"])
                
                BarStockMovement.objects.create(
                    hotel=order.hotel,
                    item=order_item.item,
                    movement_type=BarStockMovement.MovementType.SALE,
                    quantity=-Decimal(order_item.qty),
                    balance_after=order_item.item.stock_qty,
                    reference=order.order_number,
                    note=f"Sale from order {order.order_number}",
                    created_by=request.user
                )
        
        # Update finance invoice if exists
        try:
            from finance.models import Invoice, Payment, CashAccount
            from decimal import Decimal as Dec
            
            invoice = Invoice.objects.filter(
                hotel=hotel,
                order_number=order.order_number,
                status__in=[Invoice.Status.ISSUED, Invoice.Status.SENT, Invoice.Status.PARTIALLY_PAID]
            ).first()
            
            if invoice:
                # Record payment
                payment = Payment.objects.create(
                    hotel=hotel,
                    invoice=invoice,
                    method=Payment.Method.CASH,  # Default to cash, can be enhanced later
                    amount=order.total,
                    currency="UGX",
                    status=Payment.PaymentStatus.COMPLETED,
                    received_by=request.user,
                    received_at=timezone.now(),
                    notes=f"Payment for bar order #{order.order_number}",
                )
                
                # Update invoice status
                invoice.amount_paid = order.total
                invoice.status = Invoice.Status.PAID
                invoice.paid_at = timezone.now()
                invoice.save(update_fields=["amount_paid", "status", "paid_at"])
                
                messages.info(request, f"Payment recorded in finance system.")
                
        except ImportError:
            pass
        except Exception as e:
            print(f"Finance update error: {e}")
        
        # Mark order as paid
        order.status = BarOrder.Status.PAID
        if not order.closed_at:
            order.closed_at = timezone.now()
        order.save(update_fields=["status", "closed_at"])
        
        messages.success(request, f"Bar order {order.order_number} marked as paid. Stock updated.")
        
    except ValidationError as e:
        for error in getattr(e, "messages", [str(e)]):
            messages.error(request, error)
    except Exception as e:
        messages.error(request, f"Error processing payment: {str(e)}")
    
    return redirect("bar:order_detail", pk=order.pk)


# ============================================================================
# Dashboard Views
# ============================================================================

class BarDashboardView(LoginRequiredMixin, HotelAutoSelectMixin, StaffRequiredMixin, TemplateView):
    """Bar management dashboard with analytics."""
    template_name = "bar/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        today = timezone.now().date()
        this_week = today - timezone.timedelta(days=7)
        this_month = today.replace(day=1)
        
        orders = BarOrder.objects.filter(hotel=self.hotel)
        paid_orders = orders.filter(status=BarOrder.Status.PAID)
        
        def calculate_revenue(queryset):
            result = BarOrderItem.objects.filter(
                order__in=queryset,
                order__hotel=self.hotel
            ).aggregate(
                total=Coalesce(
                    Sum(
                        ExpressionWrapper(
                            F('qty') * F('unit_price'),
                            output_field=DecimalField(max_digits=14, decimal_places=2)
                        )
                    ),
                    Decimal("0.00")
                )
            )
            return result["total"]
        
        context.update({
            "total_orders": orders.count(),
            "open_orders": orders.filter(status=BarOrder.Status.OPEN).count(),
            "today_orders": orders.filter(created_at__date=today).count(),
            "total_revenue": calculate_revenue(paid_orders),
            "today_revenue": calculate_revenue(paid_orders.filter(created_at__date=today)),
            "weekly_revenue": calculate_revenue(paid_orders.filter(created_at__date__gte=this_week)),
            "monthly_revenue": calculate_revenue(paid_orders.filter(created_at__date__gte=this_month)),
        })
        
        context.update({
            "low_stock_items": BarItem.objects.filter(
                hotel=self.hotel, track_stock=True, stock_qty__lte=F("reorder_level")
            ).count(),
            "out_of_stock_items": BarItem.objects.filter(
                hotel=self.hotel, track_stock=True, stock_qty=0
            ).count(),
        })
        
        context["recent_orders"] = BarOrder.objects.filter(
            hotel=self.hotel
        ).select_related("booking", "booking__guest").prefetch_related("items").order_by("-created_at")[:10]
        
        context["top_items"] = BarOrderItem.objects.filter(
            order__hotel=self.hotel,
            order__status=BarOrder.Status.PAID
        ).values(
            "item__name", "item__category__name"
        ).annotate(
            total_qty=Sum("qty"),
            total_revenue=Sum(
                ExpressionWrapper(
                    F("unit_price") * F("qty"),
                    output_field=DecimalField(max_digits=14, decimal_places=2)
                )
            )
        ).order_by("-total_qty")[:10]
        
        context["recent_movements"] = BarStockMovement.objects.filter(
            hotel=self.hotel
        ).select_related("item", "created_by").order_by("-created_at")[:10]
        
        return context


# ============================================================================
# API Views
# ============================================================================

@login_required
@require_GET
def bar_order_stats_api(request: HttpRequest) -> JsonResponse:
    """API endpoint for order statistics"""
    try:
        require_staff_role(request)
    except ValidationError as e:
        return JsonResponse({"error": str(e)}, status=403)
    
    hotel = get_user_hotel(request.user)
    
    stats = {
        "active_orders": BarOrder.objects.filter(
            hotel=hotel,
            status__in=[BarOrder.Status.OPEN, BarOrder.Status.SERVED]
        ).count(),
        "today_orders": BarOrder.objects.filter(
            hotel=hotel,
            created_at__date=timezone.localdate()
        ).count(),
        "pending_payment": BarOrder.objects.filter(
            hotel=hotel,
            status=BarOrder.Status.BILLED
        ).count(),
    }
    
    return JsonResponse(stats)



@login_required
@require_GET
def bar_order_refresh_items(request: HttpRequest, pk: int) -> JsonResponse:
    """Refresh order items (AJAX)"""
    try:
        require_staff_role(request)
    except ValidationError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=403)
    
    hotel = get_user_hotel(request.user)
    order = get_object_or_404(BarOrder, pk=pk, hotel=hotel)
    
    items = order.items.select_related("item").order_by("-id")
    html = render_to_string(
        "bar/partials/order_items_table.html",
        {
            "order": order, 
            "items": items, 
            "can_add_items": order.status in [BarOrder.Status.OPEN, BarOrder.Status.SERVED]
        },
        request=request
    )
    
    return JsonResponse({
        "ok": True,
        "items_html": html,
        "subtotal": str(order.subtotal),
        "total": str(order.total),
        "item_count": items.count(),
    })


@login_required
@require_http_methods(["POST"])
@hotel_required
@transaction.atomic
def bar_order_cancel(request: HttpRequest, pk: int) -> HttpResponse:
    """Cancel a bar order and restore stock."""
    hotel = get_user_hotel(request.user)
    order = get_object_or_404(BarOrder, pk=pk, hotel=hotel)
    
    if order.status == BarOrder.Status.PAID:
        messages.error(request, "Cannot cancel a paid order. Process a refund instead.")
        return redirect("bar:order_detail", pk=order.pk)
    
    try:
        with transaction.atomic():
            # Restore stock for items if stock was deducted
            for order_item in order.items.all():
                if order_item.item.track_stock:
                    order_item.item.stock_qty += Decimal(order_item.qty)
                    order_item.item.save(update_fields=["stock_qty", "updated_at"])
                    
                    # Create stock movement record
                    BarStockMovement.objects.create(
                        hotel=order.hotel,
                        item=order_item.item,
                        movement_type=BarStockMovement.MovementType.ADJUSTMENT,
                        quantity=Decimal(order_item.qty),
                        balance_after=order_item.item.stock_qty,
                        reference=order.order_number,
                        note=f"Stock restored from cancelled order {order.order_number}",
                        created_by=request.user
                    )
            
            # Update finance invoice if exists
            try:
                from finance.models import Invoice
                invoice = Invoice.objects.filter(
                    hotel=hotel,
                    order_number=order.order_number,
                    status__in=[Invoice.Status.ISSUED, Invoice.Status.SENT, Invoice.Status.PARTIALLY_PAID]
                ).first()
                
                if invoice:
                    invoice.status = Invoice.Status.VOID
                    invoice.voided_at = timezone.now()
                    invoice.voided_by = request.user
                    invoice.void_reason = f"Cancelled with bar order {order.order_number}"
                    invoice.save(update_fields=["status", "voided_at", "voided_by", "void_reason"])
                    messages.info(request, "Associated invoice has been voided.")
            except ImportError:
                pass
            
            order.status = BarOrder.Status.CANCELLED
            if not order.closed_at:
                order.closed_at = timezone.now()
            order.save(update_fields=["status", "closed_at", "updated_at"])
        
        messages.warning(request, f"Bar order {order.order_number} has been cancelled. Stock restored.")
        
    except Exception as e:
        messages.error(request, f"Error cancelling order: {str(e)}")
        return redirect("bar:order_detail", pk=order.pk)
    
    return redirect("bar:order_list")


@login_required
@require_GET
def bar_items_api(request: HttpRequest) -> JsonResponse:
    """API endpoint for bar item autocomplete/search"""
    hotel = get_user_hotel(request.user)
    query = request.GET.get("q", "").strip()
    category_id = request.GET.get("category", "").strip()
    
    qs = BarItem.objects.filter(hotel=hotel, is_active=True).select_related("category")
    
    if query:
        qs = qs.filter(
            Q(name__icontains=query) | 
            Q(sku__icontains=query) | 
            Q(category__name__icontains=query)
        )
    if category_id:
        qs = qs.filter(category_id=category_id)
    
    data = [
        {
            "id": item.id,
            "name": item.name,
            "price": str(item.selling_price),
            "category": item.category.name if item.category else "",
            "stock_available": str(item.stock_qty) if item.track_stock else None,
            "unit": item.unit,
            "is_low_stock": item.is_low_stock,
        }
        for item in qs[:50]
    ]
    
    return JsonResponse({"results": data, "count": len(data)})


@login_required
@require_GET
def bar_order_stats_api(request: HttpRequest) -> JsonResponse:
    """API endpoint for order statistics"""
    try:
        require_staff_role(request)
    except ValidationError as e:
        return JsonResponse({"error": str(e)}, status=403)
    
    hotel = get_user_hotel(request.user)
    today = timezone.now().date()
    
    # Calculate today's revenue
    today_paid_orders = BarOrder.objects.filter(
        hotel=hotel,
        status=BarOrder.Status.PAID,
        closed_at__date=today
    )
    
    today_revenue = D0
    for order in today_paid_orders:
        today_revenue += order.total
    
    stats = {
        "active_orders": BarOrder.objects.filter(
            hotel=hotel,
            status__in=[BarOrder.Status.OPEN, BarOrder.Status.SERVED]
        ).count(),
        "today_orders": BarOrder.objects.filter(
            hotel=hotel,
            created_at__date=today
        ).count(),
        "today_revenue": str(today_revenue),
        "pending_payment": BarOrder.objects.filter(
            hotel=hotel,
            status=BarOrder.Status.BILLED
        ).count(),
        "low_stock_items": BarItem.objects.filter(
            hotel=hotel, 
            track_stock=True, 
            stock_qty__lte=F("reorder_level")
        ).count(),
    }
    
    return JsonResponse(stats)
