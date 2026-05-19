# Hotel Thinker Public Guest API

This update adds a clean public API for external guests to browse hotels, check room availability, and submit room, food, and drink orders.

## Base URL

```text
/api/public/
```

## Public endpoints

### Hotels

```http
GET /api/public/hotels/
GET /api/public/hotels/<hotel-slug>/
```

### Room availability

```http
GET /api/public/hotels/<hotel-slug>/availability/?check_in=2026-05-20&check_out=2026-05-22
```

Returns available room types, prices, descriptions, available room counts, and image URL where available.

### Create room booking

```http
POST /api/public/hotels/<hotel-slug>/bookings/
Content-Type: application/json

{
  "room_type": 1,
  "full_name": "John Doe",
  "phone": "+256700000000",
  "email": "john@example.com",
  "check_in": "2026-05-20",
  "check_out": "2026-05-22",
  "adults": 2,
  "children": 0,
  "special_requests": "Quiet room please"
}
```

You may send either `room_type` or a specific `room`. If neither is sent, the API selects the cheapest available room.

### Food menu and order

```http
GET /api/public/hotels/<hotel-slug>/menu/
POST /api/public/hotels/<hotel-slug>/food-orders/
```

Example body:

```json
{
  "customer_name": "John Doe",
  "customer_phone": "+256700000000",
  "special_instructions": "No onions",
  "items": [
    {"item": 1, "qty": 2, "note": "Less salt"}
  ]
}
```

For room charges, add:

```json
{
  "booking": 1,
  "room_charge": true
}
```

### Drinks and order

```http
GET /api/public/hotels/<hotel-slug>/bar/
POST /api/public/hotels/<hotel-slug>/drink-orders/
```

Example body:

```json
{
  "guest_name": "John Doe",
  "items": [
    {"item": 1, "qty": 3}
  ]
}
```

## Files changed

- Added `public_api/` app
- Registered `public_api.apps.PublicApiConfig`
- Added `/api/public/` URL routes
- Fixed mobile API status names that were causing crashes: restaurant uses `open/paid`, bar uses `open/served`
- Fixed missing `django.db.models` import in `mobile_api/serializers.py`
- Enabled CORS credentials for API clients
