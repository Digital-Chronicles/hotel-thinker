from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from .models import (
    ServiceAttendance,
    ServiceBooking,
    ServiceCategory,
    ServicePayment,
    ServiceResource,
    ServiceUnit,
)


class ServiceDashboardView(TemplateView):
    template_name = "services/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()

        bookings_today = ServiceBooking.objects.filter(scheduled_start__date=today)
        context["bookings_today"] = bookings_today.count()
        context["active_today"] = bookings_today.filter(
            status__in=[ServiceBooking.Status.RESERVED, ServiceBooking.Status.IN_PROGRESS]
        ).count()
        context["completed_today"] = bookings_today.filter(status=ServiceBooking.Status.COMPLETED).count()
        context["payments_today"] = ServicePayment.objects.filter(paid_at__date=today).aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0.00")
        context["upcoming_bookings"] = (
            ServiceBooking.objects.select_related("hotel", "service", "resource")
            .filter(scheduled_start__date__gte=today)
            .order_by("scheduled_start")[:10]
        )
        return context


class ServiceCategoryListView(ListView):
    model = ServiceCategory
    template_name = "services/category_list.html"
    context_object_name = "categories"

    def get_queryset(self):
        qs = ServiceCategory.objects.select_related("hotel").order_by("sort_order", "name")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(hotel__name__icontains=q))
        return qs


class ServiceCategoryCreateView(CreateView):
    model = ServiceCategory
    fields = ["hotel", "name", "description", "is_active", "sort_order"]
    template_name = "services/category_form.html"
    success_url = reverse_lazy("services:category_list")


class ServiceCategoryUpdateView(UpdateView):
    model = ServiceCategory
    fields = ["hotel", "name", "description", "is_active", "sort_order"]
    template_name = "services/category_form.html"
    success_url = reverse_lazy("services:category_list")


class ServiceUnitListView(ListView):
    model = ServiceUnit
    template_name = "services/service_list.html"
    context_object_name = "services"
    paginate_by = 30

    def get_queryset(self):
        qs = ServiceUnit.objects.select_related("hotel", "category").order_by("category__name", "name")
        q = self.request.GET.get("q", "").strip()
        category = self.request.GET.get("category", "").strip()
        hotel = self.request.GET.get("hotel", "").strip()

        if q:
            qs = qs.filter(
                Q(name__icontains=q)
                | Q(code__icontains=q)
                | Q(location__icontains=q)
                | Q(category__name__icontains=q)
            )
        if category:
            qs = qs.filter(category_id=category)
        if hotel:
            qs = qs.filter(hotel_id=hotel)
        return qs


class ServiceUnitCreateView(CreateView):
    model = ServiceUnit
    fields = [
        "hotel",
        "category",
        "name",
        "code",
        "service_type",
        "pricing_mode",
        "base_price",
        "default_duration_minutes",
        "max_capacity",
        "requires_schedule",
        "allows_walk_in",
        "allow_post_to_room",
        "requires_attendant",
        "location",
        "description",
        "is_active",
    ]
    template_name = "services/service_form.html"
    success_url = reverse_lazy("services:service_list")


class ServiceUnitUpdateView(UpdateView):
    model = ServiceUnit
    fields = [
        "hotel",
        "category",
        "name",
        "code",
        "service_type",
        "pricing_mode",
        "base_price",
        "default_duration_minutes",
        "max_capacity",
        "requires_schedule",
        "allows_walk_in",
        "allow_post_to_room",
        "requires_attendant",
        "location",
        "description",
        "is_active",
    ]
    template_name = "services/service_form.html"
    success_url = reverse_lazy("services:service_list")


class ServiceResourceListView(ListView):
    model = ServiceResource
    template_name = "services/resource_list.html"
    context_object_name = "resources"

    def get_queryset(self):
        qs = ServiceResource.objects.select_related("hotel", "service").order_by("service__name", "name")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(service__name__icontains=q) | Q(hotel__name__icontains=q))
        return qs


class ServiceResourceCreateView(CreateView):
    model = ServiceResource
    fields = ["hotel", "service", "name", "capacity", "is_active", "notes"]
    template_name = "services/resource_form.html"
    success_url = reverse_lazy("services:resource_list")


class ServiceResourceUpdateView(UpdateView):
    model = ServiceResource
    fields = ["hotel", "service", "name", "capacity", "is_active", "notes"]
    template_name = "services/resource_form.html"
    success_url = reverse_lazy("services:resource_list")


class ServiceBookingListView(ListView):
    model = ServiceBooking
    template_name = "services/booking_list.html"
    context_object_name = "bookings"
    paginate_by = 30

    def get_queryset(self):
        qs = (
            ServiceBooking.objects.select_related(
                "hotel", "booking", "service", "resource", "created_by", "assigned_to"
            )
            .prefetch_related("extras", "payments")
            .order_by("-scheduled_start", "-id")
        )

        q = self.request.GET.get("q", "").strip()
        status_ = self.request.GET.get("status", "").strip()
        payment_status = self.request.GET.get("payment_status", "").strip()
        service = self.request.GET.get("service", "").strip()
        hotel = self.request.GET.get("hotel", "").strip()

        if q:
            qs = qs.filter(
                Q(reference__icontains=q)
                | Q(customer_name__icontains=q)
                | Q(customer_phone__icontains=q)
                | Q(service__name__icontains=q)
            )
        if status_:
            qs = qs.filter(status=status_)
        if payment_status:
            qs = qs.filter(payment_status=payment_status)
        if service:
            qs = qs.filter(service_id=service)
        if hotel:
            qs = qs.filter(hotel_id=hotel)

        return qs


class ServiceBookingCreateView(CreateView):
    model = ServiceBooking
    fields = [
        "hotel",
        "booking",
        "service",
        "resource",
        "customer_name",
        "customer_phone",
        "attendants",
        "scheduled_start",
        "scheduled_end",
        "pricing_mode",
        "unit_price",
        "quantity",
        "discount",
        "tax",
        "deposit_paid",
        "post_to_room",
        "notes",
        "status",
        "assigned_to",
    ]
    template_name = "services/booking_form.html"
    success_url = reverse_lazy("services:booking_list")

    def form_valid(self, form):
        if self.request.user.is_authenticated:
            form.instance.created_by = self.request.user
        return super().form_valid(form)


class ServiceBookingUpdateView(UpdateView):
    model = ServiceBooking
    fields = [
        "hotel",
        "booking",
        "service",
        "resource",
        "customer_name",
        "customer_phone",
        "attendants",
        "scheduled_start",
        "scheduled_end",
        "pricing_mode",
        "unit_price",
        "quantity",
        "discount",
        "tax",
        "deposit_paid",
        "post_to_room",
        "notes",
        "status",
        "assigned_to",
    ]
    template_name = "services/booking_form.html"

    def get_success_url(self):
        return reverse_lazy("services:booking_detail", kwargs={"pk": self.object.pk})


class ServiceBookingDetailView(DetailView):
    model = ServiceBooking
    template_name = "services/booking_detail.html"
    context_object_name = "service_booking"

    def get_queryset(self):
        return (
            ServiceBooking.objects.select_related(
                "hotel", "booking", "service", "resource", "created_by", "assigned_to"
            )
            .prefetch_related("extras", "payments")
            .order_by("-scheduled_start", "-id")
        )


class ServicePaymentCreateView(CreateView):
    model = ServicePayment
    fields = ["amount", "method", "reference", "notes"]
    template_name = "services/payment_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.service_booking = get_object_or_404(ServiceBooking, pk=self.kwargs["booking_pk"])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.service_booking = self.service_booking
        if self.request.user.is_authenticated:
            form.instance.received_by = self.request.user
        messages.success(self.request, "Service payment recorded successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("services:booking_detail", kwargs={"pk": self.service_booking.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["service_booking"] = self.service_booking
        return context


@login_required
def service_booking_check_in(request, pk):
    booking = get_object_or_404(ServiceBooking, pk=pk)
    attendance, _ = ServiceAttendance.objects.get_or_create(service_booking=booking)
    attendance.checked_in_at = timezone.now()
    attendance.checked_in_by = request.user
    attendance.save()
    messages.success(request, f"{booking.reference} checked in.")
    return redirect("services:booking_detail", pk=booking.pk)


@login_required
def service_booking_check_out(request, pk):
    booking = get_object_or_404(ServiceBooking, pk=pk)
    attendance, _ = ServiceAttendance.objects.get_or_create(service_booking=booking)
    attendance.checked_out_at = timezone.now()
    attendance.checked_out_by = request.user
    attendance.save()
    messages.success(request, f"{booking.reference} checked out.")
    return redirect("services:booking_detail", pk=booking.pk)


@login_required
def service_booking_cancel(request, pk):
    booking = get_object_or_404(ServiceBooking, pk=pk)
    booking.status = ServiceBooking.Status.CANCELLED
    booking.save(update_fields=["status", "updated_at"])
    messages.warning(request, f"{booking.reference} cancelled.")
    return redirect("services:booking_detail", pk=booking.pk)


@login_required
def service_booking_complete(request, pk):
    booking = get_object_or_404(ServiceBooking, pk=pk)
    booking.status = ServiceBooking.Status.COMPLETED
    booking.save(update_fields=["status", "updated_at"])
    messages.success(request, f"{booking.reference} marked as completed.")
    return redirect("services:booking_detail", pk=booking.pk)