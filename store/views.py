from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import F, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import (
    StoreCategoryForm,
    StoreGoodsReceiptForm,
    StoreGoodsReceiptItemFormSet,
    StoreItemForm,
    StoreItemUpdateForm,
    StorePurchaseOrderForm,
    StorePurchaseOrderItemFormSet,
    StoreSaleForm,
    StoreSupplierForm,
)
from .models import (
    StoreCategory,
    StoreGoodsReceipt,
    StoreItem,
    StorePurchaseOrder,
    StoreSale,
    StoreSupplier,
)


class StoreCategoryListView(LoginRequiredMixin, ListView):
    model = StoreCategory
    template_name = "store/category_list.html"
    context_object_name = "categories"
    paginate_by = 30

    def get_queryset(self):
        qs = StoreCategory.objects.select_related("hotel").order_by("name")
        q = self.request.GET.get("q", "").strip()
        hotel = self.request.GET.get("hotel", "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(hotel__name__icontains=q))
        if hotel:
            qs = qs.filter(hotel_id=hotel)
        return qs


class StoreCategoryCreateView(LoginRequiredMixin, CreateView):
    model = StoreCategory
    form_class = StoreCategoryForm
    template_name = "store/category_form.html"
    success_url = reverse_lazy("store:category_list")


class StoreCategoryUpdateView(LoginRequiredMixin, UpdateView):
    model = StoreCategory
    form_class = StoreCategoryForm
    template_name = "store/category_form.html"
    success_url = reverse_lazy("store:category_list")


class StoreItemListView(LoginRequiredMixin, ListView):
    model = StoreItem
    template_name = "store/item_list.html"
    context_object_name = "items"
    paginate_by = 30

    def get_queryset(self):
        qs = StoreItem.objects.select_related("hotel", "category").order_by("category__name", "name")
        q = self.request.GET.get("q", "").strip()
        hotel = self.request.GET.get("hotel", "").strip()
        category = self.request.GET.get("category", "").strip()
        low_stock = self.request.GET.get("low_stock", "").strip()

        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(sku__icontains=q) | Q(category__name__icontains=q))
        if hotel:
            qs = qs.filter(hotel_id=hotel)
        if category:
            qs = qs.filter(category_id=category)
        if low_stock:
            qs = qs.filter(stock_qty__lte=F("reorder_level"))
        return qs


class StoreItemCreateView(LoginRequiredMixin, CreateView):
    model = StoreItem
    form_class = StoreItemForm
    template_name = "store/item_form.html"
    success_url = reverse_lazy("store:item_list")


class StoreItemUpdateView(LoginRequiredMixin, UpdateView):
    model = StoreItem
    form_class = StoreItemUpdateForm
    template_name = "store/item_form.html"
    success_url = reverse_lazy("store:item_list")


class StoreSupplierListView(LoginRequiredMixin, ListView):
    model = StoreSupplier
    template_name = "store/supplier_list.html"
    context_object_name = "suppliers"
    paginate_by = 30

    def get_queryset(self):
        qs = StoreSupplier.objects.select_related("hotel").order_by("name")
        q = self.request.GET.get("q", "").strip()
        hotel = self.request.GET.get("hotel", "").strip()

        if q:
            qs = qs.filter(
                Q(name__icontains=q)
                | Q(contact_person__icontains=q)
                | Q(phone__icontains=q)
                | Q(email__icontains=q)
            )
        if hotel:
            qs = qs.filter(hotel_id=hotel)
        return qs


class StoreSupplierCreateView(LoginRequiredMixin, CreateView):
    model = StoreSupplier
    form_class = StoreSupplierForm
    template_name = "store/supplier_form.html"
    success_url = reverse_lazy("store:supplier_list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class StoreSupplierUpdateView(LoginRequiredMixin, UpdateView):
    model = StoreSupplier
    form_class = StoreSupplierForm
    template_name = "store/supplier_form.html"
    success_url = reverse_lazy("store:supplier_list")


class StorePurchaseOrderListView(LoginRequiredMixin, ListView):
    model = StorePurchaseOrder
    template_name = "store/purchase_order_list.html"
    context_object_name = "purchase_orders"
    paginate_by = 30

    def get_queryset(self):
        qs = (
            StorePurchaseOrder.objects.select_related("hotel", "supplier", "created_by", "approved_by")
            .prefetch_related("items__item")
            .order_by("-created_at")
        )
        q = self.request.GET.get("q", "").strip()
        hotel = self.request.GET.get("hotel", "").strip()
        status_ = self.request.GET.get("status", "").strip()

        if q:
            qs = qs.filter(Q(po_number__icontains=q) | Q(supplier__name__icontains=q))
        if hotel:
            qs = qs.filter(hotel_id=hotel)
        if status_:
            qs = qs.filter(status=status_)
        return qs


class StorePurchaseOrderDetailView(LoginRequiredMixin, DetailView):
    model = StorePurchaseOrder
    template_name = "store/purchase_order_detail.html"
    context_object_name = "purchase_order"

    def get_queryset(self):
        return (
            StorePurchaseOrder.objects.select_related("hotel", "supplier", "created_by", "approved_by")
            .prefetch_related("items__item", "receipts__items__purchase_order_item__item")
        )


class StorePurchaseOrderCreateView(LoginRequiredMixin, CreateView):
    model = StorePurchaseOrder
    form_class = StorePurchaseOrderForm
    template_name = "store/purchase_order_form.html"

    def get_success_url(self):
        return reverse_lazy("store:purchase_order_detail", kwargs={"pk": self.object.pk})

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        hotel_id = self.request.POST.get("hotel") or self.request.GET.get("hotel")
        if hotel_id:
            kwargs["hotel"] = hotel_id
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hotel_id = self.request.POST.get("hotel") or self.request.GET.get("hotel")
        if self.request.POST:
            context["formset"] = StorePurchaseOrderItemFormSet(self.request.POST)
            if hotel_id:
                for form in context["formset"].forms:
                    form.fields["item"].queryset = form.fields["item"].queryset.filter(hotel_id=hotel_id, is_active=True)
        else:
            context["formset"] = StorePurchaseOrderItemFormSet()
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context["formset"]
        form.instance.created_by = self.request.user

        if not formset.is_valid():
            return self.form_invalid(form)

        with transaction.atomic():
            self.object = form.save()
            formset.instance = self.object
            formset.save()

        messages.success(self.request, f"Purchase order {self.object.po_number} created successfully.")
        return redirect(self.get_success_url())

    def form_invalid(self, form):
        messages.error(self.request, "Please correct the errors below.")
        return super().form_invalid(form)


class StorePurchaseOrderUpdateView(LoginRequiredMixin, UpdateView):
    model = StorePurchaseOrder
    form_class = StorePurchaseOrderForm
    template_name = "store/purchase_order_form.html"

    def get_success_url(self):
        return reverse_lazy("store:purchase_order_detail", kwargs={"pk": self.object.pk})

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["hotel"] = self.object.hotel_id
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context["formset"] = StorePurchaseOrderItemFormSet(self.request.POST, instance=self.object)
            for form in context["formset"].forms:
                form.fields["item"].queryset = form.fields["item"].queryset.filter(
                    hotel=self.object.hotel,
                    is_active=True,
                )
        else:
            context["formset"] = StorePurchaseOrderItemFormSet(instance=self.object)
            for form in context["formset"].forms:
                form.fields["item"].queryset = form.fields["item"].queryset.filter(
                    hotel=self.object.hotel,
                    is_active=True,
                )
        return context

    def form_valid(self, form):
        if self.object.status in [StorePurchaseOrder.Status.RECEIVED, StorePurchaseOrder.Status.CANCELLED]:
            messages.error(self.request, "This purchase order can no longer be edited.")
            return redirect(self.get_success_url())

        context = self.get_context_data()
        formset = context["formset"]

        if not formset.is_valid():
            return self.form_invalid(form)

        with transaction.atomic():
            self.object = form.save()
            formset.instance = self.object
            formset.save()

        self.object.refresh_status()
        messages.success(self.request, f"Purchase order {self.object.po_number} updated successfully.")
        return redirect(self.get_success_url())

    def form_invalid(self, form):
        messages.error(self.request, "Please correct the errors below.")
        return super().form_invalid(form)


class StoreGoodsReceiptListView(LoginRequiredMixin, ListView):
    model = StoreGoodsReceipt
    template_name = "store/goods_receipt_list.html"
    context_object_name = "goods_receipts"
    paginate_by = 30

    def get_queryset(self):
        qs = (
            StoreGoodsReceipt.objects.select_related("hotel", "purchase_order", "received_by")
            .prefetch_related("items__purchase_order_item__item")
            .order_by("-created_at")
        )
        q = self.request.GET.get("q", "").strip()
        hotel = self.request.GET.get("hotel", "").strip()

        if q:
            qs = qs.filter(
                Q(receipt_number__icontains=q)
                | Q(purchase_order__po_number__icontains=q)
                | Q(supplier_invoice_number__icontains=q)
            )
        if hotel:
            qs = qs.filter(hotel_id=hotel)
        return qs


class StoreGoodsReceiptDetailView(LoginRequiredMixin, DetailView):
    model = StoreGoodsReceipt
    template_name = "store/goods_receipt_detail.html"
    context_object_name = "goods_receipt"

    def get_queryset(self):
        return (
            StoreGoodsReceipt.objects.select_related("hotel", "purchase_order", "received_by")
            .prefetch_related("items__purchase_order_item__item")
        )


class StoreGoodsReceiptCreateView(LoginRequiredMixin, CreateView):
    model = StoreGoodsReceipt
    form_class = StoreGoodsReceiptForm
    template_name = "store/goods_receipt_form.html"

    def get_success_url(self):
        return reverse_lazy("store:goods_receipt_detail", kwargs={"pk": self.object.pk})

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        hotel_id = self.request.POST.get("hotel") or self.request.GET.get("hotel")
        if hotel_id:
            kwargs["hotel"] = hotel_id
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        purchase_order_id = self.request.POST.get("purchase_order") or self.request.GET.get("purchase_order")
        if self.request.POST:
            context["formset"] = StoreGoodsReceiptItemFormSet(self.request.POST)
            if purchase_order_id:
                for form in context["formset"].forms:
                    form.fields["purchase_order_item"].queryset = form.fields["purchase_order_item"].queryset.filter(
                        purchase_order_id=purchase_order_id
                    ).select_related("item")
        else:
            context["formset"] = StoreGoodsReceiptItemFormSet()
        return context

    def form_valid(self, form):
        purchase_order = form.cleaned_data["purchase_order"]
        if purchase_order.status not in [
            StorePurchaseOrder.Status.APPROVED,
            StorePurchaseOrder.Status.PARTIALLY_RECEIVED,
        ]:
            form.add_error("purchase_order", "Only approved or partially received purchase orders can receive stock.")
            return self.form_invalid(form)

        context = self.get_context_data()
        formset = context["formset"]
        if not formset.is_valid():
            return self.form_invalid(form)

        form.instance.received_by = self.request.user

        with transaction.atomic():
            self.object = form.save()
            formset.instance = self.object
            formset.save()

        messages.success(self.request, f"Goods receipt {self.object.receipt_number} created successfully.")
        return redirect(self.get_success_url())

    def form_invalid(self, form):
        messages.error(self.request, "Please correct the errors below.")
        return super().form_invalid(form)


class StoreSaleListView(LoginRequiredMixin, ListView):
    model = StoreSale
    template_name = "store/sale_list.html"
    context_object_name = "sales"
    paginate_by = 30

    def get_queryset(self):
        qs = (
            StoreSale.objects.select_related("hotel", "created_by")
            .prefetch_related("items__item")
            .order_by("-created_at")
        )
        q = self.request.GET.get("q", "").strip()
        status_ = self.request.GET.get("status", "").strip()
        hotel = self.request.GET.get("hotel", "").strip()

        if q:
            qs = qs.filter(
                Q(sale_number__icontains=q)
                | Q(customer_name__icontains=q)
                | Q(customer_phone__icontains=q)
            )
        if status_:
            qs = qs.filter(status=status_)
        if hotel:
            qs = qs.filter(hotel_id=hotel)
        return qs


class StoreSaleCreateView(LoginRequiredMixin, CreateView):
    model = StoreSale
    form_class = StoreSaleForm
    template_name = "store/sale_form.html"
    success_url = reverse_lazy("store:sale_list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class StoreSaleUpdateView(LoginRequiredMixin, UpdateView):
    model = StoreSale
    form_class = StoreSaleForm
    template_name = "store/sale_form.html"

    def get_success_url(self):
        return reverse_lazy("store:sale_detail", kwargs={"pk": self.object.pk})


class StoreSaleDetailView(LoginRequiredMixin, DetailView):
    model = StoreSale
    template_name = "store/sale_detail.html"
    context_object_name = "sale"

    def get_queryset(self):
        return (
            StoreSale.objects.select_related("hotel", "created_by")
            .prefetch_related("items__item")
            .order_by("-created_at")
        )


@login_required
def store_purchase_order_approve(request, pk):
    purchase_order = get_object_or_404(StorePurchaseOrder, pk=pk)

    if purchase_order.status == StorePurchaseOrder.Status.CANCELLED:
        messages.error(request, "Cancelled purchase order cannot be approved.")
        return redirect("store:purchase_order_detail", pk=purchase_order.pk)

    if purchase_order.status == StorePurchaseOrder.Status.RECEIVED:
        messages.error(request, "Fully received purchase order cannot be approved again.")
        return redirect("store:purchase_order_detail", pk=purchase_order.pk)

    purchase_order.status = StorePurchaseOrder.Status.APPROVED
    purchase_order.approved_by = request.user
    purchase_order.approved_at = timezone.now()
    purchase_order.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])

    messages.success(request, f"Purchase order {purchase_order.po_number} approved successfully.")
    return redirect("store:purchase_order_detail", pk=purchase_order.pk)


@login_required
def store_sale_mark_paid(request, pk):
    sale = get_object_or_404(StoreSale, pk=pk)

    if sale.status == StoreSale.Status.CANCELLED:
        messages.error(request, "Cancelled sale cannot be marked as paid.")
        return redirect("store:sale_detail", pk=sale.pk)

    sale.status = StoreSale.Status.PAID
    if not sale.closed_at:
        sale.closed_at = timezone.now()
    sale.save(update_fields=["status", "closed_at"])

    messages.success(request, f"Store sale {sale.sale_number} marked as paid.")
    return redirect("store:sale_detail", pk=sale.pk)


@login_required
def store_sale_cancel(request, pk):
    sale = get_object_or_404(StoreSale, pk=pk)

    if sale.status == StoreSale.Status.PAID:
        messages.error(request, "Paid sale cannot be cancelled directly.")
        return redirect("store:sale_detail", pk=sale.pk)

    sale.status = StoreSale.Status.CANCELLED
    if not sale.closed_at:
        sale.closed_at = timezone.now()
    sale.save(update_fields=["status", "closed_at"])

    messages.warning(request, f"Store sale {sale.sale_number} cancelled.")
    return redirect("store:sale_detail", pk=sale.pk)