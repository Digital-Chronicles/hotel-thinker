from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from django.contrib.auth import update_session_auth_hash

from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from accounts.models import HotelMember
from hotels.models import Hotel
from restaurant.models import MenuCategory, MenuItem, Table, RestaurantOrder
from bar.models import BarItem, BarOrder
from .serializers import (
    LoginSerializer,
    HotelMiniSerializer,
    TableSerializer,
    MenuCategorySerializer,
    MenuItemSerializer,
    BarItemSerializer,
    RestaurantOrderSerializer,
    RestaurantOrderCreateSerializer,
    BarOrderSerializer,
    BarOrderCreateSerializer,
    StatusUpdateSerializer,
    DashboardStatisticsSerializer,
    RestaurantStatisticsSerializer,
    BarStatisticsSerializer,
    UserProfileSerializer,
    UpdateProfileSerializer,
    ChangePasswordSerializer,
)


def user_hotel_ids(user):
    if not user or not user.is_authenticated:
        return []

    return list(
        HotelMember.objects.filter(
            user=user,
            is_active=True,
        ).values_list("hotel_id", flat=True)
    )


class HotelAccessMixin:
    hotel_query_param = "hotel"

    def get_allowed_hotel_ids(self):
        return user_hotel_ids(self.request.user)

    def get_hotel_id_from_query(self, required=True):
        hotel_id = self.request.query_params.get(self.hotel_query_param)

        if not hotel_id:
            if required:
                raise ValidationError({"hotel": "hotel query parameter is required."})
            return None

        allowed_ids = [str(x) for x in self.get_allowed_hotel_ids()]

        if str(hotel_id) not in allowed_ids:
            raise PermissionDenied("You do not have access to this hotel.")

        return hotel_id

    def filter_by_user_hotels(self, qs):
        return qs.filter(hotel_id__in=self.get_allowed_hotel_ids())


class LoginAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]

        hotels = Hotel.objects.filter(
            id__in=user_hotel_ids(user),
            is_active=True,
        ).order_by("name")

        return Response(
            {
                "token": serializer.validated_data["token"],
                "user": {
                    "id": user.id,
                    "username": user.get_username(),
                    "name": user.get_full_name() or user.get_username(),
                },
                "hotels": HotelMiniSerializer(
                    hotels,
                    many=True,
                    context={"user": user},
                ).data,
            },
            status=status.HTTP_200_OK,
        )


class MeAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        hotels = Hotel.objects.filter(
            id__in=user_hotel_ids(request.user),
            is_active=True,
        ).order_by("name")

        return Response(
            {
                "user": {
                    "id": request.user.id,
                    "username": request.user.get_username(),
                    "name": request.user.get_full_name() or request.user.get_username(),
                    "email": request.user.email,
                    "first_name": request.user.first_name,
                    "last_name": request.user.last_name,
                },
                "hotels": HotelMiniSerializer(
                    hotels,
                    many=True,
                    context={"user": request.user},
                ).data,
            }
        )


# =========================
# USER PROFILE VIEWS
# =========================

class UserProfileAPIView(APIView):
    """Get current user profile"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data)


class UpdateProfileAPIView(APIView):
    """Update current user profile"""
    permission_classes = [IsAuthenticated]

    def put(self, request):
        serializer = UpdateProfileSerializer(
            request.user, 
            data=request.data,
            context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request):
        serializer = UpdateProfileSerializer(
            request.user, 
            data=request.data, 
            partial=True,
            context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordAPIView(APIView):
    """Change user password"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={'request': request}
        )
        if serializer.is_valid():
            user = serializer.save()
            # Update session to prevent logout
            update_session_auth_hash(request, user)
            return Response(
                {"message": "Password changed successfully"},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# =========================
# STATISTICS VIEWS
# =========================

class DashboardStatisticsAPIView(APIView):
    """Get dashboard statistics for all user hotels"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = DashboardStatisticsSerializer(
            context={'request': request}
        )
        return Response(serializer.data)


class RestaurantStatisticsAPIView(APIView):
    """Get restaurant statistics for a specific hotel"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        hotel_id = request.query_params.get('hotel_id')
        period = request.query_params.get('period', 'today')
        
        # Check hotel access
        allowed_ids = [str(x) for x in user_hotel_ids(request.user)]
        if str(hotel_id) not in allowed_ids:
            raise PermissionDenied("You do not have access to this hotel.")
        
        serializer = RestaurantStatisticsSerializer(
            data={'period': period},
            context={'request': request, 'hotel_id': hotel_id}
        )
        if serializer.is_valid():
            return Response(serializer.validated_data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class BarStatisticsAPIView(APIView):
    """Get bar statistics for a specific hotel"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        hotel_id = request.query_params.get('hotel_id')
        period = request.query_params.get('period', 'today')
        
        # Check hotel access
        allowed_ids = [str(x) for x in user_hotel_ids(request.user)]
        if str(hotel_id) not in allowed_ids:
            raise PermissionDenied("You do not have access to this hotel.")
        
        serializer = BarStatisticsSerializer(
            data={'period': period},
            context={'request': request, 'hotel_id': hotel_id}
        )
        if serializer.is_valid():
            return Response(serializer.validated_data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# =========================
# RESTAURANT VIEWS
# =========================

class RestaurantMenuAPIView(HotelAccessMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        hotel_id = self.get_hotel_id_from_query(required=True)

        categories = MenuCategory.objects.filter(
            hotel_id=hotel_id,
            is_active=True,
        ).order_by("name")

        items = MenuItem.objects.filter(
            hotel_id=hotel_id,
            is_active=True,
        ).select_related("category").order_by("category__name", "name")

        return Response(
            {
                "categories": MenuCategorySerializer(categories, many=True).data,
                "items": MenuItemSerializer(items, many=True).data,
            }
        )


class RestaurantTablesAPIView(HotelAccessMixin, generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TableSerializer

    def get_queryset(self):
        hotel_id = self.get_hotel_id_from_query(required=True)

        return Table.objects.filter(
            hotel_id=hotel_id,
            is_active=True,
        ).select_related("area").order_by("number")


class RestaurantOrderListCreateAPIView(HotelAccessMixin, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        return (
            RestaurantOrderCreateSerializer
            if self.request.method == "POST"
            else RestaurantOrderSerializer
        )

    def get_queryset(self):
        qs = RestaurantOrder.objects.filter(
            hotel_id__in=self.get_allowed_hotel_ids(),
        ).prefetch_related("items__item").select_related("table")

        hotel_id = self.request.query_params.get("hotel")
        status_value = self.request.query_params.get("status")

        if hotel_id:
            if str(hotel_id) not in [str(x) for x in self.get_allowed_hotel_ids()]:
                raise PermissionDenied("You do not have access to this hotel.")
            qs = qs.filter(hotel_id=hotel_id)

        if status_value:
            qs = qs.filter(status=status_value)

        return qs.order_by("-created_at")

    def create(self, request, *args, **kwargs):
        serializer = RestaurantOrderCreateSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        order = serializer.save()

        return Response(
            RestaurantOrderSerializer(order).data,
            status=status.HTTP_201_CREATED,
        )


class RestaurantOrderDetailAPIView(HotelAccessMixin, generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = RestaurantOrderSerializer

    def get_queryset(self):
        return RestaurantOrder.objects.filter(
            hotel_id__in=self.get_allowed_hotel_ids(),
        ).prefetch_related("items__item").select_related("table")


class RestaurantOrderStatusAPIView(HotelAccessMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        serializer = StatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        order = get_object_or_404(
            RestaurantOrder,
            pk=pk,
            hotel_id__in=self.get_allowed_hotel_ids(),
        )

        try:
            order.set_status(
                serializer.validated_data["status"],
                user=request.user,
            )
        except DjangoValidationError as exc:
            return Response(
                {"detail": exc.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(RestaurantOrderSerializer(order).data)


# =========================
# BAR VIEWS
# =========================

class BarItemsAPIView(HotelAccessMixin, generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BarItemSerializer

    def get_queryset(self):
        hotel_id = self.get_hotel_id_from_query(required=True)

        return BarItem.objects.filter(
            hotel_id=hotel_id,
            is_active=True,
        ).select_related("category").order_by(
            "category__sort_order",
            "name",
        )


class BarOrderListCreateAPIView(HotelAccessMixin, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        return (
            BarOrderCreateSerializer
            if self.request.method == "POST"
            else BarOrderSerializer
        )

    def get_queryset(self):
        qs = BarOrder.objects.filter(
            hotel_id__in=self.get_allowed_hotel_ids(),
        ).prefetch_related("items__item").select_related("booking")

        hotel_id = self.request.query_params.get("hotel")
        status_value = self.request.query_params.get("status")

        if hotel_id:
            if str(hotel_id) not in [str(x) for x in self.get_allowed_hotel_ids()]:
                raise PermissionDenied("You do not have access to this hotel.")
            qs = qs.filter(hotel_id=hotel_id)

        if status_value:
            qs = qs.filter(status=status_value)

        return qs.order_by("-created_at")

    def create(self, request, *args, **kwargs):
        serializer = BarOrderCreateSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        order = serializer.save()

        return Response(
            BarOrderSerializer(order).data,
            status=status.HTTP_201_CREATED,
        )


class BarOrderDetailAPIView(HotelAccessMixin, generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BarOrderSerializer

    def get_queryset(self):
        return BarOrder.objects.filter(
            hotel_id__in=self.get_allowed_hotel_ids(),
        ).prefetch_related("items__item").select_related("booking")


class BarOrderStatusAPIView(HotelAccessMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        serializer = StatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        order = get_object_or_404(
            BarOrder,
            pk=pk,
            hotel_id__in=self.get_allowed_hotel_ids(),
        )

        try:
            order.set_status(
                serializer.validated_data["status"],
                user=request.user,
            )
        except DjangoValidationError as exc:
            return Response(
                {"detail": exc.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(BarOrderSerializer(order).data)
    

class UserStatisticsAPIView(APIView):
    """Get statistics for the current user"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        
        # Get all orders from restaurants and bars where user is involved
        from restaurant.models import RestaurantOrder
        from bar.models import BarOrder
        
        # Restaurant orders
        restaurant_orders = RestaurantOrder.objects.filter(created_by=user)
        bar_orders = BarOrder.objects.filter(created_by=user)
        
        total_orders = restaurant_orders.count() + bar_orders.count()
        completed_orders = restaurant_orders.filter(status='completed').count() + bar_orders.filter(status='served').count()
        
        # Calculate completion rate
        completion_rate = (completed_orders / total_orders * 100) if total_orders > 0 else 0
        
        # Calculate total revenue
        total_revenue = (
            restaurant_orders.filter(status='completed').aggregate(Sum('total'))['total__sum'] or 0
        ) + (
            bar_orders.filter(status='served').aggregate(Sum('total'))['total__sum'] or 0
        )
        
        # Calculate average order value
        average_order_value = total_revenue / completed_orders if completed_orders > 0 else 0
        
        # Mock rating and hours worked (you can implement real logic)
        rating = 4.8
        hours_worked = 1247
        
        return Response({
            'total_orders': total_orders,
            'completed_orders': completed_orders,
            'rating': rating,
            'hours_worked': hours_worked,
            'completion_rate': round(completion_rate, 1),
            'total_revenue': total_revenue,
            'average_order_value': round(average_order_value, 2),
        })


