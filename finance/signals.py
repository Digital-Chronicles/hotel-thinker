# finance/signals.py
from decimal import Decimal
import logging

from django.db import transaction
from django.db.models import Sum
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from bookings.models import Booking, AdditionalCharge
from finance.models import Invoice, InvoiceLineItem, Payment, Expense, ExpenseAuditLog, CashMovement, Account, JournalEntry, JournalLine
from restaurant.models import RestaurantInvoice, RestaurantPayment
from bar.models import BarOrder
from services.models import ServiceBooking, ServiceBookingExtra, ServicePayment
from store.models import StoreSale, StoreGoodsReceipt

# Set up logging
logger = logging.getLogger(__name__)

D0 = Decimal("0.00")


def money(value):
    """Safely convert value to Decimal"""
    try:
        return Decimal(str(value or 0))
    except Exception:
        return D0


def invoice_status(invoice):
    """Determine invoice status based on paid amount"""
    total = money(invoice.total_amount)
    paid = money(invoice.amount_paid)

    if total > D0 and paid >= total:
        return Invoice.Status.PAID
    if paid > D0:
        return Invoice.Status.PARTIALLY_PAID
    return Invoice.Status.ISSUED


def recalc_invoice(invoice):
    """Recalculate invoice totals from line items"""
    try:
        subtotal = invoice.line_items.aggregate(total=Sum("total"))["total"] or D0
        invoice.subtotal = money(subtotal)
        invoice.calculate_totals()
        invoice.status = invoice_status(invoice)

        if invoice.status == Invoice.Status.PAID:
            invoice.paid_at = invoice.paid_at or timezone.now()

        invoice.save(update_fields=[
            "subtotal",
            "tax_amount",
            "total_amount",
            "status",
            "paid_at",
            "updated_at",
        ])
    except Exception as e:
        logger.error(f"Error recalculating invoice {invoice.id}: {e}")


def upsert_line(invoice, description, quantity, unit_price):
    """Create or update invoice line item"""
    try:
        line, created = InvoiceLineItem.objects.get_or_create(
            invoice=invoice,
            description=description,
        )
        line.quantity = max(int(money(quantity)), 1)
        line.unit_price = money(unit_price)
        line.discount = D0
        line.tax_rate = D0
        line.save()
        return line
    except Exception as e:
        logger.error(f"Error upserting line for invoice {invoice.id}: {e}")
        return None


def sync_cash_movement(
    *,
    hotel,
    source_type,
    source_id,
    direction,
    amount,
    reference="",
    description="",
    cash_account=None,
    user=None,
):
    """Synchronize cash movement with accounting"""
    amount = money(amount)

    if amount <= D0:
        return None

    try:
        with transaction.atomic():
            movement = CashMovement.objects.filter(
                hotel=hotel,
                source_type=source_type,
                source_id=source_id,
            ).first()

            old_amount = money(movement.amount) if movement else D0
            old_direction = movement.direction if movement else None
            old_cash_account = movement.cash_account if movement else None

            if movement is None:
                movement = CashMovement(
                    hotel=hotel,
                    source_type=source_type,
                    source_id=source_id,
                )

            movement.direction = direction
            movement.amount = amount
            movement.reference = reference
            movement.description = description
            movement.cash_account = cash_account
            movement.created_by = user

            if cash_account:
                if old_cash_account and old_amount > D0:
                    old_cash_account.adjust_balance(
                        old_amount,
                        increase=(old_direction == CashMovement.Direction.CASH_OUT),
                    )

                cash_account.adjust_balance(
                    amount,
                    increase=(direction == CashMovement.Direction.CASH_IN),
                )
                movement.balance_after = cash_account.current_balance

            movement.save()
            return movement
    except Exception as e:
        logger.error(f"Error syncing cash movement for {source_type}#{source_id}: {e}")
        return None


def create_journal_entry_for_invoice(invoice):
    """Create journal entry for invoice"""
    try:
        if invoice.status != Invoice.Status.PAID:
            return None

        # Check if journal entry already exists
        if JournalEntry.objects.filter(reference_type="invoice", reference_id=invoice.id).exists():
            return None

        # Get accounts
        receivable_account = invoice.receivable_account or Account.objects.filter(
            hotel=invoice.hotel,
            account_type=Account.AccountType.ASSET,
            account_subtype=Account.SubType.RECEIVABLE,
        ).first()

        revenue_account = invoice.revenue_account or Account.objects.filter(
            hotel=invoice.hotel,
            account_type=Account.AccountType.REVENUE,
            account_subtype=Account.SubType.SALES,
        ).first()

        if not receivable_account or not revenue_account:
            logger.warning(f"Missing accounts for invoice {invoice.id}")
            return None

        with transaction.atomic():
            journal = JournalEntry.objects.create(
                hotel=invoice.hotel,
                entry_date=invoice.paid_at or timezone.now(),
                reference_type="invoice",
                reference_id=invoice.id,
                description=f"Invoice {invoice.invoice_number} payment",
                status=JournalEntry.Status.POSTED,
                posted_at=timezone.now(),
            )

            # Debit: Accounts Receivable
            JournalLine.objects.create(
                journal_entry=journal,
                account=receivable_account,
                description=f"Invoice {invoice.invoice_number}",
                debit=invoice.total_amount,
                credit=D0,
            )

            # Credit: Revenue (or appropriate account)
            JournalLine.objects.create(
                journal_entry=journal,
                account=revenue_account,
                description=f"Revenue from invoice {invoice.invoice_number}",
                debit=D0,
                credit=invoice.total_amount,
            )

            return journal

    except Exception as e:
        logger.error(f"Error creating journal entry for invoice {invoice.id}: {e}")
        return None


# =========================
# BOOKING → INVOICE
# =========================

@receiver(post_save, sender=Booking)
def booking_to_invoice(sender, instance, created, raw=False, **kwargs):
    """Create invoice when booking is created or updated"""
    if raw:
        return

    try:
        if instance.status in [Booking.Status.CANCELLED, Booking.Status.NO_SHOW]:
            invoice = getattr(instance, "invoice", None)
            if invoice and invoice.status != Invoice.Status.PAID:
                invoice.status = Invoice.Status.VOID
                invoice.voided_at = timezone.now()
                invoice.void_reason = f"Booking {instance.get_status_display()}"
                invoice.save()
                logger.info(f"Invoice {invoice.invoice_number} voided for cancelled booking {instance.booking_number}")
            return

        guest = getattr(instance, "guest", None)

        invoice, created = Invoice.objects.get_or_create(
            booking=instance,
            defaults={
                "hotel": instance.hotel,
                "customer_name": getattr(guest, "full_name", None) or "Guest",
                "customer_phone": getattr(guest, "phone", None),
                "customer_email": getattr(guest, "email", None),
                "invoice_date": timezone.localdate(),
                "due_date": timezone.localdate(),
                "currency": "UGX",
                "status": Invoice.Status.ISSUED,
                "created_by": getattr(instance, "created_by", None),
            },
        )

        nights = getattr(instance, "nights", 1) or 1
        nightly_rate = money(getattr(instance, "nightly_rate", 0))

        if nights > 0 and nightly_rate > D0:
            upsert_line(
                invoice,
                f"Room nights ({nights} night(s)) - Room {instance.room.number}",
                nights,
                nightly_rate,
            )

        extra_bed = money(getattr(instance, "extra_bed_charge", 0))
        if extra_bed > D0:
            upsert_line(invoice, "Extra bed charge", 1, extra_bed)

        for charge in instance.additional_charges.all():
            if money(charge.total) > D0:
                upsert_line(invoice, charge.description, charge.quantity, charge.unit_price)

        recalc_invoice(invoice)

        if created:
            logger.info(f"Invoice {invoice.invoice_number} created for booking {instance.booking_number}")

    except Exception as e:
        logger.error(f"Error creating invoice for booking {instance.booking_number}: {e}")


# =========================
# RESTAURANT → FINANCE
# =========================

@receiver(post_save, sender=RestaurantInvoice)
def restaurant_invoice_to_finance(sender, instance, created, raw=False, **kwargs):
    """Create finance invoice from restaurant invoice"""
    if raw:
        return

    try:
        order = instance.order
        key = f"REST-{instance.pk}"

        invoice, created = Invoice.objects.get_or_create(
            hotel=instance.hotel,
            order_number=key,
            booking=None,
            defaults={
                "customer_name": order.customer_name or "Walk-in Customer",
                "customer_phone": order.customer_phone,
                "customer_email": order.customer_email,
                "invoice_date": timezone.localdate(),
                "due_date": timezone.localdate(),
                "currency": "UGX",
                "status": Invoice.Status.ISSUED,
                "notes": f"Restaurant order {order.order_number}",
                "created_by": order.created_by,
            },
        )

        for item in order.items.select_related("item"):
            if item.unit_price > 0:
                upsert_line(
                    invoice,
                    f"Restaurant item: {item.item.name}",
                    item.qty,
                    item.unit_price,
                )

        recalc_invoice(invoice)

    except Exception as e:
        logger.error(f"Error creating finance invoice for restaurant invoice {instance.pk}: {e}")


@receiver(post_save, sender=RestaurantPayment)
def restaurant_payment_to_finance(sender, instance, created, raw=False, **kwargs):
    """Record restaurant payment in finance system"""
    if raw:
        return

    try:
        restaurant_invoice_to_finance(RestaurantInvoice, instance.invoice, False)

        finance_invoice = Invoice.objects.filter(
            hotel=instance.hotel,
            order_number=f"REST-{instance.invoice.pk}",
        ).first()

        if not finance_invoice:
            return

        payment, created = Payment.objects.get_or_create(
            invoice=finance_invoice,
            reference=f"RESTPAY-{instance.pk}",
            defaults={
                "hotel": instance.hotel,
                "amount": instance.amount,
                "currency": "UGX",
                "status": Payment.PaymentStatus.COMPLETED,
                "received_by": instance.received_by,
                "notes": "Restaurant payment",
            },
        )

        if not created:
            payment.amount = instance.amount
            payment.status = Payment.PaymentStatus.COMPLETED
            payment.save()

    except Exception as e:
        logger.error(f"Error recording restaurant payment {instance.pk}: {e}")


# =========================
# BAR → FINANCE
# =========================

@receiver(post_save, sender=BarOrder)
def bar_order_to_finance(sender, instance, created, raw=False, **kwargs):
    """Create invoice for bar order when billed or paid"""
    if raw:
        return

    try:
        key = f"BAR-{instance.pk}"

        if instance.status == BarOrder.Status.CANCELLED:
            invoice = Invoice.objects.filter(hotel=instance.hotel, order_number=key).first()
            if invoice and invoice.status != Invoice.Status.PAID:
                invoice.status = Invoice.Status.VOID
                invoice.voided_at = timezone.now()
                invoice.void_reason = "Bar order cancelled"
                invoice.save()
                logger.info(f"Invoice {invoice.invoice_number} voided for cancelled bar order {instance.order_number}")
            return

        if instance.status not in [BarOrder.Status.BILLED, BarOrder.Status.PAID]:
            return

        invoice, created = Invoice.objects.get_or_create(
            hotel=instance.hotel,
            order_number=key,
            booking=None,
            defaults={
                "customer_name": instance.display_name,
                "invoice_date": timezone.localdate(),
                "due_date": timezone.localdate(),
                "currency": "UGX",
                "status": Invoice.Status.ISSUED,
                "notes": f"Bar order {instance.order_number}",
                "created_by": instance.created_by,
            },
        )

        for item in instance.items.select_related("item"):
            if item.unit_price > 0:
                upsert_line(
                    invoice,
                    f"Bar item: {item.item.name}",
                    item.qty,
                    item.unit_price,
                )

        recalc_invoice(invoice)

        if instance.status == BarOrder.Status.PAID:
            payment, _ = Payment.objects.update_or_create(
                invoice=invoice,
                reference=f"BARPAY-{instance.pk}",
                defaults={
                    "hotel": instance.hotel,
                    "amount": invoice.total_amount,
                    "currency": "UGX",
                    "status": Payment.PaymentStatus.COMPLETED,
                    "received_by": instance.created_by,
                    "notes": "Auto bar payment",
                },
            )
            logger.info(f"Payment recorded for bar order {instance.order_number}")

    except Exception as e:
        logger.error(f"Error creating invoice for bar order {instance.order_number}: {e}")


# =========================
# SERVICES → FINANCE
# =========================

@receiver(post_save, sender=ServiceBooking)
def service_booking_to_finance(sender, instance, created, raw=False, **kwargs):
    """Create invoice for service booking"""
    if raw:
        return

    try:
        key = f"SRV-{instance.pk}"

        if instance.status in [ServiceBooking.Status.CANCELLED, ServiceBooking.Status.NO_SHOW]:
            invoice = Invoice.objects.filter(hotel=instance.hotel, order_number=key).first()
            if invoice and invoice.status != Invoice.Status.PAID:
                invoice.status = Invoice.Status.VOID
                invoice.voided_at = timezone.now()
                invoice.void_reason = f"Service {instance.get_status_display()}"
                invoice.save()
            return

        invoice, created = Invoice.objects.get_or_create(
            hotel=instance.hotel,
            order_number=key,
            booking=None,
            defaults={
                "customer_name": instance.customer_name,
                "customer_phone": instance.customer_phone,
                "invoice_date": timezone.localdate(),
                "due_date": timezone.localdate(),
                "currency": "UGX",
                "status": Invoice.Status.ISSUED,
                "notes": f"Service booking {instance.reference}",
                "created_by": instance.created_by,
            },
        )

        if instance.unit_price > 0:
            upsert_line(
                invoice,
                f"Service: {instance.service.name}",
                instance.quantity,
                instance.unit_price,
            )

        for extra in instance.extras.all():
            if extra.unit_price > 0:
                upsert_line(invoice, f"Extra: {extra.name}", extra.quantity, extra.unit_price)

        recalc_invoice(invoice)

    except Exception as e:
        logger.error(f"Error creating invoice for service booking {instance.reference}: {e}")


@receiver(post_save, sender=ServiceBookingExtra)
def service_extra_to_finance(sender, instance, created, raw=False, **kwargs):
    """Update invoice when service extra is added"""
    if raw:
        return
    service_booking_to_finance(ServiceBooking, instance.service_booking, False)


@receiver(post_save, sender=ServicePayment)
def service_payment_to_finance(sender, instance, created, raw=False, **kwargs):
    """Record service payment in finance system"""
    if raw:
        return

    try:
        service_booking = instance.service_booking
        service_booking_to_finance(ServiceBooking, service_booking, False)

        invoice = Invoice.objects.filter(
            hotel=service_booking.hotel,
            order_number=f"SRV-{service_booking.pk}",
        ).first()

        if not invoice:
            return

        payment, _ = Payment.objects.update_or_create(
            invoice=invoice,
            reference=f"SRVPAY-{instance.pk}",
            defaults={
                "hotel": service_booking.hotel,
                "amount": instance.amount,
                "currency": "UGX",
                "status": Payment.PaymentStatus.COMPLETED,
                "received_by": instance.received_by,
                "notes": f"Service payment for {service_booking.reference}",
            },
        )

    except Exception as e:
        logger.error(f"Error recording service payment {instance.pk}: {e}")


# =========================
# STORE SALES → FINANCE
# =========================

@receiver(post_save, sender=StoreSale)
def store_sale_to_finance(sender, instance, created, raw=False, **kwargs):
    """Create invoice for store sale"""
    if raw:
        return

    try:
        key = f"STORE-SALE-{instance.pk}"

        invoice, created = Invoice.objects.get_or_create(
            hotel=instance.hotel,
            order_number=key,
            booking=None,
            defaults={
                "customer_name": instance.customer_name or "Walk-in Customer",
                "customer_phone": instance.customer_phone,
                "invoice_date": timezone.localdate(),
                "due_date": timezone.localdate(),
                "currency": "UGX",
                "status": Invoice.Status.ISSUED,
                "notes": f"Store sale {instance.sale_number}",
                "created_by": instance.created_by,
            },
        )

        for item in instance.items.select_related("item"):
            if item.unit_price > 0:
                upsert_line(
                    invoice,
                    f"Store item: {item.item.name}",
                    item.qty,
                    item.unit_price,
                )

        recalc_invoice(invoice)

        if instance.status == StoreSale.Status.PAID:
            payment, _ = Payment.objects.update_or_create(
                invoice=invoice,
                reference=f"STOREPAY-{instance.pk}",
                defaults={
                    "hotel": instance.hotel,
                    "amount": invoice.total_amount,
                    "currency": "UGX",
                    "status": Payment.PaymentStatus.COMPLETED,
                    "received_by": instance.created_by,
                    "notes": f"Store sale payment {instance.sale_number}",
                },
            )

    except Exception as e:
        logger.error(f"Error creating invoice for store sale {instance.sale_number}: {e}")


# =========================
# STORE PURCHASES → EXPENSES
# =========================

@receiver(post_save, sender=StoreGoodsReceipt)
def goods_receipt_to_expense(sender, instance, created, raw=False, **kwargs):
    """Convert goods receipt to expense"""
    if raw:
        return

    try:
        total = money(instance.total_amount)

        if total <= D0:
            return

        supplier = instance.purchase_order.supplier

        expense, created = Expense.objects.update_or_create(
            hotel=instance.hotel,
            invoice_reference=instance.receipt_number,
            defaults={
                "category": Expense.Category.SUPPLIES,
                "department": Expense.Department.STORE,
                "expense_type": Expense.ExpenseType.OPERATIONAL,
                "title": f"Store goods received - {instance.receipt_number}",
                "description": f"Goods received from {supplier.name}",
                "amount": total,
                "currency": "UGX",
                "payment_method": Expense.PaymentMethod.CASH,
                "expense_date": instance.received_date,
                "payee": supplier.name,
                "approval_status": Expense.ApprovalStatus.APPROVED,
                "requested_by": instance.received_by,
                "approved_by": instance.received_by,
                "approved_at": timezone.now(),
                "created_by": instance.received_by,
            },
        )

        if created:
            logger.info(f"Expense created for goods receipt {instance.receipt_number}")

    except Exception as e:
        logger.error(f"Error creating expense for goods receipt {instance.receipt_number}: {e}")


# =========================
# PAYMENT → CASH MOVEMENT
# =========================

@receiver(post_save, sender=Payment)
def payment_to_cash_movement(sender, instance, created, raw=False, **kwargs):
    """Update invoice and create cash movement when payment is recorded"""
    if raw:
        return

    try:
        invoice = instance.invoice

        # Update invoice paid amount
        paid = invoice.payments.filter(
            status=Payment.PaymentStatus.COMPLETED,
        ).aggregate(total=Sum("amount"))["total"] or D0

        invoice.amount_paid = money(paid)
        invoice.status = invoice_status(invoice)

        if invoice.status == Invoice.Status.PAID:
            invoice.paid_at = invoice.paid_at or timezone.now()
            # Create journal entry for paid invoice
            create_journal_entry_for_invoice(invoice)

        invoice.save(update_fields=["amount_paid", "status", "paid_at", "updated_at"])

        # Update booking payment status if linked
        if invoice.booking_id:
            booking = invoice.booking
            booking.amount_paid = invoice.amount_paid

            if invoice.status == Invoice.Status.PAID:
                booking.payment_status = Booking.PaymentStatus.PAID
            elif invoice.amount_paid > D0:
                booking.payment_status = Booking.PaymentStatus.PARTIALLY_PAID
            else:
                booking.payment_status = Booking.PaymentStatus.PENDING

            booking.save(update_fields=["amount_paid", "payment_status", "updated_at"])
            logger.info(f"Booking {booking.booking_number} payment status updated to {booking.payment_status}")

        # Create cash movement for completed payments
        if instance.status == Payment.PaymentStatus.COMPLETED:
            sync_cash_movement(
                hotel=instance.hotel,
                source_type="finance_payment",
                source_id=instance.pk,
                direction=CashMovement.Direction.CASH_IN,
                amount=instance.amount,
                reference=instance.reference or instance.payment_id,
                description=f"Payment received for invoice {invoice.invoice_number}",
                cash_account=instance.cash_account,
                user=instance.received_by,
            )

    except Exception as e:
        logger.error(f"Error processing payment {instance.payment_id}: {e}")


# =========================
# EXPENSE → CASH MOVEMENT
# =========================

@receiver(pre_save, sender=Expense)
def expense_pre_save(sender, instance, **kwargs):
    """Track old paid amount for cash movement calculation"""
    if instance.pk:
        try:
            old = Expense.objects.get(pk=instance.pk)
            instance._old_paid_amount = old.paid_amount
            instance._old_approval_status = old.approval_status
        except Expense.DoesNotExist:
            instance._old_paid_amount = D0
            instance._old_approval_status = None
    else:
        instance._old_paid_amount = D0
        instance._old_approval_status = None


@receiver(post_save, sender=Expense)
def expense_to_cash_movement(sender, instance, created, raw=False, **kwargs):
    """Create audit log and cash movement for expenses"""
    if raw:
        return

    try:
        # Create audit log
        action = ExpenseAuditLog.Action.CREATE if created else ExpenseAuditLog.Action.UPDATE
        ExpenseAuditLog.objects.create(
            expense=instance,
            action=action,
            user=instance.created_by if created else None,
            description="Expense created" if created else "Expense updated",
        )

        # Check if payment status changed to paid
        old_paid_amount = getattr(instance, '_old_paid_amount', D0)
        old_status = getattr(instance, '_old_approval_status', None)
        
        current_paid = money(instance.paid_amount)
        current_status = instance.approval_status

        is_newly_paid = (
            current_paid > D0 and
            old_paid_amount <= D0 and
            current_status in [Expense.ApprovalStatus.PAID, Expense.ApprovalStatus.PARTIAL]
        ) or (
            old_status not in [Expense.ApprovalStatus.PAID, Expense.ApprovalStatus.PARTIAL] and
            current_status in [Expense.ApprovalStatus.PAID, Expense.ApprovalStatus.PARTIAL]
        )

        if is_newly_paid:
            sync_cash_movement(
                hotel=instance.hotel,
                source_type="expense_payment",
                source_id=instance.pk,
                direction=CashMovement.Direction.CASH_OUT,
                amount=current_paid,
                reference=instance.expense_number,
                description=f"Expense paid: {instance.title}",
                cash_account=instance.cash_account,
                user=instance.created_by,
            )
            logger.info(f"Cash movement created for expense {instance.expense_number}")

    except Exception as e:
        logger.error(f"Error processing expense {instance.expense_number}: {e}")