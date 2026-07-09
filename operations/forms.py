from django import forms
from .models import HousekeepingTask, MaintenanceTicket, LaundryOrder, LostFoundItem, GuestRequest, NightAudit, ChannelRate, KitchenTicket

BASE_WIDGET_CLASSES = 'w-full rounded-xl border border-slate-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500'

class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', BASE_WIDGET_CLASSES)

class HousekeepingTaskForm(StyledModelForm):
    class Meta:
        model = HousekeepingTask
        exclude = ['created_by', 'started_at', 'completed_at']
        widgets = {'due_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}), 'checklist': forms.Textarea(attrs={'rows': 4})}

class MaintenanceTicketForm(StyledModelForm):
    class Meta:
        model = MaintenanceTicket
        exclude = ['created_by', 'resolved_at']
        widgets = {'description': forms.Textarea(attrs={'rows': 4}), 'notes': forms.Textarea(attrs={'rows': 3})}

class LaundryOrderForm(StyledModelForm):
    class Meta:
        model = LaundryOrder
        exclude = ['created_by', 'order_number', 'delivered_at']
        widgets = {'expected_ready_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}), 'items_description': forms.Textarea(attrs={'rows': 4})}

class LostFoundItemForm(StyledModelForm):
    class Meta:
        model = LostFoundItem
        exclude = ['created_by', 'claimed_at']
        widgets = {'found_date': forms.DateInput(attrs={'type': 'date'}), 'description': forms.Textarea(attrs={'rows': 3})}

class GuestRequestForm(StyledModelForm):
    class Meta:
        model = GuestRequest
        exclude = ['created_by', 'completed_at']
        widgets = {'due_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}), 'description': forms.Textarea(attrs={'rows': 4})}

class NightAuditForm(StyledModelForm):
    class Meta:
        model = NightAudit
        exclude = ['created_by', 'reviewed_by', 'closed_at']
        widgets = {'audit_date': forms.DateInput(attrs={'type': 'date'}), 'notes': forms.Textarea(attrs={'rows': 4})}

class ChannelRateForm(StyledModelForm):
    class Meta:
        model = ChannelRate
        exclude = ['created_by']
        widgets = {'date': forms.DateInput(attrs={'type': 'date'})}

class KitchenTicketForm(StyledModelForm):
    class Meta:
        model = KitchenTicket
        exclude = ['created_by', 'started_at', 'ready_at', 'served_at']
        widgets = {'items': forms.Textarea(attrs={'rows': 5}), 'notes': forms.Textarea(attrs={'rows': 3})}
