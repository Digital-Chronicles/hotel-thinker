from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from hotels.models import Hotel
from rooms.models import Room, RoomType, RoomImage
from bookings.models import Booking, Guest
from restaurant.models import MenuCategory, MenuItem, RestaurantOrder, RestaurantOrderItem
from bar.models import BarItem, BarOrder, BarOrderItem


ACTIVE_BOOKING_STATUSES = [
    Booking.Status.RESERVED,
    Booking.Status.CONFIRMED,
    Booking.Status.CHECKED_IN,
]


def available_rooms(hotel, check_in, check_out):
    booked_ids = Booking.objects.filter(
        hotel=hotel,
        status__in=ACTIVE_BOOKING_STATUSES,
        check_in__lt=check_out,
        check_out__gt=check_in,
    ).values_list("room_id", flat=True)
    return Room.objects.filter(
        hotel=hotel,
        is_active=True,
        status__in=[Room.Status.AVAILABLE, Room.Status.CLEANING],
    ).exclude(id__in=booked_ids).select_related("room_type")


class PublicHotelSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()
    cover_url = serializers.SerializerMethodField()

    class Meta:
        model = Hotel
        fields = [
            "id", "name", "slug", "email", "phone", "whatsapp", "website",
            "city", "state", "country", "address_line1", "star_rating",
            "short_description", "description", "logo_url", "cover_url",
        ]

    def _absolute(self, url):
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request and url else url

    def get_logo_url(self, obj):
        image = getattr(obj, "logo", None)
        return self._absolute(image.url) if image else None

    def get_cover_url(self, obj):
        image = getattr(obj, "cover_image", None)
        return self._absolute(image.url) if image else None


class PublicRoomTypeSerializer(serializers.ModelSerializer):
    available_rooms = serializers.IntegerField(read_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = RoomType
        fields = ["id", "name", "description", "base_price", "available_rooms", "image_url"]

    def get_image_url(self, obj):
        request = self.context.get("request")
        image = RoomImage.objects.filter(room_type=obj, is_active=True).order_by("order", "-is_primary").first()
        if image and image.image:
            return request.build_absolute_uri(image.image.url) if request else image.image.url
        return None


class PublicMenuCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuCategory
        fields = ["id", "name", "description", "sort_order"]


class PublicMenuItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = MenuItem
        fields = [
            "id", "category", "category_name", "name", "description", "price",
            "is_vegetarian", "is_vegan", "is_gluten_free", "is_spicy",
            "is_featured", "is_recommended", "preparation_time",
        ]


class PublicBarItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = BarItem
        fields = ["id", "category", "category_name", "name", "unit", "selling_price", "is_out_of_stock"]


class PublicBookingCreateSerializer(serializers.Serializer):
    room = serializers.IntegerField(required=False, allow_null=True)
    room_type = serializers.IntegerField(required=False, allow_null=True)
    full_name = serializers.CharField(max_length=255)
    phone = serializers.CharField(max_length=30)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    check_in = serializers.DateField()
    check_out = serializers.DateField()
    adults = serializers.IntegerField(min_value=1, default=1)
    children = serializers.IntegerField(min_value=0, default=0)
    special_requests = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        hotel = self.context["hotel"]
        if attrs["check_out"] <= attrs["check_in"]:
            raise serializers.ValidationError({"check_out": "Check-out must be after check-in."})
        if attrs["check_in"] < timezone.localdate():
            raise serializers.ValidationError({"check_in": "Check-in cannot be in the past."})

        rooms = available_rooms(hotel, attrs["check_in"], attrs["check_out"])
        if attrs.get("room"):
            rooms = rooms.filter(id=attrs["room"])
        elif attrs.get("room_type"):
            rooms = rooms.filter(room_type_id=attrs["room_type"])

        room = rooms.order_by("room_type__base_price", "number").first()
        if not room:
            raise serializers.ValidationError("No room is available for the selected dates.")
        attrs["selected_room"] = room
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        hotel = self.context["hotel"]
        room = validated_data.pop("selected_room")
        validated_data.pop("room", None)
        validated_data.pop("room_type", None)

        guest, _ = Guest.objects.update_or_create(
            hotel=hotel,
            phone=validated_data["phone"],
            defaults={
                "full_name": validated_data["full_name"],
                "email": validated_data.get("email") or "",
                "special_requests": validated_data.get("special_requests") or "",
            },
        )
        booking = Booking(
            hotel=hotel,
            guest=guest,
            room=room,
            check_in=validated_data["check_in"],
            check_out=validated_data["check_out"],
            adults=validated_data.get("adults") or 1,
            children=validated_data.get("children") or 0,
            source=Booking.Source.WEBSITE,
            status=Booking.Status.RESERVED,
            special_requests=validated_data.get("special_requests") or "",
        )
        try:
            booking.full_clean()
            booking.save()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
        return booking


class PublicBookingSerializer(serializers.ModelSerializer):
    guest_name = serializers.CharField(source="guest.full_name", read_only=True)
    room_number = serializers.CharField(source="room.number", read_only=True)
    room_type = serializers.CharField(source="room.room_type.name", read_only=True)
    nights = serializers.IntegerField(read_only=True)
    balance_due = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Booking
        fields = [
            "id", "booking_number", "confirmation_code", "guest_name", "room_number",
            "room_type", "check_in", "check_out", "nights", "adults", "children",
            "status", "payment_status", "subtotal", "tax_amount", "total_amount",
            "amount_paid", "balance_due", "special_requests", "created_at",
        ]


class PublicOrderItemInputSerializer(serializers.Serializer):
    item = serializers.IntegerField()
    qty = serializers.IntegerField(min_value=1)
    note = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)


class PublicRestaurantOrderCreateSerializer(serializers.Serializer):
    customer_name = serializers.CharField(max_length=255)
    customer_phone = serializers.CharField(max_length=30, required=False, allow_blank=True, allow_null=True)
    customer_email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    booking = serializers.IntegerField(required=False, allow_null=True)
    room_charge = serializers.BooleanField(default=False)
    special_instructions = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    items = PublicOrderItemInputSerializer(many=True)

    def validate(self, attrs):
        hotel = self.context["hotel"]
        if not attrs.get("items"):
            raise serializers.ValidationError("Add at least one food item.")
        if attrs.get("room_charge") and not attrs.get("booking"):
            raise serializers.ValidationError("A booking is required for room-charge orders.")
        if attrs.get("booking") and not Booking.objects.filter(id=attrs["booking"], hotel=hotel).exists():
            raise serializers.ValidationError("Booking was not found for this hotel.")
        for row in attrs["items"]:
            if not MenuItem.objects.filter(id=row["item"], hotel=hotel, is_active=True).exists():
                raise serializers.ValidationError(f"Menu item {row['item']} is invalid or inactive.")
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        hotel = self.context["hotel"]
        items = validated_data.pop("items")
        order = RestaurantOrder.objects.create(hotel=hotel, **validated_data)
        for row in items:
            item = MenuItem.objects.get(id=row["item"], hotel=hotel, is_active=True)
            RestaurantOrderItem.objects.create(
                order=order, item=item, qty=row["qty"], unit_price=item.price, note=row.get("note") or ""
            )
        try:
            order.set_status(RestaurantOrder.Status.KITCHEN)
        except DjangoValidationError:
            pass
        return order


class PublicBarOrderCreateSerializer(serializers.Serializer):
    guest_name = serializers.CharField(max_length=255)
    booking = serializers.IntegerField(required=False, allow_null=True)
    room_charge = serializers.BooleanField(default=False)
    items = PublicOrderItemInputSerializer(many=True)

    def validate(self, attrs):
        hotel = self.context["hotel"]
        if not attrs.get("items"):
            raise serializers.ValidationError("Add at least one drink item.")
        if attrs.get("room_charge") and not attrs.get("booking"):
            raise serializers.ValidationError("A booking is required for room-charge orders.")
        if attrs.get("booking") and not Booking.objects.filter(id=attrs["booking"], hotel=hotel).exists():
            raise serializers.ValidationError("Booking was not found for this hotel.")
        for row in attrs["items"]:
            try:
                item = BarItem.objects.get(id=row["item"], hotel=hotel, is_active=True)
            except BarItem.DoesNotExist:
                raise serializers.ValidationError(f"Bar item {row['item']} is invalid or inactive.")
            if item.track_stock and Decimal(row["qty"]) > item.stock_qty:
                raise serializers.ValidationError(f"Not enough stock for {item.name}. Available: {item.stock_qty}")
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        hotel = self.context["hotel"]
        items = validated_data.pop("items")
        order = BarOrder.objects.create(hotel=hotel, **validated_data)
        for row in items:
            item = BarItem.objects.select_for_update().get(id=row["item"], hotel=hotel, is_active=True)
            BarOrderItem.objects.create(
                order=order, item=item, qty=row["qty"], unit_price=item.selling_price, note=row.get("note") or ""
            )
        try:
            order.set_status(BarOrder.Status.SERVED)
        except DjangoValidationError:
            pass
        return order
