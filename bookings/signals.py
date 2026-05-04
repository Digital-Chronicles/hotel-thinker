# bookings/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction

# This file intentionally disables the finance signal for bookings
# to prevent the unit_price error during booking creation

def disable_finance_signal():
    """Disable finance invoice creation signal for bookings"""
    try:
        from finance.signals import create_invoice_for_booking
        from bookings.models import Booking
        
        # Disconnect the signal
        post_save.disconnect(
            create_invoice_for_booking,
            sender=Booking,
            dispatch_uid='create_invoice_for_booking'
        )
        print("Finance signal disabled for bookings")
    except (ImportError, AttributeError):
        pass

# Run the disconnection
disable_finance_signal()