# rooms/views.py
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Count, Sum, F, Value, DecimalField, Case, When, IntegerField, Avg, Prefetch, Exists, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import ListView, CreateView, UpdateView, DetailView, TemplateView, DeleteView
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST
from django.core.files.images import get_image_dimensions
from django.core.exceptions import ValidationError

from hotel_thinker.utils import get_active_hotel_for_user, require_hotel_role
from .models import Room, RoomType, RoomImage, RoomImageGallery
from .forms import (
    RoomTypeForm, RoomForm, RoomImageForm, RoomImageGalleryForm, 
    BulkRoomImageUploadForm, RoomImageFilterForm
)

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
        
        # Search filter
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
        
        return qs.order_by("name")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hotel = self.get_hotel()
        
        # Total rooms count
        ctx["total_rooms"] = Room.objects.filter(hotel=hotel).count()
        
        # Average base price across all room types
        avg_price_data = RoomType.objects.filter(hotel=hotel).aggregate(avg=Avg("base_price"))
        ctx["avg_price"] = avg_price_data["avg"] or 0
        
        # Room distribution by type (for stats card)
        room_distribution = Room.objects.filter(
            hotel=hotel, is_active=True
        ).values("room_type__name").annotate(count=Count("id"))
        ctx["total_rooms_by_type"] = room_distribution
        
        # Pass room types for filter (if needed in template)
        ctx["room_types_for_filter"] = RoomType.objects.filter(hotel=hotel).order_by("name")
        
        return ctx


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
        messages.success(self.request, f"Room type '{form.instance.name}' created successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("rooms:roomtype_list")


@method_decorator(login_required, name="dispatch")
class RoomTypeUpdateView(HotelScopedQuerysetMixin, UpdateView):
    model = RoomType
    form_class = RoomTypeForm
    template_name = "rooms/roomtype_form.html"
    context_object_name = "roomtype"

    def dispatch(self, request, *args, **kwargs):
        require_hotel_role(request.user, {"admin", "general_manager", "operations_manager"})
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, f"Room type '{form.instance.name}' updated successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("rooms:roomtype_list")


@login_required
@require_http_methods(["POST"])
def roomtype_toggle_active(request, pk: int):
    """Toggle room type active status via AJAX"""
    hotel = get_active_hotel_for_user(request.user)
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
def roomtype_delete(request, pk: int):
    """Delete room type (only if no rooms assigned)"""
    hotel = get_active_hotel_for_user(request.user)
    roomtype = get_object_or_404(RoomType, pk=pk, hotel=hotel)
    
    # Check if there are rooms using this type
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
class RoomListView(HotelScopedQuerysetMixin, ListView):
    model = Room
    template_name = "rooms/room_list.html"
    context_object_name = "rooms"
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().select_related("room_type").prefetch_related(
            Prefetch("images", queryset=RoomImage.objects.filter(is_primary=True, is_active=True), to_attr="primary_image")
        )
        
        # Search filter
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(number__icontains=q) | 
                Q(floor__icontains=q) | 
                Q(room_type__name__icontains=q)
            )
        
        # Status filter
        status = self.request.GET.get("status", "").strip()
        if status:
            qs = qs.filter(status=status)
        
        # Room type filter
        room_type = self.request.GET.get("room_type", "").strip()
        if room_type:
            qs = qs.filter(room_type_id=room_type)
        
        # Active filter
        is_active = self.request.GET.get("is_active", "")
        if is_active in ["true", "false"]:
            qs = qs.filter(is_active=is_active == "true")
        
        # Sorting
        sort_by = self.request.GET.get("sort", "number")
        if sort_by == "number":
            qs = qs.order_by("number")
        elif sort_by == "floor":
            qs = qs.order_by("floor", "number")
        elif sort_by == "status":
            qs = qs.order_by("status", "number")
        elif sort_by == "type":
            qs = qs.order_by("room_type__name", "number")
        else:
            qs = qs.order_by("number")
        
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hotel = self.get_hotel()
        
        # Statistics
        rooms_qs = Room.objects.filter(hotel=hotel)
        
        ctx["total_rooms"] = rooms_qs.count()
        ctx["available_count"] = rooms_qs.filter(status=Room.Status.AVAILABLE).count()
        ctx["occupied_count"] = rooms_qs.filter(status=Room.Status.OCCUPIED).count()
        ctx["maintenance_count"] = rooms_qs.filter(status=Room.Status.MAINTENANCE).count()
        ctx["cleaning_count"] = rooms_qs.filter(status=Room.Status.CLEANING).count()
        
        # Status choices for filter
        ctx["statuses"] = Room.Status.choices
        
        # Room types for filter
        ctx["room_types"] = RoomType.objects.filter(hotel=hotel).order_by("name")
        
        # Current filter values
        ctx["current_status"] = self.request.GET.get("status", "")
        ctx["current_room_type"] = self.request.GET.get("room_type", "")
        ctx["current_sort"] = self.request.GET.get("sort", "number")
        
        # Occupancy rate
        if ctx["total_rooms"] > 0:
            ctx["occupancy_rate"] = round(
                (ctx["occupied_count"] / ctx["total_rooms"]) * 100, 1
            )
        else:
            ctx["occupancy_rate"] = 0
        
        return ctx


@method_decorator(login_required, name="dispatch")
class RoomDetailView(HotelScopedQuerysetMixin, DetailView):
    model = Room
    template_name = "rooms/room_detail.html"
    context_object_name = "room"

    def get_queryset(self):
        return super().get_queryset().prefetch_related(
            Prefetch("images", queryset=RoomImage.objects.filter(is_active=True).order_by("order", "-created_at")),
            "room_type__galleries",
            "galleries",
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # Get current booking for this room if any
        from bookings.models import Booking
        today = timezone.localdate()
        
        current_booking = Booking.objects.filter(
            hotel=self.object.hotel,
            room=self.object,
            status__in=["confirmed", "checked_in"],
            check_in__lte=today,
            check_out__gte=today,
        ).first()
        
        ctx["current_booking"] = current_booking
        
        # Upcoming bookings
        ctx["upcoming_bookings"] = Booking.objects.filter(
            hotel=self.object.hotel,
            room=self.object,
            status="confirmed",
            check_in__gt=today,
        ).order_by("check_in")[:5]
        
        # Past bookings count
        ctx["past_bookings_count"] = Booking.objects.filter(
            hotel=self.object.hotel,
            room=self.object,
            status="checked_out",
        ).count()
        
        # Room images grouped by category
        images_by_category = {}
        for image in self.object.images.filter(is_active=True):
            category = image.category
            if category not in images_by_category:
                images_by_category[category] = []
            images_by_category[category].append(image)
        ctx["images_by_category"] = images_by_category
        
        # Primary image
        ctx["primary_image"] = self.object.images.filter(is_primary=True, is_active=True).first()
        
        # Galleries containing this room
        ctx["room_galleries"] = RoomImageGallery.objects.filter(
            hotel=self.object.hotel,
            images__room=self.object,
            is_active=True
        ).distinct()
        
        return ctx


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
        messages.success(self.request, f"Room {form.instance.number} created successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("rooms:room_detail", kwargs={"pk": self.object.pk})


@method_decorator(login_required, name="dispatch")
class RoomUpdateView(HotelScopedQuerysetMixin, UpdateView):
    model = Room
    form_class = RoomForm
    template_name = "rooms/room_form.html"
    context_object_name = "room"

    def dispatch(self, request, *args, **kwargs):
        require_hotel_role(request.user, {"admin", "general_manager", "operations_manager"})
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["hotel"] = get_active_hotel_for_user(self.request.user)
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, f"Room {form.instance.number} updated successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("rooms:room_detail", kwargs={"pk": self.object.pk})


@login_required
@require_http_methods(["POST"])
def room_set_status(request, pk: int):
    """Update room status via POST"""
    hotel = get_active_hotel_for_user(request.user)
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
    
    # Handle AJAX requests
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({
            "success": True,
            "status": room.status,
            "status_display": room.get_status_display(),
        })
    
    return redirect("rooms:room_detail", pk=room.pk)


@login_required
@require_http_methods(["POST"])
def room_toggle_active(request, pk: int):
    """Toggle room active status"""
    hotel = get_active_hotel_for_user(request.user)
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
    
    hotel = get_active_hotel_for_user(request.user)
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
class RoomImageListView(HotelScopedQuerysetMixin, ListView):
    model = RoomImage
    template_name = "rooms/images/image_list.html"
    context_object_name = "images"
    paginate_by = 24

    def get_queryset(self):
        qs = super().get_queryset().select_related("room", "room_type", "hotel")
        
        # Filter by room
        room_id = self.request.GET.get("room_id")
        if room_id:
            qs = qs.filter(room_id=room_id)
        
        # Filter by room type
        room_type_id = self.request.GET.get("room_type_id")
        if room_type_id:
            qs = qs.filter(room_type_id=room_type_id)
        
        # Filter by category
        category = self.request.GET.get("category")
        if category:
            qs = qs.filter(category=category)
        
        # Filter by status
        is_active = self.request.GET.get("is_active")
        if is_active in ["true", "false"]:
            qs = qs.filter(is_active=is_active == "true")
        
        # Filter by featured
        is_featured = self.request.GET.get("is_featured")
        if is_featured in ["true", "false"]:
            qs = qs.filter(is_featured=is_featured == "true")
        
        # Search
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
        
        ctx["filter_form"] = RoomImageFilterForm(self.request.GET)
        ctx["rooms"] = Room.objects.filter(hotel=hotel, is_active=True).order_by("number")
        ctx["room_types"] = RoomType.objects.filter(hotel=hotel).order_by("name")
        ctx["categories"] = RoomImage.IMAGE_CATEGORIES
        
        # Statistics
        ctx["total_images"] = RoomImage.objects.filter(hotel=hotel).count()
        ctx["active_images"] = RoomImage.objects.filter(hotel=hotel, is_active=True).count()
        ctx["primary_images"] = RoomImage.objects.filter(hotel=hotel, is_primary=True).count()
        ctx["featured_images"] = RoomImage.objects.filter(hotel=hotel, is_featured=True).count()
        
        return ctx


@login_required
def room_image_upload(request, room_id=None):
    """Upload a single room image"""
    hotel = get_active_hotel_for_user(request.user)
    
    # Determine context (room-specific or general)
    room = None
    room_type = None
    
    if room_id:
        room = get_object_or_404(Room, pk=room_id, hotel=hotel)
    
    if request.method == "POST":
        form = RoomImageForm(request.POST, request.FILES, room=room, room_type=room_type, hotel=hotel)
        
        if form.is_valid():
            image = form.save()
            
            messages.success(request, "Image uploaded successfully.")
            
            if room:
                return redirect("rooms:room_detail", pk=room.pk)
            return redirect("rooms:image_list")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = RoomImageForm(room=room, room_type=room_type, hotel=hotel)
    
    context = {
        "form": form,
        "room": room,
        "room_type": room_type,
    }
    
    return render(request, "rooms/images/image_upload.html", context)


@login_required
def room_image_bulk_upload(request, room_id=None):
    """Bulk upload multiple room images"""
    hotel = get_active_hotel_for_user(request.user)
    
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
                    # Create image instance
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
                    
                    # Get image dimensions if PIL available
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
    
    context = {
        "form": form,
        "room": room,
        "is_bulk": True,
    }
    
    return render(request, "rooms/images/image_upload.html", context)


@login_required
def room_image_update(request, pk):
    """Update room image details"""
    hotel = get_active_hotel_for_user(request.user)
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
    
    context = {
        "form": form,
        "image": image,
        "is_update": True,
    }
    
    return render(request, "rooms/images/image_upload.html", context)


@login_required
@require_POST
def room_image_delete(request, pk):
    """Delete a room image"""
    hotel = get_active_hotel_for_user(request.user)
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
    hotel = get_active_hotel_for_user(request.user)
    image = get_object_or_404(RoomImage, pk=pk, hotel=hotel)
    
    if not image.room:
        messages.error(request, "This image is not associated with a room.")
        return redirect("rooms:image_list")
    
    # Set this image as primary (model's save method handles unsetting others)
    image.is_primary = True
    image.save(update_fields=["is_primary"])
    
    messages.success(request, f"Image set as primary for Room {image.room.number}.")
    
    return redirect("rooms:room_detail", pk=image.room.pk)


@login_required
@require_POST
def room_image_reorder(request):
    """Reorder room images via AJAX"""
    hotel = get_active_hotel_for_user(request.user)
    
    try:
        data = request.POST.get("order_data")
        import json
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
class RoomImageGalleryListView(HotelScopedQuerysetMixin, ListView):
    model = RoomImageGallery
    template_name = "rooms/galleries/gallery_list.html"
    context_object_name = "galleries"
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().prefetch_related("images", "room_type")
        
        # Filter by room type
        room_type_id = self.request.GET.get("room_type_id")
        if room_type_id:
            qs = qs.filter(room_type_id=room_type_id)
        
        # Filter by active
        is_active = self.request.GET.get("is_active")
        if is_active in ["true", "false"]:
            qs = qs.filter(is_active=is_active == "true")
        
        # Search
        search = self.request.GET.get("search", "").strip()
        if search:
            qs = qs.filter(name__icontains=search)
        
        return qs.order_by("order", "name")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hotel = self.get_hotel()
        
        ctx["room_types"] = RoomType.objects.filter(hotel=hotel).order_by("name")
        ctx["total_galleries"] = RoomImageGallery.objects.filter(hotel=hotel).count()
        ctx["active_galleries"] = RoomImageGallery.objects.filter(hotel=hotel, is_active=True).count()
        
        return ctx


@method_decorator(login_required, name="dispatch")
class RoomImageGalleryCreateView(CreateView):
    model = RoomImageGallery
    form_class = RoomImageGalleryForm
    template_name = "rooms/galleries/gallery_form.html"

    def dispatch(self, request, *args, **kwargs):
        require_hotel_role(request.user, {"admin", "general_manager", "operations_manager"})
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["hotel"] = get_active_hotel_for_user(self.request.user)
        return kwargs

    def form_valid(self, form):
        form.instance.hotel = get_active_hotel_for_user(self.request.user)
        messages.success(self.request, f"Gallery '{form.instance.name}' created successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("rooms:gallery_list")


@method_decorator(login_required, name="dispatch")
class RoomImageGalleryUpdateView(HotelScopedQuerysetMixin, UpdateView):
    model = RoomImageGallery
    form_class = RoomImageGalleryForm
    template_name = "rooms/galleries/gallery_form.html"
    context_object_name = "gallery"

    def dispatch(self, request, *args, **kwargs):
        require_hotel_role(request.user, {"admin", "general_manager", "operations_manager"})
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["hotel"] = get_active_hotel_for_user(self.request.user)
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, f"Gallery '{form.instance.name}' updated successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("rooms:gallery_list")


@method_decorator(login_required, name="dispatch")
class RoomImageGalleryDetailView(HotelScopedQuerysetMixin, DetailView):
    model = RoomImageGallery
    template_name = "rooms/galleries/gallery_detail.html"
    context_object_name = "gallery"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # Group images by category
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
    hotel = get_active_hotel_for_user(request.user)
    gallery = get_object_or_404(RoomImageGallery, pk=pk, hotel=hotel)
    
    name = gallery.name
    gallery.delete()
    
    messages.success(request, f"Gallery '{name}' deleted successfully.")
    return redirect("rooms:gallery_list")


@login_required
@require_POST
def room_image_gallery_add_images(request, pk):
    """Add images to an existing gallery"""
    hotel = get_active_hotel_for_user(request.user)
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
    hotel = get_active_hotel_for_user(request.user)
    gallery = get_object_or_404(RoomImageGallery, pk=gallery_pk, hotel=hotel)
    image = get_object_or_404(RoomImage, pk=image_pk, hotel=hotel)
    
    gallery.images.remove(image)
    
    messages.success(request, f"Image removed from gallery '{gallery.name}'.")
    return redirect("rooms:gallery_detail", pk=gallery.pk)


# ============================================================
# MANAGEMENT DASHBOARD
# ============================================================

@method_decorator(login_required, name="dispatch")
class RoomsManageDashboardView(TemplateView):
    template_name = "rooms/manage/dashboard.html"

    def dispatch(self, request, *args, **kwargs):
        require_hotel_role(request.user, {
            "admin", "general_manager", "operations_manager", 
            "front_desk", "housekeeping"
        })
        return super().dispatch(request, *args, **kwargs)

    def get_hotel(self):
        return get_active_hotel_for_user(self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hotel = self.get_hotel()

        rooms_qs = Room.objects.filter(hotel=hotel)
        ctx["hotel"] = hotel

        # Room statistics
        ctx["total_rooms"] = rooms_qs.count()
        ctx["available_rooms"] = rooms_qs.filter(status=Room.Status.AVAILABLE, is_active=True).count()
        ctx["occupied_rooms"] = rooms_qs.filter(status=Room.Status.OCCUPIED, is_active=True).count()
        ctx["maintenance_rooms"] = rooms_qs.filter(status=Room.Status.MAINTENANCE, is_active=True).count()
        ctx["cleaning_rooms"] = rooms_qs.filter(status=Room.Status.CLEANING, is_active=True).count()
        
        # Occupancy rate
        if ctx["total_rooms"] > 0:
            ctx["occupancy_rate"] = round((ctx["occupied_rooms"] / ctx["total_rooms"]) * 100, 1)
        else:
            ctx["occupancy_rate"] = 0

        # Room type distribution
        ctx["room_type_distribution"] = (
            RoomType.objects.filter(hotel=hotel)
            .annotate(room_count=Count("rooms", filter=Q(rooms__is_active=True)))
            .order_by("-room_count")
        )

        # Recent rooms
        ctx["recent_rooms"] = (
            rooms_qs.select_related("room_type")
            .order_by("-id")[:10]
        )

        # Rooms needing attention (maintenance or cleaning)
        ctx["attention_rooms"] = (
            rooms_qs.filter(status__in=[Room.Status.MAINTENANCE, Room.Status.CLEANING])
            .select_related("room_type")
            .order_by("status", "number")[:10]
        )
        
        # Image statistics
        ctx["total_images"] = RoomImage.objects.filter(hotel=hotel).count()
        ctx["images_without_room"] = RoomImage.objects.filter(hotel=hotel, room__isnull=True).count()
        ctx["total_galleries"] = RoomImageGallery.objects.filter(hotel=hotel).count()
        
        # Recent uploads
        ctx["recent_images"] = RoomImage.objects.filter(hotel=hotel).select_related("room").order_by("-created_at")[:12]

        # Modal forms
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
# API ENDPOINTS for AJAX
# ============================================================

@login_required
def room_list_api(request):
    """JSON API for room list (for dynamic filtering)"""
    hotel = get_active_hotel_for_user(request.user)
    
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
    hotel = get_active_hotel_for_user(request.user)
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