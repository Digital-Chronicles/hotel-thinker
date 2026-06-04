# Public Guest API Changes

This fixed version adds guest registration/login and improves hotel data returned to the guest app.

## After replacing the project

Run:

```bash
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

## Guest auth endpoints

### Register guest
`POST /api/public/auth/register/`

```json
{
  "hotel": "hotel-slug",
  "full_name": "John Guest",
  "phone": "0770000000",
  "email": "john@example.com",
  "password": "StrongPass123",
  "password_confirm": "StrongPass123",
  "city": "Kampala",
  "country": "Uganda"
}
```

Returns a token. Use it in Flutter/Next.js as:

```http
Authorization: Token YOUR_TOKEN_HERE
```

### Login guest
`POST /api/public/auth/login/`

```json
{
  "email": "john@example.com",
  "password": "StrongPass123"
}
```

### Current guest profile
`GET /api/public/auth/me/`

### Guest booking history
`GET /api/public/auth/bookings/`

## Hotel browsing endpoints

- `GET /api/public/hotels/`
- `GET /api/public/hotels/?city=Kasese`
- `GET /api/public/hotels/<slug>/`

Hotel responses now include:

- latitude
- longitude
- map_url
- directions_url
- address details
- check-in/check-out time
- logo and cover image URLs

## Booking endpoint

`POST /api/public/hotels/<slug>/bookings/`

For logged-in guests, the API can use their saved guest profile. Anonymous booking still works if `full_name` and `phone` are provided.

```json
{
  "room_type": 1,
  "check_in": "2026-06-01",
  "check_out": "2026-06-03",
  "adults": 1,
  "children": 0,
  "special_requests": "Quiet room"
}
```

## Food and drink orders

Logged-in guests can place food/drink orders and room-charge them against their own booking only.

- `POST /api/public/hotels/<slug>/food-orders/`
- `POST /api/public/hotels/<slug>/drink-orders/`
