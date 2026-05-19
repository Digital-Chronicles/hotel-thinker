from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from hotels.models import Hotel
from rooms.models import RoomType
from restaurant.models import MenuCategory, MenuItem, RestaurantOrder
from bar.models import BarItem, BarOrder

from .serializers import (
    PublicHotelSerializer,
    PublicRoomTypeSerializer,
    PublicMenuCategorySerializer,
    PublicMenuItemSerializer,
    PublicBarItemSerializer,
    PublicBookingCreateSerializer,
    PublicBookingSerializer,
    PublicRestaurantOrderCreateSerializer,
    PublicBarOrderCreateSerializer,
    available_rooms,
)


class PublicHotelMixin:
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get_hotel(self):
        return get_object_or_404(Hotel, slug=self.kwargs["slug"], is_active=True)


class PublicHotelListAPIView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    serializer_class = PublicHotelSerializer

    def get_queryset(self):
        return Hotel.objects.filter(is_active=True).order_by("name")


class PublicHotelDetailAPIView(PublicHotelMixin, APIView):
    def get(self, request, slug):
        return Response(PublicHotelSerializer(self.get_hotel(), context={"request": request}).data)


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
        serializer = PublicRestaurantOrderCreateSerializer(data=request.data, context={"hotel": hotel})
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        return Response({
            "message": "Food order received successfully.",
            "order": {"id": order.id, "order_number": order.order_number, "status": order.status, "total": order.total},
        }, status=status.HTTP_201_CREATED)


class PublicBarOrderCreateAPIView(PublicHotelMixin, APIView):
    def post(self, request, slug):
        hotel = self.get_hotel()
        serializer = PublicBarOrderCreateSerializer(data=request.data, context={"hotel": hotel})
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        return Response({
            "message": "Drink order received successfully.",
            "order": {"id": order.id, "order_number": order.order_number, "status": order.status, "total": order.total},
        }, status=status.HTTP_201_CREATED)
