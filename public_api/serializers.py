from decimal import Decimal

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.authtoken.models import Token

from hotels.models import Hotel, HotelExperience, HotelExperienceImage, HotelReview
from rooms.models import Room, RoomType, RoomImage
from bookings.models import Booking, Guest
from restaurant.models import MenuCategory, MenuItem, RestaurantOrder, RestaurantOrderItem
from bar.models import BarCategory, BarItem, BarOrder, BarOrderItem


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


def get_guest_for_user(user):
    if not user or not user.is_authenticated:
        return None
    guest = Guest.objects.filter(user=user).select_related("hotel").first()
    if guest:
        return guest
    if getattr(user, "email", None):
        guest = Guest.objects.filter(email__iexact=user.email).select_related("hotel").first()
        if guest and not guest.user_id:
            guest.user = user
            guest.save(update_fields=["user", "updated_at"])
        return guest
    return None


class PublicHotelSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()
    cover_url = serializers.SerializerMethodField()
    map_url = serializers.SerializerMethodField()
    directions_url = serializers.SerializerMethodField()
    currencies = serializers.SerializerMethodField()

    class Meta:
        model = Hotel
        fields = [
            "id", "name", "slug", "email", "phone", "phone_alt", "whatsapp", "website",
            "city", "state", "country", "address_line1", "address_line2", "postal_code",
            "latitude", "longitude", "map_url", "directions_url", "star_rating",
            "total_rooms", "default_currency", "default_currency_symbol", "supported_currencies", "currencies", "check_in_time", "check_out_time", "short_description", "description",
            "logo_url", "cover_url", "brand_color_primary", "brand_color_secondary",
        ]

    def get_currencies(self, obj):
        return {
            "default": obj.default_currency,
            "symbol": obj.default_currency_symbol,
            "supported": obj.supported_currencies or [obj.default_currency],
        }

    def _absolute(self, url):
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request and url else url

    def get_logo_url(self, obj):
        image = getattr(obj, "logo", None)
        return self._absolute(image.url) if image else None

    def get_cover_url(self, obj):
        image = getattr(obj, "cover_image", None)
        return self._absolute(image.url) if image else None

    def get_map_url(self, obj):
        if obj.latitude is not None and obj.longitude is not None:
            return f"https://www.google.com/maps/search/?api=1&query={obj.latitude},{obj.longitude}"
        if obj.address_line1 or obj.city or obj.country:
            parts = [obj.address_line1, obj.city, obj.country]
            query = "+".join(str(p).replace(" ", "+") for p in parts if p)
            return f"https://www.google.com/maps/search/?api=1&query={query}"
        return None

    def get_directions_url(self, obj):
        if obj.latitude is not None and obj.longitude is not None:
            return f"https://www.google.com/maps/dir/?api=1&destination={obj.latitude},{obj.longitude}"
        return self.get_map_url(obj)


class PublicGuestSerializer(serializers.ModelSerializer):
    hotel_name = serializers.CharField(source="hotel.name", read_only=True)
    hotel_slug = serializers.CharField(source="hotel.slug", read_only=True)

    class Meta:
        model = Guest
        fields = [
            "id", "guest_id", "hotel", "hotel_name", "hotel_slug", "full_name", "preferred_name",
            "phone", "alternative_phone", "email", "nationality", "language", "address", "city",
            "country", "special_requests", "dietary_restrictions", "room_preferences",
            "marketing_consent", "newsletter_subscribed", "created_at",
        ]
        read_only_fields = ["id", "guest_id", "hotel", "hotel_name", "hotel_slug", "created_at"]


class GuestRegisterSerializer(serializers.Serializer):
    """Simple public account registration. Guests only need a username and password."""
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, min_length=6)

    def validate_username(self, value):
        username = value.strip()
        if not username:
            raise serializers.ValidationError("Username is required.")
        User = get_user_model()
        if User.objects.filter(username__iexact=username).exists():
            raise serializers.ValidationError("This username is already taken.")
        return username

    @transaction.atomic
    def create(self, validated_data):
        User = get_user_model()
        user = User.objects.create_user(
            username=validated_data["username"],
            password=validated_data["password"],
        )
        token, _ = Token.objects.get_or_create(user=user)
        return {"user": user, "token": token.key}


class GuestLoginSerializer(serializers.Serializer):
    """Simple public login by username and password."""
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        username = attrs["username"].strip()
        user = authenticate(username=username, password=attrs["password"])
        if not user:
            raise serializers.ValidationError("Invalid username or password.")
        if not user.is_active:
            raise serializers.ValidationError("This account is inactive.")
        guest = get_guest_for_user(user)
        token, _ = Token.objects.get_or_create(user=user)
        return {"user": user, "guest": guest, "token": token.key}


class PublicExperienceImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = HotelExperienceImage
        fields = ["id", "image_url", "created_at"]

    def get_image_url(self, obj):
        request = self.context.get("request")
        if obj.image:
            return request.build_absolute_uri(obj.image.url) if request else obj.image.url
        return None


class PublicExperienceSerializer(serializers.ModelSerializer):
    hotel_name = serializers.CharField(source="hotel.name", read_only=True)
    hotel_slug = serializers.CharField(source="hotel.slug", read_only=True)
    images = PublicExperienceImageSerializer(many=True, read_only=True)

    class Meta:
        model = HotelExperience
        fields = [
            "id", "hotel", "hotel_name", "hotel_slug", "guest_name", "place_visited",
            "activity", "rating", "experience_text", "images", "created_at",
        ]
        read_only_fields = ["id", "hotel", "hotel_name", "hotel_slug", "guest_name", "images", "created_at"]


class PublicExperienceCreateSerializer(serializers.Serializer):
    place_visited = serializers.CharField(max_length=255)
    activity = serializers.CharField(max_length=255)
    rating = serializers.IntegerField(min_value=1, max_value=5, default=5)
    experience_text = serializers.CharField()
    images = serializers.ListField(
        child=serializers.ImageField(),
        required=False,
        allow_empty=True,
        max_length=5,
    )

    @transaction.atomic
    def create(self, validated_data):
        hotel = self.context["hotel"]
        request = self.context["request"]
        images = validated_data.pop("images", [])
        user = request.user
        experience = HotelExperience.objects.create(
            hotel=hotel,
            guest_name=user.get_full_name() or user.get_username(),
            guest_email=getattr(user, "email", "") or "",
            is_approved=True,
            **validated_data,
        )
        for image in images:
            HotelExperienceImage.objects.create(experience=experience, image=image)
        return experience


class PublicReviewSerializer(serializers.ModelSerializer):
    hotel_name = serializers.CharField(source="hotel.name", read_only=True)
    hotel_slug = serializers.CharField(source="hotel.slug", read_only=True)

    class Meta:
        model = HotelReview
        fields = [
            "id", "hotel", "hotel_name", "hotel_slug", "guest_name",
            "overall_rating", "cleanliness_rating", "comfort_rating", "location_rating",
            "staff_rating", "facilities_rating", "value_rating", "title", "review_text",
            "pros", "cons", "stay_date_from", "stay_date_to", "room_number",
            "is_verified_stay", "hotel_response", "hotel_response_date", "created_at",
        ]
        read_only_fields = [
            "id", "hotel", "hotel_name", "hotel_slug", "guest_name",
            "is_verified_stay", "hotel_response", "hotel_response_date", "created_at",
        ]


class PublicReviewCreateSerializer(serializers.Serializer):
    overall_rating = serializers.DecimalField(max_digits=2, decimal_places=1, min_value=1, max_value=5)
    title = serializers.CharField(max_length=255)
    review_text = serializers.CharField()
    cleanliness_rating = serializers.DecimalField(max_digits=2, decimal_places=1, min_value=1, max_value=5, required=False, allow_null=True)
    comfort_rating = serializers.DecimalField(max_digits=2, decimal_places=1, min_value=1, max_value=5, required=False, allow_null=True)
    location_rating = serializers.DecimalField(max_digits=2, decimal_places=1, min_value=1, max_value=5, required=False, allow_null=True)
    staff_rating = serializers.DecimalField(max_digits=2, decimal_places=1, min_value=1, max_value=5, required=False, allow_null=True)
    facilities_rating = serializers.DecimalField(max_digits=2, decimal_places=1, min_value=1, max_value=5, required=False, allow_null=True)
    value_rating = serializers.DecimalField(max_digits=2, decimal_places=1, min_value=1, max_value=5, required=False, allow_null=True)
    pros = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    cons = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    stay_date_from = serializers.DateField(required=False)
    stay_date_to = serializers.DateField(required=False)
    room_number = serializers.CharField(max_length=50, required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        start = attrs.get("stay_date_from")
        end = attrs.get("stay_date_to")
        if not start:
            start = timezone.now().date()
            attrs["stay_date_from"] = start
        if not end:
            attrs["stay_date_to"] = start
        if attrs["stay_date_to"] < attrs["stay_date_from"]:
            raise serializers.ValidationError("stay_date_to cannot be before stay_date_from.")
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        hotel = self.context["hotel"]
        request = self.context["request"]
        user = request.user
        return HotelReview.objects.create(
            hotel=hotel,
            guest_name=user.get_full_name() or user.get_username(),
            guest_email=getattr(user, "email", "") or "guest@example.com",
            is_approved=True,
            **validated_data,
        )


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


class PublicRoomSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="room_type.name", read_only=True)
    description = serializers.CharField(source="room_type.description", read_only=True)
    price = serializers.DecimalField(source="room_type.base_price", max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Room
        fields = [
            "id", "number", "floor", "status", "room_type", "name", "description",
            "price", "image_url",
        ]


class PublicMenuCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuCategory
        fields = ["id", "name", "description", "image_url", "sort_order"]


class PublicMenuItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    is_available = serializers.BooleanField(source="is_active", read_only=True)

    class Meta:
        model = MenuItem
        fields = [
            "id", "category", "category_name", "name", "description", "price",
            "is_available", "image_url",
            "is_vegetarian", "is_vegan", "is_gluten_free", "is_spicy",
            "is_featured", "is_recommended", "preparation_time",
        ]


class PublicBarCategorySerializer(serializers.ModelSerializer):
    description = serializers.SerializerMethodField()

    class Meta:
        model = BarCategory
        fields = ["id", "name", "description", "image_url", "sort_order"]

    def get_description(self, obj):
        return getattr(obj, "description", "") or ""


class PublicBarItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    description = serializers.SerializerMethodField()
    price = serializers.DecimalField(source="selling_price", max_digits=12, decimal_places=2, read_only=True)
    is_available = serializers.SerializerMethodField()

    class Meta:
        model = BarItem
        fields = [
            "id", "category", "category_name", "name", "description", "unit",
            "selling_price", "price", "is_available", "is_out_of_stock", "image_url",
        ]

    def get_description(self, obj):
        return getattr(obj, "description", "") or ""

    def get_is_available(self, obj):
        return bool(obj.is_active and not obj.is_out_of_stock)


class PublicBookingCreateSerializer(serializers.Serializer):
    room = serializers.IntegerField(required=False, allow_null=True)
    room_type = serializers.IntegerField(required=False, allow_null=True)
    full_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    check_in = serializers.DateField()
    check_out = serializers.DateField()
    adults = serializers.IntegerField(min_value=1, default=1)
    children = serializers.IntegerField(min_value=0, default=0)
    special_requests = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        hotel = self.context["hotel"]
        request = self.context.get("request")
        auth_guest = get_guest_for_user(getattr(request, "user", None))
        if auth_guest:
            attrs["auth_guest"] = auth_guest
            attrs.setdefault("full_name", auth_guest.full_name)
            attrs.setdefault("phone", auth_guest.phone)
            attrs.setdefault("email", auth_guest.email)
        if not attrs.get("full_name"):
            raise serializers.ValidationError({"full_name": "Full name is required."})
        if not attrs.get("phone"):
            raise serializers.ValidationError({"phone": "Phone number is required."})
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
        request = self.context.get("request")
        room = validated_data.pop("selected_room")
        auth_guest = validated_data.pop("auth_guest", None)
        validated_data.pop("room", None)
        validated_data.pop("room_type", None)

        guest_defaults = {
            "full_name": validated_data["full_name"],
            "email": validated_data.get("email") or "",
            "special_requests": validated_data.get("special_requests") or "",
        }
        if request and request.user and request.user.is_authenticated:
            guest_defaults["user"] = request.user
        guest, _ = Guest.objects.update_or_create(
            hotel=hotel,
            phone=validated_data["phone"],
            defaults=guest_defaults,
        )
        if auth_guest and auth_guest.hotel_id == hotel.id and auth_guest.id != guest.id:
            guest = auth_guest
        booking = Booking(
            hotel=hotel,
            guest=guest,
            room=room,
            check_in=validated_data["check_in"],
            check_out=validated_data["check_out"],
            adults=validated_data.get("adults") or 1,
            children=validated_data.get("children") or 0,
            source=Booking.Source.MOBILE_APP if request and request.user and request.user.is_authenticated else Booking.Source.WEBSITE,
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
    hotel_name = serializers.CharField(source="hotel.name", read_only=True)
    hotel_slug = serializers.CharField(source="hotel.slug", read_only=True)
    nights = serializers.IntegerField(read_only=True)
    balance_due = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Booking
        fields = [
            "id", "booking_number", "confirmation_code", "hotel", "hotel_name", "hotel_slug",
            "guest_name", "room_number", "room_type", "check_in", "check_out", "nights",
            "adults", "children", "status", "payment_status", "subtotal", "tax_amount",
            "total_amount", "amount_paid", "balance_due", "special_requests", "created_at",
        ]


class PublicOrderItemInputSerializer(serializers.Serializer):
    item = serializers.IntegerField()
    qty = serializers.IntegerField(min_value=1)
    note = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)


class PublicRestaurantOrderCreateSerializer(serializers.Serializer):
    customer_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    customer_phone = serializers.CharField(max_length=30, required=False, allow_blank=True, allow_null=True)
    customer_email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    booking = serializers.IntegerField(required=False, allow_null=True)
    room_charge = serializers.BooleanField(default=False)
    special_instructions = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    items = PublicOrderItemInputSerializer(many=True)

    def validate(self, attrs):
        hotel = self.context["hotel"]
        request = self.context.get("request")
        guest = get_guest_for_user(getattr(request, "user", None))
        if guest:
            attrs.setdefault("customer_name", guest.full_name)
            attrs.setdefault("customer_phone", guest.phone)
            attrs.setdefault("customer_email", guest.email)
        if not attrs.get("customer_name"):
            raise serializers.ValidationError({"customer_name": "Customer name is required."})
        if not attrs.get("items"):
            raise serializers.ValidationError("Add at least one food item.")
        if attrs.get("room_charge") and not attrs.get("booking"):
            raise serializers.ValidationError("A booking is required for room-charge orders.")
        if attrs.get("booking"):
            qs = Booking.objects.filter(id=attrs["booking"], hotel=hotel)
            if guest:
                qs = qs.filter(guest=guest)
            if not qs.exists():
                raise serializers.ValidationError("Booking was not found for this hotel/guest.")
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
    guest_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    booking = serializers.IntegerField(required=False, allow_null=True)
    room_charge = serializers.BooleanField(default=False)
    items = PublicOrderItemInputSerializer(many=True)

    def validate(self, attrs):
        hotel = self.context["hotel"]
        request = self.context.get("request")
        guest = get_guest_for_user(getattr(request, "user", None))
        if guest:
            attrs.setdefault("guest_name", guest.full_name)
        if not attrs.get("guest_name"):
            raise serializers.ValidationError({"guest_name": "Guest name is required."})
        if not attrs.get("items"):
            raise serializers.ValidationError("Add at least one drink item.")
        if attrs.get("room_charge") and not attrs.get("booking"):
            raise serializers.ValidationError("A booking is required for room-charge orders.")
        if attrs.get("booking"):
            qs = Booking.objects.filter(id=attrs["booking"], hotel=hotel)
            if guest:
                qs = qs.filter(guest=guest)
            if not qs.exists():
                raise serializers.ValidationError("Booking was not found for this hotel/guest.")
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
