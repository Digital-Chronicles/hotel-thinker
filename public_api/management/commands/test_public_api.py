from __future__ import annotations

import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test import Client, override_settings

from bar.models import BarItem
from hotels.models import Hotel
from restaurant.models import MenuItem
from rooms.models import Room


class Command(BaseCommand):
    help = "Smoke test the public guest API endpoints against local database data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--slug",
            help="Hotel slug to test. Defaults to the first active published hotel.",
        )
        parser.add_argument(
            "--fail-fast",
            action="store_true",
            help="Stop at the first failing endpoint.",
        )
        parser.add_argument(
            "--show-json",
            action="store_true",
            help="Print a shortened JSON response preview for each endpoint.",
        )

    def handle(self, *args, **options):
        hotel = self._get_hotel(options.get("slug"))
        client = Client(HTTP_HOST="testserver")
        checks = self._build_checks(hotel)
        failures = []

        allowed_hosts = list(getattr(settings, "ALLOWED_HOSTS", []))
        if "testserver" not in allowed_hosts:
            allowed_hosts.append("testserver")

        self.stdout.write(f"Testing public API for hotel: {hotel.name} ({hotel.slug})")

        with override_settings(ALLOWED_HOSTS=allowed_hosts):
            for check in checks:
                ok, message = self._run_check(client, check, options["show_json"])
                if ok:
                    self.stdout.write(self.style.SUCCESS(f"OK   {check['method']} {check['path']}"))
                else:
                    failures.append(message)
                    self.stdout.write(self.style.ERROR(f"FAIL {check['method']} {check['path']}"))
                    self.stdout.write(f"     {message}")
                    if options["fail_fast"]:
                        break

        if failures:
            raise CommandError(f"{len(failures)} public API check(s) failed.")

        self.stdout.write(self.style.SUCCESS(f"All {len(checks)} public API checks passed."))

    def _get_hotel(self, slug):
        qs = Hotel.objects.filter(is_active=True, is_published=True).order_by("name")
        if slug:
            try:
                return qs.get(slug=slug)
            except Hotel.DoesNotExist as exc:
                raise CommandError(f"No active published hotel found with slug '{slug}'.") from exc

        hotel = qs.first()
        if not hotel:
            raise CommandError(
                "No active published hotel exists. Run `python manage.py seed_testing_data` "
                "or publish a hotel, then run this command again."
            )
        return hotel

    def _build_checks(self, hotel):
        room = Room.objects.filter(hotel=hotel, is_active=True).order_by("id").first()
        menu_item = MenuItem.objects.filter(hotel=hotel, is_active=True).order_by("id").first()
        bar_item = BarItem.objects.filter(hotel=hotel, is_active=True).order_by("id").first()

        checks = [
            {
                "method": "GET",
                "path": "/api/public/hotels/",
                "required_keys": ["id", "name", "slug"],
                "root_list": True,
            },
            {
                "method": "GET",
                "path": f"/api/public/hotels/{hotel.slug}/",
                "required_keys": ["hotel", "room_types", "gallery", "rating"],
            },
            {
                "method": "GET",
                "path": f"/api/public/hotels/{hotel.slug}/rooms/",
                "required_keys": ["rooms", "room_types"],
                "image_list_key": "rooms",
            },
            {
                "method": "GET",
                "path": f"/api/public/hotels/{hotel.slug}/menu/categories/",
                "required_keys": ["categories"],
                "image_list_key": "categories",
            },
            {
                "method": "GET",
                "path": f"/api/public/hotels/{hotel.slug}/menu/items/",
                "required_keys": ["items"],
                "image_list_key": "items",
            },
            {
                "method": "GET",
                "path": f"/api/public/hotels/{hotel.slug}/bar/categories/",
                "required_keys": ["categories"],
                "image_list_key": "categories",
            },
            {
                "method": "GET",
                "path": f"/api/public/hotels/{hotel.slug}/bar/items/",
                "required_keys": ["items"],
                "image_list_key": "items",
            },
        ]

        if room:
            checks.append(
                {
                    "method": "GET",
                    "path": f"/api/public/hotels/{hotel.slug}/rooms/{room.id}/",
                    "required_keys": ["id", "name", "price", "image_url"],
                    "image_object": True,
                }
            )
        if menu_item:
            checks.extend(
                [
                    {
                        "method": "GET",
                        "path": f"/api/public/hotels/{hotel.slug}/menu/items/?category={menu_item.category_id}",
                        "required_keys": ["items"],
                        "image_list_key": "items",
                    },
                    {
                        "method": "GET",
                        "path": f"/api/public/hotels/{hotel.slug}/menu/items/{menu_item.id}/",
                        "required_keys": ["id", "category", "category_name", "name", "image_url"],
                        "image_object": True,
                    },
                ]
            )
        if bar_item:
            checks.extend(
                [
                    {
                        "method": "GET",
                        "path": f"/api/public/hotels/{hotel.slug}/bar/items/?category={bar_item.category_id}",
                        "required_keys": ["items"],
                        "image_list_key": "items",
                    },
                    {
                        "method": "GET",
                        "path": f"/api/public/hotels/{hotel.slug}/bar/items/{bar_item.id}/",
                        "required_keys": ["id", "category", "category_name", "name", "image_url"],
                        "image_object": True,
                    },
                ]
            )

        return checks

    def _run_check(self, client, check, show_json):
        response = client.get(check["path"])
        if response.status_code != 200:
            return False, f"Expected HTTP 200, got {response.status_code}: {response.content[:300]!r}"

        try:
            payload = response.json()
        except ValueError as exc:
            return False, f"Response was not JSON: {exc}"

        if check.get("root_list"):
            if not isinstance(payload, list):
                return False, "Expected a JSON list response."
            if payload:
                missing = [key for key in check.get("required_keys", []) if key not in payload[0]]
                if missing:
                    return False, f"Missing key(s) in first list item: {', '.join(missing)}"
        else:
            missing = [key for key in check.get("required_keys", []) if key not in payload]
            if missing:
                return False, f"Missing top-level key(s): {', '.join(missing)}"

        image_list_key = check.get("image_list_key")
        if image_list_key and payload.get(image_list_key):
            missing_image = [item.get("id") for item in payload[image_list_key] if "image_url" not in item]
            if missing_image:
                return False, f"Missing image_url in {image_list_key} item id(s): {missing_image}"

        if check.get("image_object") and "image_url" not in payload:
            return False, "Missing image_url in detail response."

        if show_json:
            preview = json.dumps(payload, default=str, indent=2)[:1000]
            self.stdout.write(preview)

        return True, ""
