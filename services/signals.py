from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import ServiceAttendance, ServiceBooking, ServiceBookingExtra, ServicePayment

D0 = Decimal("0.00")


def recalculate_service_booking_totals(service_booking: ServiceBooking):
    """
    Recalculate total paid and payment status after extra/payment changes.
    """
    total_paid = service_booking.payments.aggregate(s=Sum("amount"))["s"] or D0
    service_booking.deposit_paid = total_paid
    service_booking.update_payment_status()
    service_booking.save(update_fields=["deposit_paid", "payment_status", "updated_at"])


@receiver(post_save, sender=ServicePayment)
def sync_service_booking_payment_on_save(sender, instance, **kwargs):
    """
    Keep payment totals in sync after saving a service payment.
    """
    recalculate_service_booking_totals(instance.service_booking)


@receiver(post_delete, sender=ServicePayment)
def sync_service_booking_payment_on_delete(sender, instance, **kwargs):
    """
    Keep payment totals in sync after deleting a service payment.
    """
    recalculate_service_booking_totals(instance.service_booking)


@receiver(post_save, sender=ServiceBookingExtra)
def update_service_booking_after_extra_save(sender, instance, **kwargs):
    """
    Touch booking updated_at when extras change.
    You can later extend this if you want extras to affect invoice totals directly.
    """
    booking = instance.service_booking
    booking.updated_at = timezone.now()
    booking.save(update_fields=["updated_at"])


@receiver(post_delete, sender=ServiceBookingExtra)
def update_service_booking_after_extra_delete(sender, instance, **kwargs):
    """
    Touch booking updated_at when extras are removed.
    """
    booking = instance.service_booking
    booking.updated_at = timezone.now()
    booking.save(update_fields=["updated_at"])


@receiver(post_save, sender=ServiceAttendance)
def update_service_status_from_attendance(sender, instance, **kwargs):
    """
    Smart status updates from attendance check-in/check-out.
    """
    booking = instance.service_booking
    changed = False

    if instance.checked_in_at and booking.status == ServiceBooking.Status.RESERVED:
        booking.status = ServiceBooking.Status.IN_PROGRESS
        changed = True

    if instance.checked_out_at and booking.status in [
        ServiceBooking.Status.RESERVED,
        ServiceBooking.Status.IN_PROGRESS,
    ]:
        booking.status = ServiceBooking.Status.COMPLETED
        changed = True

    if changed:
        booking.updated_at = timezone.now()
        booking.save(update_fields=["status", "updated_at"])