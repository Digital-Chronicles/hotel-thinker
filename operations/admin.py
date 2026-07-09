from django.contrib import admin
from .models import HousekeepingTask, MaintenanceTicket, LaundryOrder, LostFoundItem, GuestRequest, NightAudit, ChannelRate, KitchenTicket

@admin.register(HousekeepingTask)
class HousekeepingTaskAdmin(admin.ModelAdmin):
    list_display = ('hotel', 'room', 'title', 'status', 'priority', 'assigned_to', 'due_at')
    list_filter = ('hotel', 'status', 'priority')
    search_fields = ('room__number', 'title', 'inspection_notes')

@admin.register(MaintenanceTicket)
class MaintenanceTicketAdmin(admin.ModelAdmin):
    list_display = ('hotel', 'room', 'title', 'severity', 'status', 'assigned_to', 'actual_cost')
    list_filter = ('hotel', 'severity', 'status')
    search_fields = ('title', 'description', 'vendor_name')

@admin.register(LaundryOrder)
class LaundryOrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'hotel', 'guest', 'room', 'pieces', 'status', 'amount', 'expected_ready_at')
    list_filter = ('hotel', 'status')
    search_fields = ('order_number', 'items_description', 'guest__full_name', 'room__number')

@admin.register(LostFoundItem)
class LostFoundItemAdmin(admin.ModelAdmin):
    list_display = ('hotel', 'item_name', 'found_location', 'found_date', 'status', 'storage_location')
    list_filter = ('hotel', 'status', 'found_date')
    search_fields = ('item_name', 'description', 'claimed_by_name')

@admin.register(GuestRequest)
class GuestRequestAdmin(admin.ModelAdmin):
    list_display = ('hotel', 'guest', 'room', 'request_type', 'status', 'assigned_to', 'due_at')
    list_filter = ('hotel', 'status', 'request_type')
    search_fields = ('request_type', 'description', 'guest__full_name', 'room__number')

@admin.register(NightAudit)
class NightAuditAdmin(admin.ModelAdmin):
    list_display = ('hotel', 'audit_date', 'total_revenue', 'expenses', 'closing_cash', 'variance', 'status')
    list_filter = ('hotel', 'status', 'audit_date')
    readonly_fields = ('total_revenue', 'expected_cash', 'variance')

@admin.register(ChannelRate)
class ChannelRateAdmin(admin.ModelAdmin):
    list_display = ('hotel', 'room_type', 'channel', 'date', 'rate', 'available_rooms', 'stop_sell')
    list_filter = ('hotel', 'channel', 'stop_sell', 'date')
    search_fields = ('room_type__name',)

@admin.register(KitchenTicket)
class KitchenTicketAdmin(admin.ModelAdmin):
    list_display = ('hotel', 'source', 'table_or_room', 'status', 'priority', 'created_at')
    list_filter = ('hotel', 'status', 'source')
    search_fields = ('items', 'order_reference', 'table_or_room')
