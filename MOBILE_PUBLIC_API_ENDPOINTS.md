# Hotel Thinker Public Mobile API

Base URL for phone testing:

```text
http://192.168.1.137:8000/api/public/
```

Run Django:

```bash
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

## Auth

### Register

```http
POST /api/public/auth/register/
Content-Type: application/json

{
  "username": "guest1",
  "password": "Guest123!"
}
```

### Login

```http
POST /api/public/auth/login/
Content-Type: application/json

{
  "username": "guest1",
  "password": "Guest123!"
}
```

Use the returned token:

```http
Authorization: Token YOUR_TOKEN
```

## Hotels

```http
GET /api/public/hotels/
GET /api/public/hotels/{slug}/
GET /api/public/hotels/{slug}/availability/?check_in=2026-06-01&check_out=2026-06-03
GET /api/public/hotels/{slug}/menu/
GET /api/public/hotels/{slug}/bar/
```

## Stories / Experiences

All users can view:

```http
GET /api/public/experiences/
GET /api/public/experiences/?hotel={hotel_slug}
GET /api/public/experiences/{id}/
GET /api/public/hotels/{slug}/experiences/
```

Only signed-in users can post:

```http
POST /api/public/hotels/{slug}/experiences/
Authorization: Token YOUR_TOKEN
Content-Type: multipart/form-data

place_visited=Queen Elizabeth National Park
activity=Wildlife Safari
rating=5
experience_text=It was a wonderful experience.
images=@photo1.jpg
images=@photo2.jpg
```

## Reviews

All users can view:

```http
GET /api/public/hotels/{slug}/reviews/
```

Only signed-in users can post:

```http
POST /api/public/hotels/{slug}/reviews/
Authorization: Token YOUR_TOKEN
Content-Type: application/json

{
  "overall_rating": "5.0",
  "title": "Very good stay",
  "review_text": "The rooms were clean and the staff were friendly.",
  "stay_date_from": "2026-06-01",
  "stay_date_to": "2026-06-03"
}
```

## Bookings and Orders

```http
POST /api/public/hotels/{slug}/bookings/
POST /api/public/hotels/{slug}/food-orders/
POST /api/public/hotels/{slug}/drink-orders/
GET  /api/public/auth/bookings/
```
