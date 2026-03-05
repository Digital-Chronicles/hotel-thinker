# rooms/models.py

from django.db import models
from hotels.models import Hotel


class RoomType(models.Model):
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="room_types")
    name = models.CharField(max_length=120)  # e.g. Single, Double, Deluxe
    description = models.TextField(blank=True, null=True)
    base_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hotel", "name"], name="uniq_roomtype_name_per_hotel"),
        ]

    def __str__(self):
        return f"{self.name} ({self.hotel.name})"


class Room(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        OCCUPIED = "occupied", "Occupied"
        MAINTENANCE = "maintenance", "Maintenance"
        CLEANING = "cleaning", "Cleaning"

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="rooms")
    room_type = models.ForeignKey(RoomType, on_delete=models.PROTECT, related_name="rooms")

    number = models.CharField(max_length=50)  # e.g. 101, A-01
    floor = models.CharField(max_length=50, blank=True, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AVAILABLE)

    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hotel", "number"], name="uniq_room_number_per_hotel"),
        ]
        indexes = [
            models.Index(fields=["hotel", "status"]),
        ]

    def __str__(self):
        return f"Room {self.number} - {self.hotel.name}"