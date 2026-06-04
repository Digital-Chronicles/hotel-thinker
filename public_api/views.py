from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.response import Response
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.views import APIView

from hotels.models import Hotel, HotelExperience, HotelReview
from rooms.models import RoomType
from restaurant.models import MenuCategory, MenuItem
from bar.models import BarItem
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
    PublicRoomTypeSerializer,
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
        city = self.request.query_params.get("city")
        country = self.request.query_params.get("country")
        if city:
            qs = qs.filter(city__icontains=city)
        if country:
            qs = qs.filter(country__icontains=country)
        return qs

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context


class PublicHotelDetailAPIView(PublicHotelMixin, APIView):
    def get(self, request, slug):
        return Response(PublicHotelSerializer(self.get_hotel(), context={"request": request}).data)


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


class PublicBarAPIView(PublicHotelMixin, APIView):
    def get(self, request, slug):
        items = BarItem.objects.filter(hotel=self.get_hotel(), is_active=True).select_related("category").order_by("category__sort_order", "name")
        return Response({"items": PublicBarItemSerializer(items, many=True).data})


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
