# Public Guest API Testing

Use the built-in smoke test command to verify the public guest API against local database data.

## Prepare Data

If you do not already have a published hotel with rooms, menu items, and bar items:

```bash
python manage.py seed_testing_data
```

The seed command creates a published demo hotel you can test immediately.

## Run All Public API Checks

```bash
python manage.py test_public_api
```

The command tests:

- hotel list and hotel detail
- room list and room detail
- menu categories
- menu items
- menu items filtered by category
- menu item detail
- bar categories
- bar items
- bar items filtered by category
- bar item detail
- `image_url` presence on image-enabled responses

## Test A Specific Hotel

```bash
python manage.py test_public_api --slug lakeview-demo-hotel
```

## Stop At First Failure

```bash
python manage.py test_public_api --fail-fast
```

## Show JSON Response Previews

```bash
python manage.py test_public_api --show-json
```

## Manual cURL Examples

```bash
curl http://127.0.0.1:8000/api/public/hotels/
curl http://127.0.0.1:8000/api/public/hotels/lakeview-demo-hotel/rooms/
curl http://127.0.0.1:8000/api/public/hotels/lakeview-demo-hotel/menu/categories/
curl http://127.0.0.1:8000/api/public/hotels/lakeview-demo-hotel/menu/items/
curl http://127.0.0.1:8000/api/public/hotels/lakeview-demo-hotel/bar/categories/
curl http://127.0.0.1:8000/api/public/hotels/lakeview-demo-hotel/bar/items/
```

## Image URL Expectations

For `Room`, `MenuCategory`, `MenuItem`, `BarCategory`, and `BarItem`, the API returns:

```json
{
  "image_url": ""
}
```

when no image link is saved, or the stored URL string when one exists. These are direct database values, not uploaded Django media files.
