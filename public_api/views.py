from django.db.models import Count, Avg, Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.response import Response
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.views import APIView

from hotels.models import Hotel, HotelExperience, HotelReview
from rooms.models import Room, RoomType, RoomImage
from restaurant.models import MenuCategory, MenuItem
from bar.models import BarCategory, BarItem
from bookings.models import Booking

from .serializers import (
    PublicHotelSerializer,
    PublicGuestSerializer,
    GuestRegisterSerializer,
    GuestLoginSerializer,
    PublicExperienceSerializer,
    PublicExperienceCreateSerializer,
    PublicReviewSerializer,
    PublicReviewCreateSerializer,
    PublicRoomSerializer,
    PublicRoomTypeSerializer,
    PublicBarCategorySerializer,
    PublicMenuCategorySerializer,
    PublicMenuItemSerializer,
    PublicBarItemSerializer,
    PublicBookingCreateSerializer,
    PublicBookingSerializer,
    PublicRestaurantOrderCreateSerializer,
    PublicBarOrderCreateSerializer,
    available_rooms,
    get_guest_for_user,
)


class OptionalTokenAuthentication(TokenAuthentication):
    def authenticate(self, request):
        try:
            return super().authenticate(request)
        except Exception:
            return None


class PublicHotelMixin:
    permission_classes = [permissions.AllowAny]
    authentication_classes = [OptionalTokenAuthentication, SessionAuthentication]

    def get_hotel(self):
        return get_object_or_404(Hotel, slug=self.kwargs["slug"], is_active=True, is_published=True)


class PublicHotelListAPIView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    serializer_class = PublicHotelSerializer

    def get_queryset(self):
        qs = Hotel.objects.filter(is_active=True, is_published=True).order_by("name")
        q = self.request.query_params.get("q") or self.request.query_params.get("search")
        city = self.request.query_params.get("city")
        country = self.request.query_params.get("country")
        featured = self.request.query_params.get("featured")
        if q:
            qs = qs.filter(
                Q(name__icontains=q) | Q(city__icontains=q) | Q(country__icontains=q) |
                Q(short_description__icontains=q) | Q(description__icontains=q)
            )
        if city:
            qs = qs.filter(city__icontains=city)
        if country:
            qs = qs.filter(country__icontains=country)
        if featured in ("1", "true", "True", "yes"):
            qs = qs.filter(is_featured=True)
        return qs

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context


class PublicHotelDetailAPIView(PublicHotelMixin, APIView):
    def get(self, request, slug):
        hotel = self.get_hotel()
        room_types = RoomType.objects.filter(hotel=hotel).annotate(available_rooms=Count("rooms", filter=Q(rooms__is_active=True))).order_by("base_price", "name")
        reviews = HotelReview.objects.filter(hotel=hotel, is_approved=True).order_by("-created_at")[:10]
        experiences = HotelExperience.objects.filter(hotel=hotel, is_approved=True).prefetch_related("images").order_by("-created_at")[:10]
        gallery = RoomImage.objects.filter(hotel=hotel, is_active=True).order_by("order", "-is_primary")[:20]
        return Response({
            "hotel": PublicHotelSerializer(hotel, context={"request": request}).data,
            "room_types": PublicRoomTypeSerializer(room_types, many=True, context={"request": request}).data,
            "gallery": [self._image_payload(request, img) for img in gallery],
            "rating": {
                "average": HotelReview.objects.filter(hotel=hotel, is_approved=True).aggregate(avg=Avg("overall_rating"))["avg"] or hotel.star_rating,
                "count": HotelReview.objects.filter(hotel=hotel, is_approved=True).count(),
            },
            "reviews": PublicReviewSerializer(reviews, many=True, context={"request": request}).data,
            "experiences": PublicExperienceSerializer(experiences, many=True, context={"request": request}).data,
        })

    def _image_payload(self, request, image):
        url = image.image.url if image and image.image else None
        return {
            "id": image.id,
            "url": request.build_absolute_uri(url) if request and url else url,
            "title": image.title or image.alt_text or "",
            "caption": image.caption or "",
            "category": image.category,
            "is_primary": image.is_primary,
        }


class GuestRegisterAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = GuestRegisterSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        user = result["user"]
        return Response({
            "message": "Account created successfully.",
            "token": result["token"],
            "user": {"id": user.id, "username": user.get_username()},
        }, status=status.HTTP_201_CREATED)


class GuestLoginAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = GuestLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = data["user"]
        return Response({
            "message": "Login successful.",
            "token": data["token"],
            "user": {"id": user.id, "username": user.get_username()},
            "guest": PublicGuestSerializer(data["guest"]).data if data.get("guest") else None,
        })


class GuestMeAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [TokenAuthentication, SessionAuthentication]

    def get(self, request):
        guest = get_guest_for_user(request.user)
        return Response({
            "user": {"id": request.user.id, "username": request.user.get_username(), "email": request.user.email},
            "guest": PublicGuestSerializer(guest).data if guest else None,
        })


class GuestBookingListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [TokenAuthentication, SessionAuthentication]

    def get(self, request):
        guest = get_guest_for_user(request.user)
        if not guest:
            return Response({"bookings": []})
        qs = Booking.objects.filter(guest=guest).select_related("hotel", "room", "room__room_type", "guest").order_by("-created_at")
        return Response({"bookings": PublicBookingSerializer(qs, many=True).data})


class PublicAllExperienceListAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = [OptionalTokenAuthentication, SessionAuthentication]

    def get(self, request):
        qs = HotelExperience.objects.filter(
            is_approved=True, hotel__is_active=True, hotel__is_published=True
        ).select_related("hotel").prefetch_related("images").order_by("-created_at")
        hotel_slug = request.query_params.get("hotel")
        if hotel_slug:
            qs = qs.filter(hotel__slug=hotel_slug)
        return Response({
            "experiences": PublicExperienceSerializer(qs, many=True, context={"request": request}).data
        })


class PublicExperienceDetailAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = [OptionalTokenAuthentication, SessionAuthentication]

    def get(self, request, pk):
        experience = get_object_or_404(
            HotelExperience.objects.select_related("hotel").prefetch_related("images"),
            pk=pk,
            is_approved=True,
            hotel__is_active=True,
            hotel__is_published=True,
        )
        reviews = HotelReview.objects.filter(
            hotel=experience.hotel, is_approved=True
        ).order_by("-created_at")[:20]
        return Response({
            "experience": PublicExperienceSerializer(experience, context={"request": request}).data,
            "hotel": PublicHotelSerializer(experience.hotel, context={"request": request}).data,
            "reviews": PublicReviewSerializer(reviews, many=True, context={"request": request}).data,
        })


class PublicHomeAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = [OptionalTokenAuthentication, SessionAuthentication]

    def get(self, request):
        hotels = Hotel.objects.filter(is_active=True, is_published=True)
        featured = hotels.filter(is_featured=True).order_by("name")[:10]
        recommended = hotels.order_by("name")[:10]
        experiences = HotelExperience.objects.filter(is_approved=True, hotel__is_active=True, hotel__is_published=True).select_related("hotel").prefetch_related("images").order_by("-created_at")[:10]
        destinations = hotels.exclude(city__isnull=True).exclude(city="").values("city", "country").annotate(properties=Count("id")).order_by("city")[:20]
        return Response({
            "featured_hotels": PublicHotelSerializer(featured, many=True, context={"request": request}).data,
            "recommended_hotels": PublicHotelSerializer(recommended, many=True, context={"request": request}).data,
            "experiences": PublicExperienceSerializer(experiences, many=True, context={"request": request}).data,
            "destinations": list(destinations),
            "vibes": ["Beach", "City Escape", "Countryside", "Family", "Business", "Romantic", "Wellness"],
        })


class PublicHotelRoomsAPIView(PublicHotelMixin, APIView):
    def get(self, request, slug):
        hotel = self.get_hotel()
        rooms = Room.objects.filter(hotel=hotel, is_active=True).select_related("room_type").order_by("room_type__base_price", "number")
        room_types = RoomType.objects.filter(hotel=hotel).annotate(available_rooms=Count("rooms", filter=Q(rooms__is_active=True))).order_by("base_price", "name")
        return Response({
            "rooms": PublicRoomSerializer(rooms, many=True).data,
            "room_types": PublicRoomTypeSerializer(room_types, many=True, context={"request": request}).data,
        })


class PublicHotelRoomDetailAPIView(PublicHotelMixin, APIView):
    def get(self, request, slug, pk):
        hotel = self.get_hotel()
        room = get_object_or_404(Room.objects.select_related("room_type"), pk=pk, hotel=hotel, is_active=True)
        return Response(PublicRoomSerializer(room).data)


class PublicHotelGalleryAPIView(PublicHotelMixin, APIView):
    def get(self, request, slug):
        hotel = self.get_hotel()
        qs = RoomImage.objects.filter(hotel=hotel, is_active=True).order_by("order", "-is_primary")
        category = request.query_params.get("category")
        if category:
            qs = qs.filter(category=category)
        data = []
        for img in qs:
            url = img.image.url if img.image else None
            data.append({
                "id": img.id, "url": request.build_absolute_uri(url) if request and url else url,
                "title": img.title or "", "caption": img.caption or "", "category": img.category,
                "is_primary": img.is_primary, "room_type": img.room_type_id, "room": img.room_id,
            })
        return Response({"images": data})


class PublicAvailabilityAPIView(PublicHotelMixin, APIView):
    def get(self, request, slug):
        hotel = self.get_hotel()
        check_in = request.query_params.get("check_in")
        check_out = request.query_params.get("check_out")
        if not check_in or not check_out:
            return Response({"detail": "check_in and check_out are required."}, status=status.HTTP_400_BAD_REQUEST)

        from rest_framework.fields import DateField
        parser = DateField()
        try:
            check_in_date = parser.to_internal_value(check_in)
            check_out_date = parser.to_internal_value(check_out)
        except Exception:
            return Response({"detail": "Use YYYY-MM-DD date format."}, status=status.HTTP_400_BAD_REQUEST)

        if check_out_date <= check_in_date:
            return Response({"detail": "check_out must be after check_in."}, status=status.HTTP_400_BAD_REQUEST)

        room_ids = available_rooms(hotel, check_in_date, check_out_date).values_list("id", flat=True)
        room_types = RoomType.objects.filter(hotel=hotel, rooms__id__in=room_ids).annotate(
            available_rooms=Count("rooms", distinct=True)
        ).order_by("base_price", "name")
        return Response({"room_types": PublicRoomTypeSerializer(room_types, many=True, context={"request": request}).data})


class PublicMenuAPIView(PublicHotelMixin, APIView):
    def get(self, request, slug):
        hotel = self.get_hotel()
        categories = MenuCategory.objects.filter(hotel=hotel, is_active=True).order_by("sort_order", "name")
        items = MenuItem.objects.filter(hotel=hotel, is_active=True).select_related("category").order_by("category__sort_order", "name")
        return Response({
            "categories": PublicMenuCategorySerializer(categories, many=True).data,
            "items": PublicMenuItemSerializer(items, many=True).data,
        })


class PublicMenuCategoryListAPIView(PublicHotelMixin, APIView):
    def get(self, request, slug):
        hotel = self.get_hotel()
        categories = MenuCategory.objects.filter(hotel=hotel, is_active=True).order_by("sort_order", "name")
        return Response({"categories": PublicMenuCategorySerializer(categories, many=True).data})


class PublicMenuItemListAPIView(PublicHotelMixin, APIView):
    def get(self, request, slug):
        hotel = self.get_hotel()
        items = MenuItem.objects.filter(hotel=hotel, is_active=True).select_related("category")
        category = request.query_params.get("category")
        if category:
            items = items.filter(category_id=category)
        items = items.order_by("category__sort_order", "name")
        return Response({"items": PublicMenuItemSerializer(items, many=True).data})


class PublicMenuItemDetailAPIView(PublicHotelMixin, APIView):
    def get(self, request, slug, pk):
        hotel = self.get_hotel()
        item = get_object_or_404(
            MenuItem.objects.select_related("category"),
            pk=pk,
            hotel=hotel,
            is_active=True,
        )
        return Response(PublicMenuItemSerializer(item).data)


class PublicBarAPIView(PublicHotelMixin, APIView):
    def get(self, request, slug):
        hotel = self.get_hotel()
        categories = BarCategory.objects.filter(hotel=hotel, is_active=True).order_by("sort_order", "name")
        items = BarItem.objects.filter(hotel=hotel, is_active=True).select_related("category").order_by("category__sort_order", "name")
        return Response({
            "categories": PublicBarCategorySerializer(categories, many=True).data,
            "items": PublicBarItemSerializer(items, many=True).data,
        })


class PublicBarCategoryListAPIView(PublicHotelMixin, APIView):
    def get(self, request, slug):
        hotel = self.get_hotel()
        categories = BarCategory.objects.filter(hotel=hotel, is_active=True).order_by("sort_order", "name")
        return Response({"categories": PublicBarCategorySerializer(categories, many=True).data})


class PublicBarItemListAPIView(PublicHotelMixin, APIView):
    def get(self, request, slug):
        hotel = self.get_hotel()
        items = BarItem.objects.filter(hotel=hotel, is_active=True).select_related("category")
        category = request.query_params.get("category")
        if category:
            items = items.filter(category_id=category)
        items = items.order_by("category__sort_order", "name")
        return Response({"items": PublicBarItemSerializer(items, many=True).data})


class PublicBarItemDetailAPIView(PublicHotelMixin, APIView):
    def get(self, request, slug, pk):
        hotel = self.get_hotel()
        item = get_object_or_404(
            BarItem.objects.select_related("category"),
            pk=pk,
            hotel=hotel,
            is_active=True,
        )
        return Response(PublicBarItemSerializer(item).data)


class PublicBookingCreateAPIView(PublicHotelMixin, APIView):
    def post(self, request, slug):
        hotel = self.get_hotel()
        serializer = PublicBookingCreateSerializer(data=request.data, context={"hotel": hotel, "request": request})
        serializer.is_valid(raise_exception=True)
        booking = serializer.save()
        return Response({
            "message": "Booking received successfully.",
            "booking": PublicBookingSerializer(booking).data,
        }, status=status.HTTP_201_CREATED)


class PublicRestaurantOrderCreateAPIView(PublicHotelMixin, APIView):
    def post(self, request, slug):
        hotel = self.get_hotel()
        serializer = PublicRestaurantOrderCreateSerializer(data=request.data, context={"hotel": hotel, "request": request})
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        return Response({
            "message": "Food order received successfully.",
            "order": {"id": order.id, "order_number": order.order_number, "status": order.status, "total": order.total},
        }, status=status.HTTP_201_CREATED)


class PublicBarOrderCreateAPIView(PublicHotelMixin, APIView):
    def post(self, request, slug):
        hotel = self.get_hotel()
        serializer = PublicBarOrderCreateSerializer(data=request.data, context={"hotel": hotel, "request": request})
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        return Response({
            "message": "Drink order received successfully.",
            "order": {"id": order.id, "order_number": order.order_number, "status": order.status, "total": order.total},
        }, status=status.HTTP_201_CREATED)


class PublicExperienceListCreateAPIView(PublicHotelMixin, APIView):
    authentication_classes = [OptionalTokenAuthentication, TokenAuthentication, SessionAuthentication]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_permissions(self):
        if self.request.method == "POST":
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def get(self, request, slug):
        hotel = self.get_hotel()
        qs = HotelExperience.objects.filter(hotel=hotel, is_approved=True).prefetch_related("images").order_by("-created_at")
        return Response({
            "experiences": PublicExperienceSerializer(qs, many=True, context={"request": request}).data
        })

    def post(self, request, slug):
        hotel = self.get_hotel()
        data = request.data.copy()
        if hasattr(request, "FILES") and request.FILES.getlist("images"):
            data.setlist("images", request.FILES.getlist("images"))
        serializer = PublicExperienceCreateSerializer(data=data, context={"hotel": hotel, "request": request})
        serializer.is_valid(raise_exception=True)
        experience = serializer.save()
        return Response({
            "message": "Experience posted successfully.",
            "experience": PublicExperienceSerializer(experience, context={"request": request}).data,
        }, status=status.HTTP_201_CREATED)


class PublicReviewListCreateAPIView(PublicHotelMixin, APIView):
    authentication_classes = [OptionalTokenAuthentication, TokenAuthentication, SessionAuthentication]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_permissions(self):
        if self.request.method == "POST":
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def get(self, request, slug):
        hotel = self.get_hotel()
        qs = HotelReview.objects.filter(hotel=hotel, is_approved=True).order_by("-created_at")
        return Response({
            "reviews": PublicReviewSerializer(qs, many=True, context={"request": request}).data
        })

    def post(self, request, slug):
        hotel = self.get_hotel()
        serializer = PublicReviewCreateSerializer(data=request.data, context={"hotel": hotel, "request": request})
        serializer.is_valid(raise_exception=True)
        review = serializer.save()
        return Response({
            "message": "Review posted successfully.",
            "review": PublicReviewSerializer(review, context={"request": request}).data,
        }, status=status.HTTP_201_CREATED)


class GuestProfileUpdateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [TokenAuthentication, SessionAuthentication]

    def patch(self, request):
        guest = get_guest_for_user(request.user)
        if not guest:
            return Response({"detail": "No guest profile found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = PublicGuestSerializer(guest, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"guest": serializer.data})


class GuestBookingDetailAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [TokenAuthentication, SessionAuthentication]

    def get_object(self, request, pk):
        guest = get_guest_for_user(request.user)
        return get_object_or_404(Booking.objects.select_related("hotel", "room", "room__room_type", "guest"), pk=pk, guest=guest)

    def get(self, request, pk):
        return Response({"booking": PublicBookingSerializer(self.get_object(request, pk)).data})

    def delete(self, request, pk):
        booking = self.get_object(request, pk)
        if booking.status in [Booking.Status.CHECKED_IN, Booking.Status.CHECKED_OUT, Booking.Status.CANCELLED]:
            return Response({"detail": "This booking cannot be cancelled."}, status=status.HTTP_400_BAD_REQUEST)
        booking.status = Booking.Status.CANCELLED
        booking.save(update_fields=["status", "updated_at"])
        return Response({"message": "Booking cancelled.", "booking": PublicBookingSerializer(booking).data})
