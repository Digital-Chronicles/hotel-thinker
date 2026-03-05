from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import RestaurantOrder


def _make_order_number(order: RestaurantOrder) -> str:
    d = timezone.localdate().strftime("%Y%m%d")
    return f"REST-{d}-{order.id}"


@receiver(post_save, sender=RestaurantOrder)
def restaurant_order_set_number(sender, instance: RestaurantOrder, created, **kwargs):
    if created and not instance.order_number:
        RestaurantOrder.objects.filter(pk=instance.pk).update(order_number=_make_order_number(instance))