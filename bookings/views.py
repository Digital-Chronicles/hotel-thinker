from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Prefetch, Q, Sum
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from finance.models import Payment
from hotel_thinker.utils import get_active_hotel_for_user, require_hotel_role

from .forms import (
    AdditionalChargeForm,
    BookingForm,
    BookingPaymentForm,
    BookingReportForm,
    BookingUpdateForm,
    GuestFullForm,
    GuestQuickCreateForm,
)
from .models import AdditionalCharge, Booking, BookingAuditLog, Guest


ZERO = Decimal("0")


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def is_ajax(request) -> bool:
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def get_hotel_and_booking(request, pk: int):
    hotel = get_active_hotel_for_user(request.user)
    booking = get_object_or_404(Booking, pk=pk, hotel=hotel)
    return hotel, booking


# -----------------------------------------------------------------------------
# Mixins
# -----------------------------------------------------------------------------
class HotelScopedQuerysetMixin:
    """Scope queryset objects to the user's active hotel."""

    def get_hotel(self):
        return get_active_hotel_for_user(self.request.user)

    def get_queryset(self):
        qs = super().get_queryset()
        hotel = self.get_hotel()
        if hotel and hasattr(qs, "filter"):
            return qs.filter(hotel=hotel)
        return qs


# -----------------------------------------------------------------------------
# Dashboard
# -----------------------------------------------------------------------------
@method_decorator(login_required, name="dispatch")
class BookingDashboardView(TemplateView):
    template_name = "bookings/dashboard.html"

    def dispatch(self, request, *args, **kwargs):
        require_hotel_role(
            request.user,
            {"admin", "front_desk_manager", "front_desk", "general_manager"},
        )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hotel = get_active_hotel_for_user(self.request.user)
        today = timezone.localdate()
        tomorrow = today + timedelta(days=1)
        week_later = today + timedelta(days=7)

        bookings_qs = Booking.objects.filter(hotel=hotel)

        ctx["total_bookings"] = bookings_qs.count()
        ctx["confirmed_bookings"] = bookings_qs.filter(
            status=Booking.Status.CONFIRMED
        ).count()
        ctx["checked_in_bookings"] = bookings_qs.filter(
            status=Booking.Status.CHECKED_IN
        ).count()
        ctx["checked_out_bookings"] = bookings_qs.filter(
            status=Booking.Status.CHECKED_OUT
        ).count()
        ctx["cancelled_bookings"] = bookings_qs.filter(
            status=Booking.Status.CANCELLED
        ).count()

        ctx["today_arrivals"] = bookings_qs.filter(
            status__in=[Booking.Status.CONFIRMED, Booking.Status.RESERVED],
            check_in=today,
        ).count()

        ctx["today_departures"] = bookings_qs.filter(
            status=Booking.Status.CHECKED_IN,
            check_out=today,
        ).count()

        ctx["upcoming_arrivals"] = bookings_qs.filter(
            status__in=[Booking.Status.CONFIRMED, Booking.Status.RESERVED],
            check_in__gte=tomorrow,
            check_in__lte=week_later,
        ).count()

        completed_payments = Payment.objects.filter(
            hotel=hotel,
            status=Payment.PaymentStatus.COMPLETED,
        )

        ctx["today_revenue"] = (
            completed_payments.filter(received_at__date=today).aggregate(
                total=Sum("amount")
            )["total"]
            or ZERO
        )

        ctx["monthly_revenue"] = (
            completed_payments.filter(
                received_at__date__month=today.month,
                received_at__date__year=today.year,
            ).aggregate(total=Sum("amount"))["total"]
            or ZERO
        )

        ctx["recent_bookings"] = bookings_qs.select_related(
            "guest",
            "room",
            "room__room_type",
        ).order_by("-created_at")[:10]

        ctx["recent_guests"] = Guest.objects.filter(hotel=hotel).order_by("-created_at")[
            :10
        ]

        from rooms.models import Room

        total_rooms = Room.objects.filter(hotel=hotel, is_active=True).count()
        occupied_rooms = bookings_qs.filter(
            status=Booking.Status.CHECKED_IN
        ).values("room").distinct().count()

        ctx["occupancy_rate"] = (
            round((occupied_rooms / total_rooms) * 100, 1) if total_rooms > 0 else 0
        )

        return ctx


# -----------------------------------------------------------------------------
# Guest views
# -----------------------------------------------------------------------------
@method_decorator(login_required, name="dispatch")
class GuestListView(HotelScopedQuerysetMixin, ListView):
    model = Guest
    template_name = "bookings/guest_list.html"
    context_object_name = "guests"
    paginate_by = 20

    def get_queryset(self):
        # Important: no slicing inside Prefetch queryset.
        qs = super().get_queryset().prefetch_related(
            Prefetch(
                "bookings",
                queryset=Booking.objects.select_related("room", "room__room_type").order_by(
                    "-check_in"
                ),
            )
        )

        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(full_name__icontains=q)
                | Q(preferred_name__icontains=q)
                | Q(phone__icontains=q)
                | Q(email__icontains=q)
                | Q(id_number__icontains=q)
                | Q(company_name__icontains=q)
            )

        guest_type = self.request.GET.get("guest_type", "").strip()
        if guest_type:
            qs = qs.filter(guest_type=guest_type)

        vip = self.request.GET.get("vip", "")
        if vip == "1":
            qs = qs.filter(is_vip=True)

        blacklisted = self.request.GET.get("blacklisted", "")
        if blacklisted == "1":
            qs = qs.filter(is_blacklisted=True)

        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hotel = self.get_hotel()

        ctx["total_guests"] = Guest.objects.filter(hotel=hotel).count()
        ctx["vip_guests"] = Guest.objects.filter(hotel=hotel, is_vip=True).count()
        ctx["blacklisted_guests"] = Guest.objects.filter(
            hotel=hotel, is_blacklisted=True
        ).count()
        ctx["guest_types"] = Guest.GuestType.choices
        return ctx


@method_decorator(login_required, name="dispatch")
class GuestDetailView(HotelScopedQuerysetMixin, DetailView):
    model = Guest
    template_name = "bookings/guest_detail.html"
    context_object_name = "guest"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        guest = self.object

        ctx["booking_history"] = (
            Booking.objects.filter(guest=guest)
            .select_related("room", "room__room_type")
            .order_by("-check_in")[:10]
        )

        ctx["total_bookings"] = Booking.objects.filter(guest=guest).count()
        ctx["total_spent"] = (
            Booking.objects.filter(
                guest=guest,
                payment_status=Booking.PaymentStatus.PAID,
            ).aggregate(total=Sum("total_amount"))["total"]
            or ZERO
        )

        ctx["recent_activity"] = (
            BookingAuditLog.objects.filter(booking__guest=guest)
            .select_related("booking", "user")
            .order_by("-created_at")[:10]
        )

        return ctx


@method_decorator(login_required, name="dispatch")
class GuestCreateView(CreateView):
    model = Guest
    form_class = GuestFullForm
    template_name = "bookings/guest_form.html"

    def dispatch(self, request, *args, **kwargs):
        require_hotel_role(
            request.user,
            {"admin", "front_desk_manager", "front_desk", "general_manager"},
        )
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.hotel = get_active_hotel_for_user(self.request.user)
        form.instance.created_by = self.request.user
        messages.success(
            self.request,
            f"Guest '{form.instance.full_name}' created successfully.",
        )
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("bookings:guest_detail", kwargs={"pk": self.object.pk})


@method_decorator(login_required, name="dispatch")
class GuestUpdateView(HotelScopedQuerysetMixin, UpdateView):
    model = Guest
    form_class = GuestFullForm
    template_name = "bookings/guest_form.html"
    context_object_name = "guest"

    def dispatch(self, request, *args, **kwargs):
        require_hotel_role(
            request.user,
            {"admin", "front_desk_manager", "front_desk", "general_manager"},
        )
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(
            self.request,
            f"Guest '{form.instance.full_name}' updated successfully.",
        )
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("bookings:guest_detail", kwargs={"pk": self.object.pk})


@login_required
@require_http_methods(["POST"])
def guest_toggle_blacklist(request, pk: int):
    hotel = get_active_hotel_for_user(request.user)
    require_hotel_role(request.user, {"admin", "general_manager"})

    guest = get_object_or_404(Guest, pk=pk, hotel=hotel)

    guest.is_blacklisted = not guest.is_blacklisted
    if guest.is_blacklisted:
        guest.blacklisted_at = timezone.now()
        guest.blacklisted_by = request.user
        guest.blacklist_reason = request.POST.get("reason", "").strip()
        messages.warning(request, f"Guest '{guest.full_name}' has been blacklisted.")
    else:
        guest.blacklisted_at = None
        guest.blacklisted_by = None
        guest.blacklist_reason = ""
        messages.success(
            request,
            f"Guest '{guest.full_name}' removed from blacklist.",
        )

    guest.save()
    return redirect("bookings:guest_detail", pk=guest.pk)


@login_required
@require_POST
def guest_quick_create(request):
    hotel = get_active_hotel_for_user(request.user)
    require_hotel_role(
        request.user,
        {"admin", "front_desk_manager", "front_desk", "general_manager"},
    )

    form = GuestQuickCreateForm(request.POST, request.FILES)
    if form.is_valid():
        guest = form.save(commit=False)
        guest.hotel = hotel
        guest.created_by = request.user
        guest.save()

        label = guest.full_name
        if guest.phone:
            label = f"{guest.full_name} ({guest.phone})"

        return JsonResponse(
            {
                "ok": True,
                "id": guest.id,
                "label": label,
                "full_name": guest.full_name,
                "phone": guest.phone,
                "email": guest.email or "",
            }
        )

    return JsonResponse({"ok": False, "errors": form.errors}, status=400)


# -----------------------------------------------------------------------------
# Booking views
# -----------------------------------------------------------------------------
@method_decorator(login_required, name="dispatch")
class BookingListView(HotelScopedQuerysetMixin, ListView):
    model = Booking
    template_name = "bookings/booking_list.html"
    context_object_name = "bookings"
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().select_related("guest", "room", "room__room_type")

        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(booking_number__icontains=q)
                | Q(guest__full_name__icontains=q)
                | Q(guest__phone__icontains=q)
                | Q(room__number__icontains=q)
            )

        status = self.request.GET.get("status", "").strip()
        if status:
            qs = qs.filter(status=status)

        payment_status = self.request.GET.get("payment_status", "").strip()
        if payment_status:
            qs = qs.filter(payment_status=payment_status)

        date_from = self.request.GET.get("date_from", "").strip()
        if date_from:
            qs = qs.filter(check_in__gte=date_from)

        date_to = self.request.GET.get("date_to", "").strip()
        if date_to:
            qs = qs.filter(check_out__lte=date_to)

        return qs.order_by("-check_in", "-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hotel = self.get_hotel()
        today = timezone.localdate()

        bookings_qs = Booking.objects.filter(hotel=hotel)

        ctx["total_bookings"] = bookings_qs.count()
        ctx["confirmed_count"] = bookings_qs.filter(
            status=Booking.Status.CONFIRMED
        ).count()
        ctx["checked_in_count"] = bookings_qs.filter(
            status=Booking.Status.CHECKED_IN
        ).count()
        ctx["checked_out_count"] = bookings_qs.filter(
            status=Booking.Status.CHECKED_OUT
        ).count()
        ctx["cancelled_count"] = bookings_qs.filter(
            status=Booking.Status.CANCELLED
        ).count()
        ctx["today_arrivals"] = bookings_qs.filter(
            status__in=[Booking.Status.CONFIRMED, Booking.Status.RESERVED],
            check_in=today,
        ).count()

        ctx["status_choices"] = Booking.Status.choices
        ctx["payment_status_choices"] = Booking.PaymentStatus.choices
        return ctx


@method_decorator(login_required, name="dispatch")
class BookingDetailView(HotelScopedQuerysetMixin, DetailView):
    model = Booking
    template_name = "bookings/booking_detail.html"
    context_object_name = "booking"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        booking = ctx["booking"]

        booking.calculate_totals()
        booking.refresh_payment_status()

        ctx["payment_form"] = BookingPaymentForm()
        ctx["charge_form"] = AdditionalChargeForm()
        ctx["payment_methods"] = Payment.Method.choices

        ctx["balance_due"] = booking.balance_due
        ctx["required_checkin_amount"] = booking.required_checkin_amount
        ctx["min_pay_for_checkin"] = max(
            booking.required_checkin_amount - booking.amount_paid,
            ZERO,
        )

        ctx["additional_charges"] = booking.additional_charges.all().order_by(
            "-created_at"
        )
        ctx["charges_total"] = booking.additional_charges_total

        if hasattr(booking, "invoice"):
            ctx["payments"] = booking.invoice.payments.all().order_by("-received_at")
        else:
            ctx["payments"] = []

        ctx["audit_logs"] = booking.audit_logs.all().order_by("-created_at")[:20]

        ctx["can_check_in"] = booking.status in [
            Booking.Status.RESERVED,
            Booking.Status.CONFIRMED,
        ]
        ctx["can_check_out"] = booking.status == Booking.Status.CHECKED_IN
        ctx["can_cancel"] = booking.status not in [
            Booking.Status.CHECKED_OUT,
            Booking.Status.CANCELLED,
        ]

        return ctx


@method_decorator(login_required, name="dispatch")
class BookingCreateView(CreateView):
    model = Booking
    form_class = BookingForm
    template_name = "bookings/booking_form.html"

    def dispatch(self, request, *args, **kwargs):
        require_hotel_role(
            request.user,
            {"admin", "front_desk_manager", "front_desk", "general_manager"},
        )
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["hotel"] = get_active_hotel_for_user(self.request.user)
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["guest_quick_form"] = GuestQuickCreateForm()
        ctx["is_edit"] = False
        return ctx

    def form_valid(self, form):
        hotel = get_active_hotel_for_user(self.request.user)
        form.instance.hotel = hotel
        form.instance.created_by = self.request.user

        if form.instance.room:
            form.instance.set_nightly_rate_from_room()

        response = super().form_valid(form)
        messages.success(
            self.request,
            f"Booking {self.object.booking_number} created successfully.",
        )
        return response

    def get_success_url(self):
        return reverse("bookings:booking_detail", kwargs={"pk": self.object.pk})


@method_decorator(login_required, name="dispatch")
class BookingUpdateView(HotelScopedQuerysetMixin, UpdateView):
    model = Booking
    form_class = BookingUpdateForm
    template_name = "bookings/booking_form.html"
    context_object_name = "booking"

    def dispatch(self, request, *args, **kwargs):
        require_hotel_role(
            request.user,
            {"admin", "front_desk_manager", "front_desk", "general_manager"},
        )
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["hotel"] = get_active_hotel_for_user(self.request.user)
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["is_edit"] = True
        return ctx

    def form_valid(self, form):
        if form.instance.room:
            form.instance.set_nightly_rate_from_room()

        messages.success(
            self.request,
            f"Booking {form.instance.booking_number} updated successfully.",
        )
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("bookings:booking_detail", kwargs={"pk": self.object.pk})


# -----------------------------------------------------------------------------
# Booking actions
# -----------------------------------------------------------------------------
@login_required
@require_POST
def booking_check_in(request, pk: int):
    require_hotel_role(
        request.user,
        {"admin", "front_desk_manager", "front_desk", "general_manager"},
    )
    _, booking = get_hotel_and_booking(request, pk)

    try:
        booking.check_in_guest(request.user)
        messages.success(request, f"Guest {booking.guest.full_name} checked in successfully.")

        if is_ajax(request):
            return JsonResponse(
                {
                    "ok": True,
                    "status": booking.status,
                    "status_display": booking.get_status_display(),
                    "message": "Guest checked in successfully",
                }
            )
    except ValidationError as e:
        error_msg = ", ".join(e.messages) if hasattr(e, "messages") else str(e)
        messages.error(request, error_msg)
        if is_ajax(request):
            return JsonResponse({"ok": False, "error": error_msg}, status=400)

    return redirect("bookings:booking_detail", pk=booking.pk)


@login_required
@require_POST
def booking_check_out(request, pk: int):
    require_hotel_role(
        request.user,
        {"admin", "front_desk_manager", "front_desk", "general_manager"},
    )
    _, booking = get_hotel_and_booking(request, pk)

    try:
        booking.check_out_guest(request.user)
        messages.success(request, f"Guest {booking.guest.full_name} checked out successfully.")

        if is_ajax(request):
            return JsonResponse(
                {
                    "ok": True,
                    "status": booking.status,
                    "status_display": booking.get_status_display(),
                    "message": "Guest checked out successfully",
                }
            )
    except ValidationError as e:
        error_msg = ", ".join(e.messages) if hasattr(e, "messages") else str(e)
        messages.error(request, error_msg)
        if is_ajax(request):
            return JsonResponse({"ok": False, "error": error_msg}, status=400)

    return redirect("bookings:booking_detail", pk=booking.pk)


@login_required
@require_POST
def booking_cancel(request, pk: int):
    require_hotel_role(
        request.user,
        {"admin", "front_desk_manager", "general_manager"},
    )
    _, booking = get_hotel_and_booking(request, pk)

    reason = request.POST.get("reason", "").strip()
    fee_raw = request.POST.get("fee", "0")

    try:
        fee = Decimal(fee_raw or "0")
    except Exception:
        fee = ZERO

    try:
        booking.cancel(request.user, reason=reason, fee=fee)
        messages.success(request, f"Booking {booking.booking_number} cancelled.")

        if is_ajax(request):
            return JsonResponse(
                {
                    "ok": True,
                    "status": booking.status,
                    "status_display": booking.get_status_display(),
                    "message": "Booking cancelled successfully",
                }
            )
    except ValidationError as e:
        error_msg = ", ".join(e.messages) if hasattr(e, "messages") else str(e)
        messages.error(request, error_msg)
        if is_ajax(request):
            return JsonResponse({"ok": False, "error": error_msg}, status=400)

    return redirect("bookings:booking_detail", pk=booking.pk)


# -----------------------------------------------------------------------------
# Payments
# -----------------------------------------------------------------------------
@login_required
@require_POST
def booking_add_payment(request, pk: int):
    require_hotel_role(
        request.user,
        {"admin", "front_desk_manager", "front_desk", "general_manager"},
    )
    _, booking = get_hotel_and_booking(request, pk)

    form = BookingPaymentForm(request.POST)
    if not form.is_valid():
        if is_ajax(request):
            return JsonResponse({"ok": False, "errors": form.errors}, status=400)
        messages.error(request, "Invalid payment details.")
        return redirect("bookings:booking_detail", pk=booking.pk)

    invoice = getattr(booking, "invoice", None)
    if invoice is None:
        booking.save()
        booking.refresh_from_db()
        invoice = getattr(booking, "invoice", None)

    if invoice is None:
        error_msg = "Invoice could not be created for this booking."
        if is_ajax(request):
            return JsonResponse({"ok": False, "error": error_msg}, status=400)
        messages.error(request, error_msg)
        return redirect("bookings:booking_detail", pk=booking.pk)

    with transaction.atomic():
        invoice.record_payment(
            amount=form.cleaned_data["amount"],
            method=form.cleaned_data["method"],
            user=request.user,
            reference=form.cleaned_data.get("reference") or None,
        )

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
                "payment_status_display": booking.get_payment_status_display(),
                "total_amount": str(booking.total_amount),
                "balance_due": str(booking.balance_due),
                "required_checkin_amount": str(booking.required_checkin_amount),
            }
        )

    messages.success(
        request,
        f"Payment of {form.cleaned_data['amount']} recorded successfully.",
    )
    return redirect("bookings:booking_detail", pk=booking.pk)


# -----------------------------------------------------------------------------
# Charges
# -----------------------------------------------------------------------------
@login_required
@require_POST
def booking_add_charge(request, pk: int):
    require_hotel_role(
        request.user,
        {"admin", "front_desk_manager", "front_desk", "general_manager"},
    )
    _, booking = get_hotel_and_booking(request, pk)

    form = AdditionalChargeForm(request.POST)
    if form.is_valid():
        charge = form.save(commit=False)
        charge.booking = booking
        charge.created_by = request.user
        charge.save()

        booking.refresh_from_db()

        messages.success(request, f"Charge '{charge.description}' added successfully.")

        if is_ajax(request):
            return JsonResponse(
                {
                    "ok": True,
                    "charge_id": charge.id,
                    "description": charge.description,
                    "total": str(charge.total),
                    "new_total": str(booking.total_amount),
                    "balance_due": str(booking.balance_due),
                }
            )
    else:
        if is_ajax(request):
            return JsonResponse({"ok": False, "errors": form.errors}, status=400)
        messages.error(request, "Invalid charge details.")

    return redirect("bookings:booking_detail", pk=booking.pk)


@login_required
@require_POST
def booking_delete_charge(request, pk: int):
    require_hotel_role(
        request.user,
        {"admin", "front_desk_manager", "general_manager"},
    )

    charge = get_object_or_404(AdditionalCharge, pk=pk)
    booking = charge.booking
    hotel = get_active_hotel_for_user(request.user)

    if booking.hotel_id != hotel.id:
        raise Http404()

    charge.delete()
    messages.success(request, "Charge removed successfully.")
    return redirect("bookings:booking_detail", pk=booking.pk)


# -----------------------------------------------------------------------------
# AJAX / APIs
# -----------------------------------------------------------------------------
@login_required
@require_GET
def check_room_availability(request):
    hotel = get_active_hotel_for_user(request.user)

    room_id = request.GET.get("room_id")
    check_in = request.GET.get("check_in")
    check_out = request.GET.get("check_out")
    exclude_booking = request.GET.get("exclude_booking")

    if not all([room_id, check_in, check_out]):
        return JsonResponse({"available": False, "error": "Missing parameters"}, status=400)

    from rooms.models import Room

    try:
        room = Room.objects.get(pk=room_id, hotel=hotel)
    except Room.DoesNotExist:
        return JsonResponse({"available": False, "error": "Room not found"}, status=404)

    overlapping = Booking.objects.filter(
        room=room,
        status__in=[
            Booking.Status.RESERVED,
            Booking.Status.CONFIRMED,
            Booking.Status.CHECKED_IN,
        ],
        check_in__lt=check_out,
        check_out__gt=check_in,
    )

    if exclude_booking:
        overlapping = overlapping.exclude(pk=exclude_booking)

    available = not overlapping.exists()

    return JsonResponse(
        {
            "available": available,
            "room_id": room.id,
            "room_number": room.number,
            "message": "Room is available"
            if available
            else "Room is already booked for these dates",
        }
    )


@login_required
@require_GET
def booking_stats_api(request):
    hotel = get_active_hotel_for_user(request.user)
    today = timezone.localdate()
    last_30_days = today - timedelta(days=30)

    daily_stats_qs = (
        Booking.objects.filter(
            hotel=hotel,
            created_at__date__gte=last_30_days,
        )
        .extra(select={"date": "date(created_at)"})
        .values("date")
        .annotate(count=Count("id"), revenue=Sum("total_amount"))
        .order_by("date")
    )

    status_stats_qs = Booking.objects.filter(hotel=hotel).values("status").annotate(
        count=Count("id")
    )

    daily_stats = [
        {
            "date": item["date"].isoformat() if item["date"] else None,
            "count": item["count"],
            "revenue": str(item["revenue"] or 0),
        }
        for item in daily_stats_qs
    ]

    status_stats = [
        {
            "status": item["status"],
            "status_label": dict(Booking.Status.choices).get(item["status"], item["status"]),
            "count": item["count"],
        }
        for item in status_stats_qs
    ]

    return JsonResponse(
        {
            "daily_stats": daily_stats,
            "status_stats": status_stats,
        }
    )


# -----------------------------------------------------------------------------
# Reports
# -----------------------------------------------------------------------------
@login_required
def booking_report(request):
    hotel = get_active_hotel_for_user(request.user)
    require_hotel_role(request.user, {"admin", "front_desk_manager", "general_manager"})

    form = BookingReportForm(request.GET or None)
    bookings = Booking.objects.filter(hotel=hotel).select_related(
        "guest",
        "room",
        "room__room_type",
    )

    if form.is_valid():
        date_from = form.cleaned_data.get("date_from")
        date_to = form.cleaned_data.get("date_to")
        status = form.cleaned_data.get("status")
        payment_status = form.cleaned_data.get("payment_status")

        if date_from:
            bookings = bookings.filter(check_in__gte=date_from)
        if date_to:
            bookings = bookings.filter(check_out__lte=date_to)
        if status:
            bookings = bookings.filter(status=status)
        if payment_status:
            bookings = bookings.filter(payment_status=payment_status)

    total_revenue = bookings.aggregate(total=Sum("total_amount"))["total"] or ZERO
    total_paid = bookings.aggregate(total=Sum("amount_paid"))["total"] or ZERO
    total_balance = total_revenue - total_paid

    context = {
        "form": form,
        "bookings": bookings.order_by("-check_in"),
        "total_bookings": bookings.count(),
        "total_revenue": total_revenue,
        "total_paid": total_paid,
        "total_balance": total_balance,
        "status_choices": Booking.Status.choices,
        "payment_status_choices": Booking.PaymentStatus.choices,
    }

    return render(request, "bookings/booking_report.html", context)