# bookings/apps.py
from django.apps import AppConfig

class BookingsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'bookings'

    def ready(self):
        # Disconnect finance signal to prevent unit_price error
        try:
            from django.db.models.signals import post_save
            from finance.signals import create_invoice_for_booking
            from bookings.models import Booking
            
            post_save.disconnect(
                create_invoice_for_booking,
                sender=Booking,
                dispatch_uid='create_invoice_for_booking'
            )
        except (ImportError, AttributeError):
            pass