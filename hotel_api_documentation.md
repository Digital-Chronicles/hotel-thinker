# Hotel Thinker API Documentation

Generated from the uploaded Django project `hotel.zip`.

## Base URLs

- Public guest API: `/api/public/`
- Staff/mobile API: `/api/mobile/`

For local development, examples use:

```text
http://127.0.0.1:8000
```

Replace this with your deployed domain, for example:

```text
https://your-domain.com
```

## Authentication

The APIs use Django REST Framework token authentication.

Send authenticated requests with:

```http
Authorization: Token <token>
Content-Type: application/json
Accept: application/json
```

Public read endpoints generally do not require authentication. Guest profile, guest bookings, posting reviews/experiences, and mobile/staff APIs require authentication.

## Common Error Responses

```json
{"detail": "Authentication credentials were not provided."}
```

```json
{"detail": "You do not have permission to perform this action."}
```

Validation errors usually return field-level messages:

```json
{"check_out": "Check-out must be after check-in."}
```

---

# Public Guest API

Base path: `/api/public/`

## Auth

### Register Guest Account

```http
POST /api/public/auth/register/
```

Creates a simple guest login account.

Request:

```json
{
  "username": "guest001",
  "password": "secret123"
}
```

Response `201`:

```json
{
  "message": "Account created successfully.",
  "token": "TOKEN_VALUE",
  "user": {
    "id": 1,
    "username": "guest001"
  }
}
```

Notes:

- `username` is required and must be unique.
- `password` must be at least 6 characters.

### Login Guest

```http
POST /api/public/auth/login/
```

Request:

```json
{
  "username": "guest001",
  "password": "secret123"
}
```

Response `200`:

```json
{
  "message": "Login successful.",
  "token": "TOKEN_VALUE",
  "user": {
    "id": 1,
    "username": "guest001"
  },
  "guest": null
}
```

### Get Current Guest/User

```http
GET /api/public/auth/me/
Authorization: Token <token>
```

Response:

```json
{
  "user": {
    "id": 1,
    "username": "guest001",
    "email": "guest@example.com"
  },
  "guest": {
    "id": 10,
    "guest_id": "GST-0010",
    "hotel": 1,
    "hotel_name": "Demo Hotel",
    "hotel_slug": "demo-hotel",
    "full_name": "John Guest",
    "phone": "+256700000000",
    "email": "guest@example.com"
  }
}
```

### Update Guest Profile

```http
PATCH /api/public/auth/profile/
Authorization: Token <token>
```

Request fields:

```json
{
  "full_name": "John Guest",
  "preferred_name": "John",
  "phone": "+256700000000",
  "alternative_phone": "+256711111111",
  "email": "guest@example.com",
  "nationality": "Ugandan",
  "language": "English",
  "address": "Kampala",
  "city": "Kampala",
  "country": "Uganda",
  "special_requests": "Late checkout",
  "dietary_restrictions": "No pork",
  "room_preferences": "Quiet room",
  "marketing_consent": true,
  "newsletter_subscribed": true
}
```

Response:

```json
{"guest": {"id": 10, "full_name": "John Guest"}}
```

### List My Bookings

```http
GET /api/public/auth/bookings/
Authorization: Token <token>
```

Response:

```json
{
  "bookings": [
    {
      "id": 15,
      "booking_number": "BK-00015",
      "confirmation_code": "ABC123",
      "hotel": 1,
      "hotel_name": "Demo Hotel",
      "hotel_slug": "demo-hotel",
      "guest_name": "John Guest",
      "room_number": "101",
      "room_type": "Deluxe Room",
      "check_in": "2026-07-01",
      "check_out": "2026-07-03",
      "nights": 2,
      "adults": 2,
      "children": 0,
      "status": "reserved",
      "payment_status": "unpaid",
      "subtotal": "200000.00",
      "tax_amount": "0.00",
      "total_amount": "200000.00",
      "amount_paid": "0.00",
      "balance_due": "200000.00",
      "special_requests": "Late checkout",
      "created_at": "2026-06-24T10:00:00Z"
    }
  ]
}
```

### Get Booking Detail

```http
GET /api/public/auth/bookings/{id}/
Authorization: Token <token>
```

Response:

```json
{"booking": {"id": 15, "booking_number": "BK-00015", "status": "reserved"}}
```

### Cancel Booking

```http
DELETE /api/public/auth/bookings/{id}/
Authorization: Token <token>
```

Response:

```json
{
  "message": "Booking cancelled.",
  "booking": {
    "id": 15,
    "status": "cancelled"
  }
}
```

Cancellation is blocked if the booking is already checked in, checked out, or cancelled.

---

## Home and Discovery

### Public Home

```http
GET /api/public/home/
```

Returns featured hotels, recommended hotels, recent experiences, destination counts, and static vibe labels.

Response:

```json
{
  "featured_hotels": [],
  "recommended_hotels": [],
  "experiences": [],
  "destinations": [
    {"city": "Kampala", "country": "Uganda", "properties": 3}
  ],
  "vibes": ["Beach", "City Escape", "Countryside", "Family", "Business", "Romantic", "Wellness"]
}
```

### List Hotels

```http
GET /api/public/hotels/
```

Query parameters:

| Name | Required | Description |
|---|---:|---|
| `q` or `search` | No | Search name, city, country, short description, or description |
| `city` | No | Filter by city |
| `country` | No | Filter by country |
| `featured` | No | `1`, `true`, `True`, or `yes` to show only featured hotels |

Example:

```http
GET /api/public/hotels/?city=Kampala&featured=true
```

Hotel fields:

```json
{
  "id": 1,
  "name": "Demo Hotel",
  "slug": "demo-hotel",
  "email": "info@demo.com",
  "phone": "+256700000000",
  "phone_alt": "",
  "whatsapp": "+256700000000",
  "website": "https://demo.com",
  "city": "Kampala",
  "state": "Central",
  "country": "Uganda",
  "address_line1": "Plot 1",
  "address_line2": "",
  "postal_code": "",
  "latitude": "0.3476",
  "longitude": "32.5825",
  "map_url": "https://www.google.com/maps/search/?api=1&query=0.3476,32.5825",
  "directions_url": "https://www.google.com/maps/dir/?api=1&destination=0.3476,32.5825",
  "star_rating": 4,
  "total_rooms": 20,
  "default_currency": "UGX",
  "default_currency_symbol": "UGX",
  "supported_currencies": ["UGX", "USD"],
  "currencies": {"default": "UGX", "symbol": "UGX", "supported": ["UGX", "USD"]},
  "check_in_time": "14:00:00",
  "check_out_time": "10:00:00",
  "short_description": "Short text",
  "description": "Long text",
  "logo_url": null,
  "cover_url": null,
  "brand_color_primary": "#000000",
  "brand_color_secondary": "#FFFFFF"
}
```

### Hotel Detail

```http
GET /api/public/hotels/{slug}/
```

Returns hotel details, room types, gallery, rating summary, reviews, and experiences.

Response shape:

```json
{
  "hotel": {},
  "room_types": [],
  "gallery": [],
  "rating": {"average": 4.5, "count": 10},
  "reviews": [],
  "experiences": []
}
```

### Hotel Rooms

```http
GET /api/public/hotels/{slug}/rooms/
```

Response:

```json
{
  "room_types": [
    {
      "id": 1,
      "name": "Deluxe Room",
      "description": "Large room with balcony",
      "base_price": "150000.00",
      "available_rooms": 5,
      "image_url": "https://example.com/media/room.jpg"
    }
  ]
}
```

### Hotel Gallery

```http
GET /api/public/hotels/{slug}/gallery/
```

Query parameters:

| Name | Required | Description |
|---|---:|---|
| `category` | No | Filter image category |

Response:

```json
{
  "images": [
    {
      "id": 1,
      "url": "https://example.com/media/image.jpg",
      "title": "Lobby",
      "caption": "Main lobby",
      "category": "hotel",
      "is_primary": true,
      "room_type": null,
      "room": null
    }
  ]
}
```

### Availability

```http
GET /api/public/hotels/{slug}/availability/?check_in=YYYY-MM-DD&check_out=YYYY-MM-DD
```

Required query parameters:

| Name | Required | Format |
|---|---:|---|
| `check_in` | Yes | `YYYY-MM-DD` |
| `check_out` | Yes | `YYYY-MM-DD` |

Response:

```json
{
  "room_types": [
    {
      "id": 1,
      "name": "Deluxe Room",
      "base_price": "150000.00",
      "available_rooms": 3,
      "image_url": null
    }
  ]
}
```

Validation errors:

```json
{"detail": "check_in and check_out are required."}
```

```json
{"detail": "Use YYYY-MM-DD date format."}
```

```json
{"detail": "check_out must be after check_in."}
```

---

## Public Restaurant Menu and Orders

### Get Food Menu

```http
GET /api/public/hotels/{slug}/menu/
```

Response:

```json
{
  "categories": [
    {"id": 1, "name": "Breakfast", "description": "Morning meals", "sort_order": 1}
  ],
  "items": [
    {
      "id": 1,
      "category": 1,
      "category_name": "Breakfast",
      "name": "Rolex",
      "description": "Chapati with eggs and vegetables",
      "price": "8000.00",
      "is_vegetarian": false,
      "is_vegan": false,
      "is_gluten_free": false,
      "is_spicy": false,
      "is_featured": true,
      "is_recommended": true,
      "preparation_time": 15
    }
  ]
}
```

### Create Food Order

```http
POST /api/public/hotels/{slug}/food-orders/
```

Optional authentication can auto-fill guest details.

Request:

```json
{
  "customer_name": "John Guest",
  "customer_phone": "+256700000000",
  "customer_email": "guest@example.com",
  "booking": 15,
  "room_charge": false,
  "special_instructions": "Less salt",
  "items": [
    {"item": 1, "qty": 2, "note": "Extra sauce"}
  ]
}
```

Response `201`:

```json
{
  "message": "Food order received successfully.",
  "order": {
    "id": 30,
    "order_number": "RO-00030",
    "status": "kitchen",
    "total": "16000.00"
  }
}
```

Rules:

- `customer_name` is required unless an authenticated guest is found.
- `items` must contain at least one item.
- `room_charge=true` requires `booking`.
- Each item must be active and belong to the hotel.

---

## Public Bar Menu and Orders

### Get Bar Items

```http
GET /api/public/hotels/{slug}/bar/
```

Response:

```json
{
  "categories": [
    {"id": 1, "name": "Soft Drinks", "sort_order": 1}
  ],
  "items": [
    {
      "id": 1,
      "category": 1,
      "category_name": "Soft Drinks",
      "name": "Soda",
      "unit": "bottle",
      "selling_price": "3000.00",
      "is_out_of_stock": false
    }
  ]
}
```

### Create Drink Order

```http
POST /api/public/hotels/{slug}/drink-orders/
```

Request:

```json
{
  "guest_name": "John Guest",
  "booking": 15,
  "room_charge": false,
  "items": [
    {"item": 1, "qty": 3, "note": "Cold"}
  ]
}
```

Response `201`:

```json
{
  "message": "Drink order received successfully.",
  "order": {
    "id": 20,
    "order_number": "BO-00020",
    "status": "served",
    "total": "9000.00"
  }
}
```

Rules:

- `guest_name` is required unless an authenticated guest is found.
- `items` must contain at least one drink.
- `room_charge=true` requires `booking`.
- Stock is checked for stock-tracked items.

---

## Public Experiences

### List All Experiences

```http
GET /api/public/experiences/
```

Query parameters:

| Name | Required | Description |
|---|---:|---|
| `hotel` | No | Filter by hotel slug |

Response:

```json
{
  "experiences": [
    {
      "id": 1,
      "hotel": 1,
      "hotel_name": "Demo Hotel",
      "hotel_slug": "demo-hotel",
      "guest_name": "John Guest",
      "place_visited": "Lake Victoria",
      "activity": "Boat cruise",
      "rating": 5,
      "experience_text": "Great experience",
      "images": [],
      "created_at": "2026-06-24T10:00:00Z"
    }
  ]
}
```

### Experience Detail

```http
GET /api/public/experiences/{id}/
```

Response:

```json
{
  "experience": {},
  "hotel": {},
  "reviews": []
}
```

### List Hotel Experiences

```http
GET /api/public/hotels/{slug}/experiences/
```

Response:

```json
{"experiences": []}
```

### Create Hotel Experience

```http
POST /api/public/hotels/{slug}/experiences/
Authorization: Token <token>
Content-Type: multipart/form-data
```

Request fields:

| Field | Required | Notes |
|---|---:|---|
| `place_visited` | Yes | Text |
| `activity` | Yes | Text |
| `rating` | No | Integer 1-5, default 5 |
| `experience_text` | Yes | Text |
| `images` | No | Up to 5 image files |

JSON example without images:

```json
{
  "place_visited": "Lake Victoria",
  "activity": "Boat cruise",
  "rating": 5,
  "experience_text": "Amazing staff and views."
}
```

Response `201`:

```json
{
  "message": "Experience posted successfully.",
  "experience": {
    "id": 1,
    "place_visited": "Lake Victoria",
    "activity": "Boat cruise",
    "rating": 5
  }
}
```

---

## Public Reviews

### List Hotel Reviews

```http
GET /api/public/hotels/{slug}/reviews/
```

Response:

```json
{"reviews": []}
```

### Create Hotel Review

```http
POST /api/public/hotels/{slug}/reviews/
Authorization: Token <token>
```

Request:

```json
{
  "overall_rating": "4.5",
  "title": "Great stay",
  "review_text": "Clean rooms and kind staff.",
  "cleanliness_rating": "5.0",
  "comfort_rating": "4.5",
  "location_rating": "4.0",
  "staff_rating": "5.0",
  "facilities_rating": "4.0",
  "value_rating": "4.5",
  "pros": "Good location",
  "cons": "Noisy street",
  "stay_date_from": "2026-07-01",
  "stay_date_to": "2026-07-03",
  "room_number": "101"
}
```

Response `201`:

```json
{
  "message": "Review posted successfully.",
  "review": {
    "id": 1,
    "overall_rating": "4.5",
    "title": "Great stay"
  }
}
```

Rules:

- `overall_rating` must be between 1 and 5.
- If stay dates are omitted, the current date is used.
- `stay_date_to` cannot be before `stay_date_from`.

---

## Public Booking Creation

### Create Booking

```http
POST /api/public/hotels/{slug}/bookings/
```

Optional authentication can connect the booking to the current guest.

Request:

```json
{
  "room": 5,
  "room_type": null,
  "full_name": "John Guest",
  "phone": "+256700000000",
  "email": "guest@example.com",
  "check_in": "2026-07-01",
  "check_out": "2026-07-03",
  "adults": 2,
  "children": 0,
  "special_requests": "Quiet room"
}
```

Alternative: send `room_type` instead of `room` and the system picks the cheapest available room of that type.

Response `201`:

```json
{
  "message": "Booking received successfully.",
  "booking": {
    "id": 15,
    "booking_number": "BK-00015",
    "hotel_name": "Demo Hotel",
    "room_number": "101",
    "room_type": "Deluxe Room",
    "check_in": "2026-07-01",
    "check_out": "2026-07-03",
    "status": "reserved",
    "total_amount": "300000.00"
  }
}
```

Rules:

- `full_name` and `phone` are required unless an authenticated guest profile supplies them.
- `check_out` must be after `check_in`.
- `check_in` cannot be in the past.
- A room must be available for the selected date range.

---

# Staff / Mobile API

Base path: `/api/mobile/`

All staff/mobile endpoints require:

```http
Authorization: Token <token>
```

Except login.

Access to hotel-specific resources is controlled by `HotelMember`. Most endpoints require a `hotel` query parameter or a `hotel` field in the request body.

## Staff Auth and Profile

### Staff Login

```http
POST /api/mobile/login/
```

Request:

```json
{
  "username": "staff",
  "password": "secret123"
}
```

Response:

```json
{
  "token": "TOKEN_VALUE",
  "user": {
    "id": 2,
    "username": "staff",
    "name": "Staff User"
  },
  "hotels": [
    {"id": 1, "name": "Demo Hotel", "slug": "demo-hotel", "role": "manager"}
  ]
}
```

### Current Staff User

```http
GET /api/mobile/me/
```

Response:

```json
{
  "user": {
    "id": 2,
    "username": "staff",
    "name": "Staff User",
    "email": "staff@example.com",
    "first_name": "Staff",
    "last_name": "User"
  },
  "hotels": []
}
```

### Get Profile

```http
GET /api/mobile/profile/
```

Response fields:

```json
{
  "id": 2,
  "username": "staff",
  "email": "staff@example.com",
  "first_name": "Staff",
  "last_name": "User",
  "full_name": "Staff User",
  "date_joined": "2026-06-24T10:00:00Z",
  "joined_date": "2026-06-24T10:00:00Z",
  "is_active": true,
  "last_login": "2026-06-24T10:00:00Z"
}
```

### Update Profile

```http
PUT /api/mobile/profile/update/
PATCH /api/mobile/profile/update/
```

Request:

```json
{
  "username": "staff",
  "email": "staff@example.com",
  "first_name": "Staff",
  "last_name": "User"
}
```

### Change Password

```http
POST /api/mobile/profile/change-password/
```

Request:

```json
{
  "old_password": "oldpass123",
  "new_password": "newpass123",
  "confirm_password": "newpass123"
}
```

Response:

```json
{"message": "Password changed successfully"}
```

---

## Staff Statistics

### Dashboard Statistics

```http
GET /api/mobile/statistics/dashboard/
```

Returns aggregate dashboard stats for the staff member's accessible hotels.

### Restaurant Statistics

```http
GET /api/mobile/statistics/restaurant/?hotel_id=1&period=today
```

Query parameters:

| Name | Required | Description |
|---|---:|---|
| `hotel_id` | Yes | Hotel ID user can access |
| `period` | No | Defaults to `today` |

### Bar Statistics

```http
GET /api/mobile/statistics/bar/?hotel_id=1&period=today
```

### User Statistics

```http
GET /api/mobile/users/stats/
```

Response:

```json
{
  "total_orders": 10,
  "completed_orders": 8,
  "rating": 4.8,
  "hours_worked": 1247,
  "completion_rate": 80.0,
  "total_revenue": "100000.00",
  "average_order_value": 12500.0
}
```

---

## Staff Restaurant

### Get Restaurant Menu

```http
GET /api/mobile/restaurant/menu/?hotel=1
```

Response:

```json
{
  "categories": [
    {"id": 1, "name": "Breakfast", "description": "Morning meals"}
  ],
  "items": [
    {
      "id": 1,
      "category": 1,
      "category_name": "Breakfast",
      "name": "Rolex",
      "description": "Chapati with eggs",
      "price": "8000.00",
      "preparation_time": 15,
      "is_active": true,
      "track_stock": false,
      "stock_qty": "0.00"
    }
  ]
}
```

### Get Tables

```http
GET /api/mobile/restaurant/tables/?hotel=1
```

Response item fields:

```json
{
  "id": 1,
  "number": "T1",
  "seats": 4,
  "area_name": "Main Hall"
}
```

### List Restaurant Orders

```http
GET /api/mobile/restaurant/orders/?hotel=1&status=kitchen
```

Query parameters:

| Name | Required | Description |
|---|---:|---|
| `hotel` | No | Filter by hotel ID; user must have access |
| `status` | No | Filter by order status |

### Create Restaurant Order

```http
POST /api/mobile/restaurant/orders/
```

Request:

```json
{
  "hotel": 1,
  "table": 2,
  "customer_name": "Walk-in Guest",
  "customer_phone": "+256700000000",
  "special_instructions": "No onions",
  "send_to_kitchen": true,
  "items": [
    {"item": 1, "qty": 2, "note": "Extra sauce"}
  ]
}
```

Response `201`:

```json
{
  "id": 100,
  "order_number": "RO-00100",
  "hotel": 1,
  "table": 2,
  "table_number": "T2",
  "customer_name": "Walk-in Guest",
  "customer_phone": "+256700000000",
  "status": "kitchen",
  "special_instructions": "No onions",
  "kitchen_notes": "",
  "subtotal": "16000.00",
  "discount": "0.00",
  "tax": "0.00",
  "service_charge": "0.00",
  "total": "16000.00",
  "created_at": "2026-06-24T10:00:00Z",
  "items": []
}
```

### Restaurant Order Detail

```http
GET /api/mobile/restaurant/orders/{id}/
```

### Update Restaurant Order Status

```http
POST /api/mobile/restaurant/orders/{id}/status/
```

Request:

```json
{"status": "paid"}
```

Response: restaurant order object.

---

## Staff Bar

### Get Bar Items

```http
GET /api/mobile/bar/items/?hotel=1
```

Response item fields:

```json
{
  "id": 1,
  "category": 1,
  "category_name": "Soft Drinks",
  "name": "Soda",
  "sku": "SODA-001",
  "unit": "bottle",
  "selling_price": "3000.00",
  "cost_price": "1800.00",
  "track_stock": true,
  "stock_qty": "50.00",
  "reorder_level": "10.00",
  "is_active": true,
  "is_low_stock": false,
  "is_out_of_stock": false
}
```

### List Bar Orders

```http
GET /api/mobile/bar/orders/?hotel=1&status=served
```

### Create Bar Order

```http
POST /api/mobile/bar/orders/
```

Request:

```json
{
  "hotel": 1,
  "booking": null,
  "guest_name": "Walk-in Guest",
  "room_charge": false,
  "mark_served": true,
  "items": [
    {"item": 1, "qty": 2, "note": "Cold"}
  ]
}
```

Response `201`:

```json
{
  "id": 50,
  "order_number": "BO-00050",
  "hotel": 1,
  "booking": null,
  "guest_name": "Walk-in Guest",
  "display_name": "Walk-in Guest",
  "room_charge": false,
  "status": "served",
  "subtotal": "6000.00",
  "discount": "0.00",
  "tax": "0.00",
  "total": "6000.00",
  "item_count": 2,
  "created_at": "2026-06-24T10:00:00Z",
  "closed_at": null,
  "items": []
}
```

### Bar Order Detail

```http
GET /api/mobile/bar/orders/{id}/
```

### Update Bar Order Status

```http
POST /api/mobile/bar/orders/{id}/status/
```

Request:

```json
{"status": "served"}
```

Response: bar order object.

---

# Superuser Setup API

Base path: `/api/mobile/`

These endpoints require the authenticated user to be a Django superuser.

## Register Hotel With Setup Data

```http
POST /api/mobile/admin/register-hotel/
Authorization: Token <superuser-token>
```

Creates one hotel and optionally creates room types, rooms, menu categories, and menu items in the same request.

Request:

```json
{
  "hotel": {
    "name": "Demo Hotel",
    "email": "info@demo.com",
    "phone": "+256700000000",
    "city": "Kampala",
    "country": "Uganda",
    "address_line1": "Plot 1",
    "star_rating": 4,
    "default_currency": "UGX",
    "default_currency_symbol": "UGX",
    "short_description": "Comfortable city hotel",
    "description": "A demo hotel for testing.",
    "is_active": true,
    "is_published": true
  },
  "room_types": [
    {"name": "Deluxe Room", "description": "Large room", "base_price": "150000.00"}
  ],
  "rooms": [
    {"number": "101", "room_type_name": "Deluxe Room", "floor": "1", "status": "available", "is_active": true}
  ],
  "menu_categories": [
    {"name": "Breakfast", "description": "Morning meals", "sort_order": 1, "is_active": true}
  ],
  "menu_items": [
    {
      "name": "Rolex",
      "category_name": "Breakfast",
      "description": "Chapati with eggs",
      "price": "8000.00",
      "preparation_time": 15,
      "is_active": true
    }
  ]
}
```

Response `201`:

```json
{
  "hotel": {},
  "room_types": [],
  "rooms": [],
  "menu_categories": [],
  "menu_items": []
}
```

## Superuser CRUD ViewSets

The project registers these resources with DRF `DefaultRouter`, so standard REST routes are available.

| Resource | List/Create | Detail/Update/Delete | Filters |
|---|---|---|---|
| Hotels | `GET/POST /api/mobile/admin/hotels/` | `GET/PUT/PATCH/DELETE /api/mobile/admin/hotels/{id}/` | Search/order fields configured in viewset |
| Room Types | `GET/POST /api/mobile/admin/room-types/` | `GET/PUT/PATCH/DELETE /api/mobile/admin/room-types/{id}/` | `hotel` |
| Rooms | `GET/POST /api/mobile/admin/rooms/` | `GET/PUT/PATCH/DELETE /api/mobile/admin/rooms/{id}/` | `hotel`, `status` |
| Menu Categories | `GET/POST /api/mobile/admin/menu-categories/` | `GET/PUT/PATCH/DELETE /api/mobile/admin/menu-categories/{id}/` | `hotel` |
| Menu Items | `GET/POST /api/mobile/admin/menu-items/` | `GET/PUT/PATCH/DELETE /api/mobile/admin/menu-items/{id}/` | `hotel`, `category` |

### Superuser Hotel Main Fields

The hotel serializer includes these common fields:

```text
id, name, slug, hotel_chain, category, email, phone, phone_alt, whatsapp, website,
address_line1, address_line2, city, state, country, postal_code, latitude, longitude,
timezone, logo, cover_image, star_rating, total_rooms, default_currency,
default_currency_symbol, supported_currencies, is_active, is_published, is_featured,
brand_color_primary, brand_color_secondary, short_description, description,
facebook_url, instagram_url, twitter_url, linkedin_url, youtube_url, tripadvisor_url,
check_in_time, check_out_time, reception_open_time, reception_close_time,
cancellation_policy, payment_policy, house_rules, child_policy, pet_policy,
created_by, created_at, updated_at
```

### Superuser Room Type Fields

```json
{
  "id": 1,
  "hotel": 1,
  "hotel_name": "Demo Hotel",
  "name": "Deluxe Room",
  "description": "Large room",
  "base_price": "150000.00"
}
```

### Superuser Room Fields

```json
{
  "id": 1,
  "hotel": 1,
  "hotel_name": "Demo Hotel",
  "room_type": 1,
  "room_type_name": "Deluxe Room",
  "number": "101",
  "floor": "1",
  "status": "available",
  "is_active": true
}
```

### Superuser Menu Category Fields

```json
{
  "id": 1,
  "hotel": 1,
  "hotel_name": "Demo Hotel",
  "name": "Breakfast",
  "description": "Morning meals",
  "sort_order": 1,
  "is_active": true,
  "created_at": "2026-06-24T10:00:00Z",
  "updated_at": "2026-06-24T10:00:00Z"
}
```

### Superuser Menu Item Fields

```json
{
  "id": 1,
  "hotel": 1,
  "hotel_name": "Demo Hotel",
  "category": 1,
  "category_name": "Breakfast",
  "name": "Rolex",
  "description": "Chapati with eggs",
  "ingredients": "Eggs, chapati, tomato, onion",
  "price": "8000.00",
  "cost_price": "3000.00",
  "track_stock": false,
  "stock_qty": "0.00",
  "reorder_level": "0.00",
  "is_vegetarian": false,
  "is_vegan": false,
  "is_gluten_free": false,
  "is_spicy": false,
  "is_featured": true,
  "is_recommended": true,
  "is_active": true,
  "preparation_time": 15,
  "created_at": "2026-06-24T10:00:00Z",
  "updated_at": "2026-06-24T10:00:00Z"
}
```

---

# Flutter Integration Notes

## Store Token After Login

Use the `token` from either public guest login or mobile staff login and include it in every protected request.

```dart
final headers = {
  'Authorization': 'Token $token',
  'Content-Type': 'application/json',
  'Accept': 'application/json',
};
```

## Typical Guest App Flow

1. `GET /api/public/home/`
2. `GET /api/public/hotels/`
3. `GET /api/public/hotels/{slug}/`
4. `GET /api/public/hotels/{slug}/availability/?check_in=2026-07-01&check_out=2026-07-03`
5. `POST /api/public/hotels/{slug}/bookings/`
6. `GET /api/public/hotels/{slug}/menu/`
7. `POST /api/public/hotels/{slug}/food-orders/`
8. `GET /api/public/hotels/{slug}/bar/`
9. `POST /api/public/hotels/{slug}/drink-orders/`

## Typical Staff App Flow

1. `POST /api/mobile/login/`
2. Pick a hotel from `hotels` in the login response.
3. `GET /api/mobile/statistics/dashboard/`
4. `GET /api/mobile/restaurant/menu/?hotel={hotelId}`
5. `GET /api/mobile/restaurant/orders/?hotel={hotelId}`
6. `POST /api/mobile/restaurant/orders/`
7. `GET /api/mobile/bar/items/?hotel={hotelId}`
8. `POST /api/mobile/bar/orders/`

---

# Quick cURL Examples

## Public hotel list

```bash
curl -X GET "http://127.0.0.1:8000/api/public/hotels/"
```

## Guest login

```bash
curl -X POST "http://127.0.0.1:8000/api/public/auth/login/" \
  -H "Content-Type: application/json" \
  -d '{"username":"guest001","password":"secret123"}'
```

## Create booking

```bash
curl -X POST "http://127.0.0.1:8000/api/public/hotels/demo-hotel/bookings/" \
  -H "Content-Type: application/json" \
  -d '{
    "room_type": 1,
    "full_name": "John Guest",
    "phone": "+256700000000",
    "email": "guest@example.com",
    "check_in": "2026-07-01",
    "check_out": "2026-07-03",
    "adults": 2,
    "children": 0
  }'
```

## Staff login

```bash
curl -X POST "http://127.0.0.1:8000/api/mobile/login/" \
  -H "Content-Type: application/json" \
  -d '{"username":"staff","password":"secret123"}'
```

## Staff restaurant order

```bash
curl -X POST "http://127.0.0.1:8000/api/mobile/restaurant/orders/" \
  -H "Authorization: Token TOKEN_VALUE" \
  -H "Content-Type: application/json" \
  -d '{
    "hotel": 1,
    "table": 2,
    "customer_name": "Walk-in Guest",
    "items": [{"item": 1, "qty": 2, "note": "Extra sauce"}],
    "send_to_kitchen": true
  }'
```
