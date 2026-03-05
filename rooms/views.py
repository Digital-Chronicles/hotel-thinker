# rooms/views.py
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView
from django.contrib import messages
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator

from hotel_thinker.utils import get_active_hotel_for_user, require_hotel_role
from .models import Room, RoomType
from .forms import RoomTypeForm, RoomForm
from hotel_thinker.utils import get_active_hotel_for_user, require_hotel_role
from .models import RoomType, Room
from .forms import RoomTypeForm, RoomForm


class HotelScopedQuerysetMixin:
    def get_hotel(self):
        return get_active_hotel_for_user(self.request.user)

    def get_queryset(self):
        return super().get_queryset().filter(hotel=self.get_hotel())


@method_decorator(login_required, name="dispatch")
class RoomTypeListView(HotelScopedQuerysetMixin, ListView):
    model = RoomType
    template_name = "rooms/roomtype_list.html"
    context_object_name = "roomtypes"
    paginate_by = 30

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
        return qs.order_by("name")


@method_decorator(login_required, name="dispatch")
class RoomTypeCreateView(CreateView):
    model = RoomType
    form_class = RoomTypeForm
    template_name = "rooms/roomtype_form.html"

    def dispatch(self, request, *args, **kwargs):
        require_hotel_role(request.user, {"admin", "general_manager", "operations_manager"})
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.hotel = get_active_hotel_for_user(self.request.user)
        messages.success(self.request, "Room type created.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("rooms:roomtype_list")


@method_decorator(login_required, name="dispatch")
class RoomTypeUpdateView(HotelScopedQuerysetMixin, UpdateView):
    model = RoomType
    form_class = RoomTypeForm
    template_name = "rooms/roomtype_form.html"

    def dispatch(self, request, *args, **kwargs):
        require_hotel_role(request.user, {"admin", "general_manager", "operations_manager"})
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, "Room type updated.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("rooms:roomtype_list")


@method_decorator(login_required, name="dispatch")
class RoomListView(HotelScopedQuerysetMixin, ListView):
    model = Room
    template_name = "rooms/room_list.html"
    context_object_name = "rooms"
    paginate_by = 50

    def get_queryset(self):
        qs = super().get_queryset().select_related("room_type")
        q = self.request.GET.get("q")
        status = self.request.GET.get("status")
        rtype = self.request.GET.get("room_type")

        if q:
            qs = qs.filter(Q(number__icontains=q) | Q(floor__icontains=q) | Q(room_type__name__icontains=q))
        if status:
            qs = qs.filter(status=status)
        if rtype:
            qs = qs.filter(room_type_id=rtype)

        return qs.order_by("number")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hotel = get_active_hotel_for_user(self.request.user)
        ctx["statuses"] = Room.Status.choices
        ctx["room_types"] = RoomType.objects.filter(hotel=hotel).order_by("name")
        return ctx


@method_decorator(login_required, name="dispatch")
class RoomDetailView(HotelScopedQuerysetMixin, DetailView):
    model = Room
    template_name = "rooms/room_detail.html"
    context_object_name = "room"


@method_decorator(login_required, name="dispatch")
class RoomCreateView(CreateView):
    model = Room
    form_class = RoomForm
    template_name = "rooms/room_form.html"

    def dispatch(self, request, *args, **kwargs):
        require_hotel_role(request.user, {"admin", "general_manager", "operations_manager"})
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["hotel"] = get_active_hotel_for_user(self.request.user)
        return kwargs

    def form_valid(self, form):
        form.instance.hotel = get_active_hotel_for_user(self.request.user)
        messages.success(self.request, "Room created.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("rooms:room_list")


@method_decorator(login_required, name="dispatch")
class RoomUpdateView(HotelScopedQuerysetMixin, UpdateView):
    model = Room
    form_class = RoomForm
    template_name = "rooms/room_form.html"

    def dispatch(self, request, *args, **kwargs):
        require_hotel_role(request.user, {"admin", "general_manager", "operations_manager"})
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["hotel"] = get_active_hotel_for_user(self.request.user)
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Room updated.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("rooms:room_detail", kwargs={"pk": self.object.pk})


@login_required
def room_set_status(request, pk: int):
    if request.method != "POST":
        raise Http404()

    hotel = get_active_hotel_for_user(request.user)
    room = get_object_or_404(Room, pk=pk, hotel=hotel)

    new_status = request.POST.get("status")
    valid = {c[0] for c in Room.Status.choices}
    if new_status not in valid:
        messages.error(request, "Invalid status.")
        return redirect("rooms:room_detail", pk=room.pk)

    room.status = new_status
    room.save(update_fields=["status"])
    messages.success(request, "Room status updated.")
    return redirect("rooms:room_detail", pk=room.pk)


@method_decorator(login_required, name="dispatch")
class RoomsManageDashboardView(TemplateView):
    template_name = "rooms/manage/dashboard.html"

    def dispatch(self, request, *args, **kwargs):
        # allow roles that should manage rooms
        require_hotel_role(request.user, {"admin", "general_manager", "operations_manager", "front_desk", "housekeeping"})
        return super().dispatch(request, *args, **kwargs)

    def get_hotel(self):
        return get_active_hotel_for_user(self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hotel = self.get_hotel()

        qs = Room.objects.filter(hotel=hotel)
        ctx["hotel"] = hotel

        # Stats
        ctx["total_rooms"] = qs.count()
        ctx["available_rooms"] = qs.filter(status=Room.Status.AVAILABLE, is_active=True).count()
        ctx["occupied_rooms"] = qs.filter(status=Room.Status.OCCUPIED, is_active=True).count()
        ctx["maintenance_rooms"] = qs.filter(status=Room.Status.MAINTENANCE, is_active=True).count()
        ctx["cleaning_rooms"] = qs.filter(status=Room.Status.CLEANING, is_active=True).count()

        # Modal forms
        ctx["roomtype_form"] = RoomTypeForm()
        ctx["room_form"] = RoomForm(hotel=hotel)

        # Recent rooms
        ctx["recent_rooms"] = (
            qs.select_related("room_type")
            .order_by("-id")[:10]
        )

        return ctx

    def post(self, request, *args, **kwargs):
        hotel = self.get_hotel()
        action = (request.POST.get("action") or "").strip()

        if action == "add_roomtype":
            form = RoomTypeForm(request.POST)
            if form.is_valid():
                obj = form.save(commit=False)
                obj.hotel = hotel
                obj.save()
                messages.success(request, "Room type added.")
            else:
                messages.error(request, "Failed to add room type. Check the fields.")

        elif action == "add_room":
            form = RoomForm(request.POST, hotel=hotel)
            if form.is_valid():
                obj = form.save(commit=False)
                obj.hotel = hotel
                obj.save()
                messages.success(request, "Room added.")
            else:
                messages.error(request, "Failed to add room. Check the fields.")

        else:
            messages.error(request, "Invalid action.")

        return redirect("rooms:manage_dashboard")