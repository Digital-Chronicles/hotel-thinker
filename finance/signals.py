# finance/signals.py
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from bookings.models import AdditionalCharge, Booking
from finance.models import Expense, ExpenseAuditLog, Invoice, InvoiceLineItem, Payment


D0 = Decimal("0")


# -----------------------------
# Helpers
# -----------------------------

def _recalc_invoice_from_lines(invoice: Invoice) -> None:
    """
    Recalculate invoice subtotal/tax/total from linked line items.
    Keeps Invoice.calculate_totals() as the source of truth.
    """
    subtotal = invoice.line_items.aggregate(s=Sum("total"))["s"] or D0
    invoice.subtotal = Decimal(subtotal or D0)
    invoice.calculate_totals()

    update_fields = ["subtotal", "tax_amount", "total_amount", "updated_at"]

    # Keep invoice status sensible after line recalculation
    if invoice.amount_paid >= invoice.total_amount and invoice.total_amount > D0:
        invoice.status = Invoice.Status.PAID
        if not invoice.paid_at:
            invoice.paid_at = timezone.now()
        update_fields.extend(["status", "paid_at"])
    elif invoice.amount_paid > D0:
        invoice.status = Invoice.Status.PARTIALLY_PAID
        invoice.paid_at = None
        update_fields.extend(["status", "paid_at"])
    elif invoice.status not in [Invoice.Status.DRAFT, Invoice.Status.PROFORMA, Invoice.Status.VOID, Invoice.Status.CREDIT_NOTE]:
        invoice.status = Invoice.Status.ISSUED
        invoice.paid_at = None
        update_fields.extend(["status", "paid_at"])

    invoice.save(update_fields=list(dict.fromkeys(update_fields)))


def _get_booking_guest_name(booking: Booking) -> str:
    guest = getattr(booking, "guest", None)
    if guest:
        full_name = getattr(guest, "full_name", None)
        if full_name:
            return full_name
        first_name = getattr(guest, "first_name", "") or ""
        last_name = getattr(guest, "last_name", "") or ""
        combined = f"{first_name} {last_name}".strip()
        if combined:
            return combined
    return f"Booking #{booking.pk}"


def _ensure_booking_invoice(booking: Booking) -> Invoice:
    """
    Create or update invoice linked to booking.
    """
    inv = getattr(booking, "invoice", None)

    guest = getattr(booking, "guest", None)
    customer_name = _get_booking_guest_name(booking)
    customer_email = getattr(guest, "email", None) if guest else None
    customer_phone = getattr(guest, "phone", None) if guest else None

    booking_tax_rate = Decimal(getattr(booking, "tax_rate", D0) or D0)
    booking_discount = Decimal(getattr(booking, "discount", D0) or D0)
    booking_discount_type = getattr(booking, "discount_type", "fixed") or "fixed"

    if inv is None:
        inv = Invoice.objects.create(
            hotel=booking.hotel,
            booking=booking,
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            invoice_date=timezone.localdate(),
            due_date=timezone.localdate() + timezone.timedelta(days=30),
            status=Invoice.Status.ISSUED,
            currency="USD",
            tax_rate=booking_tax_rate,
            subtotal=D0,
            discount=booking_discount,
            discount_type=booking_discount_type,
        )
    else:
        inv.customer_name = customer_name
        inv.customer_email = customer_email
        inv.customer_phone = customer_phone
        inv.tax_rate = booking_tax_rate
        inv.discount = booking_discount
        inv.discount_type = booking_discount_type
        inv.save(
            update_fields=[
                "customer_name",
                "customer_email",
                "customer_phone",
                "tax_rate",
                "discount",
                "discount_type",
                "updated_at",
            ]
        )

    return inv


def _upsert_room_nights_line(inv: Invoice, booking: Booking) -> None:
    """
    Maintain one room-night line item per booking invoice.
    """
    nights = int(getattr(booking, "nights", 0) or 0)
    quantity = nights if nights > 0 else 1
    unit_price = Decimal(getattr(booking, "nightly_rate", D0) or D0)

    li, created = InvoiceLineItem.objects.get_or_create(
        invoice=inv,
        booking=booking,
        charge=None,
        description__startswith="Room nights",
        defaults={
            "description": f"Room nights ({quantity} night(s))",
            "quantity": quantity,
            "unit_price": unit_price,
            "discount": D0,
            "tax_rate": inv.tax_rate or D0,
        },
    )

    if not created:
        li.description = f"Room nights ({quantity} night(s))"
        li.quantity = quantity
        li.unit_price = unit_price
        li.discount = D0
        li.tax_rate = inv.tax_rate or D0

    li.save()


def _upsert_extra_bed_line(inv: Invoice, booking: Booking) -> None:
    """
    Maintain optional extra bed line.
    """
    extra_bed_charge = Decimal(getattr(booking, "extra_bed_charge", D0) or D0)

    existing = InvoiceLineItem.objects.filter(
        invoice=inv,
        booking=booking,
        charge=None,
        description="Extra bed charge",
    ).first()

    if extra_bed_charge > D0:
        if existing is None:
            existing = InvoiceLineItem(
                invoice=inv,
                booking=booking,
                charge=None,
                description="Extra bed charge",
            )

        existing.quantity = 1
        existing.unit_price = extra_bed_charge
        existing.discount = D0
        existing.tax_rate = inv.tax_rate or D0
        existing.save()
    elif existing:
        existing.delete()


# -----------------------------
# Booking -> Invoice sync
# -----------------------------

@receiver(post_save, sender=Booking)
def booking_auto_invoice(sender, instance: Booking, created: bool, **kwargs):
    """
    Ensure booking has an invoice and core booking lines stay in sync.
    """
    with transaction.atomic():
        inv = _ensure_booking_invoice(instance)
        _upsert_room_nights_line(inv, instance)
        _upsert_extra_bed_line(inv, instance)
        _recalc_invoice_from_lines(inv)


# -----------------------------
# AdditionalCharge -> InvoiceLineItem sync
# -----------------------------

@receiver(post_save, sender=AdditionalCharge)
def charge_to_invoice_line(sender, instance: AdditionalCharge, created: bool, **kwargs):
    """
    Sync additional charges into invoice line items.
    """
    booking = instance.booking
    inv = getattr(booking, "invoice", None)
    if inv is None:
        inv = _ensure_booking_invoice(booking)

    with transaction.atomic():
        li, _ = InvoiceLineItem.objects.get_or_create(
            invoice=inv,
            charge=instance,
            defaults={
                "booking": booking,
                "description": instance.description,
                "quantity": instance.quantity or 1,
                "unit_price": instance.unit_price or D0,
                "discount": D0,
                "tax_rate": inv.tax_rate or D0,
            },
        )

        li.booking = booking
        li.description = instance.description
        li.quantity = instance.quantity or 1
        li.unit_price = instance.unit_price or D0
        li.tax_rate = inv.tax_rate or D0
        li.save()

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
# Payment -> Invoice sync
# -----------------------------

@receiver(post_save, sender=Payment)
def payment_updates_invoice(sender, instance: Payment, created: bool, **kwargs):
    """
    Keep invoice totals in sync when payments are created outside Invoice.record_payment().

    Important:
    - If Payment was created through Invoice.record_payment(), that method already updates invoice.amount_paid.
    - So here we recompute from all completed/refunded payments instead of incrementing blindly.
    """
    inv = instance.invoice
    if inv.status == Invoice.Status.VOID:
        return

    with transaction.atomic():
        completed_total = inv.payments.filter(
            status__in=[
                Payment.PaymentStatus.COMPLETED,
                Payment.PaymentStatus.PARTIALLY_REFUNDED,
                Payment.PaymentStatus.REFUNDED,
            ]
        ).aggregate(t=Sum("amount"))["t"] or D0

        refunded_total = (
            inv.payments.filter(
                status__in=[
                    Payment.PaymentStatus.PARTIALLY_REFUNDED,
                    Payment.PaymentStatus.REFUNDED,
                ]
            )
            .aggregate(t=Sum("refunds__amount"))["t"] or D0
        )

        net_paid = Decimal(completed_total or D0) - Decimal(refunded_total or D0)
        if net_paid < D0:
            net_paid = D0

        inv.amount_paid = net_paid

        if inv.amount_paid >= Decimal(inv.total_amount or D0) and Decimal(inv.total_amount or D0) > D0:
            inv.status = Invoice.Status.PAID
            if not inv.paid_at:
                inv.paid_at = timezone.now()
        elif inv.amount_paid > D0:
            inv.status = Invoice.Status.PARTIALLY_PAID
            inv.paid_at = None
        else:
            if inv.due_date and inv.due_date < timezone.localdate():
                inv.status = Invoice.Status.OVERDUE
            else:
                inv.status = Invoice.Status.ISSUED
            inv.paid_at = None

        inv.save(update_fields=["amount_paid", "status", "paid_at", "updated_at"])


# -----------------------------
# Expense audit logs
# -----------------------------

@receiver(post_save, sender=Expense)
def expense_audit(sender, instance: Expense, created: bool, **kwargs):
    """
    Create simple audit entries for create/update.

    To avoid noisy logs:
    - create a CREATE log once
    - create UPDATE only when the record already exists
    """
    if created:
        ExpenseAuditLog.objects.create(
            expense=instance,
            action=ExpenseAuditLog.Action.CREATE,
            user=instance.created_by,
            description="Expense created via signal",
        )
        return

    ExpenseAuditLog.objects.create(
        expense=instance,
        action=ExpenseAuditLog.Action.UPDATE,
        user=None,
        description="Expense updated via signal",
    )