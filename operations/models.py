from decimal import Decimal
from django.conf import settings
from django.db import models
from django.utils import timezone
from hotels.models import Hotel
from rooms.models import Room
from bookings.models import Booking, Guest


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="%(class)s_created")

    class Meta:
        abstract = True


class HousekeepingTask(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        IN_PROGRESS = 'in_progress', 'In Progress'
        INSPECTION = 'inspection', 'Inspection'
        DONE = 'done', 'Done'
        BLOCKED = 'blocked', 'Blocked'

    class Priority(models.TextChoices):
        LOW = 'low', 'Low'
        NORMAL = 'normal', 'Normal'
        HIGH = 'high', 'High'
        URGENT = 'urgent', 'Urgent'

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='housekeeping_tasks')
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='housekeeping_tasks')
    booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name='housekeeping_tasks')
    title = models.CharField(max_length=180, default='Room cleaning')
    checklist = models.TextField(blank=True, null=True, help_text='Example: Change linen, clean bathroom, restock water, inspect minibar')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.NORMAL, db_index=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='housekeeping_assignments')
    due_at = models.DateTimeField(blank=True, null=True)
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    inspection_notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['status', '-priority', 'due_at']
        indexes = [models.Index(fields=['hotel', 'status']), models.Index(fields=['room', 'status'])]

    def save(self, *args, **kwargs):
        if self.status == self.Status.DONE and not self.completed_at:
            self.completed_at = timezone.now()
            self.room.status = Room.Status.AVAILABLE
            self.room.save(update_fields=['status'])
        elif self.status in [self.Status.PENDING, self.Status.IN_PROGRESS, self.Status.INSPECTION]:
            self.room.status = Room.Status.CLEANING
            self.room.save(update_fields=['status'])
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.room} - {self.title}'


class MaintenanceTicket(TimeStampedModel):
    class Status(models.TextChoices):
        OPEN = 'open', 'Open'
        ASSIGNED = 'assigned', 'Assigned'
        IN_PROGRESS = 'in_progress', 'In Progress'
        RESOLVED = 'resolved', 'Resolved'
        CLOSED = 'closed', 'Closed'

    class Severity(models.TextChoices):
        LOW = 'low', 'Low'
        MEDIUM = 'medium', 'Medium'
        HIGH = 'high', 'High'
        CRITICAL = 'critical', 'Critical'

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='maintenance_tickets')
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, blank=True, related_name='maintenance_tickets')
    title = models.CharField(max_length=200)
    description = models.TextField()
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.MEDIUM, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='maintenance_assignments')
    estimated_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    actual_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    vendor_name = models.CharField(max_length=160, blank=True, null=True)
    resolved_at = models.DateTimeField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['hotel', 'status']), models.Index(fields=['severity', 'status'])]

    def save(self, *args, **kwargs):
        if self.room and self.status not in [self.Status.RESOLVED, self.Status.CLOSED]:
            self.room.status = Room.Status.MAINTENANCE
            self.room.save(update_fields=['status'])
        if self.status in [self.Status.RESOLVED, self.Status.CLOSED] and not self.resolved_at:
            self.resolved_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class LaundryOrder(TimeStampedModel):
    class Status(models.TextChoices):
        RECEIVED = 'received', 'Received'
        WASHING = 'washing', 'Washing'
        DRYING = 'drying', 'Drying'
        IRONING = 'ironing', 'Ironing'
        READY = 'ready', 'Ready'
        DELIVERED = 'delivered', 'Delivered'
        CANCELLED = 'cancelled', 'Cancelled'

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='laundry_orders')
    guest = models.ForeignKey(Guest, on_delete=models.SET_NULL, null=True, blank=True, related_name='laundry_orders')
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, blank=True, related_name='laundry_orders')
    booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name='laundry_orders')
    order_number = models.CharField(max_length=40, unique=True, blank=True)
    items_description = models.TextField(help_text='Example: 3 shirts, 2 trousers, 1 dress')
    pieces = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RECEIVED, db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    expected_ready_at = models.DateTimeField(blank=True, null=True)
    delivered_at = models.DateTimeField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['hotel', 'status']), models.Index(fields=['order_number'])]

    def save(self, *args, **kwargs):
        if not self.order_number:
            today = timezone.localdate().strftime('%Y%m%d')
            count = LaundryOrder.objects.filter(created_at__date=timezone.localdate()).count() + 1
            self.order_number = f'LDY-{today}-{count:04d}'
        if self.status == self.Status.DELIVERED and not self.delivered_at:
            self.delivered_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.order_number


class LostFoundItem(TimeStampedModel):
    class Status(models.TextChoices):
        FOUND = 'found', 'Found'
        CLAIMED = 'claimed', 'Claimed'
        DISPOSED = 'disposed', 'Disposed'
        DONATED = 'donated', 'Donated'

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='lost_found_items')
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, blank=True, related_name='lost_found_items')
    guest = models.ForeignKey(Guest, on_delete=models.SET_NULL, null=True, blank=True, related_name='lost_found_items')
    item_name = models.CharField(max_length=180)
    description = models.TextField(blank=True, null=True)
    found_location = models.CharField(max_length=180, blank=True, null=True)
    found_date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.FOUND, db_index=True)
    storage_location = models.CharField(max_length=180, blank=True, null=True)
    claimed_by_name = models.CharField(max_length=180, blank=True, null=True)
    claimed_by_phone = models.CharField(max_length=40, blank=True, null=True)
    claimed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-found_date', '-created_at']

    def __str__(self):
        return self.item_name


class GuestRequest(TimeStampedModel):
    class Status(models.TextChoices):
        NEW = 'new', 'New'
        ACKNOWLEDGED = 'acknowledged', 'Acknowledged'
        IN_PROGRESS = 'in_progress', 'In Progress'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='guest_requests')
    guest = models.ForeignKey(Guest, on_delete=models.SET_NULL, null=True, blank=True, related_name='requests')
    booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name='guest_requests')
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, blank=True, related_name='guest_requests')
    request_type = models.CharField(max_length=120, help_text='Example: extra towel, airport pickup, room service, complaint')
    description = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW, db_index=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='guest_request_assignments')
    due_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['status', '-created_at']
        indexes = [models.Index(fields=['hotel', 'status'])]

    def __str__(self):
        return self.request_type


class NightAudit(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        REVIEWED = 'reviewed', 'Reviewed'
        CLOSED = 'closed', 'Closed'

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='night_audits')
    audit_date = models.DateField(default=timezone.localdate, db_index=True)
    opening_cash = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    room_revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    restaurant_revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    bar_revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    services_revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    other_revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    expenses = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    closing_cash = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    notes = models.TextField(blank=True, null=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='night_audits_reviewed')
    closed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        unique_together = ('hotel', 'audit_date')
        ordering = ['-audit_date']

    @property
    def total_revenue(self):
        return self.room_revenue + self.restaurant_revenue + self.bar_revenue + self.services_revenue + self.other_revenue

    @property
    def expected_cash(self):
        return self.opening_cash + self.total_revenue - self.expenses

    @property
    def variance(self):
        return self.closing_cash - self.expected_cash

    def save(self, *args, **kwargs):
        if self.status == self.Status.CLOSED and not self.closed_at:
            self.closed_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.hotel} - {self.audit_date}'


class ChannelRate(TimeStampedModel):
    class Channel(models.TextChoices):
        WEBSITE = 'website', 'Website'
        BOOKING = 'booking', 'Booking.com'
        EXPEDIA = 'expedia', 'Expedia'
        AIRBNB = 'airbnb', 'Airbnb'
        WALK_IN = 'walk_in', 'Walk-in'
        CORPORATE = 'corporate', 'Corporate'

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='channel_rates')
    room_type = models.ForeignKey('rooms.RoomType', on_delete=models.CASCADE, related_name='channel_rates')
    channel = models.CharField(max_length=30, choices=Channel.choices, db_index=True)
    date = models.DateField(db_index=True)
    rate = models.DecimalField(max_digits=12, decimal_places=2, validators=[])
    available_rooms = models.PositiveIntegerField(default=0)
    min_stay = models.PositiveIntegerField(default=1)
    stop_sell = models.BooleanField(default=False)

    class Meta:
        unique_together = ('hotel', 'room_type', 'channel', 'date')
        ordering = ['date', 'channel']
        indexes = [models.Index(fields=['hotel', 'date']), models.Index(fields=['channel', 'date'])]

    def __str__(self):
        return f'{self.room_type} {self.channel} {self.date}'


class KitchenTicket(TimeStampedModel):
    class Status(models.TextChoices):
        NEW = 'new', 'New'
        COOKING = 'cooking', 'Cooking'
        READY = 'ready', 'Ready'
        SERVED = 'served', 'Served'
        CANCELLED = 'cancelled', 'Cancelled'

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='kitchen_tickets')
    source = models.CharField(max_length=80, default='restaurant', help_text='restaurant, bar, room_service, events')
    table_or_room = models.CharField(max_length=80, blank=True, null=True)
    order_reference = models.CharField(max_length=80, blank=True, null=True)
    items = models.TextField(help_text='Food/drink items to prepare')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW, db_index=True)
    priority = models.PositiveSmallIntegerField(default=2, help_text='1 urgent, 2 normal, 3 low')
    started_at = models.DateTimeField(blank=True, null=True)
    ready_at = models.DateTimeField(blank=True, null=True)
    served_at = models.DateTimeField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['status', 'priority', '-created_at']
        indexes = [models.Index(fields=['hotel', 'status'])]

    def __str__(self):
        return f'Kitchen ticket {self.pk or "new"}'
