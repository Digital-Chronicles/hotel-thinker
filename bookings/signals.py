# bookings/signals.py — FULL REWRITE (NO recursion)
from __future__ import annotations

from decimal import Decimal
from django.db import transaction
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import Booking, AdditionalCharge
from finance.models import Invoice, InvoiceLineItem, Payment


ZERO = Decimal("0")


def _d(v) -> Decimal:
    try:
        return Decimal(v or 0)
    except Exception:
        return ZERO


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def _ensure_invoice_for_booking(booking: Booking) -> Invoice:
    """
    Create invoice once (or fetch if exists).
    Must NOT call booking.save() here.
    """
    guest = booking.guest

    invoice, _ = Invoice.objects.get_or_create(
        booking=booking,
        defaults={
            "hotel": booking.hotel,
            "customer_name": guest.full_name,
            "customer_email": guest.email,
            "customer_phone": guest.phone,
            "status": Invoice.Status.DRAFT,
            "subtotal": _d(booking.subtotal),
            "discount": ZERO,
            "tax_amount": _d(getattr(booking, "tax_amount", 0)),
            "total_amount": _d(booking.total_amount),
            "amount_paid": _d(getattr(booking, "amount_paid", 0)),
        },
    )

    # In case invoice exists but hotel/customer fields are blank/old, update safely
    changed = False
    if invoice.hotel_id != booking.hotel_id:
        invoice.hotel = booking.hotel
        changed = True

    if not invoice.customer_name and guest.full_name:
        invoice.customer_name = guest.full_name
        changed = True
    if not invoice.customer_phone and guest.phone:
        invoice.customer_phone = guest.phone
        changed = True
    if (not invoice.customer_email) and guest.email:
        invoice.customer_email = guest.email
        changed = True

    if changed:
        invoice.save(update_fields=["hotel", "customer_name", "customer_phone", "customer_email", "updated_at"])

    return invoice


def _upsert_booking_room_line_item(invoice: Invoice, booking: Booking) -> None:
    """
    One line item representing the room stay.
    """
    nights = booking.nights if hasattr(booking, "nights") else 0
    qty = int(nights) if int(nights) > 0 else 1
    unit_price = _d(getattr(booking, "nightly_rate", 0))
    total = _d(getattr(booking, "nightly_rate", 0)) * Decimal(qty)

    InvoiceLineItem.objects.update_or_create(
        invoice=invoice,
        booking=booking,
        charge=None,
        defaults={
            "description": f"Room {booking.room.number} ({booking.room.room_type.name})",
            "quantity": qty,
            "unit_price": unit_price,
            "discount": ZERO,
            "tax_rate": ZERO,
            "total": total,
        },
    )


def _upsert_charge_line_item(invoice: Invoice, charge: AdditionalCharge) -> None:
    """
    Each AdditionalCharge becomes an InvoiceLineItem linked by charge FK.
    """
    InvoiceLineItem.objects.update_or_create(
        invoice=invoice,
        charge=charge,
        defaults={
            "booking": charge.booking,
            "description": charge.description,
            "quantity": int(charge.quantity or 1),
            "unit_price": _d(charge.unit_price),
            "discount": ZERO,
            "tax_rate": ZERO,
            "total": _d(charge.total),
        },
    )


def _recalculate_invoice_from_booking(invoice: Invoice, booking: Booking) -> None:
    """
    Keep invoice totals aligned with booking totals.
    (Room pricing comes from booking which already auto fetches RoomType.base_price)
    """
    invoice.subtotal = _d(booking.subtotal)
    invoice.tax_amount = _d(getattr(booking, "tax_amount", 0))
    invoice.discount = ZERO
    invoice.total_amount = _d(booking.total_amount)

    # IMPORTANT: do NOT override amount_paid here (payments manage it)
    invoice.save(update_fields=["subtotal", "tax_amount", "discount", "total_amount", "updated_at"])


def _sync_booking_paid_from_invoice_no_recursion(booking: Booking, invoice: Invoice) -> None:
    """
    CRITICAL: never do booking.save() here.
    Use queryset update to avoid triggering Booking post_save again.
    """
    total = _d(booking.total_amount)
    paid = _d(invoice.amount_paid)

    if total <= 0:
        status = Booking.PaymentStatus.PAID
    elif paid <= 0:
        status = Booking.PaymentStatus.PENDING
    elif paid < total:
        status = Booking.PaymentStatus.PARTIALLY_PAID
    else:
        status = Booking.PaymentStatus.PAID

    Booking.objects.filter(pk=booking.pk).update(
        amount_paid=paid,
        payment_status=status,
    )


# ------------------------------------------------------------
# Signals
# ------------------------------------------------------------
@receiver(post_save, sender=Booking)
def booking_auto_invoice(sender, instance: Booking, created: bool, raw: bool, **kwargs):
    """
    Auto-create/update invoice + line items whenever booking is created/updated.
    SAFE: No booking.save() inside this signal.
    """
    if raw:
        return

    # Don't invoice cancelled/no-show bookings (optional rule)
    if instance.status in [Booking.Status.CANCELLED, Booking.Status.NO_SHOW]:
        return

    with transaction.atomic():
        invoice = _ensure_invoice_for_booking(instance)

        # Room line item
        _upsert_booking_room_line_item(invoice, instance)

        # Ensure additional charge items exist too
        for charge in instance.additional_charges.all():
            _upsert_charge_line_item(invoice, charge)

        # Update invoice totals based on booking totals
        _recalculate_invoice_from_booking(invoice, instance)

        # Sync booking amount_paid snapshot from invoice without recursion
        _sync_booking_paid_from_invoice_no_recursion(instance, invoice)


@receiver(post_save, sender=AdditionalCharge)
def additional_charge_sync_invoice(sender, instance: AdditionalCharge, created: bool, raw: bool, **kwargs):
    """
    When a charge is added/updated, update invoice line item and totals.
    """
    if raw:
        return

    booking = instance.booking
    if booking.status in [Booking.Status.CANCELLED, Booking.Status.NO_SHOW]:
        return

    with transaction.atomic():
        invoice = _ensure_invoice_for_booking(booking)
        _upsert_charge_line_item(invoice, instance)

        # Booking.save() will recalc totals; BUT do not call from here to avoid loops.
        # Instead, align invoice to current booking totals (booking totals are handled elsewhere).
        _recalculate_invoice_from_booking(invoice, booking)


@receiver(post_delete, sender=AdditionalCharge)
def additional_charge_delete_sync_invoice(sender, instance: AdditionalCharge, **kwargs):
    """
    When a charge is deleted, remove its invoice line item and update totals.
    """
    booking = instance.booking

    # If invoice exists, delete matching line item
    try:
        invoice = Invoice.objects.get(booking=booking)
    except Invoice.DoesNotExist:
        return

    with transaction.atomic():
        InvoiceLineItem.objects.filter(invoice=invoice, charge_id=instance.pk).delete()
        _recalculate_invoice_from_booking(invoice, booking)


@receiver(post_save, sender=Payment)
def payment_sync_booking(sender, instance: Payment, created: bool, raw: bool, **kwargs):
    """
    When a payment is recorded, sync booking.amount_paid snapshot safely.
    Payment model already updates invoice.amount_paid inside Invoice.record_payment() :contentReference[oaicite:1]{index=1}
    """
    if raw:
        return

    invoice = instance.invoice
    if not invoice or not invoice.booking_id:
        return

    booking = invoice.booking

    # Sync booking paid snapshot safely (NO booking.save())
    _sync_booking_paid_from_invoice_no_recursion(booking, invoice)