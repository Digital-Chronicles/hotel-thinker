# bookings/views.py — UPDATED (AJAX payment support for check-in/check-out modals)
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from hotel_thinker.utils import get_active_hotel_for_user, require_hotel_role
from finance.models import Payment

from .models import Booking, Guest
from .forms import (
    BookingForm,
    BookingUpdateForm,
    GuestFullForm,
    GuestQuickCreateForm,
    BookingPaymentForm,
)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def is_ajax(request) -> bool:
    # Works with fetch() if you set header: X-Requested-With: XMLHttpRequest
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


# -----------------------------------------------------------------------------
# Hotel scoping
# -----------------------------------------------------------------------------
class HotelScopedQuerysetMixin:
    """
    Ensures any CBV queryset is scoped to the active hotel.
    """

    def get_hotel(self):
        return get_active_hotel_for_user(self.request.user)

    def get_queryset(self):
        return super().get_queryset().filter(hotel=self.get_hotel())


# -----------------------------------------------------------------------------
# Guests
# -----------------------------------------------------------------------------
@method_decorator(login_required, name="dispatch")
class GuestListView(HotelScopedQuerysetMixin, ListView):
    model = Guest
    template_name = "bookings/guest_list.html"
    context_object_name = "guests"
    paginate_by = 50

    def get_queryset(self):
        qs = super().get_queryset()
        q = (self.request.GET.get("q") or "").strip()
        guest_type = (self.request.GET.get("guest_type") or "").strip()
        vip = (self.request.GET.get("vip") or "").strip()

        if q:
            qs = qs.filter(
                Q(full_name__icontains=q)
                | Q(preferred_name__icontains=q)
                | Q(phone__icontains=q)
                | Q(email__icontains=q)
                | Q(id_number__icontains=q)
                | Q(company_name__icontains=q)
            )
        if guest_type:
            qs = qs.filter(guest_type=guest_type)
        if vip == "1":
            qs = qs.filter(is_vip=True)

        return qs.order_by("full_name")


@method_decorator(login_required, name="dispatch")
class GuestCreateView(CreateView):
    model = Guest
    form_class = GuestFullForm
    template_name = "bookings/guest_form.html"

    def dispatch(self, request, *args, **kwargs):
        require_hotel_role(request.user, {"admin", "front_desk_manager", "front_desk", "general_manager"})
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.hotel = get_active_hotel_for_user(self.request.user)
        form.instance.created_by = self.request.user
        messages.success(self.request, "Guest created.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("bookings:guest_list")


@method_decorator(login_required, name="dispatch")
class GuestUpdateView(HotelScopedQuerysetMixin, UpdateView):
    model = Guest
    form_class = GuestFullForm
    template_name = "bookings/guest_form.html"
    context_object_name = "guest"

    def dispatch(self, request, *args, **kwargs):
        require_hotel_role(request.user, {"admin", "front_desk_manager", "front_desk", "general_manager"})
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, "Guest updated.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("bookings:guest_list")


# -----------------------------------------------------------------------------
# Bookings
# -----------------------------------------------------------------------------
@method_decorator(login_required, name="dispatch")
class BookingListView(HotelScopedQuerysetMixin, ListView):
    model = Booking
    template_name = "bookings/booking_list.html"
    context_object_name = "bookings"
    paginate_by = 50

    def get_queryset(self):
        qs = super().get_queryset().select_related("guest", "room", "room__room_type")

        q = (self.request.GET.get("q") or "").strip()
        status = (self.request.GET.get("status") or "").strip()
        payment_status = (self.request.GET.get("payment_status") or "").strip()

        if q:
            qs = qs.filter(
                Q(booking_number__icontains=q)
                | Q(guest__full_name__icontains=q)
                | Q(guest__phone__icontains=q)
                | Q(room__number__icontains=q)
            )
        if status:
            qs = qs.filter(status=status)
        if payment_status:
            qs = qs.filter(payment_status=payment_status)

        return qs.order_by("-created_at")


@method_decorator(login_required, name="dispatch")
class BookingDetailView(HotelScopedQuerysetMixin, DetailView):
    model = Booking
    template_name = "bookings/booking_detail.html"
    context_object_name = "booking"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        booking: Booking = ctx["booking"]
        # Ensure totals are up to date for display (doesn't write to DB)
        booking.calculate_totals()
        booking.refresh_payment_status()

        ctx["payment_form"] = BookingPaymentForm()
        ctx["payment_methods"] = Payment.Method.choices

        # Helpful numbers for the modals/UI
        ctx["balance_due"] = booking.balance_due
        ctx["required_checkin_amount"] = booking.required_checkin_amount
        ctx["min_pay_for_checkin_now"] = max(booking.required_checkin_amount - booking.amount_paid, 0)

        return ctx


@method_decorator(login_required, name="dispatch")
class BookingCreateView(CreateView):
    model = Booking
    form_class = BookingForm
    template_name = "bookings/booking_form.html"

    def dispatch(self, request, *args, **kwargs):
        require_hotel_role(request.user, {"admin", "front_desk_manager", "front_desk", "general_manager"})
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["hotel"] = get_active_hotel_for_user(self.request.user)
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["guest_quick_form"] = GuestQuickCreateForm()
        return ctx

    def form_valid(self, form):
        hotel = get_active_hotel_for_user(self.request.user)
        form.instance.hotel = hotel
        form.instance.created_by = self.request.user
        messages.success(self.request, "Booking created.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("bookings:booking_list")


@method_decorator(login_required, name="dispatch")
class BookingUpdateView(HotelScopedQuerysetMixin, UpdateView):
    model = Booking
    form_class = BookingUpdateForm
    template_name = "bookings/booking_form.html"
    context_object_name = "booking"

    def dispatch(self, request, *args, **kwargs):
        require_hotel_role(request.user, {"admin", "front_desk_manager", "front_desk", "general_manager"})
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["hotel"] = get_active_hotel_for_user(self.request.user)
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Booking updated.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("bookings:booking_detail", kwargs={"pk": self.object.pk})


# -----------------------------------------------------------------------------
# Actions (Check-in / Check-out / Cancel)
# -----------------------------------------------------------------------------
@login_required
@require_POST
def booking_check_in(request, pk: int):
    require_hotel_role(request.user, {"admin", "front_desk_manager", "front_desk", "general_manager"})

    hotel = get_active_hotel_for_user(request.user)
    booking = get_object_or_404(Booking, pk=pk, hotel=hotel)

    try:
        booking.check_in_guest(request.user)  # enforces >= 50% (in model)
        messages.success(request, "Guest checked in.")
        if is_ajax(request):
            return JsonResponse({"ok": True})
    except ValidationError as e:
        messages.error(request, str(e))
        if is_ajax(request):
            return JsonResponse({"ok": False, "error": str(e)}, status=400)

    return redirect("bookings:booking_detail", pk=booking.pk)


@login_required
@require_POST
def booking_check_out(request, pk: int):
    require_hotel_role(request.user, {"admin", "front_desk_manager", "front_desk", "general_manager"})

    hotel = get_active_hotel_for_user(request.user)
    booking = get_object_or_404(Booking, pk=pk, hotel=hotel)

    try:
        booking.check_out_guest(request.user)  # enforces 100% (in model)
        messages.success(request, "Guest checked out.")
        if is_ajax(request):
            return JsonResponse({"ok": True})
    except ValidationError as e:
        messages.error(request, str(e))
        if is_ajax(request):
            return JsonResponse({"ok": False, "error": str(e)}, status=400)

    return redirect("bookings:booking_detail", pk=booking.pk)


@login_required
@require_POST
def booking_cancel(request, pk: int):
    require_hotel_role(request.user, {"admin", "front_desk_manager", "general_manager"})

    hotel = get_active_hotel_for_user(request.user)
    booking = get_object_or_404(Booking, pk=pk, hotel=hotel)

    reason = (request.POST.get("reason") or "").strip()
    fee = request.POST.get("fee") or 0

    try:
        booking.cancel(request.user, reason=reason, fee=fee)
        messages.success(request, "Booking cancelled.")
        if is_ajax(request):
            return JsonResponse({"ok": True})
    except ValidationError as e:
        messages.error(request, str(e))
        if is_ajax(request):
            return JsonResponse({"ok": False, "error": str(e)}, status=400)

    return redirect("bookings:booking_detail", pk=booking.pk)


# -----------------------------------------------------------------------------
# Receive Payment (Supports AJAX for modal flow)
# -----------------------------------------------------------------------------
@login_required
@require_POST
def booking_add_payment(request, pk: int):
    require_hotel_role(request.user, {"admin", "front_desk_manager", "front_desk", "general_manager"})

    hotel = get_active_hotel_for_user(request.user)
    booking = get_object_or_404(Booking, pk=pk, hotel=hotel)

    form = BookingPaymentForm(request.POST)
    if not form.is_valid():
        if is_ajax(request):
            return JsonResponse({"ok": False, "errors": form.errors}, status=400)
        messages.error(request, "Invalid payment details.")
        return redirect("bookings:booking_detail", pk=booking.pk)

    # Ensure invoice exists (signals may create on save)
    invoice = getattr(booking, "invoice", None)
    if invoice is None:
        # triggers booking post_save signals (safe if your signals are recursion-safe)
        booking.save()
        booking.refresh_from_db()
        invoice = getattr(booking, "invoice", None)

    if invoice is None:
        if is_ajax(request):
            return JsonResponse({"ok": False, "error": "Invoice could not be created for this booking."}, status=400)
        messages.error(request, "Invoice could not be created for this booking.")
        return redirect("bookings:booking_detail", pk=booking.pk)

    with transaction.atomic():
        invoice.record_payment(
            amount=form.cleaned_data["amount"],
            method=form.cleaned_data["method"],
            user=request.user,
            reference=form.cleaned_data.get("reference") or None,
        )

        # Sync booking snapshot (avoid heavy logic; model handles payment status well)
        booking.refresh_from_db()
        booking.amount_paid = invoice.amount_paid
        booking.refresh_payment_status()
        booking.save(update_fields=["amount_paid", "payment_status", "updated_at"])

    if is_ajax(request):
        booking.refresh_from_db()
        return JsonResponse(
            {
                "ok": True,
                "amount_paid": str(booking.amount_paid),
                "payment_status": booking.payment_status,
                "total_amount": str(booking.total_amount),
                "balance_due": str(booking.balance_due),
                "required_checkin_amount": str(getattr(booking, "required_checkin_amount", 0)),
            }
        )

    messages.success(request, "Payment recorded.")
    return redirect("bookings:booking_detail", pk=booking.pk)


# -----------------------------------------------------------------------------
# AJAX: Quick Guest Create
# -----------------------------------------------------------------------------
@login_required
@require_POST
def guest_quick_create(request):
    hotel = get_active_hotel_for_user(request.user)
    require_hotel_role(request.user, {"admin", "front_desk_manager", "front_desk", "general_manager"})

    form = GuestQuickCreateForm(request.POST, request.FILES)
    if form.is_valid():
        guest = form.save(commit=False)
        guest.hotel = hotel
        guest.created_by = request.user
        guest.save()

        label = guest.full_name
        if guest.phone:
            label = f"{guest.full_name} ({guest.phone})"

        return JsonResponse({"ok": True, "id": guest.id, "label": label})

    return JsonResponse({"ok": False, "errors": form.errors}, status=400)