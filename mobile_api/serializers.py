from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models, transaction
from django.db.models import Count, Sum, Q, Avg
from django.utils import timezone
from datetime import timedelta
from rest_framework import serializers
from rest_framework.authtoken.models import Token
from accounts.models import HotelMember
from hotels.models import Hotel
from restaurant.models import (
    MenuCategory,
    MenuItem,
    Table,
    RestaurantOrder,
    RestaurantOrderItem,
)
from bar.models import BarItem, BarOrder, BarOrderItem


# =========================
# AUTH
# =========================

class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(
            username=attrs.get("username"),
            password=attrs.get("password"),
        )

        if not user:
            raise serializers.ValidationError("Invalid username or password.")

        if not user.is_active:
            raise serializers.ValidationError("This account is inactive.")

        token, _ = Token.objects.get_or_create(user=user)

        attrs["user"] = user
        attrs["token"] = token.key
        return attrs


class HotelMiniSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()

    class Meta:
        model = Hotel
        fields = ["id", "name", "slug", "role"]

    def get_role(self, obj):
        user = self.context.get("user")

        if not user or not user.is_authenticated:
            return None

        member = HotelMember.objects.filter(
            hotel=obj,
            user=user,
            is_active=True,
        ).first()

        return member.role if member else None


# =========================
# USER PROFILE
# =========================

class UserProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    joined_date = serializers.DateTimeField(source="date_joined", read_only=True)
    
    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "date_joined",
            "joined_date",
            "is_active",
            "last_login",
        ]
        read_only_fields = ["id", "date_joined", "last_login", "is_active"]

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username


class UpdateProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=False)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    
    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name"]

    def validate_username(self, value):
        user = self.context["request"].user
        if User.objects.exclude(pk=user.pk).filter(username=value).exists():
            raise serializers.ValidationError("This username is already taken.")
        return value

    def validate_email(self, value):
        if value:
            user = self.context["request"].user
            if User.objects.exclude(pk=user.pk).filter(email=value).exists():
                raise serializers.ValidationError("This email is already registered.")
        return value

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=6)
    confirm_password = serializers.CharField(write_only=True, min_length=6)

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        
        if attrs["current_password"] == attrs["new_password"]:
            raise serializers.ValidationError({"new_password": "New password must be different from current password."})
        
        return attrs

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save()
        return user


# =========================
# STATISTICS
# =========================

class OrderStatisticsSerializer(serializers.Serializer):
    total_orders = serializers.IntegerField()
    completed_orders = serializers.IntegerField()
    pending_orders = serializers.IntegerField()
    cancelled_orders = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    average_order_value = serializers.DecimalField(max_digits=12, decimal_places=2)


class RestaurantStatisticsSerializer(serializers.Serializer):
    period = serializers.ChoiceField(
        choices=["today", "week", "month", "year", "all"],
        default="today"
    )
    
    def get_orders_queryset(self, hotel_id, period):
        now = timezone.now()
        
        if period == "today":
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "week":
            start_date = now - timedelta(days=7)
        elif period == "month":
            start_date = now - timedelta(days=30)
        elif period == "year":
            start_date = now - timedelta(days=365)
        else:
            start_date = None
        
        queryset = RestaurantOrder.objects.filter(hotel_id=hotel_id)
        
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        
        return queryset
    
    def to_representation(self, instance):
        hotel_id = self.context.get("hotel_id")
        period = instance.get("period", "today")
        
        orders = self.get_orders_queryset(hotel_id, period)
        
        total_orders = orders.count()
        completed_orders = orders.filter(status=RestaurantOrder.Status.PAID).count()
        pending_orders = orders.filter(
            status__in=[RestaurantOrder.Status.OPEN, RestaurantOrder.Status.KITCHEN]
        ).count()
        cancelled_orders = orders.filter(status=RestaurantOrder.Status.CANCELLED).count()
        
        total_revenue = orders.filter(
            status=RestaurantOrder.Status.PAID
        ).aggregate(total=Sum("total"))["total"] or 0
        
        avg_order_value = total_revenue / completed_orders if completed_orders > 0 else 0
        
        # Top selling items
        top_items = RestaurantOrderItem.objects.filter(
            order__in=orders,
            order__status=RestaurantOrder.Status.PAID
        ).values(
            "item__name"
        ).annotate(
            total_quantity=Sum("qty"),
            total_revenue=Sum("line_total")
        ).order_by("-total_quantity")[:5]
        
        # Orders by hour (for heatmap)
        orders_by_hour = orders.filter(
            status=RestaurantOrder.Status.PAID
        ).extra(
            {"hour": "EXTRACT(hour FROM created_at)"}
        ).values("hour").annotate(
            count=Count("id")
        ).order_by("hour")
        
        return {
            "period": period,
            "summary": {
                "total_orders": total_orders,
                "completed_orders": completed_orders,
                "pending_orders": pending_orders,
                "cancelled_orders": cancelled_orders,
                "total_revenue": total_revenue,
                "average_order_value": round(avg_order_value, 2),
                "completion_rate": round((completed_orders / total_orders * 100) if total_orders > 0 else 0, 2),
            },
            "top_items": list(top_items),
            "orders_by_hour": list(orders_by_hour),
        }


class BarStatisticsSerializer(serializers.Serializer):
    period = serializers.ChoiceField(
        choices=["today", "week", "month", "year", "all"],
        default="today"
    )
    
    def get_orders_queryset(self, hotel_id, period):
        now = timezone.now()
        
        if period == "today":
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "week":
            start_date = now - timedelta(days=7)
        elif period == "month":
            start_date = now - timedelta(days=30)
        elif period == "year":
            start_date = now - timedelta(days=365)
        else:
            start_date = None
        
        queryset = BarOrder.objects.filter(hotel_id=hotel_id)
        
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        
        return queryset
    
    def to_representation(self, instance):
        hotel_id = self.context.get("hotel_id")
        period = instance.get("period", "today")
        
        orders = self.get_orders_queryset(hotel_id, period)
        
        total_orders = orders.count()
        served_orders = orders.filter(status=BarOrder.Status.SERVED).count()
        pending_orders = orders.filter(status=BarOrder.Status.OPEN).count()
        cancelled_orders = orders.filter(status=BarOrder.Status.CANCELLED).count()
        
        total_revenue = orders.filter(
            status=BarOrder.Status.SERVED
        ).aggregate(total=Sum("total"))["total"] or 0
        
        avg_order_value = total_revenue / served_orders if served_orders > 0 else 0
        
        # Top selling drinks
        top_drinks = BarOrderItem.objects.filter(
            order__in=orders,
            order__status=BarOrder.Status.SERVED
        ).values(
            "item__name",
            "item__category__name"
        ).annotate(
            total_quantity=Sum("qty"),
            total_revenue=Sum("line_total")
        ).order_by("-total_quantity")[:5]
        
        # Stock alerts
        low_stock_items = BarItem.objects.filter(
            hotel_id=hotel_id,
            is_active=True,
            track_stock=True,
            stock_qty__lte=models.F("reorder_level")
        ).values("id", "name", "stock_qty", "reorder_level")
        
        return {
            "period": period,
            "summary": {
                "total_orders": total_orders,
                "served_orders": served_orders,
                "pending_orders": pending_orders,
                "cancelled_orders": cancelled_orders,
                "total_revenue": total_revenue,
                "average_order_value": round(avg_order_value, 2),
                "service_rate": round((served_orders / total_orders * 100) if total_orders > 0 else 0, 2),
            },
            "top_drinks": list(top_drinks),
            "low_stock_alerts": list(low_stock_items),
        }


class DashboardStatisticsSerializer(serializers.Serializer):
    def to_representation(self, instance):
        user = self.context["request"].user
        hotels = HotelMember.objects.filter(user=user, is_active=True).values_list("hotel_id", flat=True)
        
        # Restaurant stats
        restaurant_orders = RestaurantOrder.objects.filter(hotel_id__in=hotels)
        restaurant_today = restaurant_orders.filter(
            created_at__date=timezone.now().date()
        )
        
        # Bar stats
        bar_orders = BarOrder.objects.filter(hotel_id__in=hotels)
        bar_today = bar_orders.filter(
            created_at__date=timezone.now().date()
        )
        
        # Today's totals
        today_orders = restaurant_today.count() + bar_today.count()
        today_revenue = (restaurant_today.filter(status=RestaurantOrder.Status.PAID).aggregate(t=Sum("total"))["t"] or 0) + \
                       (bar_today.filter(status=BarOrder.Status.SERVED).aggregate(t=Sum("total"))["t"] or 0)
        
        # Active orders
        active_restaurant_orders = restaurant_orders.filter(
            status__in=[RestaurantOrder.Status.OPEN, RestaurantOrder.Status.KITCHEN]
        ).count()
        active_bar_orders = bar_orders.filter(
            status=BarOrder.Status.OPEN
        ).count()
        
        return {
            "today": {
                "total_orders": today_orders,
                "total_revenue": today_revenue,
                "restaurant_orders": restaurant_today.count(),
                "bar_orders": bar_today.count(),
            },
            "active_orders": {
                "restaurant": active_restaurant_orders,
                "bar": active_bar_orders,
                "total": active_restaurant_orders + active_bar_orders,
            },
            "total_hotels": len(hotels),
            "total_restaurant_items": MenuItem.objects.filter(hotel_id__in=hotels, is_active=True).count(),
            "total_bar_items": BarItem.objects.filter(hotel_id__in=hotels, is_active=True).count(),
        }


# =========================
# RESTAURANT
# =========================

class TableSerializer(serializers.ModelSerializer):
    area_name = serializers.CharField(source="area.name", read_only=True)

    class Meta:
        model = Table
        fields = ["id", "number", "seats", "area_name"]


class MenuCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuCategory
        fields = ["id", "name", "description", "image_url"]


class MenuItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = MenuItem
        fields = [
            "id",
            "category",
            "category_name",
            "name",
            "description",
            "image_url",
            "price",
            "preparation_time",
            "is_active",
            "track_stock",
            "stock_qty",
        ]


class RestaurantOrderItemInputSerializer(serializers.Serializer):
    item = serializers.IntegerField()
    qty = serializers.IntegerField(min_value=1)
    note = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=255,
    )


class RestaurantOrderItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)
    line_total = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = RestaurantOrderItem
        fields = [
            "id",
            "item",
            "item_name",
            "qty",
            "unit_price",
            "note",
            "line_total",
        ]


class RestaurantOrderSerializer(serializers.ModelSerializer):
    items = RestaurantOrderItemSerializer(many=True, read_only=True)
    table_number = serializers.CharField(source="table.number", read_only=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = RestaurantOrder
        fields = [
            "id",
            "order_number",
            "hotel",
            "table",
            "table_number",
            "customer_name",
            "customer_phone",
            "status",
            "special_instructions",
            "kitchen_notes",
            "subtotal",
            "discount",
            "tax",
            "service_charge",
            "total",
            "created_at",
            "items",
        ]
        read_only_fields = ["hotel", "status", "created_at"]


class RestaurantOrderCreateSerializer(serializers.Serializer):
    hotel = serializers.IntegerField()
    table = serializers.IntegerField(required=False, allow_null=True)
    customer_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    customer_phone = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    special_instructions = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    send_to_kitchen = serializers.BooleanField(default=True)
    items = RestaurantOrderItemInputSerializer(many=True)

    def validate(self, attrs):
        request = self.context["request"]
        hotel_id = attrs["hotel"]

        if not HotelMember.objects.filter(
            hotel_id=hotel_id,
            user=request.user,
            is_active=True,
        ).exists():
            raise serializers.ValidationError("You are not a member of this hotel.")

        if not attrs.get("items"):
            raise serializers.ValidationError("Add at least one item.")

        table_id = attrs.get("table")
        if table_id:
            if not Table.objects.filter(
                id=table_id,
                hotel_id=hotel_id,
                is_active=True,
            ).exists():
                raise serializers.ValidationError(
                    "Selected table does not belong to this hotel."
                )

        for row in attrs["items"]:
            if not MenuItem.objects.filter(
                id=row["item"],
                hotel_id=hotel_id,
                is_active=True,
            ).exists():
                raise serializers.ValidationError(
                    f"Menu item {row['item']} is invalid or inactive."
                )

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        items_data = validated_data.pop("items")
        hotel_id = validated_data.pop("hotel")
        send_to_kitchen = validated_data.pop("send_to_kitchen", True)

        order = RestaurantOrder.objects.create(
            hotel_id=hotel_id,
            created_by=request.user,
            updated_by=request.user,
            **validated_data,
        )

        for row in items_data:
            menu_item = MenuItem.objects.get(
                id=row["item"],
                hotel_id=hotel_id,
                is_active=True,
            )

            order_item = RestaurantOrderItem(
                order=order,
                item=menu_item,
                qty=row["qty"],
                note=row.get("note") or "",
                unit_price=menu_item.price,
            )
            order_item.full_clean()
            order_item.save()

        if send_to_kitchen:
            try:
                order.set_status(RestaurantOrder.Status.KITCHEN, user=request.user)
            except DjangoValidationError as exc:
                raise serializers.ValidationError(exc.messages)

        return order


# =========================
# BAR
# =========================

class BarItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)
    is_out_of_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = BarItem
        fields = [
            "id",
            "category",
            "category_name",
            "name",
            "sku",
            "image_url",
            "unit",
            "selling_price",
            "cost_price",
            "track_stock",
            "stock_qty",
            "reorder_level",
            "is_active",
            "is_low_stock",
            "is_out_of_stock",
        ]


class BarOrderItemInputSerializer(serializers.Serializer):
    item = serializers.IntegerField()
    qty = serializers.IntegerField(min_value=1)
    note = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=255,
    )


class BarOrderItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)
    unit = serializers.CharField(source="item.unit", read_only=True)
    line_total = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = BarOrderItem
        fields = [
            "id",
            "item",
            "item_name",
            "unit",
            "qty",
            "unit_price",
            "note",
            "line_total",
        ]


class BarOrderSerializer(serializers.ModelSerializer):
    items = BarOrderItemSerializer(many=True, read_only=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    item_count = serializers.IntegerField(read_only=True)
    display_name = serializers.CharField(read_only=True)

    class Meta:
        model = BarOrder
        fields = [
            "id",
            "order_number",
            "hotel",
            "booking",
            "guest_name",
            "display_name",
            "room_charge",
            "status",
            "subtotal",
            "discount",
            "tax",
            "total",
            "item_count",
            "created_at",
            "closed_at",
            "items",
        ]
        read_only_fields = [
            "hotel",
            "status",
            "created_at",
            "closed_at",
        ]


class BarOrderCreateSerializer(serializers.Serializer):
    hotel = serializers.IntegerField()
    booking = serializers.IntegerField(required=False, allow_null=True)
    guest_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    room_charge = serializers.BooleanField(default=False)
    mark_served = serializers.BooleanField(default=True)
    items = BarOrderItemInputSerializer(many=True)

    def validate(self, attrs):
        request = self.context["request"]
        hotel_id = attrs["hotel"]

        if not HotelMember.objects.filter(
            hotel_id=hotel_id,
            user=request.user,
            is_active=True,
        ).exists():
            raise serializers.ValidationError("You are not a member of this hotel.")

        if not attrs.get("items"):
            raise serializers.ValidationError("Add at least one item.")

        if attrs.get("room_charge") and not attrs.get("booking"):
            raise serializers.ValidationError(
                "A booking is required when room_charge is enabled."
            )

        for row in attrs["items"]:
            try:
                bar_item = BarItem.objects.get(
                    id=row["item"],
                    hotel_id=hotel_id,
                    is_active=True,
                )
            except BarItem.DoesNotExist:
                raise serializers.ValidationError(
                    f"Bar item {row['item']} is invalid or inactive."
                )

            if bar_item.track_stock and row["qty"] > bar_item.stock_qty:
                raise serializers.ValidationError(
                    f"Not enough stock for {bar_item.name}. Available: {bar_item.stock_qty}"
                )

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        items_data = validated_data.pop("items")
        hotel_id = validated_data.pop("hotel")
        mark_served = validated_data.pop("mark_served", True)

        order = BarOrder.objects.create(
            hotel_id=hotel_id,
            created_by=request.user,
            **validated_data,
        )

        for row in items_data:
            bar_item = BarItem.objects.select_for_update().get(
                id=row["item"],
                hotel_id=hotel_id,
                is_active=True,
            )

            order_item = BarOrderItem(
                order=order,
                item=bar_item,
                qty=row["qty"],
                note=row.get("note") or "",
                unit_price=bar_item.selling_price,
            )
            order_item.full_clean()
            order_item.save()

        if mark_served:
            try:
                order.set_status(BarOrder.Status.SERVED, user=request.user)
            except DjangoValidationError as exc:
                raise serializers.ValidationError(exc.messages)

        return order


# =========================
# STATUS UPDATE
# =========================

class StatusUpdateSerializer(serializers.Serializer):
    status = serializers.CharField()

# =========================
# SUPERUSER HOTEL REGISTRATION / SETUP API
# =========================

from rooms.models import RoomType, Room


class SuperuserHotelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Hotel
        fields = [
            "id",
            "name",
            "slug",
            "hotel_chain",
            "category",
            "email",
            "phone",
            "phone_alt",
            "whatsapp",
            "website",
            "address_line1",
            "address_line2",
            "city",
            "state",
            "postal_code",
            "country",
            "latitude",
            "longitude",
            "tax_number",
            "business_registration",
            "year_established",
            "number_of_employees",
            "star_rating",
            "total_rooms",
            "total_floors",
            "default_currency",
            "default_currency_symbol",
            "supported_currencies",
            "short_description",
            "description",
            "meta_description",
            "meta_keywords",
            "brand_color_primary",
            "brand_color_secondary",
            "is_active",
            "is_featured",
            "is_verified",
            "is_published",
            "facebook_url",
            "instagram_url",
            "twitter_url",
            "linkedin_url",
            "youtube_url",
            "tripadvisor_url",
            "check_in_time",
            "check_out_time",
            "reception_open_time",
            "reception_close_time",
            "cancellation_policy",
            "payment_policy",
            "house_rules",
            "child_policy",
            "pet_policy",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "slug", "created_by", "created_at", "updated_at"]

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            validated_data.setdefault("created_by", request.user)
        return super().create(validated_data)


class SuperuserRoomTypeSerializer(serializers.ModelSerializer):
    hotel_name = serializers.CharField(source="hotel.name", read_only=True)

    class Meta:
        model = RoomType
        fields = ["id", "hotel", "hotel_name", "name", "description", "base_price"]
        read_only_fields = ["id", "hotel_name"]


class SuperuserRoomSerializer(serializers.ModelSerializer):
    hotel_name = serializers.CharField(source="hotel.name", read_only=True)
    room_type_name = serializers.CharField(source="room_type.name", read_only=True)

    class Meta:
        model = Room
        fields = [
            "id",
            "hotel",
            "hotel_name",
            "room_type",
            "room_type_name",
            "number",
            "floor",
            "status",
            "image_url",
            "is_active",
        ]
        read_only_fields = ["id", "hotel_name", "room_type_name"]

    def validate(self, attrs):
        hotel = attrs.get("hotel") or getattr(self.instance, "hotel", None)
        room_type = attrs.get("room_type") or getattr(self.instance, "room_type", None)
        if hotel and room_type and room_type.hotel_id != hotel.id:
            raise serializers.ValidationError({"room_type": "Room type must belong to the selected hotel."})
        return attrs


class SuperuserMenuCategorySerializer(serializers.ModelSerializer):
    hotel_name = serializers.CharField(source="hotel.name", read_only=True)

    class Meta:
        model = MenuCategory
        fields = [
            "id",
            "hotel",
            "hotel_name",
            "name",
            "description",
            "image_url",
            "sort_order",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "hotel_name", "created_at", "updated_at"]


class SuperuserMenuItemSerializer(serializers.ModelSerializer):
    hotel_name = serializers.CharField(source="hotel.name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = MenuItem
        fields = [
            "id",
            "hotel",
            "hotel_name",
            "category",
            "category_name",
            "name",
            "description",
            "image_url",
            "ingredients",
            "price",
            "cost_price",
            "track_stock",
            "stock_qty",
            "reorder_level",
            "is_vegetarian",
            "is_vegan",
            "is_gluten_free",
            "is_spicy",
            "is_featured",
            "is_recommended",
            "is_active",
            "preparation_time",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "hotel_name", "category_name", "created_at", "updated_at"]

    def validate(self, attrs):
        hotel = attrs.get("hotel") or getattr(self.instance, "hotel", None)
        category = attrs.get("category") or getattr(self.instance, "category", None)
        if hotel and category and category.hotel_id != hotel.id:
            raise serializers.ValidationError({"category": "Menu category must belong to the selected hotel."})
        return attrs


class HotelRegistrationRoomTypeInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    base_price = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=0)


class HotelRegistrationRoomInputSerializer(serializers.Serializer):
    number = serializers.CharField(max_length=50)
    room_type = serializers.IntegerField(required=False)
    room_type_name = serializers.CharField(max_length=120, required=False)
    floor = serializers.CharField(max_length=50, required=False, allow_blank=True, allow_null=True)
    status = serializers.ChoiceField(choices=Room.Status.choices, required=False, default=Room.Status.AVAILABLE)
    is_active = serializers.BooleanField(required=False, default=True)

    def validate(self, attrs):
        if not attrs.get("room_type") and not attrs.get("room_type_name"):
            raise serializers.ValidationError("Provide either room_type or room_type_name for each room.")
        return attrs


class HotelRegistrationMenuCategoryInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    sort_order = serializers.IntegerField(required=False, default=0, min_value=0)
    is_active = serializers.BooleanField(required=False, default=True)


class HotelRegistrationMenuItemInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=160)
    category = serializers.IntegerField(required=False)
    category_name = serializers.CharField(max_length=120, required=False)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    ingredients = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    price = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=0)
    cost_price = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=0)
    track_stock = serializers.BooleanField(required=False, default=False)
    stock_qty = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=0)
    reorder_level = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=0)
    is_vegetarian = serializers.BooleanField(required=False, default=False)
    is_vegan = serializers.BooleanField(required=False, default=False)
    is_gluten_free = serializers.BooleanField(required=False, default=False)
    is_spicy = serializers.BooleanField(required=False, default=False)
    is_featured = serializers.BooleanField(required=False, default=False)
    is_recommended = serializers.BooleanField(required=False, default=False)
    is_active = serializers.BooleanField(required=False, default=True)
    preparation_time = serializers.IntegerField(required=False, default=15, min_value=0)

    def validate(self, attrs):
        if not attrs.get("category") and not attrs.get("category_name"):
            raise serializers.ValidationError("Provide either category or category_name for each menu item.")
        return attrs


class HotelRegistrationSerializer(serializers.Serializer):
    hotel = SuperuserHotelSerializer()
    room_types = HotelRegistrationRoomTypeInputSerializer(many=True, required=False)
    rooms = HotelRegistrationRoomInputSerializer(many=True, required=False)
    menu_categories = HotelRegistrationMenuCategoryInputSerializer(many=True, required=False)
    menu_items = HotelRegistrationMenuItemInputSerializer(many=True, required=False)

    @transaction.atomic
    def create(self, validated_data):
        request = self.context.get("request")
        hotel_data = validated_data.get("hotel")
        room_types_data = validated_data.get("room_types", [])
        rooms_data = validated_data.get("rooms", [])
        categories_data = validated_data.get("menu_categories", [])
        items_data = validated_data.get("menu_items", [])

        if request and request.user and request.user.is_authenticated:
            hotel_data.setdefault("created_by", request.user)
        hotel = Hotel.objects.create(**hotel_data)

        room_types_by_name = {}
        created_room_types = []
        for room_type_data in room_types_data:
            room_type = RoomType.objects.create(hotel=hotel, **room_type_data)
            room_types_by_name[room_type.name] = room_type
            created_room_types.append(room_type)

        categories_by_name = {}
        created_categories = []
        for category_data in categories_data:
            category = MenuCategory.objects.create(hotel=hotel, **category_data)
            categories_by_name[category.name] = category
            created_categories.append(category)

        created_rooms = []
        for room_data in rooms_data:
            room_type_id = room_data.pop("room_type", None)
            room_type_name = room_data.pop("room_type_name", None)
            if room_type_id:
                room_type = RoomType.objects.get(pk=room_type_id, hotel=hotel)
            else:
                room_type = room_types_by_name.get(room_type_name) or RoomType.objects.get(hotel=hotel, name=room_type_name)
            created_rooms.append(Room.objects.create(hotel=hotel, room_type=room_type, **room_data))

        created_items = []
        for item_data in items_data:
            category_id = item_data.pop("category", None)
            category_name = item_data.pop("category_name", None)
            if category_id:
                category = MenuCategory.objects.get(pk=category_id, hotel=hotel)
            else:
                category = categories_by_name.get(category_name) or MenuCategory.objects.get(hotel=hotel, name=category_name)
            created_items.append(MenuItem.objects.create(hotel=hotel, category=category, **item_data))

        return {
            "hotel": hotel,
            "room_types": created_room_types,
            "rooms": created_rooms,
            "menu_categories": created_categories,
            "menu_items": created_items,
        }

    def to_representation(self, instance):
        return {
            "hotel": SuperuserHotelSerializer(instance["hotel"]).data,
            "room_types": SuperuserRoomTypeSerializer(instance["room_types"], many=True).data,
            "rooms": SuperuserRoomSerializer(instance["rooms"], many=True).data,
            "menu_categories": SuperuserMenuCategorySerializer(instance["menu_categories"], many=True).data,
            "menu_items": SuperuserMenuItemSerializer(instance["menu_items"], many=True).data,
        }
