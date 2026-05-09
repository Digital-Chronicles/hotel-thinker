# rooms/views.py

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import (
    Q, Count, Sum, F, Value, DecimalField, Case, When, 
    IntegerField, Avg, Prefetch, Exists, OuterRef, Subquery,
    PositiveIntegerField
)
from django.db.models.functions import Coalesce
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import ListView, CreateView, UpdateView, DetailView, TemplateView, DeleteView
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST
from django.core.files.images import get_image_dimensions

from dateutil.relativedelta import relativedelta

from hotel_thinker.utils import get_active_hotel_for_user, require_hotel_role
from .models import (
    Room, RoomType, RoomImage, RoomImageGallery,
    RoomAsset, RoomLiability, AssetCategory, AssetDepreciationSchedule, LiabilityPayment
)
from .forms import (
    RoomTypeForm, RoomForm, RoomImageForm, RoomImageGalleryForm, 
    BulkRoomImageUploadForm, RoomImageFilterForm,
    AssetCategoryForm, RoomAssetForm, RoomLiabilityForm, 
    LiabilityPaymentForm, AssetFilterForm, LiabilityFilterForm,
)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_hotel(request):
    """Get current active hotel for the user"""
    return get_active_hotel_for_user(request.user)


def require_manager_role(request):
    """Require manager level access"""
    require_hotel_role(request.user, {"admin", "general_manager", "operations_manager"})


def require_staff_role(request):
    """Require staff level access"""
    require_hotel_role(request.user, {"admin", "general_manager", "operations_manager", "front_desk", "housekeeping"})


# ============================================================
# MIXINS
# ============================================================

class HotelScopedQuerysetMixin:
    """Mixin to filter querysets by active hotel"""
    
    def get_hotel(self):
        return get_active_hotel_for_user(self.request.user)

    def get_queryset(self):
        qs = super().get_queryset()
        hotel = self.get_hotel()
        if hotel and hasattr(qs, 'filter'):
            return qs.filter(hotel=hotel)
        return qs


class ManagerRequiredMixin:
    """Mixin to require manager role"""
    
    def dispatch(self, request, *args, **kwargs):
        require_manager_role(request)
        return super().dispatch(request, *args, **kwargs)


class StaffRequiredMixin:
    """Mixin to require staff role"""
    
    def dispatch(self, request, *args, **kwargs):
        require_staff_role(request)
        return super().dispatch(request, *args, **kwargs)


# ============================================================
# ROOM TYPE VIEWS
# ============================================================

@method_decorator(login_required, name="dispatch")
class RoomTypeListView(HotelScopedQuerysetMixin, ListView):
    model = RoomType
    template_name = "rooms/roomtype_list.html"
    context_object_name = "roomtypes"
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().annotate(
            room_count=Count("rooms", filter=Q(rooms__is_active=True)),
            primary_image=Subquery(
                RoomImage.objects.filter(
                    room_type=OuterRef('pk'),
                    is_primary=True,
                    is_active=True
                ).values('image')[:1]
            )
        )
        
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
        
        return qs.order_by("name")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hotel = self.get_hotel()
        
        ctx["total_rooms"] = Room.objects.filter(hotel=hotel).count()
        
        avg_price_data = RoomType.objects.filter(hotel=hotel).aggregate(avg=Avg("base_price"))
        ctx["avg_price"] = avg_price_data["avg"] or 0
        
        ctx["total_rooms_by_type"] = Room.objects.filter(
            hotel=hotel, is_active=True
        ).values("room_type__name").annotate(count=Count("id"))
        
        ctx["room_types_for_filter"] = RoomType.objects.filter(hotel=hotel).order_by("name")
        
        return ctx


@method_decorator(login_required, name="dispatch")
class RoomTypeCreateView(ManagerRequiredMixin, CreateView):
    model = RoomType
    form_class = RoomTypeForm
    template_name = "rooms/roomtype_form.html"

    def form_valid(self, form):
        form.instance.hotel = get_hotel(self.request)
        messages.success(self.request, f"Room type '{form.instance.name}' created successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("rooms:roomtype_list")


@method_decorator(login_required, name="dispatch")
class RoomTypeUpdateView(HotelScopedQuerysetMixin, ManagerRequiredMixin, UpdateView):
    model = RoomType
    form_class = RoomTypeForm
    template_name = "rooms/roomtype_form.html"
    context_object_name = "roomtype"

    def form_valid(self, form):
        messages.success(self.request, f"Room type '{form.instance.name}' updated successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("rooms:roomtype_list")


@login_required
@require_http_methods(["POST"])
def roomtype_toggle_active(request, pk):
    """Toggle room type active status"""
    hotel = get_hotel(request)
    roomtype = get_object_or_404(RoomType, pk=pk, hotel=hotel)
    
    roomtype.is_active = not roomtype.is_active
    roomtype.save(update_fields=["is_active"])
    
    status = "activated" if roomtype.is_active else "deactivated"
    messages.success(request, f"Room type '{roomtype.name}' {status}.")
    
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"success": True, "is_active": roomtype.is_active})
    
    return redirect("rooms:roomtype_list")


@login_required
@require_http_methods(["POST"])
def roomtype_delete(request, pk):
    """Delete room type (only if no rooms assigned)"""
    hotel = get_hotel(request)
    roomtype = get_object_or_404(RoomType, pk=pk, hotel=hotel)
    
    room_count = Room.objects.filter(hotel=hotel, room_type=roomtype).count()
    
    if room_count > 0:
        messages.error(
            request, 
            f"Cannot delete '{roomtype.name}' - it has {room_count} room(s) assigned."
        )
    else:
        name = roomtype.name
        roomtype.delete()
        messages.success(request, f"Room type '{name}' deleted successfully.")
    
    return redirect("rooms:roomtype_list")


# ============================================================
# ROOM VIEWS
# ============================================================

@method_decorator(login_required, name="dispatch")
class RoomListView(HotelScopedQuerysetMixin, StaffRequiredMixin, ListView):
    model = Room
    template_name = "rooms/room_list.html"
    context_object_name = "rooms"
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().select_related("room_type").prefetch_related(
            Prefetch("images", queryset=RoomImage.objects.filter(is_primary=True, is_active=True), to_attr="primary_image")
        )
        
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(number__icontains=q) | 
                Q(floor__icontains=q) | 
                Q(room_type__name__icontains=q)
            )
        
        status = self.request.GET.get("status", "").strip()
        if status:
            qs = qs.filter(status=status)
        
        room_type = self.request.GET.get("room_type", "").strip()
        if room_type:
            qs = qs.filter(room_type_id=room_type)
        
        is_active = self.request.GET.get("is_active", "")
        if is_active in ["true", "false"]:
            qs = qs.filter(is_active=is_active == "true")
        
        sort_by = self.request.GET.get("sort", "number")
        sort_mapping = {
            "number": "number",
            "floor": ("floor", "number"),
            "status": ("status", "number"),
            "type": ("room_type__name", "number"),
        }
        sort_fields = sort_mapping.get(sort_by, "number")
        if isinstance(sort_fields, tuple):
            qs = qs.order_by(*sort_fields)
        else:
            qs = qs.order_by(sort_fields)
        
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hotel = self.get_hotel()
        
        rooms_qs = Room.objects.filter(hotel=hotel)
        
        ctx.update({
            "total_rooms": rooms_qs.count(),
            "available_count": rooms_qs.filter(status=Room.Status.AVAILABLE).count(),
            "occupied_count": rooms_qs.filter(status=Room.Status.OCCUPIED).count(),
            "maintenance_count": rooms_qs.filter(status=Room.Status.MAINTENANCE).count(),
            "cleaning_count": rooms_qs.filter(status=Room.Status.CLEANING).count(),
            "statuses": Room.Status.choices,
            "room_types": RoomType.objects.filter(hotel=hotel).order_by("name"),
            "current_status": self.request.GET.get("status", ""),
            "current_room_type": self.request.GET.get("room_type", ""),
            "current_sort": self.request.GET.get("sort", "number"),
        })
        
        if ctx["total_rooms"] > 0:
            ctx["occupancy_rate"] = round((ctx["occupied_count"] / ctx["total_rooms"]) * 100, 1)
        else:
            ctx["occupancy_rate"] = 0
        
        return ctx


@method_decorator(login_required, name="dispatch")
class RoomDetailView(HotelScopedQuerysetMixin, StaffRequiredMixin, DetailView):
    model = Room
    template_name = "rooms/room_detail.html"
    context_object_name = "room"

    def get_queryset(self):
        return super().get_queryset().prefetch_related(
            Prefetch("images", queryset=RoomImage.objects.filter(is_active=True).order_by("order", "-created_at")),
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = timezone.localdate()
        
        from bookings.models import Booking
        
        ctx["current_booking"] = Booking.objects.filter(
            hotel=self.object.hotel,
            room=self.object,
            status__in=["confirmed", "checked_in"],
            check_in__lte=today,
            check_out__gte=today,
        ).first()
        
        ctx["upcoming_bookings"] = Booking.objects.filter(
            hotel=self.object.hotel,
            room=self.object,
            status="confirmed",
            check_in__gt=today,
        ).order_by("check_in")[:5]
        
        ctx["past_bookings_count"] = Booking.objects.filter(
            hotel=self.object.hotel,
            room=self.object,
            status="checked_out",
        ).count()
        
        images_by_category = {}
        for image in self.object.images.filter(is_active=True):
            category = image.category
            if category not in images_by_category:
                images_by_category[category] = []
            images_by_category[category].append(image)
        ctx["images_by_category"] = images_by_category
        
        ctx["primary_image"] = self.object.images.filter(is_primary=True, is_active=True).first()
        
        ctx["room_galleries"] = RoomImageGallery.objects.filter(
            hotel=self.object.hotel,
            images__room=self.object,
            is_active=True
        ).distinct()
        
        return ctx


@method_decorator(login_required, name="dispatch")
class RoomCreateView(ManagerRequiredMixin, CreateView):
    model = Room
    form_class = RoomForm
    template_name = "rooms/room_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["hotel"] = get_hotel(self.request)
        return kwargs

    def form_valid(self, form):
        form.instance.hotel = get_hotel(self.request)
        messages.success(self.request, f"Room {form.instance.number} created successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("rooms:room_detail", kwargs={"pk": self.object.pk})


@method_decorator(login_required, name="dispatch")
class RoomUpdateView(HotelScopedQuerysetMixin, ManagerRequiredMixin, UpdateView):
    model = Room
    form_class = RoomForm
    template_name = "rooms/room_form.html"
    context_object_name = "room"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["hotel"] = get_hotel(self.request)
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, f"Room {form.instance.number} updated successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("rooms:room_detail", kwargs={"pk": self.object.pk})


@login_required
@require_http_methods(["POST"])
def room_set_status(request, pk):
    """Update room status"""
    hotel = get_hotel(request)
    room = get_object_or_404(Room, pk=pk, hotel=hotel)

    new_status = request.POST.get("status")
    valid = {c[0] for c in Room.Status.choices}
    
    if new_status not in valid:
        messages.error(request, "Invalid status selected.")
        return redirect("rooms:room_detail", pk=room.pk)

    old_status = room.get_status_display()
    room.status = new_status
    room.save(update_fields=["status"])
    
    messages.success(
        request, 
        f"Room {room.number} status changed from {old_status} to {room.get_status_display()}."
    )
    
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({
            "success": True,
            "status": room.status,
            "status_display": room.get_status_display(),
        })
    
    return redirect("rooms:room_detail", pk=room.pk)


@login_required
@require_http_methods(["POST"])
def room_toggle_active(request, pk):
    """Toggle room active status"""
    hotel = get_hotel(request)
    room = get_object_or_404(Room, pk=pk, hotel=hotel)
    
    room.is_active = not room.is_active
    room.save(update_fields=["is_active"])
    
    status = "activated" if room.is_active else "deactivated"
    messages.success(request, f"Room {room.number} {status}.")
    
    return redirect("rooms:room_list")


@login_required
def room_bulk_status_update(request):
    """Bulk update room statuses"""
    if request.method != "POST":
        raise Http404()
    
    hotel = get_hotel(request)
    room_ids = request.POST.getlist("room_ids")
    new_status = request.POST.get("status")
    
    if not room_ids or not new_status:
        messages.error(request, "No rooms selected or invalid status.")
        return redirect("rooms:room_list")
    
    valid = {c[0] for c in Room.Status.choices}
    if new_status not in valid:
        messages.error(request, "Invalid status selected.")
        return redirect("rooms:room_list")
    
    updated = Room.objects.filter(
        hotel=hotel, id__in=room_ids
    ).update(status=new_status)
    
    messages.success(request, f"Updated {updated} room(s) to {dict(Room.Status.choices).get(new_status)}.")
    
    return redirect("rooms:room_list")


# ============================================================
# ROOM IMAGE VIEWS
# ============================================================

@method_decorator(login_required, name="dispatch")
class RoomImageListView(HotelScopedQuerysetMixin, StaffRequiredMixin, ListView):
    model = RoomImage
    template_name = "rooms/images/image_list.html"
    context_object_name = "images"
    paginate_by = 24

    def get_queryset(self):
        qs = super().get_queryset().select_related("room", "room_type", "hotel")
        
        room_id = self.request.GET.get("room_id")
        if room_id:
            qs = qs.filter(room_id=room_id)
        
        room_type_id = self.request.GET.get("room_type_id")
        if room_type_id:
            qs = qs.filter(room_type_id=room_type_id)
        
        category = self.request.GET.get("category")
        if category:
            qs = qs.filter(category=category)
        
        is_active = self.request.GET.get("is_active")
        if is_active in ["true", "false"]:
            qs = qs.filter(is_active=is_active == "true")
        
        is_featured = self.request.GET.get("is_featured")
        if is_featured in ["true", "false"]:
            qs = qs.filter(is_featured=is_featured == "true")
        
        search = self.request.GET.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(title__icontains=search) |
                Q(alt_text__icontains=search) |
                Q(caption__icontains=search) |
                Q(room__number__icontains=search)
            )
        
        return qs.order_by("order", "-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hotel = self.get_hotel()
        
        ctx.update({
            "filter_form": RoomImageFilterForm(self.request.GET),
            "rooms": Room.objects.filter(hotel=hotel, is_active=True).order_by("number"),
            "room_types": RoomType.objects.filter(hotel=hotel).order_by("name"),
            "categories": RoomImage.IMAGE_CATEGORIES,
            "total_images": RoomImage.objects.filter(hotel=hotel).count(),
            "active_images": RoomImage.objects.filter(hotel=hotel, is_active=True).count(),
            "primary_images": RoomImage.objects.filter(hotel=hotel, is_primary=True).count(),
            "featured_images": RoomImage.objects.filter(hotel=hotel, is_featured=True).count(),
        })
        
        return ctx


@login_required
def room_image_upload(request, room_id=None):
    """Upload a single room image"""
    hotel = get_hotel(request)
    room = None
    
    if room_id:
        room = get_object_or_404(Room, pk=room_id, hotel=hotel)
    
    if request.method == "POST":
        form = RoomImageForm(request.POST, request.FILES, room=room, hotel=hotel)
        
        if form.is_valid():
            form.save()
            messages.success(request, "Image uploaded successfully.")
            
            if room:
                return redirect("rooms:room_detail", pk=room.pk)
            return redirect("rooms:image_list")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = RoomImageForm(room=room, hotel=hotel)
    
    return render(request, "rooms/images/image_upload.html", {"form": form, "room": room})


@login_required
def room_image_bulk_upload(request, room_id=None):
    """Bulk upload multiple room images"""
    hotel = get_hotel(request)
    room = None
    
    if room_id:
        room = get_object_or_404(Room, pk=room_id, hotel=hotel)
    
    if request.method == "POST":
        form = BulkRoomImageUploadForm(request.POST, request.FILES)
        
        if form.is_valid():
            images = request.FILES.getlist("images")
            category = form.cleaned_data["category"]
            set_as_primary = form.cleaned_data["set_as_primary"]
            
            uploaded_count = 0
            for index, image_file in enumerate(images):
                try:
                    room_image = RoomImage(
                        room=room,
                        hotel=hotel,
                        image=image_file,
                        category=category,
                        title=image_file.name,
                        order=index,
                        is_primary=(set_as_primary and index == 0),
                        is_active=True,
                    )
                    
                    try:
                        from PIL import Image
                        img = Image.open(image_file)
                        room_image.width, room_image.height = img.size
                        room_image.file_size = image_file.size
                    except:
                        pass
                    
                    room_image.save()
                    uploaded_count += 1
                except Exception as e:
                    messages.error(request, f"Failed to upload {image_file.name}: {str(e)}")
            
            if uploaded_count > 0:
                messages.success(request, f"Successfully uploaded {uploaded_count} image(s).")
            
            if room:
                return redirect("rooms:room_detail", pk=room.pk)
            return redirect("rooms:image_list")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, error)
    else:
        form = BulkRoomImageUploadForm()
    
    return render(request, "rooms/images/image_upload.html", {"form": form, "room": room, "is_bulk": True})


@login_required
def room_image_update(request, pk):
    """Update room image details"""
    hotel = get_hotel(request)
    image = get_object_or_404(RoomImage, pk=pk, hotel=hotel)
    
    if request.method == "POST":
        form = RoomImageForm(request.POST, request.FILES, instance=image, hotel=hotel)
        
        if form.is_valid():
            form.save()
            messages.success(request, "Image updated successfully.")
            
            if image.room:
                return redirect("rooms:room_detail", pk=image.room.pk)
            return redirect("rooms:image_list")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = RoomImageForm(instance=image, hotel=hotel)
    
    return render(request, "rooms/images/image_upload.html", {"form": form, "image": image, "is_update": True})


@login_required
@require_POST
def room_image_delete(request, pk):
    """Delete a room image"""
    hotel = get_hotel(request)
    image = get_object_or_404(RoomImage, pk=pk, hotel=hotel)
    
    room_pk = image.room.pk if image.room else None
    image.delete()
    
    messages.success(request, "Image deleted successfully.")
    
    if room_pk:
        return redirect("rooms:room_detail", pk=room_pk)
    return redirect("rooms:image_list")


@login_required
@require_POST
def room_image_set_primary(request, pk):
    """Set an image as primary for its room"""
    hotel = get_hotel(request)
    image = get_object_or_404(RoomImage, pk=pk, hotel=hotel)
    
    if not image.room:
        messages.error(request, "This image is not associated with a room.")
        return redirect("rooms:image_list")
    
    image.is_primary = True
    image.save(update_fields=["is_primary"])
    
    messages.success(request, f"Image set as primary for Room {image.room.number}.")
    
    return redirect("rooms:room_detail", pk=image.room.pk)


@login_required
@require_POST
def room_image_reorder(request):
    """Reorder room images via AJAX"""
    hotel = get_hotel(request)
    
    try:
        data = request.POST.get("order_data")
        order_data = json.loads(data)
        
        for item in order_data:
            image_id = item.get("id")
            order = item.get("order")
            
            RoomImage.objects.filter(pk=image_id, hotel=hotel).update(order=order)
        
        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


# ============================================================
# ROOM IMAGE GALLERY VIEWS
# ============================================================

@method_decorator(login_required, name="dispatch")
class RoomImageGalleryListView(HotelScopedQuerysetMixin, StaffRequiredMixin, ListView):
    model = RoomImageGallery
    template_name = "rooms/galleries/gallery_list.html"
    context_object_name = "galleries"
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().prefetch_related("images", "room_type")
        
        room_type_id = self.request.GET.get("room_type_id")
        if room_type_id:
            qs = qs.filter(room_type_id=room_type_id)
        
        is_active = self.request.GET.get("is_active")
        if is_active in ["true", "false"]:
            qs = qs.filter(is_active=is_active == "true")
        
        search = self.request.GET.get("search", "").strip()
        if search:
            qs = qs.filter(name__icontains=search)
        
        return qs.order_by("order", "name")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hotel = self.get_hotel()
        
        ctx.update({
            "room_types": RoomType.objects.filter(hotel=hotel).order_by("name"),
            "total_galleries": RoomImageGallery.objects.filter(hotel=hotel).count(),
            "active_galleries": RoomImageGallery.objects.filter(hotel=hotel, is_active=True).count(),
        })
        
        return ctx


@method_decorator(login_required, name="dispatch")
class RoomImageGalleryCreateView(ManagerRequiredMixin, CreateView):
    model = RoomImageGallery
    form_class = RoomImageGalleryForm
    template_name = "rooms/galleries/gallery_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["hotel"] = get_hotel(self.request)
        return kwargs

    def form_valid(self, form):
        form.instance.hotel = get_hotel(self.request)
        messages.success(self.request, f"Gallery '{form.instance.name}' created successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("rooms:gallery_list")


@method_decorator(login_required, name="dispatch")
class RoomImageGalleryUpdateView(HotelScopedQuerysetMixin, ManagerRequiredMixin, UpdateView):
    model = RoomImageGallery
    form_class = RoomImageGalleryForm
    template_name = "rooms/galleries/gallery_form.html"
    context_object_name = "gallery"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["hotel"] = get_hotel(self.request)
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, f"Gallery '{form.instance.name}' updated successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("rooms:gallery_list")


@method_decorator(login_required, name="dispatch")
class RoomImageGalleryDetailView(HotelScopedQuerysetMixin, StaffRequiredMixin, DetailView):
    model = RoomImageGallery
    template_name = "rooms/galleries/gallery_detail.html"
    context_object_name = "gallery"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        images_by_category = {}
        for image in self.object.images.filter(is_active=True).order_by("order"):
            category = image.category
            if category not in images_by_category:
                images_by_category[category] = []
            images_by_category[category].append(image)
        
        ctx["images_by_category"] = images_by_category
        ctx["total_images"] = self.object.images.count()
        
        return ctx


@login_required
@require_POST
def room_image_gallery_delete(request, pk):
    """Delete a gallery"""
    hotel = get_hotel(request)
    gallery = get_object_or_404(RoomImageGallery, pk=pk, hotel=hotel)
    
    name = gallery.name
    gallery.delete()
    
    messages.success(request, f"Gallery '{name}' deleted successfully.")
    return redirect("rooms:gallery_list")


@login_required
@require_POST
def room_image_gallery_add_images(request, pk):
    """Add images to an existing gallery"""
    hotel = get_hotel(request)
    gallery = get_object_or_404(RoomImageGallery, pk=pk, hotel=hotel)
    
    image_ids = request.POST.getlist("image_ids")
    
    if not image_ids:
        messages.error(request, "No images selected.")
        return redirect("rooms:gallery_detail", pk=gallery.pk)
    
    images = RoomImage.objects.filter(pk__in=image_ids, hotel=hotel)
    gallery.images.add(*images)
    
    messages.success(request, f"Added {images.count()} image(s) to gallery '{gallery.name}'.")
    return redirect("rooms:gallery_detail", pk=gallery.pk)


@login_required
@require_POST
def room_image_gallery_remove_image(request, gallery_pk, image_pk):
    """Remove an image from a gallery"""
    hotel = get_hotel(request)
    gallery = get_object_or_404(RoomImageGallery, pk=gallery_pk, hotel=hotel)
    image = get_object_or_404(RoomImage, pk=image_pk, hotel=hotel)
    
    gallery.images.remove(image)
    
    messages.success(request, f"Image removed from gallery '{gallery.name}'.")
    return redirect("rooms:gallery_detail", pk=gallery.pk)


# ============================================================
# MANAGEMENT DASHBOARD
# ============================================================

@method_decorator(login_required, name="dispatch")
class RoomsManageDashboardView(StaffRequiredMixin, TemplateView):
    template_name = "rooms/manage/dashboard.html"

    def get_hotel(self):
        return get_hotel(self.request)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hotel = self.get_hotel()

        rooms_qs = Room.objects.filter(hotel=hotel)
        ctx["hotel"] = hotel

        ctx["total_rooms"] = rooms_qs.count()
        ctx["available_rooms"] = rooms_qs.filter(status=Room.Status.AVAILABLE, is_active=True).count()
        ctx["occupied_rooms"] = rooms_qs.filter(status=Room.Status.OCCUPIED, is_active=True).count()
        ctx["maintenance_rooms"] = rooms_qs.filter(status=Room.Status.MAINTENANCE, is_active=True).count()
        ctx["cleaning_rooms"] = rooms_qs.filter(status=Room.Status.CLEANING, is_active=True).count()
        
        if ctx["total_rooms"] > 0:
            ctx["occupancy_rate"] = round((ctx["occupied_rooms"] / ctx["total_rooms"]) * 100, 1)
        else:
            ctx["occupancy_rate"] = 0

        ctx["room_type_distribution"] = (
            RoomType.objects.filter(hotel=hotel)
            .annotate(room_count=Count("rooms", filter=Q(rooms__is_active=True)))
            .order_by("-room_count")
        )

        ctx["recent_rooms"] = rooms_qs.select_related("room_type").order_by("-id")[:10]

        ctx["attention_rooms"] = (
            rooms_qs.filter(status__in=[Room.Status.MAINTENANCE, Room.Status.CLEANING])
            .select_related("room_type")
            .order_by("status", "number")[:10]
        )
        
        ctx["total_images"] = RoomImage.objects.filter(hotel=hotel).count()
        ctx["images_without_room"] = RoomImage.objects.filter(hotel=hotel, room__isnull=True).count()
        ctx["total_galleries"] = RoomImageGallery.objects.filter(hotel=hotel).count()
        
        ctx["recent_images"] = RoomImage.objects.filter(hotel=hotel).select_related("room").order_by("-created_at")[:12]

        ctx["roomtype_form"] = RoomTypeForm()
        ctx["room_form"] = RoomForm(hotel=hotel)

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
                messages.success(request, f"Room type '{obj.name}' added successfully.")
            else:
                for field, errors in form.errors.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")

        elif action == "add_room":
            form = RoomForm(request.POST, hotel=hotel)
            if form.is_valid():
                obj = form.save(commit=False)
                obj.hotel = hotel
                obj.save()
                messages.success(request, f"Room {obj.number} added successfully.")
            else:
                for field, errors in form.errors.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")

        else:
            messages.error(request, "Invalid action.")

        return redirect("rooms:manage_dashboard")


# ============================================================
# API ENDPOINTS
# ============================================================

@login_required
def room_list_api(request):
    """JSON API for room list"""
    hotel = get_hotel(request)
    
    rooms = Room.objects.filter(hotel=hotel, is_active=True).select_related("room_type")
    
    status = request.GET.get("status")
    if status:
        rooms = rooms.filter(status=status)
    
    room_type = request.GET.get("room_type")
    if room_type:
        rooms = rooms.filter(room_type_id=room_type)
    
    data = {
        "rooms": [
            {
                "id": room.id,
                "number": room.number,
                "floor": room.floor,
                "status": room.status,
                "status_display": room.get_status_display(),
                "room_type": room.room_type.name,
                "price": str(room.room_type.base_price),
            }
            for room in rooms
        ]
    }
    
    return JsonResponse(data)


@login_required
def room_images_api(request, room_id):
    """JSON API for room images"""
    hotel = get_hotel(request)
    room = get_object_or_404(Room, pk=room_id, hotel=hotel)
    
    images = room.images.filter(is_active=True).order_by("order", "-created_at")
    
    data = {
        "room": {
            "id": room.id,
            "number": room.number,
        },
        "images": [
            {
                "id": img.id,
                "url": img.image.url,
                "thumbnail": img.thumbnail_url,
                "category": img.category,
                "category_display": img.get_category_display(),
                "title": img.title,
                "caption": img.caption,
                "is_primary": img.is_primary,
                "order": img.order,
            }
            for img in images
        ]
    }
    
    return JsonResponse(data)


# ============================================================
# ASSET CATEGORY VIEWS
# ============================================================
@method_decorator(login_required, name="dispatch")
class AssetCategoryListView(HotelScopedQuerysetMixin, ManagerRequiredMixin, ListView):
    model = AssetCategory
    template_name = "rooms/assets/category_list.html"
    context_object_name = "categories"
    
    def get_queryset(self):
        return super().get_queryset().annotate(
            asset_count=Count('assets')
        ).order_by('name')
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['form'] = AssetCategoryForm()
        return ctx


@login_required
@require_POST
def asset_category_create(request):
    """Create a new asset category"""
    hotel = get_hotel(request)
    
    form = AssetCategoryForm(request.POST)
    
    if form.is_valid():
        category = form.save(commit=False)
        category.hotel = hotel
        category.save()
        messages.success(request, f"Category '{category.name}' created successfully.")
    else:
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"{field}: {error}")
    
    return redirect("rooms:asset_category_list")


# ============================================================
# ASSET MANAGEMENT VIEWS
# ============================================================
@method_decorator(login_required, name="dispatch")
class AssetListView(HotelScopedQuerysetMixin, ManagerRequiredMixin, ListView):
    model = RoomAsset
    template_name = "rooms/assets/asset_list.html"
    context_object_name = "assets"
    paginate_by = 20
    
    def get_queryset(self):
        qs = super().get_queryset().select_related('category', 'room', 'room_type')
        
        # Apply filters
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        
        category = self.request.GET.get('category')
        if category:
            qs = qs.filter(category_id=category)
        
        room = self.request.GET.get('room')
        if room:
            qs = qs.filter(room_id=room)
        
        depreciation_method = self.request.GET.get('depreciation_method')
        if depreciation_method:
            qs = qs.filter(depreciation_method=depreciation_method)
        
        search = self.request.GET.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(serial_number__icontains=search) |
                Q(brand__icontains=search)
            )
        
        # Annotate half price for each asset
        qs = qs.annotate(
            half_price=F('purchase_price') / 2
        )
        
        return qs.order_by('-purchase_date')
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hotel = self.get_hotel()
        
        ctx['filter_form'] = AssetFilterForm(self.request.GET, hotel=hotel)
        ctx['categories'] = AssetCategory.objects.filter(hotel=hotel, is_active=True)
        
        assets_qs = RoomAsset.objects.filter(hotel=hotel)
        ctx['total_assets'] = assets_qs.count()
        ctx['total_value'] = assets_qs.aggregate(total=Sum('current_value'))['total'] or 0
        ctx['total_depreciation'] = assets_qs.aggregate(total=Sum('total_depreciation'))['total'] or 0
        ctx['active_assets'] = assets_qs.filter(status='active').count()
        
        ctx['assets_by_room'] = assets_qs.filter(room__isnull=False).values('room__number').annotate(
            count=Count('id'),
            value=Sum('current_value')
        ).order_by('-value')[:10]
        
        return ctx

@method_decorator(login_required, name="dispatch")
class AssetCreateView(ManagerRequiredMixin, CreateView):
    model = RoomAsset
    form_class = RoomAssetForm
    template_name = "rooms/assets/asset_form.html"
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['hotel'] = get_hotel(self.request)
        return kwargs
    
    def form_valid(self, form):
        form.instance.hotel = get_hotel(self.request)
        messages.success(self.request, f"Asset '{form.instance.name}' created successfully.")
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse("rooms:asset_list")


@method_decorator(login_required, name="dispatch")
class AssetUpdateView(HotelScopedQuerysetMixin, ManagerRequiredMixin, UpdateView):
    model = RoomAsset
    form_class = RoomAssetForm
    template_name = "rooms/assets/asset_form.html"
    context_object_name = "asset"
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['hotel'] = get_hotel(self.request)
        return kwargs
    
    def form_valid(self, form):
        messages.success(self.request, f"Asset '{form.instance.name}' updated successfully.")
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse("rooms:asset_list")


@method_decorator(login_required, name="dispatch")
class AssetDetailView(HotelScopedQuerysetMixin, ManagerRequiredMixin, DetailView):
    model = RoomAsset
    template_name = "rooms/assets/asset_detail.html"
    context_object_name = "asset"
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = date.today()
        
        ctx['yearly_depreciation'] = self.object.get_annual_depreciation()
        ctx['appreciation_potential'] = self.object.get_appreciation_potential()
        ctx['depreciation_schedule'] = self.object.depreciation_schedule.all()[:12]
        
        months_used = relativedelta(today, self.object.purchase_date).years * 12 + relativedelta(today, self.object.purchase_date).months
        total_months = self.object.useful_life_years * 12
        ctx['remaining_months'] = max(0, total_months - months_used)
        ctx['depreciation_percentage'] = (self.object.total_depreciation / self.object.purchase_price * 100) if self.object.purchase_price > 0 else 0
        
        return ctx


@login_required
def asset_calculate_depreciation(request, pk):
    """Manually trigger depreciation calculation for an asset"""
    hotel = get_hotel(request)
    asset = get_object_or_404(RoomAsset, pk=pk, hotel=hotel)
    
    old_value = asset.current_value
    asset.update_current_value()
    
    messages.success(
        request,
        f"Depreciation calculated for {asset.name}. Value changed from {old_value} to {asset.current_value}"
    )
    
    return redirect("rooms:asset_detail", pk=asset.pk)


@login_required
@require_POST
def asset_bulk_depreciation(request):
    """Calculate depreciation for all active assets"""
    hotel = get_hotel(request)
    
    assets = RoomAsset.objects.filter(hotel=hotel, status='active')
    updated_count = 0
    
    for asset in assets:
        old_value = asset.current_value
        asset.update_current_value()
        if old_value != asset.current_value:
            updated_count += 1
    
    messages.success(request, f"Depreciation calculated for {updated_count} out of {assets.count()} assets.")
    
    return redirect("rooms:asset_list")


@login_required
@require_POST
def asset_delete(request, pk):
    """Delete an asset"""
    hotel = get_hotel(request)
    asset = get_object_or_404(RoomAsset, pk=pk, hotel=hotel)
    
    name = asset.name
    asset.delete()
    
    messages.success(request, f"Asset '{name}' deleted successfully.")
    return redirect("rooms:asset_list")


# ============================================================
# LIABILITY MANAGEMENT VIEWS
# ============================================================

@method_decorator(login_required, name="dispatch")
class LiabilityListView(HotelScopedQuerysetMixin, ManagerRequiredMixin, ListView):
    model = RoomLiability
    template_name = "rooms/liabilities/liability_list.html"
    context_object_name = "liabilities"
    paginate_by = 20
    
    def get_queryset(self):
        qs = super().get_queryset().select_related('room', 'room_type')
        
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        
        liability_type = self.request.GET.get('liability_type')
        if liability_type:
            qs = qs.filter(liability_type=liability_type)
        
        room = self.request.GET.get('room')
        if room:
            qs = qs.filter(room_id=room)
        
        search = self.request.GET.get('search', '').strip()
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(description__icontains=search))
        
        return qs.order_by('-start_date', 'status')
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hotel = self.get_hotel()
        
        ctx['filter_form'] = LiabilityFilterForm(self.request.GET, hotel=hotel)
        
        liabilities_qs = RoomLiability.objects.filter(hotel=hotel)
        ctx['total_liabilities'] = liabilities_qs.count()
        ctx['total_balance'] = liabilities_qs.aggregate(total=Sum('remaining_balance'))['total'] or 0
        ctx['active_liabilities'] = liabilities_qs.filter(status='active').count()
        ctx['overdue_liabilities'] = sum(1 for l in liabilities_qs if l.is_overdue())
        
        ctx['liabilities_by_room'] = liabilities_qs.filter(room__isnull=False).values('room__number').annotate(
            count=Count('id'),
            balance=Sum('remaining_balance')
        ).order_by('-balance')[:10]
        
        return ctx


@method_decorator(login_required, name="dispatch")
class LiabilityCreateView(ManagerRequiredMixin, CreateView):
    model = RoomLiability
    form_class = RoomLiabilityForm
    template_name = "rooms/liabilities/liability_form.html"
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['hotel'] = get_hotel(self.request)
        return kwargs
    
    def form_valid(self, form):
        form.instance.hotel = get_hotel(self.request)
        messages.success(self.request, f"Liability '{form.instance.name}' created successfully.")
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse("rooms:liability_list")


@method_decorator(login_required, name="dispatch")
class LiabilityUpdateView(HotelScopedQuerysetMixin, ManagerRequiredMixin, UpdateView):
    model = RoomLiability
    form_class = RoomLiabilityForm
    template_name = "rooms/liabilities/liability_form.html"
    context_object_name = "liability"
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['hotel'] = get_hotel(self.request)
        return kwargs
    
    def form_valid(self, form):
        messages.success(self.request, f"Liability '{form.instance.name}' updated successfully.")
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse("rooms:liability_list")


@method_decorator(login_required, name="dispatch")
class LiabilityDetailView(HotelScopedQuerysetMixin, ManagerRequiredMixin, DetailView):
    model = RoomLiability
    template_name = "rooms/liabilities/liability_detail.html"
    context_object_name = "liability"
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        ctx['payment_form'] = LiabilityPaymentForm()
        ctx['payments'] = self.object.payments.all()[:20]
        ctx['total_paid'] = self.object.payments.aggregate(total=Sum('amount'))['total'] or 0
        ctx['percent_paid'] = (ctx['total_paid'] / self.object.principal_amount * 100) if self.object.principal_amount > 0 else 0
        
        if self.object.monthly_payment > 0 and self.object.remaining_balance > 0:
            months_to_payoff = self.object.remaining_balance / self.object.monthly_payment
            ctx['projected_payoff_date'] = date.today() + relativedelta(months=int(months_to_payoff))
        
        return ctx


@login_required
def liability_make_payment(request, pk):
    """Record a payment against a liability"""
    hotel = get_hotel(request)
    liability = get_object_or_404(RoomLiability, pk=pk, hotel=hotel)
    
    if request.method == "POST":
        form = LiabilityPaymentForm(request.POST)
        
        if form.is_valid():
            payment = form.save(commit=False)
            payment.liability = liability
            payment.save()
            
            messages.success(request, f"Payment of {payment.amount} recorded successfully.")
            
            if liability.remaining_balance == 0:
                messages.info(request, f"Liability '{liability.name}' has been fully paid!")
            
            return redirect("rooms:liability_detail", pk=liability.pk)
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    
    return redirect("rooms:liability_detail", pk=liability.pk)


@login_required
@require_POST
def liability_delete(request, pk):
    """Delete a liability"""
    hotel = get_hotel(request)
    liability = get_object_or_404(RoomLiability, pk=pk, hotel=hotel)
    
    name = liability.name
    liability.delete()
    
    messages.success(request, f"Liability '{name}' deleted successfully.")
    return redirect("rooms:liability_list")


@login_required
def liability_mark_paid(request, pk):
    """Mark a liability as fully paid"""
    hotel = get_hotel(request)
    liability = get_object_or_404(RoomLiability, pk=pk, hotel=hotel)
    
    liability.remaining_balance = 0
    liability.status = 'paid'
    liability.paid_date = date.today()
    liability.save(update_fields=['remaining_balance', 'status', 'paid_date'])
    
    messages.success(request, f"Liability '{liability.name}' marked as paid.")
    return redirect("rooms:liability_detail", pk=liability.pk)


# ============================================================
# FINANCIAL DASHBOARD
# ============================================================

@method_decorator(login_required, name="dispatch")
class RoomsFinancialDashboardView(ManagerRequiredMixin, TemplateView):
    template_name = "rooms/financial_dashboard.html"
    
    def get_hotel(self):
        return get_hotel(self.request)
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hotel = self.get_hotel()
        today = date.today()
        
        # Asset summary
        assets_qs = RoomAsset.objects.filter(hotel=hotel)
        ctx['total_asset_value'] = assets_qs.aggregate(total=Sum('current_value'))['total'] or 0
        ctx['total_asset_cost'] = assets_qs.aggregate(total=Sum('purchase_price'))['total'] or 0
        ctx['total_depreciation'] = assets_qs.aggregate(total=Sum('total_depreciation'))['total'] or 0
        ctx['asset_count'] = assets_qs.count()
        
        # Liability summary
        liabilities_qs = RoomLiability.objects.filter(hotel=hotel)
        ctx['total_liability_balance'] = liabilities_qs.aggregate(total=Sum('remaining_balance'))['total'] or 0
        ctx['total_liability_principal'] = liabilities_qs.aggregate(total=Sum('principal_amount'))['total'] or 0
        ctx['liability_count'] = liabilities_qs.count()
        
        # Net room value
        ctx['net_room_value'] = ctx['total_asset_value'] - ctx['total_liability_balance']
        
        # Assets by room (top 10 by value)
        ctx['assets_by_room'] = assets_qs.filter(room__isnull=False).values(
            'room__number', 'room__id'
        ).annotate(
            total_value=Sum('current_value'),
            asset_count=Count('id')
        ).order_by('-total_value')[:10]
        
        # Liabilities by room (top 10 by balance)
        ctx['liabilities_by_room'] = liabilities_qs.filter(room__isnull=False).values(
            'room__number', 'room__id'
        ).annotate(
            total_balance=Sum('remaining_balance'),
            liability_count=Count('id')
        ).order_by('-total_balance')[:10]
        
        # Depreciation by category
        ctx['depreciation_by_category'] = assets_qs.values('category__name').annotate(
            total_depreciation=Sum('total_depreciation'),
            total_value=Sum('current_value')
        ).order_by('-total_depreciation')
        
        # Assets by type
        ctx['assets_by_type'] = assets_qs.values('category__asset_type').annotate(
            count=Count('id'),
            total_value=Sum('current_value')
        ).order_by('-total_value')
        
        # Recent assets
        ctx['recent_assets'] = assets_qs.select_related('category', 'room').order_by('-created_at')[:10]
        
        # Upcoming liability payments
        ctx['upcoming_payments'] = liabilities_qs.filter(
            status__in=['active', 'pending'],
            next_payment_date__gte=today,
            next_payment_date__lte=today + timedelta(days=30)
        ).order_by('next_payment_date')[:10]
        
        # Overdue liabilities
        overdue = []
        for liability in liabilities_qs.filter(status__in=['active', 'pending']):
            if liability.is_overdue():
                overdue.append(liability)
        ctx['overdue_liabilities'] = overdue
        
        return ctx