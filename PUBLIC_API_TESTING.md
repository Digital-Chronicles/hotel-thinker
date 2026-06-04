# Public Guest API Testing

## Register

POST `/api/public/auth/register/`

```json
{
  "username": "guest1",
  "password": "Guest123"
}
```

## Login

POST `/api/public/auth/login/`

```json
{
  "username": "guest1",
  "password": "Guest123"
}
```

Use the returned token:

```http
Authorization: Token YOUR_TOKEN
```

## View experiences - public

GET `/api/public/hotels/ocean-hotel/experiences/`

## Create experience - signed-in users only

POST `/api/public/hotels/ocean-hotel/experiences/`

Headers:

```http
Authorization: Token YOUR_TOKEN
Content-Type: application/json
```

```json
{
  "place_visited": "Queen Elizabeth National Park",
  "activity": "Wildlife safari",
  "rating": 5,
  "experience_text": "The place was beautiful and the hotel helped us find directions."
}
```

For image uploads, use `multipart/form-data` with fields:

- `place_visited`
- `activity`
- `rating`
- `experience_text`
- `images` one or more image files
