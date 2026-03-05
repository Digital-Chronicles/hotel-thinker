from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import ListView, CreateView, DetailView, TemplateView, UpdateView

from hotel_thinker.utils import get_active_hotel_for_user, require_hotel_role

from .models import (
    DiningArea, Table, MenuCategory, MenuItem,
    RestaurantOrder, RestaurantOrderItem,
)
from .forms import (
    DiningAreaForm, TableForm, MenuCategoryForm, MenuItemForm,
    RestaurantOrderForm, RestaurantOrderItemForm,
    OrderStatusForm, PaymentForm,
)


def _hotel(request):
    return get_active_hotel_for_user(request.user, request=request)


def _guard_staff(request):
    require_hotel_role(request.user, {"admin", "restaurant_manager", "server", "general_manager"})


def _guard_manager(request):
    require_hotel_role(request.user, {"admin", "restaurant_manager", "general_manager"})


def _order_or_404(request, pk: int):
    return get_object_or_404(RestaurantOrder, pk=pk, hotel=_hotel(request))


class HotelScopedQuerysetMixin:
    def get_hotel(self):
        return get_active_hotel_for_user(self.request.user, request=self.request)

    def get_queryset(self):
        return super().get_queryset().filter(hotel=self.get_hotel())


@method_decorator(login_required, name="dispatch")
class OrderListView(HotelScopedQuerysetMixin, ListView):
    model = RestaurantOrder
    template_name = "restaurant/order_list.html"
    context_object_name = "orders"
    paginate_by = 50

    def dispatch(self, request, *args, **kwargs):
        _guard_staff(request)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset().select_related("table", "table__area").order_by("-created_at")
        q = (self.request.GET.get("q") or "").strip()
        status = (self.request.GET.get("status") or "").strip()

        if q:
            qs = qs.filter(
                Q(order_number__icontains=q) |
                Q(customer_name__icontains=q) |
                Q(table__number__icontains=q)
            )
        if status:
            qs = qs.filter(status=status)
        return qs


@method_decorator(login_required, name="dispatch")
class OrderDetailView(HotelScopedQuerysetMixin, DetailView):
    model = RestaurantOrder
    template_name = "restaurant/order_detail.html"
    context_object_name = "order"

    def dispatch(self, request, *args, **kwargs):
        _guard_staff(request)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return (
            super().get_queryset()
            .select_related("table", "table__area")
            .prefetch_related("items", "items__item")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hotel = self.get_hotel()
        order = self.object
        ctx["hotel"] = hotel
        ctx["items"] = order.items.select_related("item").order_by("-id")
        ctx["item_form"] = RestaurantOrderItemForm(hotel=hotel)
        ctx["status_form"] = OrderStatusForm(initial={"status": order.status})
        ctx["payment_form"] = PaymentForm(order=order)
        ctx["can_edit"] = order.status not in {RestaurantOrder.Status.PAID, RestaurantOrder.Status.CANCELLED}
        return ctx


@method_decorator(login_required, name="dispatch")
class OrderCreateView(CreateView):
    model = RestaurantOrder
    form_class = RestaurantOrderForm
    template_name = "restaurant/order_form.html"

    def dispatch(self, request, *args, **kwargs):
        _guard_staff(request)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["hotel"] = _hotel(self.request)
        return kwargs

    def form_valid(self, form):
        form.instance.hotel = _hotel(self.request)
        form.instance.created_by = self.request.user
        messages.success(self.request, "Order created.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("restaurant:order_detail", kwargs={"pk": self.object.pk})


@login_required
@require_GET
def menu_items_api(request):
    hotel = _hotel(request)
    q = (request.GET.get("q") or "").strip()

    qs = MenuItem.objects.filter(hotel=hotel, is_active=True).select_related("category").order_by("name")
    if q:
        qs = qs.filter(name__icontains=q)

    data = [
        {"id": mi.id, "name": mi.name, "price": str(mi.price), "category": mi.category.name if mi.category_id else ""}
        for mi in qs[:50]
    ]
    return JsonResponse({"results": data})


@login_required
@require_POST
def order_add_item_ajax(request, pk: int):
    _guard_staff(request)
    hotel = _hotel(request)
    order = get_object_or_404(RestaurantOrder, pk=pk, hotel=hotel)

    if order.status in {RestaurantOrder.Status.PAID, RestaurantOrder.Status.CANCELLED}:
        return JsonResponse({"ok": False, "errors": {"__all__": ["Order is closed."]}}, status=400)

    form = RestaurantOrderItemForm(request.POST, hotel=hotel)
    if not form.is_valid():
        return JsonResponse({"ok": False, "errors": form.errors}, status=400)

    with transaction.atomic():
        oi = form.save(commit=False)
        oi.order = order
        oi.unit_price = oi.item.price  # lock price
        oi.save()

        if order.status == RestaurantOrder.Status.OPEN:
            order.status = RestaurantOrder.Status.KITCHEN
            order.save(update_fields=["status"])

    items = order.items.select_related("item").order_by("-id")
    html = render_to_string("restaurant/partials/order_items_table.html", {"order": order, "items": items}, request=request)

    return JsonResponse({
        "ok": True,
        "items_html": html,
        "subtotal": str(order.subtotal),
        "discount": str(order.discount or 0),
        "tax": str(order.tax or 0),
        "total": str(order.total),
        "status": order.status,
    })


@login_required
@require_POST
def order_remove_item_ajax(request, pk: int, item_id: int):
    _guard_staff(request)
    hotel = _hotel(request)
    order = get_object_or_404(RestaurantOrder, pk=pk, hotel=hotel)

    if order.status in {RestaurantOrder.Status.PAID, RestaurantOrder.Status.CANCELLED}:
        return JsonResponse({"ok": False, "errors": {"__all__": ["Order is closed."]}}, status=400)

    oi = get_object_or_404(RestaurantOrderItem, pk=item_id, order=order)
    oi.delete()

    items = order.items.select_related("item").order_by("-id")
    html = render_to_string("restaurant/partials/order_items_table.html", {"order": order, "items": items}, request=request)

    return JsonResponse({
        "ok": True,
        "items_html": html,
        "subtotal": str(order.subtotal),
        "discount": str(order.discount or 0),
        "tax": str(order.tax or 0),
        "total": str(order.total),
    })


@login_required
@require_POST
def order_update_item_qty_ajax(request, pk: int, item_id: int):
    _guard_staff(request)
    hotel = _hotel(request)
    order = get_object_or_404(RestaurantOrder, pk=pk, hotel=hotel)

    if order.status in {RestaurantOrder.Status.PAID, RestaurantOrder.Status.CANCELLED}:
        return JsonResponse({"ok": False, "errors": {"__all__": ["Order is closed."]}}, status=400)

    oi = get_object_or_404(RestaurantOrderItem, pk=item_id, order=order)

    try:
        qty = int(request.POST.get("qty") or "0")
    except ValueError:
        qty = 0

    if qty <= 0:
        return JsonResponse({"ok": False, "errors": {"qty": ["Qty must be at least 1."]}}, status=400)

    oi.qty = qty
    oi.save(update_fields=["qty"])

    items = order.items.select_related("item").order_by("-id")
    html = render_to_string("restaurant/partials/order_items_table.html", {"order": order, "items": items}, request=request)

    return JsonResponse({
        "ok": True,
        "items_html": html,
        "subtotal": str(order.subtotal),
        "discount": str(order.discount or 0),
        "tax": str(order.tax or 0),
        "total": str(order.total),
    })


@login_required
@require_POST
def order_set_status(request, pk: int):
    _guard_staff(request)
    order = _order_or_404(request, pk)

    form = OrderStatusForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Invalid status.")
        return redirect("restaurant:order_detail", pk=pk)

    new_status = form.cleaned_data["status"]
    try:
        order.set_status(new_status, user=request.user)
        messages.success(request, f"Order updated to {order.get_status_display()}.")
    except ValidationError as e:
        messages.error(request, ", ".join(getattr(e, "messages", [str(e)])))

    return redirect("restaurant:order_detail", pk=pk)


@login_required
@require_POST
def order_bill(request, pk: int):
    _guard_staff(request)
    order = _order_or_404(request, pk)

    try:
        inv = order.bill(user=request.user)
        messages.success(request, f"Order billed. Invoice: {inv.invoice_number}")
    except ValidationError as e:
        messages.error(request, ", ".join(getattr(e, "messages", [str(e)])))

    return redirect("restaurant:order_detail", pk=pk)


@login_required
def order_pay(request, pk: int):
    _guard_staff(request)
    order = _order_or_404(request, pk)

    if request.method == "POST":
        form = PaymentForm(request.POST, order=order)
        if form.is_valid():
            try:
                order.pay(
                    amount=form.cleaned_data["amount"],
                    method=form.cleaned_data["method"],
                    user=request.user,
                    reference=form.cleaned_data.get("reference") or None,
                )
                messages.success(request, "Payment recorded.")
                return redirect("restaurant:receipt_print", pk=pk)
            except ValidationError as e:
                messages.error(request, ", ".join(getattr(e, "messages", [str(e)])))
        else:
            messages.error(request, "Please correct the form errors.")
    else:
        form = PaymentForm(order=order)

    return render(request, "restaurant/payment_form.html", {"order": order, "form": form})


@login_required
def receipt_print(request, pk: int):
    _guard_staff(request)
    order = _order_or_404(request, pk)

    invoice = getattr(order, "invoice", None)
    payments = invoice.payments.select_related("received_by").order_by("-received_at") if invoice else []
    items = order.items.select_related("item").order_by("id")

    return render(request, "restaurant/receipt_print.html", {
        "hotel": _hotel(request),
        "order": order,
        "invoice": invoice,
        "payments": payments,
        "items": items,
    })


# ---------------- Manager dashboard + CRUD ----------------

@method_decorator(login_required, name="dispatch")
class RestaurantManageDashboardView(TemplateView):
    template_name = "restaurant/manage/dashboard.html"

    def dispatch(self, request, *args, **kwargs):
        _guard_manager(request)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hotel = _hotel(self.request)

        ctx["hotel"] = hotel
        ctx["areas_count"] = DiningArea.objects.filter(hotel=hotel).count()
        ctx["tables_count"] = Table.objects.filter(hotel=hotel).count()
        ctx["categories_count"] = MenuCategory.objects.filter(hotel=hotel).count()
        ctx["items_count"] = MenuItem.objects.filter(hotel=hotel).count()

        ctx["area_form"] = DiningAreaForm()
        ctx["table_form"] = TableForm(hotel=hotel)
        ctx["category_form"] = MenuCategoryForm()
        ctx["item_form"] = MenuItemForm(hotel=hotel)

        ctx["recent_orders"] = (
            RestaurantOrder.objects.filter(hotel=hotel)
            .select_related("table", "table__area")
            .order_by("-created_at")[:10]
        )
        return ctx

    def post(self, request, *args, **kwargs):
        hotel = _hotel(request)
        action = (request.POST.get("action") or "").strip()

        if action == "add_area":
            form = DiningAreaForm(request.POST)
            if form.is_valid():
                obj = form.save(commit=False)
                obj.hotel = hotel
                obj.save()
                messages.success(request, "Dining area added.")
            else:
                messages.error(request, "Failed to add dining area.")

        elif action == "add_table":
            form = TableForm(request.POST, hotel=hotel)
            if form.is_valid():
                obj = form.save(commit=False)
                obj.hotel = hotel
                obj.save()
                messages.success(request, "Table added.")
            else:
                messages.error(request, "Failed to add table.")

        elif action == "add_category":
            form = MenuCategoryForm(request.POST)
            if form.is_valid():
                obj = form.save(commit=False)
                obj.hotel = hotel
                obj.save()
                messages.success(request, "Menu category added.")
            else:
                messages.error(request, "Failed to add category.")

        elif action == "add_item":
            form = MenuItemForm(request.POST, hotel=hotel)
            if form.is_valid():
                obj = form.save(commit=False)
                obj.hotel = hotel
                obj.save()
                messages.success(request, "Menu item added.")
            else:
                messages.error(request, "Failed to add menu item.")
        else:
            messages.error(request, "Invalid action.")

        return redirect("restaurant:manage_dashboard")


@method_decorator(login_required, name="dispatch")
class DiningAreaListView(ListView):
    model = DiningArea
    template_name = "restaurant/manage/area_list.html"
    context_object_name = "areas"
    paginate_by = 50

    def dispatch(self, request, *args, **kwargs):
        _guard_manager(request)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return DiningArea.objects.filter(hotel=_hotel(self.request)).order_by("name")


@method_decorator(login_required, name="dispatch")
class DiningAreaCreateView(CreateView):
    model = DiningArea
    form_class = DiningAreaForm
    template_name = "restaurant/manage/area_form.html"

    def dispatch(self, request, *args, **kwargs):
        _guard_manager(request)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.hotel = _hotel(self.request)
        messages.success(self.request, "Dining area created.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("restaurant:area_list")


@method_decorator(login_required, name="dispatch")
class DiningAreaUpdateView(UpdateView):
    model = DiningArea
    form_class = DiningAreaForm
    template_name = "restaurant/manage/area_form.html"
    context_object_name = "area"

    def dispatch(self, request, *args, **kwargs):
        _guard_manager(request)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return DiningArea.objects.filter(hotel=_hotel(self.request))

    def form_valid(self, form):
        messages.success(self.request, "Dining area updated.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("restaurant:area_list")


@method_decorator(login_required, name="dispatch")
class TableListView(ListView):
    model = Table
    template_name = "restaurant/manage/table_list.html"
    context_object_name = "tables"
    paginate_by = 50

    def dispatch(self, request, *args, **kwargs):
        _guard_manager(request)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return Table.objects.filter(hotel=_hotel(self.request)).select_related("area").order_by("area__name", "number")


@method_decorator(login_required, name="dispatch")
class TableCreateView(CreateView):
    model = Table
    form_class = TableForm
    template_name = "restaurant/manage/table_form.html"

    def dispatch(self, request, *args, **kwargs):
        _guard_manager(request)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["hotel"] = _hotel(self.request)
        return kwargs

    def form_valid(self, form):
        form.instance.hotel = _hotel(self.request)
        messages.success(self.request, "Table created.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("restaurant:table_list")


@method_decorator(login_required, name="dispatch")
class TableUpdateView(UpdateView):
    model = Table
    form_class = TableForm
    template_name = "restaurant/manage/table_form.html"
    context_object_name = "table"

    def dispatch(self, request, *args, **kwargs):
        _guard_manager(request)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["hotel"] = _hotel(self.request)
        return kwargs

    def get_queryset(self):
        return Table.objects.filter(hotel=_hotel(self.request)).select_related("area")

    def form_valid(self, form):
        messages.success(self.request, "Table updated.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("restaurant:table_list")


@method_decorator(login_required, name="dispatch")
class MenuCategoryListView(ListView):
    model = MenuCategory
    template_name = "restaurant/manage/category_list.html"
    context_object_name = "categories"
    paginate_by = 50

    def dispatch(self, request, *args, **kwargs):
        _guard_manager(request)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return MenuCategory.objects.filter(hotel=_hotel(self.request)).order_by("sort_order", "name")


@method_decorator(login_required, name="dispatch")
class MenuCategoryCreateView(CreateView):
    model = MenuCategory
    form_class = MenuCategoryForm
    template_name = "restaurant/manage/category_form.html"

    def dispatch(self, request, *args, **kwargs):
        _guard_manager(request)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.hotel = _hotel(self.request)
        messages.success(self.request, "Category created.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("restaurant:category_list")


@method_decorator(login_required, name="dispatch")
class MenuCategoryUpdateView(UpdateView):
    model = MenuCategory
    form_class = MenuCategoryForm
    template_name = "restaurant/manage/category_form.html"
    context_object_name = "category"

    def dispatch(self, request, *args, **kwargs):
        _guard_manager(request)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return MenuCategory.objects.filter(hotel=_hotel(self.request))

    def form_valid(self, form):
        messages.success(self.request, "Category updated.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("restaurant:category_list")


@method_decorator(login_required, name="dispatch")
class MenuItemListView(ListView):
    model = MenuItem
    template_name = "restaurant/manage/item_list.html"
    context_object_name = "items"
    paginate_by = 50

    def dispatch(self, request, *args, **kwargs):
        _guard_manager(request)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        hotel = _hotel(self.request)
        q = (self.request.GET.get("q") or "").strip()
        cat = (self.request.GET.get("category") or "").strip()

        qs = MenuItem.objects.filter(hotel=hotel).select_related("category").order_by("category__name", "name")
        if q:
            qs = qs.filter(name__icontains=q)
        if cat:
            qs = qs.filter(category_id=cat)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["categories"] = MenuCategory.objects.filter(hotel=_hotel(self.request)).order_by("name")
        return ctx


@method_decorator(login_required, name="dispatch")
class MenuItemCreateView(CreateView):
    model = MenuItem
    form_class = MenuItemForm
    template_name = "restaurant/manage/item_form.html"

    def dispatch(self, request, *args, **kwargs):
        _guard_manager(request)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["hotel"] = _hotel(self.request)
        return kwargs

    def form_valid(self, form):
        form.instance.hotel = _hotel(self.request)
        messages.success(self.request, "Menu item created.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("restaurant:item_list")


@method_decorator(login_required, name="dispatch")
class MenuItemUpdateView(UpdateView):
    model = MenuItem
    form_class = MenuItemForm
    template_name = "restaurant/manage/item_form.html"
    context_object_name = "item"

    def dispatch(self, request, *args, **kwargs):
        _guard_manager(request)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["hotel"] = _hotel(self.request)
        return kwargs

    def get_queryset(self):
        return MenuItem.objects.filter(hotel=_hotel(self.request)).select_related("category")

    def form_valid(self, form):
        messages.success(self.request, "Menu item updated.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("restaurant:item_list")