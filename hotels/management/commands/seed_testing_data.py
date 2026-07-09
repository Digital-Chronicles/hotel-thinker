from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import HotelMember
from bar.models import BarCategory, BarItem, BarOrder, BarOrderItem
from bookings.models import AdditionalCharge, Booking, Guest
from finance.models import Account, CashAccount, Invoice, InvoiceLineItem, JournalEntry, JournalLine, Vendor
from hotels.models import Hotel, HotelAmenity, HotelAmenityMapping, HotelCategory, HotelChain
from restaurant.models import DiningArea, MenuCategory, MenuItem, RestaurantOrder, RestaurantOrderItem, Table
from rooms.models import AssetCategory, Room, RoomAsset, RoomType
from services.models import ServiceBooking, ServiceCategory, ServicePayment, ServiceResource, ServiceUnit
from store.models import StoreCategory, StoreItem, StoreSale, StoreSaleItem, StoreStockMovement, StoreSupplier


D = Decimal


class Command(BaseCommand):
    help = "Create idempotent demo/testing data for the hotel management system."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default="TestPass123!",
            help="Password for the demo staff users. Default: TestPass123!",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        password = options["password"]
        today = timezone.localdate()
        now = timezone.now()
        User = get_user_model()

        admin = self._user(
            User,
            "demo.admin",
            "admin@demo.hotelthinker.test",
            password,
            first_name="Amara",
            last_name="Kato",
            is_staff=True,
            is_superuser=True,
        )
        front_desk = self._user(
            User,
            "demo.frontdesk",
            "frontdesk@demo.hotelthinker.test",
            password,
            first_name="Brian",
            last_name="Okello",
            is_staff=True,
        )

        chain, _ = HotelChain.objects.update_or_create(
            name="Hotel Thinker Demo Group",
            defaults={
                "website": "https://hotelthinker.site",
                "description": "Demo hotel group used for local testing.",
                "headquarters_address": "Kampala, Uganda",
            },
        )
        category, _ = HotelCategory.objects.update_or_create(
            name="Boutique Resort",
            defaults={"description": "Upscale boutique hotel with rooms, dining, bar, and services.", "star_rating_min": D("4.0"), "star_rating_max": D("5.0")},
        )
        hotel, _ = Hotel.objects.update_or_create(
            name="Lakeview Demo Hotel",
            defaults={
                "hotel_chain": chain,
                "category": category,
                "email": "stay@lakeview-demo.test",
                "phone": "+256700000001",
                "whatsapp": "+256700000001",
                "website": "https://hotelthinker.site",
                "address_line1": "Plot 42 Demo Avenue",
                "city": "Kampala",
                "country": "Uganda",
                "latitude": D("0.3475964"),
                "longitude": D("32.5825197"),
                "star_rating": D("4.5"),
                "total_rooms": 12,
                "total_floors": 3,
                "default_currency": "UGX",
                "default_currency_symbol": "UGX",
                "supported_currencies": ["UGX", "USD"],
                "short_description": "A seeded demo hotel for exercising local workflows.",
                "description": "Testing data for rooms, reservations, restaurant, bar, services, store, and finance modules.",
                "brand_color_primary": "#14532d",
                "brand_color_secondary": "#0f766e",
                "is_active": True,
                "is_featured": True,
                "is_verified": True,
                "is_published": True,
                "created_by": admin,
            },
        )

        self._member(hotel, admin, HotelMember.Role.ADMIN)
        self._member(hotel, front_desk, HotelMember.Role.FRONT_DESK)
        self._amenities(hotel)
        room_types, rooms = self._rooms(hotel)
        guests = self._guests(hotel, admin)
        bookings = self._bookings(hotel, rooms, guests, admin, today)
        self._restaurant(hotel, bookings, front_desk)
        self._bar(hotel, bookings, front_desk)
        self._services(hotel, bookings, front_desk, now)
        self._store(hotel, front_desk)
        self._room_assets(hotel, room_types, rooms)
        self._finance(hotel, bookings, admin, today)

        self.stdout.write(self.style.SUCCESS("Seeded testing data successfully."))
        self.stdout.write(f"Hotel: {hotel.name}")
        self.stdout.write(f"Users: demo.admin / demo.frontdesk")
        self.stdout.write(f"Password: {password}")

    def _user(self, User, username, email, password, **defaults):
        user, created = User.objects.update_or_create(username=username, defaults={"email": email, **defaults})
        if created or not user.has_usable_password():
            user.set_password(password)
            user.save(update_fields=["password"])
        return user

    def _member(self, hotel, user, role):
        defaults = {
            "role": role,
            "permission_level": HotelMember.PermissionLevel.FULL if role == HotelMember.Role.ADMIN else HotelMember.PermissionLevel.READ_WRITE,
            "work_email": user.email,
            "work_phone": "+256700000002",
            "hire_date": timezone.localdate() - timedelta(days=180),
            "is_active": True,
            "can_manage_bookings": True,
            "can_manage_rooms": True,
            "can_manage_inventory": role == HotelMember.Role.ADMIN,
            "can_view_financials": role == HotelMember.Role.ADMIN,
            "can_manage_reports": role == HotelMember.Role.ADMIN,
            "can_manage_settings": role == HotelMember.Role.ADMIN,
            "can_access_front_desk": True,
            "can_access_housekeeping": True,
            "can_access_restaurant": True,
            "can_access_finance": role == HotelMember.Role.ADMIN,
        }
        member, _ = HotelMember.objects.update_or_create(hotel=hotel, user=user, defaults=defaults)
        return member

    def _amenities(self, hotel):
        for name, category, paid in [
            ("Free Wi-Fi", "internet", False),
            ("Airport Shuttle", "parking", True),
            ("Swimming Pool", "pool_spa", False),
            ("Conference Room", "business", True),
            ("24-hour Reception", "services", False),
        ]:
            amenity, _ = HotelAmenity.objects.update_or_create(name=name, defaults={"category": category, "is_paid": paid})
            HotelAmenityMapping.objects.update_or_create(
                hotel=hotel,
                amenity=amenity,
                defaults={"is_available": True, "charge_amount": D("40000.00") if paid else None},
            )

    def _rooms(self, hotel):
        specs = [
            ("Standard Queen", D("180000.00"), ["101", "102", "103", "104"]),
            ("Deluxe King", D("280000.00"), ["201", "202", "203"]),
            ("Executive Suite", D("450000.00"), ["301", "302"]),
        ]
        room_types = {}
        rooms = []
        for name, price, numbers in specs:
            room_type, _ = RoomType.objects.update_or_create(
                hotel=hotel,
                name=name,
                defaults={"base_price": price, "description": f"{name} room for seeded testing."},
            )
            room_types[name] = room_type
            for number in numbers:
                room, _ = Room.objects.update_or_create(
                    hotel=hotel,
                    number=number,
                    defaults={"room_type": room_type, "floor": number[0], "status": Room.Status.AVAILABLE, "is_active": True},
                )
                rooms.append(room)
        return room_types, rooms

    def _guests(self, hotel, user):
        rows = [
            ("Grace Nambasa", "grace@example.test", "+256701111111", "Uganda", True),
            ("David Mwangi", "david@example.test", "+254702222222", "Kenya", False),
            ("Amina Yusuf", "amina@example.test", "+255703333333", "Tanzania", False),
            ("Noah Smith", "noah@example.test", "+12025550104", "United States", False),
        ]
        guests = []
        for full_name, email, phone, country, vip in rows:
            guest, _ = Guest.objects.update_or_create(
                hotel=hotel,
                email=email,
                defaults={
                    "full_name": full_name,
                    "phone": phone,
                    "country": country,
                    "nationality": country,
                    "guest_type": Guest.GuestType.VIP if vip else Guest.GuestType.INDIVIDUAL,
                    "is_vip": vip,
                    "marketing_consent": True,
                    "newsletter_subscribed": True,
                    "created_by": user,
                },
            )
            guests.append(guest)
        return guests

    def _bookings(self, hotel, rooms, guests, user, today):
        plans = [
            (guests[0], rooms[0], today - timedelta(days=1), today + timedelta(days=2), Booking.Status.CHECKED_IN, D("360000.00")),
            (guests[1], rooms[4], today + timedelta(days=3), today + timedelta(days=6), Booking.Status.CONFIRMED, D("200000.00")),
            (guests[2], rooms[7], today - timedelta(days=10), today - timedelta(days=7), Booking.Status.CHECKED_OUT, D("1350000.00")),
            (guests[3], rooms[2], today + timedelta(days=8), today + timedelta(days=10), Booking.Status.RESERVED, D("0.00")),
        ]
        bookings = []
        for guest, room, check_in, check_out, status, paid in plans:
            booking, _ = Booking.objects.update_or_create(
                hotel=hotel,
                guest=guest,
                room=room,
                check_in=check_in,
                check_out=check_out,
                defaults={
                    "status": status,
                    "source": Booking.Source.DIRECT,
                    "adults": 2,
                    "children": 0,
                    "tax_rate": D("18.00"),
                    "amount_paid": paid,
                    "special_requests": "Seeded testing booking.",
                    "created_by": user,
                },
            )
            bookings.append(booking)

        current = bookings[0]
        AdditionalCharge.objects.update_or_create(
            booking=current,
            description="Laundry service",
            defaults={"category": AdditionalCharge.Category.LAUNDRY, "quantity": 2, "unit_price": D("15000.00"), "created_by": user},
        )
        room = current.room
        room.status = Room.Status.OCCUPIED
        room.save(update_fields=["status"])
        return bookings

    def _restaurant(self, hotel, bookings, user):
        area, _ = DiningArea.objects.update_or_create(hotel=hotel, name="Garden Terrace", defaults={"is_active": True})
        table, _ = Table.objects.update_or_create(hotel=hotel, number="T1", defaults={"area": area, "seats": 4, "is_active": True})
        mains, _ = MenuCategory.objects.update_or_create(hotel=hotel, name="Mains", defaults={"sort_order": 1, "is_active": True})
        drinks, _ = MenuCategory.objects.update_or_create(hotel=hotel, name="Beverages", defaults={"sort_order": 2, "is_active": True})
        rolex, _ = MenuItem.objects.update_or_create(
            hotel=hotel,
            name="Lakeview Chicken Rolex",
            defaults={"category": mains, "price": D("28000.00"), "cost_price": D("12000.00"), "is_featured": True, "is_active": True},
        )
        juice, _ = MenuItem.objects.update_or_create(
            hotel=hotel,
            name="Passion Fruit Juice",
            defaults={"category": drinks, "price": D("12000.00"), "cost_price": D("4000.00"), "track_stock": True, "stock_qty": D("50.00"), "reorder_level": D("10.00")},
        )
        order, _ = RestaurantOrder.objects.update_or_create(
            hotel=hotel,
            order_number="RST-DEMO-0001",
            defaults={"table": table, "booking": bookings[0], "room_charge": True, "status": RestaurantOrder.Status.SERVED, "created_by": user},
        )
        RestaurantOrderItem.objects.update_or_create(order=order, item=rolex, defaults={"qty": 2, "unit_price": rolex.price})
        RestaurantOrderItem.objects.update_or_create(order=order, item=juice, defaults={"qty": 2, "unit_price": juice.price})

    def _bar(self, hotel, bookings, user):
        category, _ = BarCategory.objects.update_or_create(hotel=hotel, name="Soft Drinks", defaults={"sort_order": 1, "is_active": True})
        item, _ = BarItem.objects.update_or_create(
            hotel=hotel,
            name="Sparkling Water",
            defaults={"category": category, "sku": "BAR-WATER-001", "unit": "bottle", "selling_price": D("7000.00"), "cost_price": D("2500.00"), "stock_qty": D("72.00"), "reorder_level": D("12.00")},
        )
        order, _ = BarOrder.objects.update_or_create(
            hotel=hotel,
            order_number="BAR-DEMO-0001",
            defaults={"booking": bookings[0], "room_charge": True, "status": BarOrder.Status.SERVED, "created_by": user},
        )
        BarOrderItem.objects.update_or_create(order=order, item=item, defaults={"qty": 3, "unit_price": item.selling_price})

    def _services(self, hotel, bookings, user, now):
        wellness, _ = ServiceCategory.objects.update_or_create(hotel=hotel, name="Wellness", defaults={"sort_order": 1, "is_active": True})
        spa, _ = ServiceUnit.objects.update_or_create(
            hotel=hotel,
            name="Couples Spa Session",
            defaults={"category": wellness, "service_type": ServiceUnit.ServiceType.ACTIVITY, "pricing_mode": ServiceUnit.PricingMode.PER_SESSION, "base_price": D("95000.00"), "default_duration_minutes": 90, "max_capacity": 2},
        )
        room, _ = ServiceResource.objects.update_or_create(hotel=hotel, service=spa, name="Spa Room 1", defaults={"capacity": 2, "is_active": True})
        service_booking, _ = ServiceBooking.objects.update_or_create(
            hotel=hotel,
            reference="SRV-DEMO-0001",
            defaults={
                "booking": bookings[0],
                "service": spa,
                "resource": room,
                "customer_name": bookings[0].guest.full_name,
                "customer_phone": bookings[0].guest.phone,
                "attendants": 2,
                "scheduled_start": now + timedelta(hours=4),
                "post_to_room": False,
                "deposit_paid": D("50000.00"),
                "created_by": user,
            },
        )
        ServicePayment.objects.update_or_create(
            service_booking=service_booking,
            reference="SRV-PAY-DEMO-0001",
            defaults={"amount": D("50000.00"), "method": ServicePayment.Method.CASH, "received_by": user},
        )

    def _store(self, hotel, user):
        housekeeping, _ = StoreCategory.objects.update_or_create(hotel=hotel, name="Housekeeping", defaults={"is_active": True})
        towel, _ = StoreItem.objects.update_or_create(
            hotel=hotel,
            name="Bath Towel",
            defaults={"category": housekeeping, "sku": "HK-TOWEL-001", "unit": "pcs", "cost_price": D("18000.00"), "selling_price": D("25000.00"), "stock_qty": D("120.00"), "reorder_level": D("25.00")},
        )
        StoreStockMovement.objects.update_or_create(
            hotel=hotel,
            item=towel,
            reference="OPENING-DEMO",
            defaults={"movement_type": StoreStockMovement.MovementType.OPENING, "quantity": D("120.00"), "balance_after": D("120.00"), "created_by": user},
        )
        StoreSupplier.objects.update_or_create(
            hotel=hotel,
            name="Kampala Linen Supplies",
            defaults={"contact_person": "Sarah Namuli", "phone": "+256704444444", "email": "sales@linen-demo.test", "created_by": user},
        )
        sale, _ = StoreSale.objects.update_or_create(
            hotel=hotel,
            sale_number="STR-DEMO-0001",
            defaults={"customer_name": "Walk-in Guest", "customer_phone": "+256705555555", "status": StoreSale.Status.PAID, "created_by": user},
        )
        StoreSaleItem.objects.update_or_create(sale=sale, item=towel, defaults={"qty": D("2.00"), "unit_price": towel.selling_price})

    def _room_assets(self, hotel, room_types, rooms):
        furniture, _ = AssetCategory.objects.update_or_create(hotel=hotel, name="Furniture", defaults={"asset_type": "furniture"})
        RoomAsset.objects.update_or_create(
            hotel=hotel,
            room=rooms[0],
            name="Queen Bed Frame",
            defaults={
                "room_type": room_types["Standard Queen"],
                "category": furniture,
                "serial_number": "BED-DEMO-101",
                "brand": "Demo Furnishings",
                "purchase_date": timezone.localdate() - timedelta(days=365),
                "purchase_price": D("850000.00"),
                "current_value": D("720000.00"),
                "salvage_value": D("85000.00"),
            },
        )

    def _finance(self, hotel, bookings, user, today):
        accounts = {}
        for code, name, account_type, subtype in [
            ("1000", "Cash on Hand", Account.AccountType.ASSET, Account.SubType.CASH),
            ("1100", "Accounts Receivable", Account.AccountType.ASSET, Account.SubType.RECEIVABLE),
            ("2000", "Accounts Payable", Account.AccountType.LIABILITY, Account.SubType.PAYABLE),
            ("4000", "Room Revenue", Account.AccountType.REVENUE, Account.SubType.SALES),
            ("5000", "Operating Expenses", Account.AccountType.EXPENSE, Account.SubType.OPERATING_EXPENSE),
        ]:
            accounts[code], _ = Account.objects.update_or_create(
                hotel=hotel,
                account_code=code,
                defaults={"name": name, "account_type": account_type, "account_subtype": subtype, "is_active": True, "is_system": False},
            )
        CashAccount.objects.update_or_create(
            hotel=hotel,
            name="Front Desk Cash",
            defaults={"account_type": CashAccount.AccountType.CASH, "currency": hotel.default_currency, "opening_balance": D("500000.00"), "current_balance": D("500000.00"), "gl_account": accounts["1000"], "is_active": True},
        )
        Vendor.objects.update_or_create(
            hotel=hotel,
            vendor_code="VEN-DEMO-001",
            defaults={"name": "Kampala Linen Supplies", "phone": "+256704444444", "email": "accounts@linen-demo.test"},
        )
        invoice = Invoice.objects.filter(booking=bookings[0]).first()
        if invoice is None:
            invoice = Invoice(hotel=hotel, booking=bookings[0])
        invoice.invoice_number = "INV-DEMO-0001"
        invoice.customer_name = bookings[0].guest.full_name
        invoice.customer_email = bookings[0].guest.email
        invoice.customer_phone = bookings[0].guest.phone
        invoice.status = Invoice.Status.PARTIALLY_PAID
        invoice.invoice_date = today
        invoice.due_date = today + timedelta(days=7)
        invoice.currency = hotel.default_currency
        invoice.tax_rate = D("18.00")
        invoice.amount_paid = D("360000.00")
        invoice.receivable_account = accounts["1100"]
        invoice.revenue_account = accounts["4000"]
        invoice.save()
        InvoiceLineItem.objects.update_or_create(
            invoice=invoice,
            description="Room accommodation",
            defaults={"quantity": bookings[0].nights, "unit_price": bookings[0].nightly_rate, "tax_rate": D("18.00"), "booking": bookings[0]},
        )
        invoice.save()
        journal, _ = JournalEntry.objects.update_or_create(
            hotel=hotel,
            entry_number="JE-DEMO-0001",
            defaults={"entry_date": today, "description": "Seeded room revenue example", "status": JournalEntry.Status.DRAFT, "created_by": user},
        )
        JournalLine.objects.update_or_create(journal_entry=journal, account=accounts["1100"], defaults={"description": "Receivable", "debit": D("540000.00"), "credit": D("0.00")})
        JournalLine.objects.update_or_create(journal_entry=journal, account=accounts["4000"], defaults={"description": "Room revenue", "debit": D("0.00"), "credit": D("540000.00")})
