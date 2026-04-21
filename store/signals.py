from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import (
    StoreGoodsReceiptItem,
    StoreItem,
    StorePurchaseOrderItem,
    StoreSaleItem,
    StoreStockMovement,
)

D0 = Decimal("0.00")


@receiver(pre_save, sender=StoreSaleItem)
def cache_previous_store_sale_item(sender, instance, **kwargs):
    """
    Cache previous values before update so we can adjust stock correctly.
    """
    instance._old_qty = None
    instance._old_item_id = None

    if not instance.pk:
        return

    try:
        old = StoreSaleItem.objects.get(pk=instance.pk)
        instance._old_qty = Decimal(old.qty or 0)
        instance._old_item_id = old.item_id
    except StoreSaleItem.DoesNotExist:
        pass


@receiver(post_save, sender=StoreSaleItem)
def sync_store_stock_on_sale_save(sender, instance, created, **kwargs):
    """
    Reduce or adjust stock when a store sale item is created/updated.
    """
    with transaction.atomic():
        item = StoreItem.objects.select_for_update().get(pk=instance.item_id)
        new_qty = Decimal(instance.qty or 0)

        if created:
            if Decimal(item.stock_qty or 0) < new_qty:
                raise ValidationError(f"Insufficient stock for {item.name}.")

            item.stock_qty = Decimal(item.stock_qty or 0) - new_qty
            item.save(update_fields=["stock_qty"])

            StoreStockMovement.objects.create(
                hotel=item.hotel,
                item=item,
                movement_type=StoreStockMovement.MovementType.SALE,
                quantity=-new_qty,
                balance_after=item.stock_qty,
                reference=instance.sale.sale_number,
                created_by=instance.sale.created_by,
                note=f"Store sale {instance.sale.sale_number}",
            )
            return

        old_qty = getattr(instance, "_old_qty", None)
        old_item_id = getattr(instance, "_old_item_id", None)

        if old_qty is None:
            return

        # Item changed
        if old_item_id and old_item_id != instance.item_id:
            old_item = StoreItem.objects.select_for_update().get(pk=old_item_id)

            # restore old item
            old_item.stock_qty = Decimal(old_item.stock_qty or 0) + old_qty
            old_item.save(update_fields=["stock_qty"])

            StoreStockMovement.objects.create(
                hotel=old_item.hotel,
                item=old_item,
                movement_type=StoreStockMovement.MovementType.RETURN,
                quantity=old_qty,
                balance_after=old_item.stock_qty,
                reference=instance.sale.sale_number,
                created_by=instance.sale.created_by,
                note=f"Sale item changed from {old_item.name} in sale {instance.sale.sale_number}",
            )

            # reduce new item
            if Decimal(item.stock_qty or 0) < new_qty:
                raise ValidationError(f"Insufficient stock for {item.name}.")

            item.stock_qty = Decimal(item.stock_qty or 0) - new_qty
            item.save(update_fields=["stock_qty"])

            StoreStockMovement.objects.create(
                hotel=item.hotel,
                item=item,
                movement_type=StoreStockMovement.MovementType.SALE,
                quantity=-new_qty,
                balance_after=item.stock_qty,
                reference=instance.sale.sale_number,
                created_by=instance.sale.created_by,
                note=f"Sale item changed to {item.name} in sale {instance.sale.sale_number}",
            )
            return

        diff = new_qty - old_qty
        if diff == 0:
            return

        if diff > 0:
            if Decimal(item.stock_qty or 0) < diff:
                raise ValidationError(f"Insufficient stock for {item.name}.")

        item.stock_qty = Decimal(item.stock_qty or 0) - diff
        item.save(update_fields=["stock_qty"])

        movement_type = (
            StoreStockMovement.MovementType.SALE
            if diff > 0
            else StoreStockMovement.MovementType.RETURN
        )

        StoreStockMovement.objects.create(
            hotel=item.hotel,
            item=item,
            movement_type=movement_type,
            quantity=-diff,
            balance_after=item.stock_qty,
            reference=instance.sale.sale_number,
            created_by=instance.sale.created_by,
            note=f"Store sale item quantity updated for sale {instance.sale.sale_number}",
        )


@receiver(post_delete, sender=StoreSaleItem)
def restore_store_stock_on_sale_delete(sender, instance, **kwargs):
    """
    Restore stock when a store sale item is deleted.
    """
    with transaction.atomic():
        item = StoreItem.objects.select_for_update().get(pk=instance.item_id)
        qty = Decimal(instance.qty or 0)

        item.stock_qty = Decimal(item.stock_qty or 0) + qty
        item.save(update_fields=["stock_qty"])

        StoreStockMovement.objects.create(
            hotel=item.hotel,
            item=item,
            movement_type=StoreStockMovement.MovementType.RETURN,
            quantity=qty,
            balance_after=item.stock_qty,
            reference=instance.sale.sale_number,
            created_by=instance.sale.created_by,
            note=f"Store sale item removed from sale {instance.sale.sale_number}",
        )


@receiver(pre_save, sender=StoreGoodsReceiptItem)
def cache_previous_goods_receipt_item(sender, instance, **kwargs):
    """
    Cache previous values before update so we can adjust stock and PO received qty correctly.
    """
    instance._old_qty_received = None
    instance._old_purchase_order_item_id = None

    if not instance.pk:
        return

    try:
        old = StoreGoodsReceiptItem.objects.get(pk=instance.pk)
        instance._old_qty_received = Decimal(old.qty_received or 0)
        instance._old_purchase_order_item_id = old.purchase_order_item_id
    except StoreGoodsReceiptItem.DoesNotExist:
        pass


@receiver(post_save, sender=StoreGoodsReceiptItem)
def sync_store_stock_on_goods_receipt_save(sender, instance, created, **kwargs):
    """
    Increase stock when goods are received and update purchase order item received_qty.
    """
    with transaction.atomic():
        po_item = StorePurchaseOrderItem.objects.select_for_update().select_related(
            "item", "purchase_order"
        ).get(pk=instance.purchase_order_item_id)

        item = StoreItem.objects.select_for_update().get(pk=po_item.item_id)
        new_qty = Decimal(instance.qty_received or 0)

        if created:
            po_item.received_qty = Decimal(po_item.received_qty or 0) + new_qty
            if po_item.received_qty > Decimal(po_item.qty_ordered or 0):
                raise ValidationError(
                    f"Received quantity cannot exceed ordered quantity for {item.name}."
                )
            po_item.save(update_fields=["received_qty"])

            item.stock_qty = Decimal(item.stock_qty or 0) + new_qty
            item.cost_price = Decimal(instance.unit_cost or item.cost_price or D0)
            item.save(update_fields=["stock_qty", "cost_price"])

            StoreStockMovement.objects.create(
                hotel=item.hotel,
                item=item,
                movement_type=StoreStockMovement.MovementType.PURCHASE,
                quantity=new_qty,
                balance_after=item.stock_qty,
                reference=instance.goods_receipt.receipt_number,
                created_by=instance.goods_receipt.received_by,
                note=f"Goods receipt {instance.goods_receipt.receipt_number}",
            )

            po_item.purchase_order.refresh_status()
            return

        old_qty = getattr(instance, "_old_qty_received", None)
        old_po_item_id = getattr(instance, "_old_purchase_order_item_id", None)

        if old_qty is None:
            return

        # purchase order item changed
        if old_po_item_id and old_po_item_id != instance.purchase_order_item_id:
            old_po_item = StorePurchaseOrderItem.objects.select_for_update().select_related(
                "item", "purchase_order"
            ).get(pk=old_po_item_id)
            old_item = StoreItem.objects.select_for_update().get(pk=old_po_item.item_id)

            old_po_item.received_qty = Decimal(old_po_item.received_qty or 0) - old_qty
            if old_po_item.received_qty < D0:
                old_po_item.received_qty = D0
            old_po_item.save(update_fields=["received_qty"])

            old_item.stock_qty = Decimal(old_item.stock_qty or 0) - old_qty
            if old_item.stock_qty < D0:
                raise ValidationError(f"Stock cannot go below zero for {old_item.name}.")
            old_item.save(update_fields=["stock_qty"])

            StoreStockMovement.objects.create(
                hotel=old_item.hotel,
                item=old_item,
                movement_type=StoreStockMovement.MovementType.ADJUSTMENT,
                quantity=-old_qty,
                balance_after=old_item.stock_qty,
                reference=instance.goods_receipt.receipt_number,
                created_by=instance.goods_receipt.received_by,
                note=f"Goods receipt item moved out from {old_item.name}",
            )

            po_item.received_qty = Decimal(po_item.received_qty or 0) + new_qty
            if po_item.received_qty > Decimal(po_item.qty_ordered or 0):
                raise ValidationError(
                    f"Received quantity cannot exceed ordered quantity for {item.name}."
                )
            po_item.save(update_fields=["received_qty"])

            item.stock_qty = Decimal(item.stock_qty or 0) + new_qty
            item.cost_price = Decimal(instance.unit_cost or item.cost_price or D0)
            item.save(update_fields=["stock_qty", "cost_price"])

            StoreStockMovement.objects.create(
                hotel=item.hotel,
                item=item,
                movement_type=StoreStockMovement.MovementType.PURCHASE,
                quantity=new_qty,
                balance_after=item.stock_qty,
                reference=instance.goods_receipt.receipt_number,
                created_by=instance.goods_receipt.received_by,
                note=f"Goods receipt item moved into {item.name}",
            )

            old_po_item.purchase_order.refresh_status()
            po_item.purchase_order.refresh_status()
            return

        diff = new_qty - old_qty
        if diff == 0:
            return

        new_received_qty = Decimal(po_item.received_qty or 0) + diff
        if new_received_qty < D0:
            raise ValidationError(f"Received quantity cannot go below zero for {item.name}.")
        if new_received_qty > Decimal(po_item.qty_ordered or 0):
            raise ValidationError(
                f"Received quantity cannot exceed ordered quantity for {item.name}."
            )

        po_item.received_qty = new_received_qty
        po_item.save(update_fields=["received_qty"])

        item.stock_qty = Decimal(item.stock_qty or 0) + diff
        if item.stock_qty < D0:
            raise ValidationError(f"Stock cannot go below zero for {item.name}.")
        item.cost_price = Decimal(instance.unit_cost or item.cost_price or D0)
        item.save(update_fields=["stock_qty", "cost_price"])

        movement_type = (
            StoreStockMovement.MovementType.PURCHASE
            if diff > 0
            else StoreStockMovement.MovementType.ADJUSTMENT
        )

        StoreStockMovement.objects.create(
            hotel=item.hotel,
            item=item,
            movement_type=movement_type,
            quantity=diff,
            balance_after=item.stock_qty,
            reference=instance.goods_receipt.receipt_number,
            created_by=instance.goods_receipt.received_by,
            note=f"Goods receipt item updated for {instance.goods_receipt.receipt_number}",
        )

        po_item.purchase_order.refresh_status()


@receiver(post_delete, sender=StoreGoodsReceiptItem)
def reverse_store_stock_on_goods_receipt_delete(sender, instance, **kwargs):
    """
    Reverse stock and PO received_qty when a goods receipt item is deleted.
    """
    with transaction.atomic():
        po_item = StorePurchaseOrderItem.objects.select_for_update().select_related(
            "item", "purchase_order"
        ).get(pk=instance.purchase_order_item_id)

        item = StoreItem.objects.select_for_update().get(pk=po_item.item_id)
        qty = Decimal(instance.qty_received or 0)

        po_item.received_qty = Decimal(po_item.received_qty or 0) - qty
        if po_item.received_qty < D0:
            po_item.received_qty = D0
        po_item.save(update_fields=["received_qty"])

        item.stock_qty = Decimal(item.stock_qty or 0) - qty
        if item.stock_qty < D0:
            raise ValidationError(f"Stock cannot go below zero for {item.name}.")
        item.save(update_fields=["stock_qty"])

        StoreStockMovement.objects.create(
            hotel=item.hotel,
            item=item,
            movement_type=StoreStockMovement.MovementType.ADJUSTMENT,
            quantity=-qty,
            balance_after=item.stock_qty,
            reference=instance.goods_receipt.receipt_number,
            created_by=instance.goods_receipt.received_by,
            note=f"Goods receipt item removed from {instance.goods_receipt.receipt_number}",
        )

        po_item.purchase_order.refresh_status()