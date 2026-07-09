# Hotel Thinker Public Guest API

The public guest API lets external apps browse published hotels, rooms, menu items, bar items, guest experiences, reviews, and create guest-facing bookings or orders.

## Base URL

```text
/api/public/
```

## Authentication

Most browsing endpoints are public. Guest profile, guest booking history, and authenticated experience/review creation use token auth:

```http
Authorization: Token YOUR_TOKEN
```

### Register

```http
POST /api/public/auth/register/
Content-Type: application/json
```

```json
{
  "username": "guest1",
  "password": "Guest123"
}
```

### Login

```http
POST /api/public/auth/login/
Content-Type: application/json
```

```json
{
  "username": "guest1",
  "password": "Guest123"
}
```

## Hotels

```http
GET /api/public/hotels/
GET /api/public/hotels/?city=Kampala
GET /api/public/hotels/?country=Uganda
GET /api/public/hotels/?q=lake
GET /api/public/hotels/<hotel-slug>/
```

Hotel responses include contact details, location fields, map links, supported currencies, check-in/check-out time, logo URL, and cover URL.

## Rooms

```http
GET /api/public/hotels/<hotel-slug>/rooms/
GET /api/public/hotels/<hotel-slug>/rooms/<room-id>/
GET /api/public/hotels/<hotel-slug>/availability/?check_in=2026-08-01&check_out=2026-08-03
```

Room responses include `image_url` directly from the `Room.image_url` database field.

Example room detail:

```json
{
  "id": 1,
  "number": "101",
  "floor": "1",
  "status": "available",
  "room_type": 1,
  "name": "Deluxe Room",
  "description": "Comfortable deluxe room with city view",
  "price": "150000.00",
  "image_url": "https://example.com/images/deluxe-room.jpg"
}
```

## Menu

```http
GET /api/public/hotels/<hotel-slug>/menu/
GET /api/public/hotels/<hotel-slug>/menu/categories/
GET /api/public/hotels/<hotel-slug>/menu/items/
GET /api/public/hotels/<hotel-slug>/menu/items/?category=<category-id>
GET /api/public/hotels/<hotel-slug>/menu/items/<item-id>/
```

Example menu item:

```json
{
  "id": 1,
  "category": 1,
  "category_name": "Breakfast",
  "name": "Katogo",
  "description": "Matooke cooked with beef or beans",
  "price": "15000.00",
  "is_available": true,
  "image_url": "https://example.com/images/katogo.jpg"
}
```

## Bar

```http
GET /api/public/hotels/<hotel-slug>/bar/
GET /api/public/hotels/<hotel-slug>/bar/categories/
GET /api/public/hotels/<hotel-slug>/bar/items/
GET /api/public/hotels/<hotel-slug>/bar/items/?category=<category-id>
GET /api/public/hotels/<hotel-slug>/bar/items/<item-id>/
```

Example bar item:

```json
{
  "id": 1,
  "category": 1,
  "category_name": "Soft Drinks",
  "name": "Mineral Water",
  "description": "",
  "unit": "bottle",
  "selling_price": "3000.00",
  "price": "3000.00",
  "is_available": true,
  "is_out_of_stock": false,
  "image_url": "https://example.com/images/water.jpg"
}
```

## Image URL Fields

`Room`, `MenuCategory`, `MenuItem`, `BarCategory`, and `BarItem` store image links in:

```python
image_url
```

Rules:

- `image_url` is a plain URL string stored directly in the database.
- Images are not uploaded to Django for these fields.
- Empty image URLs return `""`.
- Flutter should use the returned `image_url` directly.

## Bookings

```http
POST /api/public/hotels/<hotel-slug>/bookings/
Content-Type: application/json
```

```json
{
  "room_type": 1,
  "full_name": "John Doe",
  "phone": "+256700000000",
  "email": "john@example.com",
  "check_in": "2026-08-01",
  "check_out": "2026-08-03",
  "adults": 2,
  "children": 0,
  "special_requests": "Quiet room please"
}
```

You may send either `room_type` or a specific `room`. If neither is sent, the API selects the cheapest available room.

## Food Orders

```http
POST /api/public/hotels/<hotel-slug>/food-orders/
Content-Type: application/json
```

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

For room charges, include:

```json
{
  "booking": 1,
  "room_charge": true
}
```

## Drink Orders

```http
POST /api/public/hotels/<hotel-slug>/drink-orders/
Content-Type: application/json
```

```json
{
  "guest_name": "John Doe",
  "items": [
    {"item": 1, "qty": 3}
  ]
}
```

## Testing The API

Seed demo data if needed:

```bash
python manage.py seed_testing_data
```

Run the public API smoke test:

```bash
python manage.py test_public_api
```

Test a specific hotel:

```bash
python manage.py test_public_api --slug lakeview-demo-hotel
```

Print response previews:

```bash
python manage.py test_public_api --show-json
```
