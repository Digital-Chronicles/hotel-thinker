from __future__ import annotations

from decimal import Decimal

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import BarItem, BarOrderItem, BarStockMovement

D0 = Decimal("0.00")


@receiver(pre_save, sender=BarOrderItem)
def cache_previous_bar_order_item(sender, instance, **kwargs):
    """
    Cache previous values before update so we can adjust stock correctly.
    """
    if not instance.pk:
        instance._old_qty = None
        instance._old_item_id = None
        return

    try:
        old = BarOrderItem.objects.get(pk=instance.pk)
        instance._old_qty = Decimal(old.qty or 0)
        instance._old_item_id = old.item_id
    except BarOrderItem.DoesNotExist:
        instance._old_qty = None
        instance._old_item_id = None


@receiver(post_save, sender=BarOrderItem)
def sync_bar_stock_on_save(sender, instance, created, **kwargs):
    """
    Adjust bar stock when an order item is created or updated.
    """
    item = instance.item
    if not item.track_stock:
        return

    new_qty = Decimal(instance.qty or 0)

    if created:
        item.stock_qty = Decimal(item.stock_qty or D0) - new_qty
        if item.stock_qty < D0:
            item.stock_qty = D0
        item.save(update_fields=["stock_qty"])

        BarStockMovement.objects.create(
            hotel=item.hotel,
            item=item,
            movement_type=BarStockMovement.MovementType.SALE,
            quantity=-new_qty,
            balance_after=item.stock_qty,
            reference=instance.order.order_number,
            created_by=instance.order.created_by,
            note=f"Bar sale for order {instance.order.order_number}",
        )
        return

    old_qty = getattr(instance, "_old_qty", None)
    old_item_id = getattr(instance, "_old_item_id", None)

    if old_qty is None:
        return

    # If item changed, restore old item stock then reduce new item stock
    if old_item_id and old_item_id != instance.item_id:
        try:
            old_item = BarItem.objects.get(pk=old_item_id)
            if old_item.track_stock:
                old_item.stock_qty = Decimal(old_item.stock_qty or D0) + old_qty
                old_item.save(update_fields=["stock_qty"])

                BarStockMovement.objects.create(
                    hotel=old_item.hotel,
                    item=old_item,
                    movement_type=BarStockMovement.MovementType.RETURN,
                    quantity=old_qty,
                    balance_after=old_item.stock_qty,
                    reference=instance.order.order_number,
                    created_by=instance.order.created_by,
                    note=f"Bar order item changed from order {instance.order.order_number}",
                )
        except BarItem.DoesNotExist:
            pass

        item.stock_qty = Decimal(item.stock_qty or D0) - new_qty
        if item.stock_qty < D0:
            item.stock_qty = D0
        item.save(update_fields=["stock_qty"])

        BarStockMovement.objects.create(
            hotel=item.hotel,
            item=item,
            movement_type=BarStockMovement.MovementType.SALE,
            quantity=-new_qty,
            balance_after=item.stock_qty,
            reference=instance.order.order_number,
            created_by=instance.order.created_by,
            note=f"Bar order item changed into {item.name} for order {instance.order.order_number}",
        )
        return

    diff = new_qty - old_qty
    if diff == 0:
        return

    item.stock_qty = Decimal(item.stock_qty or D0) - diff
    if item.stock_qty < D0:
        item.stock_qty = D0
    item.save(update_fields=["stock_qty"])

    movement_type = (
        BarStockMovement.MovementType.SALE if diff > 0 else BarStockMovement.MovementType.RETURN
    )

    BarStockMovement.objects.create(
        hotel=item.hotel,
        item=item,
        movement_type=movement_type,
        quantity=-diff,
        balance_after=item.stock_qty,
        reference=instance.order.order_number,
        created_by=instance.order.created_by,
        note=f"Bar order item quantity updated for order {instance.order.order_number}",
    )


@receiver(post_delete, sender=BarOrderItem)
def restore_bar_stock_on_delete(sender, instance, **kwargs):
    """
    Restore bar stock when an order item is deleted.
    """
    item = instance.item
    if not item.track_stock:
        return

    qty = Decimal(instance.qty or 0)
    item.stock_qty = Decimal(item.stock_qty or D0) + qty
    item.save(update_fields=["stock_qty"])

    BarStockMovement.objects.create(
        hotel=item.hotel,
        item=item,
        movement_type=BarStockMovement.MovementType.RETURN,
        quantity=qty,
        balance_after=item.stock_qty,
        reference=instance.order.order_number,
        created_by=instance.order.created_by,
        note=f"Bar order item removed from order {instance.order.order_number}",
    )