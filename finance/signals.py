# finance/signals.py
from __future__ import annotations

from decimal import Decimal
from django.db import transaction
from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from django.db.models import Sum

from finance.models import Invoice, InvoiceLineItem, Payment, Expense, ExpenseAuditLog
from bookings.models import Booking, AdditionalCharge


# -----------------------------
# Helpers
# -----------------------------

def _recalc_invoice_from_lines(invoice: Invoice) -> None:
    """
    Recalculate invoice.subtotal/tax/total based on InvoiceLineItem rows.
    Keeps your Invoice.calculate_totals() logic intact. :contentReference[oaicite:9]{index=9}
    """
    totals = invoice.line_items.aggregate(
        s=Sum("total"),
    )
    subtotal = totals["s"] or Decimal("0")

    invoice.subtotal = subtotal
    invoice.calculate_totals()  # uses discount/tax_rate rules :contentReference[oaicite:10]{index=10}
    invoice.save(update_fields=["subtotal", "tax_amount", "total_amount", "updated_at"])


def _ensure_booking_invoice(booking: Booking) -> Invoice:
    """
    Create or update an invoice for a booking. Booking has OneToOne invoice link in Invoice model. :contentReference[oaicite:11]{index=11}
    """
    inv = getattr(booking, "invoice", None)

    if inv is None:
        # Use booking guest data as customer snapshot (denormalized historical accuracy) :contentReference[oaicite:12]{index=12}
        inv = Invoice.objects.create(
            hotel=booking.hotel,
            booking=booking,
            customer_name=booking.guest.full_name,
            customer_email=booking.guest.email,
            customer_phone=booking.guest.phone,
            invoice_date=timezone.now().date(),
            due_date=timezone.now().date() + timezone.timedelta(days=30),
            status=Invoice.Status.ISSUED,  # or DRAFT if you prefer
            currency="USD",               # adjust if you want UGX
            tax_rate=booking.tax_rate or Decimal("0"),
            subtotal=Decimal("0"),
            discount=booking.discount or Decimal("0"),
            discount_type=booking.discount_type or "fixed",
        )
    else:
        # keep invoice in sync with booking basics
        inv.customer_name = booking.guest.full_name
        inv.customer_email = booking.guest.email
        inv.customer_phone = booking.guest.phone
        inv.tax_rate = booking.tax_rate or Decimal("0")
        inv.discount = booking.discount or Decimal("0")
        inv.discount_type = booking.discount_type or "fixed"
        inv.save(update_fields=["customer_name", "customer_email", "customer_phone", "tax_rate", "discount", "discount_type", "updated_at"])

    return inv


def _upsert_room_nights_line(inv: Invoice, booking: Booking) -> None:
    """
    Make a single line item: Room Nights (nights × nightly_rate).
    Booking has nights + nightly_rate. :contentReference[oaicite:13]{index=13}
    """
    nights = Decimal(str(booking.nights or 0))
    unit_price = booking.nightly_rate or Decimal("0")
    total = (nights * unit_price) - Decimal("0")

    li, created = InvoiceLineItem.objects.get_or_create(
        invoice=inv,
        booking=booking,
        charge=None,
        defaults={
            "description": f"Room nights ({int(nights)} night(s))",
            "quantity": int(nights) if nights > 0 else 1,
            "unit_price": unit_price,
            "discount": Decimal("0"),
            "tax_rate": inv.tax_rate or Decimal("0"),
            "total": total,
        },
    )

    # update if booking changed
    if not created:
        li.description = f"Room nights ({int(nights)} night(s))"
        li.quantity = int(nights) if nights > 0 else 1
        li.unit_price = unit_price
        li.discount = Decimal("0")
        li.tax_rate = inv.tax_rate or Decimal("0")
        li.total = (Decimal(li.quantity) * li.unit_price) - li.discount
        li.save(update_fields=["description", "quantity", "unit_price", "discount", "tax_rate", "total"])


# -----------------------------
# Booking → Invoice auto-post
# -----------------------------

@receiver(post_save, sender=Booking)
def booking_auto_invoice(sender, instance: Booking, created: bool, **kwargs):
    """
    Any booking create/update ensures an invoice exists and line items match booking.
    Booking model is in bookings app. :contentReference[oaicite:14]{index=14}
    """
    with transaction.atomic():
        inv = _ensure_booking_invoice(instance)
        _upsert_room_nights_line(inv, instance)

        # Optional: add extra bed charge as its own line (if you want)
        if (instance.extra_bed_charge or Decimal("0")) > 0:
            li, _ = InvoiceLineItem.objects.get_or_create(
                invoice=inv,
                booking=instance,
                charge=None,
                description="Extra bed charge",
                defaults={
                    "quantity": 1,
                    "unit_price": instance.extra_bed_charge,
                    "discount": Decimal("0"),
                    "tax_rate": inv.tax_rate or Decimal("0"),
                    "total": instance.extra_bed_charge,
                },
            )
            # If it existed with same description, keep in sync
            li.quantity = 1
            li.unit_price = instance.extra_bed_charge
            li.total = (Decimal(li.quantity) * li.unit_price) - (li.discount or Decimal("0"))
            li.save(update_fields=["quantity", "unit_price", "total", "tax_rate"])

        _recalc_invoice_from_lines(inv)


# -----------------------------
# AdditionalCharge → InvoiceLineItem auto-post
# -----------------------------

@receiver(post_save, sender=AdditionalCharge)
def charge_to_invoice_line(sender, instance: AdditionalCharge, created: bool, **kwargs):
    """
    When a charge is added to a booking, add it to invoice line items and recalc invoice.
    AdditionalCharge exists in bookings app. :contentReference[oaicite:15]{index=15}
    """
    booking = instance.booking
    inv = getattr(booking, "invoice", None)
    if inv is None:
        # In case charge comes before invoice is created
        inv = _ensure_booking_invoice(booking)

    with transaction.atomic():
        li, _ = InvoiceLineItem.objects.get_or_create(
            invoice=inv,
            charge=instance,   # link to the charge for traceability :contentReference[oaicite:16]{index=16}
            defaults={
                "booking": booking,
                "description": instance.description,
                "quantity": instance.quantity or 1,
                "unit_price": instance.unit_price,
                "discount": Decimal("0"),
                "tax_rate": inv.tax_rate or Decimal("0"),
                "total": instance.total,
            }
        )

        # sync updates if charge edited
        li.description = instance.description
        li.quantity = instance.quantity or 1
        li.unit_price = instance.unit_price
        li.total = (Decimal(li.quantity) * li.unit_price) - (li.discount or Decimal("0"))
        li.save(update_fields=["description", "quantity", "unit_price", "total"])

        _recalc_invoice_from_lines(inv)


@receiver(post_delete, sender=AdditionalCharge)
def charge_deleted_remove_line(sender, instance: AdditionalCharge, **kwargs):
    booking = instance.booking
    inv = getattr(booking, "invoice", None)
    if inv is None:
        return
    with transaction.atomic():
        InvoiceLineItem.objects.filter(invoice=inv, charge=instance).delete()
        _recalc_invoice_from_lines(inv)


# -----------------------------
# Payment → Invoice auto-update
# -----------------------------

@receiver(post_save, sender=Payment)
def payment_updates_invoice(sender, instance: Payment, created: bool, **kwargs):
    """
    If payments are created from admin/API, invoice balance updates automatically.
    Payment model in finance. :contentReference[oaicite:17]{index=17}
    """
    if not created:
        return

    inv = instance.invoice
    if inv.status == Invoice.Status.VOID:
        return

    with transaction.atomic():
        inv.amount_paid = (inv.amount_paid or Decimal("0")) + (instance.amount or Decimal("0"))

        if inv.amount_paid >= inv.total_amount:
            inv.status = Invoice.Status.PAID
            inv.paid_at = timezone.now()
        elif inv.amount_paid > 0:
            inv.status = Invoice.Status.PARTIALLY_PAID

        inv.save(update_fields=["amount_paid", "status", "paid_at", "updated_at"])


# -----------------------------
# Expense audit auto logs
# -----------------------------

@receiver(post_save, sender=Expense)
def expense_audit(sender, instance: Expense, created: bool, **kwargs):
    """
    Auto audit entries for Expense creates/updates.
    Expense exists in finance. :contentReference[oaicite:18]{index=18}
    """
    action = ExpenseAuditLog.Action.CREATE if created else ExpenseAuditLog.Action.UPDATE
    ExpenseAuditLog.objects.create(
        expense=instance,
        action=action,
        user=instance.created_by if created else None,
        description=f"Expense {action} via signal",
    )