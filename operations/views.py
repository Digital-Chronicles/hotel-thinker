from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Sum, Q
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from .models import HousekeepingTask, MaintenanceTicket, LaundryOrder, LostFoundItem, GuestRequest, NightAudit, ChannelRate, KitchenTicket
from .forms import HousekeepingTaskForm, MaintenanceTicketForm, LaundryOrderForm, LostFoundItemForm, GuestRequestForm, NightAuditForm, ChannelRateForm, KitchenTicketForm

@login_required
def dashboard(request):
    context = {
        'housekeeping_open': HousekeepingTask.objects.exclude(status=HousekeepingTask.Status.DONE).count(),
        'maintenance_open': MaintenanceTicket.objects.exclude(status__in=[MaintenanceTicket.Status.RESOLVED, MaintenanceTicket.Status.CLOSED]).count(),
        'laundry_active': LaundryOrder.objects.exclude(status__in=[LaundryOrder.Status.DELIVERED, LaundryOrder.Status.CANCELLED]).count(),
        'guest_requests_open': GuestRequest.objects.exclude(status__in=[GuestRequest.Status.COMPLETED, GuestRequest.Status.CANCELLED]).count(),
        'kitchen_active': KitchenTicket.objects.exclude(status__in=[KitchenTicket.Status.SERVED, KitchenTicket.Status.CANCELLED]).count(),
        'night_audit_drafts': NightAudit.objects.exclude(status=NightAudit.Status.CLOSED).count(),
        'recent_housekeeping': HousekeepingTask.objects.select_related('hotel','room','assigned_to')[:8],
        'recent_maintenance': MaintenanceTicket.objects.select_related('hotel','room','assigned_to')[:8],
        'recent_requests': GuestRequest.objects.select_related('hotel','guest','room')[:8],
    }
    return render(request, 'operations/dashboard.html', context)

class SearchableListView(LoginRequiredMixin, ListView):
    paginate_by = 25
    template_name = 'operations/list.html'
    search_fields = []
    create_url_name = None
    title = 'Records'

    def get_queryset(self):
        qs = super().get_queryset()
        query = self.request.GET.get('q', '').strip()
        status = self.request.GET.get('status', '').strip()
        if query and self.search_fields:
            search_q = Q()
            for field in self.search_fields:
                search_q |= Q(**{f'{field}__icontains': query})
            qs = qs.filter(search_q)
        if status and any(getattr(f, 'name', '') == 'status' for f in self.model._meta.fields):
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({'title': self.title, 'create_url_name': self.create_url_name, 'query': self.request.GET.get('q',''), 'status': self.request.GET.get('status','')})
        return ctx

class OperationCreateView(LoginRequiredMixin, CreateView):
    template_name = 'operations/form.html'
    success_url = reverse_lazy('operations:dashboard')
    title = 'Create Record'
    def form_valid(self, form):
        if hasattr(form.instance, 'created_by'):
            form.instance.created_by = self.request.user
        return super().form_valid(form)
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs); ctx['title'] = self.title; return ctx

class OperationUpdateView(LoginRequiredMixin, UpdateView):
    template_name = 'operations/form.html'
    success_url = reverse_lazy('operations:dashboard')
    title = 'Update Record'
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs); ctx['title'] = self.title; return ctx

class OperationDetailView(LoginRequiredMixin, DetailView):
    template_name = 'operations/detail.html'
    title = 'Detail'
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        fields = []
        for field in self.object._meta.fields:
            try:
                value = getattr(self.object, field.name)
            except Exception:
                value = ''
            fields.append((field.verbose_name.title(), value))
        ctx['title'] = self.title
        ctx['detail_fields'] = fields
        return ctx

# Housekeeping
class HousekeepingList(SearchableListView):
    model = HousekeepingTask; title = 'Housekeeping'; create_url_name = 'operations:housekeeping_create'; search_fields = ['title','room__number','inspection_notes']
class HousekeepingCreate(OperationCreateView):
    model = HousekeepingTask; form_class = HousekeepingTaskForm; title = 'New Housekeeping Task'
class HousekeepingUpdate(OperationUpdateView):
    model = HousekeepingTask; form_class = HousekeepingTaskForm; title = 'Update Housekeeping Task'
class HousekeepingDetail(OperationDetailView):
    model = HousekeepingTask; title = 'Housekeeping Task'

# Maintenance
class MaintenanceList(SearchableListView):
    model = MaintenanceTicket; title = 'Maintenance'; create_url_name = 'operations:maintenance_create'; search_fields = ['title','description','room__number','vendor_name']
class MaintenanceCreate(OperationCreateView):
    model = MaintenanceTicket; form_class = MaintenanceTicketForm; title = 'New Maintenance Ticket'
class MaintenanceUpdate(OperationUpdateView):
    model = MaintenanceTicket; form_class = MaintenanceTicketForm; title = 'Update Maintenance Ticket'
class MaintenanceDetail(OperationDetailView):
    model = MaintenanceTicket; title = 'Maintenance Ticket'

# Laundry
class LaundryList(SearchableListView):
    model = LaundryOrder; title = 'Laundry Orders'; create_url_name = 'operations:laundry_create'; search_fields = ['order_number','items_description','guest__full_name','room__number']
class LaundryCreate(OperationCreateView):
    model = LaundryOrder; form_class = LaundryOrderForm; title = 'New Laundry Order'
class LaundryUpdate(OperationUpdateView):
    model = LaundryOrder; form_class = LaundryOrderForm; title = 'Update Laundry Order'
class LaundryDetail(OperationDetailView):
    model = LaundryOrder; title = 'Laundry Order'

# Lost and found
class LostFoundList(SearchableListView):
    model = LostFoundItem; title = 'Lost & Found'; create_url_name = 'operations:lostfound_create'; search_fields = ['item_name','description','found_location','claimed_by_name']
class LostFoundCreate(OperationCreateView):
    model = LostFoundItem; form_class = LostFoundItemForm; title = 'New Lost & Found Item'
class LostFoundUpdate(OperationUpdateView):
    model = LostFoundItem; form_class = LostFoundItemForm; title = 'Update Lost & Found Item'
class LostFoundDetail(OperationDetailView):
    model = LostFoundItem; title = 'Lost & Found Item'

# Guest requests
class GuestRequestList(SearchableListView):
    model = GuestRequest; title = 'Guest Requests'; create_url_name = 'operations:guest_request_create'; search_fields = ['request_type','description','guest__full_name','room__number']
class GuestRequestCreate(OperationCreateView):
    model = GuestRequest; form_class = GuestRequestForm; title = 'New Guest Request'
class GuestRequestUpdate(OperationUpdateView):
    model = GuestRequest; form_class = GuestRequestForm; title = 'Update Guest Request'
class GuestRequestDetail(OperationDetailView):
    model = GuestRequest; title = 'Guest Request'

# Night audit
class NightAuditList(SearchableListView):
    model = NightAudit; title = 'Night Audit'; create_url_name = 'operations:night_audit_create'; search_fields = ['notes','hotel__name']
class NightAuditCreate(OperationCreateView):
    model = NightAudit; form_class = NightAuditForm; title = 'New Night Audit'
class NightAuditUpdate(OperationUpdateView):
    model = NightAudit; form_class = NightAuditForm; title = 'Update Night Audit'
class NightAuditDetail(OperationDetailView):
    model = NightAudit; title = 'Night Audit'

# Channel rates
class ChannelRateList(SearchableListView):
    model = ChannelRate; title = 'Channel Rates & Inventory'; create_url_name = 'operations:channel_rate_create'; search_fields = ['room_type__name','channel']
class ChannelRateCreate(OperationCreateView):
    model = ChannelRate; form_class = ChannelRateForm; title = 'New Channel Rate'
class ChannelRateUpdate(OperationUpdateView):
    model = ChannelRate; form_class = ChannelRateForm; title = 'Update Channel Rate'
class ChannelRateDetail(OperationDetailView):
    model = ChannelRate; title = 'Channel Rate'

# Kitchen tickets
class KitchenTicketList(SearchableListView):
    model = KitchenTicket; title = 'Kitchen Display Tickets'; create_url_name = 'operations:kitchen_ticket_create'; search_fields = ['items','order_reference','table_or_room','source']
class KitchenTicketCreate(OperationCreateView):
    model = KitchenTicket; form_class = KitchenTicketForm; title = 'New Kitchen Ticket'
class KitchenTicketUpdate(OperationUpdateView):
    model = KitchenTicket; form_class = KitchenTicketForm; title = 'Update Kitchen Ticket'
class KitchenTicketDetail(OperationDetailView):
    model = KitchenTicket; title = 'Kitchen Ticket'
