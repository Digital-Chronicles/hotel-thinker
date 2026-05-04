# restaurant/signals.py
from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import RestaurantOrder, RestaurantOrderItem


def _make_order_number(order: RestaurantOrder) -> str:
    d = timezone.localdate().strftime("%Y%m%d")
    return f"REST-{d}-{order.pk}"


@receiver(post_save, sender=RestaurantOrder)
def restaurant_order_set_number(sender, instance: RestaurantOrder, created: bool, raw: bool = False, **kwargs):
    if raw:
        return
    if created and not instance.order_number:
        RestaurantOrder.objects.filter(pk=instance.pk).update(order_number=_make_order_number(instance))


@receiver(post_save, sender=RestaurantOrderItem)
def restaurant_item_rebill_order(sender, instance: RestaurantOrderItem, created: bool, raw: bool = False, **kwargs):
    if raw:
        return
    order = instance.order
    if order.status in {RestaurantOrder.Status.PAID, RestaurantOrder.Status.CANCELLED}:
        return
    invoice = getattr(order, "invoice", None)
    if not invoice:
        return
    invoice.subtotal = order.subtotal
    invoice.discount = order.discount
    invoice.discount_percent = order.discount_percent
    invoice.tax = order.tax
    invoice.tax_percent = order.tax_percent
    invoice.service_charge = order.service_charge
    invoice.total = order.total
    invoice.save()


@receiver(post_delete, sender=RestaurantOrderItem)
def restaurant_item_delete_rebill_order(sender, instance: RestaurantOrderItem, **kwargs):
    order = instance.order
    if order.status in {RestaurantOrder.Status.PAID, RestaurantOrder.Status.CANCELLED}:
        return
    invoice = getattr(order, "invoice", None)
    if not invoice:
        return
    invoice.subtotal = order.subtotal
    invoice.discount = order.discount
    invoice.discount_percent = order.discount_percent
    invoice.tax = order.tax
    invoice.tax_percent = order.tax_percent
    invoice.service_charge = order.service_charge
    invoice.total = order.total
    invoice.save()
