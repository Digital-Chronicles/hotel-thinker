# Hotel currency setup

This version allows each hotel to define currencies while adding/editing the hotel.

## New hotel fields

- `default_currency` - main currency used by the hotel, for example `UGX` or `USD`.
- `default_currency_symbol` - display symbol/text, for example `UGX`, `$`, `KSh`.
- `supported_currencies` - JSON list of accepted currencies, for example `["UGX", "USD"]`.

The default currency is automatically included in the supported currencies list.

## Public API output

Hotel listing/details now return:

```json
{
  "default_currency": "UGX",
  "default_currency_symbol": "UGX",
  "supported_currencies": ["UGX", "USD"],
  "currencies": {
    "default": "UGX",
    "symbol": "UGX",
    "supported": ["UGX", "USD"]
  }
}
```

## Apply changes

```bash
python manage.py migrate
python manage.py runserver
```
