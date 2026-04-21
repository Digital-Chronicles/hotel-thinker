from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum, Prefetch, F
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.generic import CreateView, DetailView, ListView, UpdateView, TemplateView

from .forms import BarCategoryForm, BarItemForm, BarOrderForm, BarOrderItemFormSet
from .models import BarCategory, BarItem, BarOrder, BarOrderItem, BarStockMovement


# ============================================================================
# Category Views
# ============================================================================

class BarCategoryListView(LoginRequiredMixin, ListView):
    """List all bar categories with filtering and stats."""
    model = BarCategory
    template_name = "bar/category_list.html"
    context_object_name = "categories"
    paginate_by = 20

    def get_queryset(self):
        qs = BarCategory.objects.select_related("hotel").prefetch_related("items")
        
        # Search filter
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(hotel__name__icontains=q))
        
        # Hotel filter
        hotel_id = self.request.GET.get("hotel", "").strip()
        if hotel_id:
            qs = qs.filter(hotel_id=hotel_id)
        
        # Active filter
        active = self.request.GET.get("active", "")
        if active == "true":
            qs = qs.filter(is_active=True)
        elif active == "false":
            qs = qs.filter(is_active=False)
        
        return qs.order_by("sort_order", "name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queryset = self.get_queryset()
        
        context["total_categories"] = queryset.count()
        context["active_categories"] = queryset.filter(is_active=True).count()
        context["inactive_categories"] = queryset.filter(is_active=False).count()
        
        context["current_filters"] = {
            "q": self.request.GET.get("q", ""),
            "hotel": self.request.GET.get("hotel", ""),
            "active": self.request.GET.get("active", ""),
        }
        
        # Get hotels for filter dropdown
        from hotels.models import Hotel
        context["hotels"] = Hotel.objects.filter(
            id__in=queryset.values_list("hotel_id", flat=True).distinct()
        )
        
        return context


class BarCategoryCreateView(LoginRequiredMixin, CreateView):
    """Create a new bar category."""
    model = BarCategory
    form_class = BarCategoryForm
    template_name = "bar/category_form.html"
    success_url = reverse_lazy("bar:category_list")

    def form_valid(self, form):
        messages.success(self.request, f"Category '{form.instance.name}' created successfully.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Create Category"
        context["submit_text"] = "Create Category"
        context["is_edit"] = False
        return context


class BarCategoryUpdateView(LoginRequiredMixin, UpdateView):
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
        context["title"] = "Edit Category"
        context["submit_text"] = "Update Category"
        context["is_edit"] = True
        return context


# ============================================================================
# Item Views
# ============================================================================

class BarItemListView(LoginRequiredMixin, ListView):
    """List all bar items with advanced filtering and stock alerts."""
    model = BarItem
    template_name = "bar/item_list.html"
    context_object_name = "items"
    paginate_by = 30

    def get_queryset(self):
        qs = BarItem.objects.select_related("hotel", "category")
        
        # Search filter
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(name__icontains=q) | 
                Q(sku__icontains=q) | 
                Q(category__name__icontains=q)
            )
        
        # Hotel filter
        hotel_id = self.request.GET.get("hotel", "").strip()
        if hotel_id:
            qs = qs.filter(hotel_id=hotel_id)
        
        # Category filter
        category_id = self.request.GET.get("category", "").strip()
        if category_id:
            qs = qs.filter(category_id=category_id)
        
        # Stock filters
        low_stock = self.request.GET.get("low_stock", "")
        if low_stock == "true":
            qs = qs.filter(track_stock=True, stock_qty__lte=F("reorder_level"))
        elif low_stock == "out":
            qs = qs.filter(track_stock=True, stock_qty=0)
        
        # Active filter
        active = self.request.GET.get("active", "")
        if active == "true":
            qs = qs.filter(is_active=True)
        elif active == "false":
            qs = qs.filter(is_active=False)
        
        # Stock tracking filter
        track_stock = self.request.GET.get("track_stock", "")
        if track_stock == "true":
            qs = qs.filter(track_stock=True)
        
        return qs.order_by("category__name", "name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queryset = BarItem.objects.all()
        
        # Stats
        context["total_items"] = queryset.count()
        context["active_items"] = queryset.filter(is_active=True).count()
        context["low_stock_items"] = queryset.filter(
            track_stock=True, stock_qty__lte=F("reorder_level")
        ).count()
        context["out_of_stock_items"] = queryset.filter(
            track_stock=True, stock_qty=0
        ).count()
        
        # Total inventory value
        total_value = queryset.aggregate(
            total=Sum(F("stock_qty") * F("cost_price"))
        )["total"] or Decimal("0.00")
        context["total_value"] = total_value
        
        # Categories for filter
        context["categories"] = BarCategory.objects.filter(is_active=True)
        
        # Hotels for filter
        from hotels.models import Hotel
        context["hotels"] = Hotel.objects.filter(
            id__in=queryset.values_list("hotel_id", flat=True).distinct()
        )
        
        context["current_filters"] = {
            "q": self.request.GET.get("q", ""),
            "hotel": self.request.GET.get("hotel", ""),
            "category": self.request.GET.get("category", ""),
            "low_stock": self.request.GET.get("low_stock", ""),
            "active": self.request.GET.get("active", ""),
            "track_stock": self.request.GET.get("track_stock", ""),
        }
        
        return context


class BarItemCreateView(LoginRequiredMixin, CreateView):
    """Create a new bar item with stock tracking."""
    model = BarItem
    form_class = BarItemForm
    template_name = "bar/item_form.html"
    success_url = reverse_lazy("bar:item_list")

    def form_valid(self, form):
        with transaction.atomic():
            response = super().form_valid(form)
            
            # Create opening stock movement if track_stock is enabled
            if form.instance.track_stock and form.instance.stock_qty > 0:
                BarStockMovement.objects.create(
                    hotel=form.instance.hotel,
                    item=form.instance,
                    movement_type=BarStockMovement.MovementType.OPENING,
                    quantity=form.instance.stock_qty,
                    balance_after=form.instance.stock_qty,
                    note="Opening stock",
                    created_by=self.request.user
                )
        
        messages.success(self.request, f"Item '{form.instance.name}' created successfully.")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Create Item"
        context["submit_text"] = "Create Item"
        context["is_edit"] = False
        return context


class BarItemUpdateView(LoginRequiredMixin, UpdateView):
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
        context["title"] = "Edit Item"
        context["submit_text"] = "Update Item"
        context["is_edit"] = True
        return context


# ============================================================================
# Order Views
# ============================================================================

class BarOrderListView(LoginRequiredMixin, ListView):
    """List all bar orders with comprehensive filtering and stats."""
    model = BarOrder
    template_name = "bar/order_list.html"
    context_object_name = "orders"
    paginate_by = 30

    def get_queryset(self):
        qs = BarOrder.objects.select_related(
            "hotel", "booking", "created_by"
        ).prefetch_related(
            Prefetch("items", queryset=BarOrderItem.objects.select_related("item"))
        )
        
        # Search filter
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(order_number__icontains=q) |
                Q(guest_name__icontains=q) |
                Q(booking__guest__first_name__icontains=q) |
                Q(booking__guest__last_name__icontains=q)
            )
        
        # Status filter
        status_ = self.request.GET.get("status", "").strip()
        if status_:
            qs = qs.filter(status=status_)
        
        # Hotel filter
        hotel_id = self.request.GET.get("hotel", "").strip()
        if hotel_id:
            qs = qs.filter(hotel_id=hotel_id)
        
        # Date range filter
        date_from = self.request.GET.get("date_from", "")
        date_to = self.request.GET.get("date_to", "")
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        
        # Room charge filter
        room_charge = self.request.GET.get("room_charge", "")
        if room_charge == "true":
            qs = qs.filter(room_charge=True)
        elif room_charge == "false":
            qs = qs.filter(room_charge=False)
        
        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queryset = self.get_queryset()
        
        # Status counts
        context["total_orders"] = queryset.count()
        context["open_orders"] = queryset.filter(status=BarOrder.Status.OPEN).count()
        context["served_orders"] = queryset.filter(status=BarOrder.Status.SERVED).count()
        context["billed_orders"] = queryset.filter(status=BarOrder.Status.BILLED).count()
        context["paid_orders"] = queryset.filter(status=BarOrder.Status.PAID).count()
        context["cancelled_orders"] = queryset.filter(status=BarOrder.Status.CANCELLED).count()
        
        # Today's orders
        today = timezone.now().date()
        today_orders = queryset.filter(created_at__date=today)
        context["today_orders"] = today_orders.count()
        
        # Today's revenue (only paid orders)
        today_paid = today_orders.filter(status=BarOrder.Status.PAID)
        context["today_revenue"] = sum(order.total for order in today_paid)
        
        # Average order value
        paid_orders = queryset.filter(status=BarOrder.Status.PAID)
        if paid_orders.exists():
            total_revenue = sum(order.total for order in paid_orders)
            context["avg_order_value"] = total_revenue / paid_orders.count()
        else:
            context["avg_order_value"] = Decimal("0.00")
        
        # Hotels for filter
        from hotels.models import Hotel
        context["hotels"] = Hotel.objects.filter(
            id__in=queryset.values_list("hotel_id", flat=True).distinct()
        )
        
        context["status_choices"] = BarOrder.Status.choices
        context["current_filters"] = {
            "q": self.request.GET.get("q", ""),
            "status": self.request.GET.get("status", ""),
            "hotel": self.request.GET.get("hotel", ""),
            "date_from": self.request.GET.get("date_from", ""),
            "date_to": self.request.GET.get("date_to", ""),
            "room_charge": self.request.GET.get("room_charge", ""),
        }
        
        return context


class BarOrderCreateView(LoginRequiredMixin, CreateView):
    """Create a new bar order."""
    model = BarOrder
    form_class = BarOrderForm
    template_name = "bar/order_form.html"

    def get_success_url(self):
        return reverse("bar:order_detail", kwargs={"pk": self.object.pk})

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # Pass initial hotel from GET parameter if provided
        hotel_id = self.request.GET.get("hotel") or self.request.POST.get("hotel")
        if hotel_id:
            kwargs["initial"] = {"hotel": hotel_id}
        return kwargs

    def form_valid(self, form):
        if self.request.user.is_authenticated:
            form.instance.created_by = self.request.user
        
        response = super().form_valid(form)
        messages.success(
            self.request, 
            f"Bar order {form.instance.order_number} created successfully. "
            "Add items to complete the order."
        )
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Create Bar Order"
        context["submit_text"] = "Create Order"
        context["is_edit"] = False
        return context


class BarOrderUpdateView(LoginRequiredMixin, UpdateView):
    """Update an existing bar order."""
    model = BarOrder
    form_class = BarOrderForm
    template_name = "bar/order_form.html"

    def get_success_url(self):
        return reverse("bar:order_detail", kwargs={"pk": self.object.pk})

    def form_valid(self, form):
        messages.success(self.request, f"Bar order {form.instance.order_number} updated successfully.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Edit Bar Order"
        context["submit_text"] = "Update Order"
        context["is_edit"] = True
        return context


class BarOrderDetailView(LoginRequiredMixin, DetailView):
    """Display detailed bar order information."""
    model = BarOrder
    template_name = "bar/order_detail.html"
    context_object_name = "order"

    def get_queryset(self):
        return BarOrder.objects.select_related(
            "hotel", "booking", "booking__guest", "created_by"
        ).prefetch_related(
            Prefetch("items", queryset=BarOrderItem.objects.select_related("item", "item__category"))
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Determine which actions are available
        context["can_edit"] = self.object.status not in [
            BarOrder.Status.PAID, 
            BarOrder.Status.CANCELLED
        ]
        context["can_add_items"] = self.object.status in [
            BarOrder.Status.OPEN, 
            BarOrder.Status.SERVED
        ]
        context["can_mark_served"] = self.object.status == BarOrder.Status.OPEN
        context["can_mark_billed"] = self.object.status in [
            BarOrder.Status.OPEN, 
            BarOrder.Status.SERVED
        ] and self.object.items.exists()
        context["can_mark_paid"] = self.object.status == BarOrder.Status.BILLED
        context["can_cancel"] = self.object.status not in [
            BarOrder.Status.PAID, 
            BarOrder.Status.CANCELLED
        ]
        
        # Get available items for adding
        if context["can_add_items"]:
            context["available_items"] = BarItem.objects.filter(
                hotel=self.object.hotel, 
                is_active=True
            ).select_related("category").order_by("category__name", "name")
        
        return context


# ============================================================================
# Order Action Views (Functions)
# ============================================================================

@login_required
@require_http_methods(["POST"])
def bar_order_mark_paid(request, pk):
    """Mark a bar order as paid."""
    order = get_object_or_404(BarOrder, pk=pk)
    
    if order.status != BarOrder.Status.BILLED:
        messages.error(request, "Only billed orders can be marked as paid.")
        return redirect("bar:order_detail", pk=order.pk)
    
    try:
        with transaction.atomic():
            # Process stock deductions for items
            for item in order.items.all():
                if item.item.track_stock:
                    # Check stock availability
                    if Decimal(item.qty) > item.item.stock_qty:
                        messages.error(
                            request, 
                            f"Insufficient stock for {item.item.name}. Available: {item.item.stock_qty}"
                        )
                        return redirect("bar:order_detail", pk=order.pk)
                    
                    # Update stock quantity
                    item.item.stock_qty -= Decimal(item.qty)
                    item.item.save(update_fields=["stock_qty"])
                    
                    # Create stock movement record
                    BarStockMovement.objects.create(
                        hotel=order.hotel,
                        item=item.item,
                        movement_type=BarStockMovement.MovementType.SALE,
                        quantity=-Decimal(item.qty),
                        balance_after=item.item.stock_qty,
                        reference=order.order_number,
                        note=f"Sale from order {order.order_number}",
                        created_by=request.user
                    )
            
            order.mark_paid()
            messages.success(
                request, 
                f"Bar order {order.order_number} marked as paid. Stock updated."
            )
    except ValidationError as e:
        messages.error(request, "; ".join(e.messages))
    except Exception as e:
        messages.error(request, f"Error processing payment: {str(e)}")
    
    return redirect("bar:order_detail", pk=order.pk)


@login_required
@require_http_methods(["POST"])
def bar_order_mark_served(request, pk):
    """Mark a bar order as served."""
    order = get_object_or_404(BarOrder, pk=pk)
    
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
def bar_order_mark_billed(request, pk):
    """Mark a bar order as billed (ready for payment)."""
    order = get_object_or_404(BarOrder, pk=pk)
    
    if order.items.count() == 0:
        messages.error(request, "Cannot bill an empty order. Please add items first.")
        return redirect("bar:order_detail", pk=order.pk)
    
    if order.status == BarOrder.Status.CANCELLED:
        messages.error(request, "Cannot bill a cancelled order.")
        return redirect("bar:order_detail", pk=order.pk)
    
    order.status = BarOrder.Status.BILLED
    order.save(update_fields=["status"])
    
    messages.success(request, f"Bar order {order.order_number} has been billed. Ready for payment.")
    return redirect("bar:order_detail", pk=order.pk)


@login_required
@require_http_methods(["POST"])
def bar_order_cancel(request, pk):
    """Cancel a bar order."""
    order = get_object_or_404(BarOrder, pk=pk)
    
    if order.status == BarOrder.Status.PAID:
        messages.error(request, "Cannot cancel a paid order. Process a refund instead.")
        return redirect("bar:order_detail", pk=order.pk)
    
    order.status = BarOrder.Status.CANCELLED
    if not order.closed_at:
        order.closed_at = timezone.now()
    order.save(update_fields=["status", "closed_at"])
    
    messages.warning(request, f"Bar order {order.order_number} has been cancelled.")
    return redirect("bar:order_list")


# ============================================================================
# Dashboard Views
# ============================================================================

class BarDashboardView(LoginRequiredMixin, TemplateView):
    """Bar management dashboard with analytics."""
    template_name = "bar/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        today = timezone.now().date()
        this_week = today - timezone.timedelta(days=7)
        this_month = today.replace(day=1)
        
        # Order statistics
        orders = BarOrder.objects.all()
        context["total_orders"] = orders.count()
        context["open_orders"] = orders.filter(status=BarOrder.Status.OPEN).count()
        context["today_orders"] = orders.filter(created_at__date=today).count()
        
        # Revenue statistics
        paid_orders = orders.filter(status=BarOrder.Status.PAID)
        
        # Calculate revenue safely
        def calculate_revenue(queryset):
            total = Decimal("0.00")
            for order in queryset:
                total += order.total
            return total
        
        context["total_revenue"] = calculate_revenue(paid_orders)
        context["today_revenue"] = calculate_revenue(paid_orders.filter(created_at__date=today))
        context["weekly_revenue"] = calculate_revenue(paid_orders.filter(created_at__date__gte=this_week))
        context["monthly_revenue"] = calculate_revenue(paid_orders.filter(created_at__date__gte=this_month))
        
        # Stock alerts
        context["low_stock_items"] = BarItem.objects.filter(
            track_stock=True, stock_qty__lte=F("reorder_level")
        ).count()
        
        context["out_of_stock_items"] = BarItem.objects.filter(
            track_stock=True, stock_qty=0
        ).count()
        
        # Recent orders
        context["recent_orders"] = BarOrder.objects.select_related(
            "hotel"
        ).prefetch_related("items").order_by("-created_at")[:10]
        
        # Top selling items
        top_items = BarOrderItem.objects.values(
            "item__name", "item__category__name"
        ).annotate(
            total_qty=Sum("qty"),
            total_revenue=Sum("unit_price") * Sum("qty")
        ).order_by("-total_qty")[:10]
        
        context["top_items"] = top_items
        
        # Recent stock movements
        context["recent_movements"] = BarStockMovement.objects.select_related(
            "item", "created_by"
        ).order_by("-created_at")[:10]
        
        return context


# ============================================================================
# API Views (AJAX)
# ============================================================================

@login_required
def bar_order_add_item_ajax(request, pk):
    """AJAX endpoint to add an item to an order."""
    if not request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"error": "AJAX required"}, status=400)
    
    order = get_object_or_404(BarOrder, pk=pk)
    
    if order.status not in [BarOrder.Status.OPEN, BarOrder.Status.SERVED]:
        return JsonResponse({"error": "Cannot add items to a closed order"}, status=400)
    
    item_id = request.POST.get("item_id")
    qty = Decimal(request.POST.get("qty", 1))
    note = request.POST.get("note", "")
    
    if not item_id:
        return JsonResponse({"error": "Item ID required"}, status=400)
    
    item = get_object_or_404(BarItem, pk=item_id)
    
    try:
        # Check stock if tracking is enabled
        if item.track_stock and qty > item.stock_qty:
            return JsonResponse({
                "error": f"Not enough stock. Available: {item.stock_qty}"
            }, status=400)
        
        # Check if item already exists in order
        existing_item = order.items.filter(item=item).first()
        if existing_item:
            existing_item.qty += qty
            existing_item.save()
            order_item = existing_item
        else:
            # Create order item
            order_item = BarOrderItem.objects.create(
                order=order,
                item=item,
                qty=qty,
                unit_price=item.selling_price,
                note=note
            )
        
        # Prepare response data
        from django.template.loader import render_to_string
        
        items_html = render_to_string("bar/partials/order_items_table.html", {
            "order": order,
            "items": order.items.all()
        }, request=request)
        
        return JsonResponse({
            "success": True,
            "items_html": items_html,
            "subtotal": float(order.subtotal),
            "total": float(order.total),
            "item_id": order_item.id,
            "item_name": item.name,
            "qty": float(qty),
            "unit_price": float(item.selling_price),
            "line_total": float(qty * item.selling_price),
        })
    except ValidationError as e:
        return JsonResponse({"error": "; ".join(e.messages)}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
def bar_order_remove_item_ajax(request, pk, item_id):
    """AJAX endpoint to remove an item from an order."""
    if not request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"error": "AJAX required"}, status=400)
    
    order = get_object_or_404(BarOrder, pk=pk)
    order_item = get_object_or_404(BarOrderItem, pk=item_id, order=order)
    
    if order.status not in [BarOrder.Status.OPEN, BarOrder.Status.SERVED]:
        return JsonResponse({"error": "Cannot remove items from a closed order"}, status=400)
    
    order_item.delete()
    
    from django.template.loader import render_to_string
    
    items_html = render_to_string("bar/partials/order_items_table.html", {
        "order": order,
        "items": order.items.all()
    }, request=request)
    
    return JsonResponse({
        "success": True,
        "items_html": items_html,
        "subtotal": float(order.subtotal),
        "total": float(order.total),
    })