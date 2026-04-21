# accounts/views.py
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional
from datetime import datetime

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q, Sum, Avg, Max, Min, F
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods, require_POST
from django.views.generic import (
    ListView, UpdateView, TemplateView, DetailView, CreateView, FormView
)

from hotel_thinker.utils import get_active_hotel_for_user, require_hotel_role
from .forms import (
    HotelMemberForm, ProfileForm, HotelMemberInviteForm, HotelMemberBulkInviteForm
)
from .models import HotelMember, Profile, UserActivityLog

import logging

logger = logging.getLogger(__name__)
User = get_user_model()
D0 = Decimal("0.00")


class DashboardSection:
    """Helper class to manage dashboard sections"""
    
    def __init__(self, request: HttpRequest, hotel, today, month_start):
        self.request = request
        self.hotel = hotel
        self.today = today
        self.month_start = month_start
        self.context = {}
    
    def add_staff_summary(self):
        """Add staff/team summary to context"""
        members_qs = HotelMember.objects.filter(hotel=self.hotel).select_related("user")
        active_members = members_qs.filter(is_active=True).count()
        
        self.context.update({
            "total_members": members_qs.count(),
            "active_members": active_members,
            "inactive_members": members_qs.filter(is_active=False).count(),
            "recent_members": members_qs.order_by("-id")[:6],
        })
        return self
    
    def add_rooms_summary(self):
        """Add rooms summary to context"""
        try:
            from rooms.models import Room, RoomType
            
            rooms_qs = Room.objects.filter(hotel=self.hotel).select_related("room_type")
            room_types_qs = RoomType.objects.filter(hotel=self.hotel)
            
            status_counts = rooms_qs.values('status').annotate(count=Count('id'))
            status_dict = {item['status']: item['count'] for item in status_counts}
            
            total_rooms = rooms_qs.count()
            occupied_rooms = status_dict.get('occupied', 0)
            occupancy_rate = round((occupied_rooms / total_rooms) * 100, 1) if total_rooms > 0 else 0
            
            self.context.update({
                "total_rooms": total_rooms,
                "total_room_types": room_types_qs.count(),
                "occupied_rooms": occupied_rooms,
                "available_rooms": status_dict.get('available', 0),
                "reserved_rooms": status_dict.get('reserved', 0),
                "cleaning_rooms": status_dict.get('cleaning', 0),
                "maintenance_rooms": status_dict.get('maintenance', 0),
                "occupancy_rate": occupancy_rate,
                "recent_rooms": rooms_qs.order_by("room_number")[:8],
            })
        except ImportError:
            self._add_empty_room_context()
        except Exception as e:
            self._add_empty_room_context()
            self._log_error("rooms_summary", e)
        
        return self
    
    def _add_empty_room_context(self):
        self.context.update({
            "total_rooms": 0, "total_room_types": 0, "occupied_rooms": 0,
            "available_rooms": 0, "reserved_rooms": 0, "cleaning_rooms": 0,
            "maintenance_rooms": 0, "occupancy_rate": 0, "recent_rooms": [],
        })
    
    def add_bookings_summary(self):
        """Add bookings summary to context"""
        try:
            from bookings.models import Booking
            
            bookings_qs = Booking.objects.filter(hotel=self.hotel)
            
            active_statuses = ["confirmed", "checked_in", "pending", "reserved"]
            
            self.context.update({
                "total_bookings": bookings_qs.count(),
                "active_bookings": bookings_qs.filter(status__in=active_statuses).count(),
                "today_checkins": bookings_qs.filter(check_in=self.today).count() if hasattr(Booking, "check_in") else 0,
                "today_checkouts": bookings_qs.filter(check_out=self.today).count() if hasattr(Booking, "check_out") else 0,
                "monthly_bookings": bookings_qs.filter(created_at__date__gte=self.month_start).count() if hasattr(Booking, "created_at") else 0,
                "recent_bookings": bookings_qs.select_related("guest").order_by("-id")[:8],
            })
        except ImportError:
            self._add_empty_booking_context()
        except Exception as e:
            self._add_empty_booking_context()
            self._log_error("bookings_summary", e)
        
        return self
    
    def _add_empty_booking_context(self):
        self.context.update({
            "total_bookings": 0, "active_bookings": 0, "today_checkins": 0,
            "today_checkouts": 0, "monthly_bookings": 0, "recent_bookings": [],
        })
    
    def add_finance_summary(self):
        """Add finance summary to context"""
        try:
            from finance.models import Invoice, Payment, Expense
            
            payments_qs = Payment.objects.filter(
                hotel=self.hotel,
                status=Payment.PaymentStatus.COMPLETED,
            )
            
            today_revenue = payments_qs.filter(received_at__date=self.today).aggregate(
                total=Coalesce(Sum('amount'), D0)
            )['total']
            
            monthly_revenue = payments_qs.filter(
                received_at__date__gte=self.month_start,
                received_at__date__lte=self.today
            ).aggregate(total=Coalesce(Sum('amount'), D0))['total']
            
            expenses_qs = Expense.objects.filter(
                hotel=self.hotel,
                payment_date__gte=self.month_start,
                payment_date__lte=self.today,
                approval_status=Expense.ApprovalStatus.PAID,
            )
            monthly_expenses = expenses_qs.aggregate(
                total=Coalesce(Sum('total_amount'), D0)
            )['total']
            
            invoices_qs = Invoice.objects.filter(hotel=self.hotel)
            overdue_invoices = invoices_qs.filter(
                due_date__lt=self.today,
                total_amount__gt=0,
            ).exclude(status__in=[Invoice.Status.PAID, Invoice.Status.VOID]).count()
            
            pending_statuses = [Invoice.Status.ISSUED, Invoice.Status.SENT, 
                               Invoice.Status.PARTIALLY_PAID, Invoice.Status.OVERDUE]
            pending_invoices = invoices_qs.filter(status__in=pending_statuses).count()
            
            receivables = invoices_qs.exclude(status__in=[Invoice.Status.PAID, Invoice.Status.VOID]).aggregate(
                total=Coalesce(Sum('balance_due'), D0)
            )['total']
            
            self.context.update({
                "today_revenue": today_revenue,
                "monthly_revenue": monthly_revenue,
                "monthly_expenses": monthly_expenses,
                "net_monthly_position": monthly_revenue - monthly_expenses,
                "pending_invoices": pending_invoices,
                "overdue_invoices": overdue_invoices,
                "receivables": receivables,
                "recent_invoices": invoices_qs.order_by("-invoice_date", "-created_at")[:6],
                "recent_payments": payments_qs.select_related("invoice").order_by("-received_at")[:6],
                "recent_expenses": expenses_qs.order_by("-payment_date", "-created_at")[:6],
            })
        except ImportError:
            self._add_empty_finance_context()
        except Exception as e:
            self._add_empty_finance_context()
            self._log_error("finance_summary", e)
        
        return self
    
    def _add_empty_finance_context(self):
        self.context.update({
            "today_revenue": D0, "monthly_revenue": D0, "monthly_expenses": D0,
            "net_monthly_position": D0, "pending_invoices": 0, "overdue_invoices": 0,
            "receivables": D0, "recent_invoices": [], "recent_payments": [],
            "recent_expenses": [],
        })
    
    def add_store_summary(self):
        """Add store/inventory summary to context"""
        try:
            from store.models import StoreItem, StoreSale, StorePurchaseOrder, StoreGoodsReceipt
            
            items_qs = StoreItem.objects.filter(hotel=self.hotel)
            
            low_stock_count = items_qs.filter(
                stock_qty__lte=F('reorder_level')
            ).count()
            
            store_sales_month = D0
            if hasattr(StoreSale, "created_at"):
                store_sales_month = StoreSale.objects.filter(
                    hotel=self.hotel,
                    status="paid",
                    created_at__date__gte=self.month_start,
                    created_at__date__lte=self.today
                ).aggregate(total=Coalesce(Sum('total'), D0))['total']
            
            self.context.update({
                "total_store_items": items_qs.count(),
                "low_stock_count": low_stock_count,
                "store_sales_month": store_sales_month,
                "open_store_sales": StoreSale.objects.filter(hotel=self.hotel, status="open").count(),
                "pending_purchase_orders": StorePurchaseOrder.objects.filter(
                    hotel=self.hotel, status__in=["draft", "approved", "partially_received"]
                ).count(),
                "recent_store_items": items_qs.order_by("name")[:6],
                "recent_purchase_orders": StorePurchaseOrder.objects.filter(hotel=self.hotel).order_by("-created_at")[:6],
                "recent_goods_receipts": StoreGoodsReceipt.objects.filter(hotel=self.hotel).order_by("-created_at")[:6],
            })
        except ImportError:
            self._add_empty_store_context()
        except Exception as e:
            self._add_empty_store_context()
            self._log_error("store_summary", e)
        
        return self
    
    def _add_empty_store_context(self):
        self.context.update({
            "total_store_items": 0, "low_stock_count": 0, "store_sales_month": D0,
            "open_store_sales": 0, "pending_purchase_orders": 0,
            "recent_store_items": [], "recent_purchase_orders": [], "recent_goods_receipts": [],
        })
    
    def add_restaurant_summary(self):
        """Add restaurant summary to context"""
        try:
            from restaurant.models import RestaurantOrder
            
            restaurant_orders = RestaurantOrder.objects.filter(hotel=self.hotel)
            open_order_statuses = ["open", "pending", "preparing", "served"]
            
            order_field = "-created_at" if hasattr(RestaurantOrder, "created_at") else "-id"
            
            self.context.update({
                "restaurant_total_orders": restaurant_orders.count(),
                "restaurant_open_orders": restaurant_orders.filter(status__in=open_order_statuses).count(),
                "recent_restaurant_orders": restaurant_orders.order_by(order_field)[:6],
            })
        except ImportError:
            self.context.update({
                "restaurant_total_orders": 0, "restaurant_open_orders": 0, "recent_restaurant_orders": [],
            })
        except Exception as e:
            self.context.update({
                "restaurant_total_orders": 0, "restaurant_open_orders": 0, "recent_restaurant_orders": [],
            })
            self._log_error("restaurant_summary", e)
        
        return self
    
    def _log_error(self, section: str, error: Exception):
        """Log errors without breaking the dashboard"""
        logger.warning(f"Dashboard section '{section}' failed: {error}", exc_info=True)


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    """Main dashboard view with comprehensive hotel statistics"""
    hotel = get_active_hotel_for_user(request.user, request=request)
    today = timezone.localdate()
    month_start = today.replace(day=1)
    
    builder = DashboardSection(request, hotel, today, month_start)
    
    context = {
        "hotel": hotel,
        "today": today,
        "month_start": month_start,
    }
    
    builder.add_staff_summary()
    builder.add_rooms_summary()
    builder.add_bookings_summary()
    builder.add_finance_summary()
    builder.add_store_summary()
    builder.add_restaurant_summary()
    
    context.update(builder.context)
    
    return render(request, "accounts/dashboard.html", context)


@login_required
def my_profile(request: HttpRequest) -> HttpResponse:
    """View and edit user profile"""
    profile, created = Profile.objects.get_or_create(user=request.user)
    
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=profile, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, _("Profile updated successfully."))
            return redirect("accounts:my_profile")
    else:
        form = ProfileForm(instance=profile, user=request.user)
    
    return render(request, "accounts/my_profile.html", {
        "form": form,
        "profile": profile,
    })


class HotelMemberRequiredMixin(UserPassesTestMixin):
    """Mixin to require hotel management permissions"""
    
    allowed_roles = {"admin", "general_manager", "operations_manager"}
    
    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        
        try:
            hotel = get_active_hotel_for_user(self.request.user, request=self.request)
            membership = HotelMember.objects.get(user=self.request.user, hotel=hotel)
            return membership.role in self.allowed_roles
        except (HotelMember.DoesNotExist, AttributeError):
            return False
    
    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect('login')
        raise PermissionDenied(_("You don't have permission to access this page."))

# accounts/views.py - Simplified working version

@method_decorator(login_required, name="dispatch")
class HotelMembersListView(ListView):
    model = HotelMember
    template_name = "accounts/hotel_members_list.html"
    context_object_name = "members"
    paginate_by = 50
    
    def get_queryset(self):
        hotel = get_active_hotel_for_user(self.request.user, request=self.request)
        
        # Start with base queryset
        qs = HotelMember.objects.filter(hotel=hotel)
        qs = qs.select_related("user", "hotel", "invited_by")
        qs = qs.prefetch_related("user__profile")
        
        # Apply filters
        role = self.request.GET.get('role')
        if role:
            qs = qs.filter(role=role)
        
        status = self.request.GET.get('status')
        if status == 'active':
            qs = qs.filter(is_active=True)
        elif status == 'inactive':
            qs = qs.filter(is_active=False)
        elif status == 'on_leave':
            qs = qs.filter(is_on_leave=True)
        
        search = self.request.GET.get('q')
        if search:
            qs = qs.filter(
                Q(user__email__icontains=search) |
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search) |
                Q(employee_code__icontains=search)
            )
        
        # Apply ordering
        order_by = self.request.GET.get('order_by', '-is_active')
        allowed_fields = ['is_active', 'role', 'user__email', 'joined_at', 'employee_code']
        
        if order_by.lstrip('-') in allowed_fields:
            qs = qs.order_by(order_by)
        else:
            qs = qs.order_by('-is_active', 'role', 'user__email')
        
        return qs
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hotel = get_active_hotel_for_user(self.request.user, request=self.request)
        
        # Filter values
        context['current_role'] = self.request.GET.get('role', '')
        context['current_status'] = self.request.GET.get('status', '')
        context['search_query'] = self.request.GET.get('q', '')
        
        # Role choices for dropdown
        context['role_choices'] = HotelMember.Role.choices
        
        # Counts for stats cards
        context['total_members'] = HotelMember.objects.filter(hotel=hotel).count()
        context['active_count'] = HotelMember.objects.filter(hotel=hotel, is_active=True).count()
        context['inactive_count'] = HotelMember.objects.filter(hotel=hotel, is_active=False).count()
        context['on_leave_count'] = HotelMember.objects.filter(hotel=hotel, is_on_leave=True).count()
        
        # Management count
        management_roles = ['admin', 'general_manager', 'operations_manager', 
                           'front_desk_manager', 'housekeeping_manager', 'restaurant_manager']
        context['management_count'] = HotelMember.objects.filter(
            hotel=hotel, 
            role__in=management_roles,
            is_active=True
        ).count()
        
        return context


@method_decorator(login_required, name="dispatch")
class HotelMemberUpdateView(HotelMemberRequiredMixin, UpdateView):
    """Update hotel member information"""
    
    model = HotelMember
    form_class = HotelMemberForm
    template_name = "accounts/hotel_member_form.html"
    context_object_name = "member"
    
    def get_queryset(self):
        hotel = get_active_hotel_for_user(self.request.user, request=self.request)
        return HotelMember.objects.filter(hotel=hotel).select_related("user", "hotel")
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['hotel'] = get_active_hotel_for_user(self.request.user, request=self.request)
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, _("Member updated successfully."))
        return response
    
    def form_invalid(self, form):
        messages.error(self.request, _("Please correct the errors below."))
        return super().form_invalid(form)
    
    def get_success_url(self):
        return reverse("accounts:hotel_members_list")
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_edit'] = True
        context['hotel'] = get_active_hotel_for_user(self.request.user, request=self.request)
        return context


@login_required
@require_http_methods(["POST"])
def hotel_member_toggle_active(request: HttpRequest, pk: int) -> HttpResponse:
    """Toggle member active status with audit logging"""
    require_hotel_role(request.user, {"admin", "general_manager", "operations_manager"})
    hotel = get_active_hotel_for_user(request.user, request=request)
    
    member = get_object_or_404(HotelMember, pk=pk, hotel=hotel)
    
    if member.user == request.user and member.is_active:
        messages.error(request, _("You cannot deactivate your own account."))
        return redirect("accounts:hotel_members_list")
    
    if member.is_active:
        reason = request.POST.get('reason', _('Deactivated by administrator'))
        member.terminate(request.user, reason=reason, eligible_for_rehire=True)
        messages.success(request, _("Member '{email}' has been deactivated.").format(email=member.user.email))
    else:
        member.is_active = True
        member.terminated_at = None
        member.terminated_by = None
        member.termination_reason = None
        member.save(update_fields=['is_active', 'terminated_at', 'terminated_by', 'termination_reason'])
        messages.success(request, _("Member '{email}' has been activated.").format(email=member.user.email))
    
    try:
        UserActivityLog.log(
            user=request.user,
            action=UserActivityLog.Action.UPDATE,
            hotel=hotel,
            content_type='HotelMember',
            object_id=str(member.pk),
            object_repr=str(member),
            description=f"Toggled active status to {member.is_active}"
        )
    except Exception:
        pass
    
    return redirect("accounts:hotel_members_list")


class HotelMemberDashboardView(LoginRequiredMixin, TemplateView):
    """Individual member's personal dashboard"""
    template_name = "accounts/member_dashboard.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hotel = get_active_hotel_for_user(self.request.user, request=self.request)
        
        context['membership'] = get_object_or_404(
            HotelMember, 
            user=self.request.user, 
            hotel=hotel
        )
        context['hotel'] = hotel
        context['profile'] = self.request.user.profile
        
        return context


@login_required
@require_POST
def resend_member_invitation(request: HttpRequest, pk: int) -> HttpResponse:
    """Resend invitation email to a pending member"""
    require_hotel_role(request.user, {"admin", "general_manager", "operations_manager"})
    hotel = get_active_hotel_for_user(request.user, request=request)
    
    member = get_object_or_404(HotelMember, pk=pk, hotel=hotel, invitation_accepted_at__isnull=True)
    
    member.resend_invitation(request.user)
    messages.success(request, _("Invitation resent to {email}.").format(email=member.user.email))
    
    return redirect("accounts:hotel_members_list")


class HotelMemberDetailView(LoginRequiredMixin, HotelMemberRequiredMixin, DetailView):
    """Detailed view of a single hotel member"""
    model = HotelMember
    template_name = "accounts/hotel_member_detail.html"
    context_object_name = "member"
    
    def get_queryset(self):
        hotel = get_active_hotel_for_user(self.request.user, request=self.request)
        return HotelMember.objects.filter(hotel=hotel).select_related(
            "user", "hotel", "invited_by", "terminated_by"
        ).prefetch_related(
            "user__profile"
        )
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context['recent_activity'] = UserActivityLog.objects.filter(
            user=self.object.user,
            hotel=self.object.hotel
        )[:20]
        
        context['member_stats'] = {
            'days_since_joined': (timezone.now().date() - self.object.joined_at.date()).days if self.object.joined_at else 0,
            'is_management': self.object.is_management,
            'years_of_service': self.object.years_of_service,
        }
        
        return context


class HotelMemberInviteView(LoginRequiredMixin, HotelMemberRequiredMixin, CreateView):
    """Invite a new member to the hotel"""
    model = HotelMember
    form_class = HotelMemberInviteForm
    template_name = "accounts/hotel_member_invite.html"
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['hotel'] = get_active_hotel_for_user(self.request.user, request=self.request)
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        hotel = get_active_hotel_for_user(self.request.user, request=self.request)
        email = form.cleaned_data['email']
        
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'username': email,
                'first_name': form.cleaned_data.get('first_name', ''),
                'last_name': form.cleaned_data.get('last_name', ''),
            }
        )
        
        member = form.save(commit=False)
        member.user = user
        member.hotel = hotel
        member.invited_by = self.request.user
        member.invitation_sent_at = timezone.now()
        member.invitation_expires_at = timezone.now() + timezone.timedelta(days=7)
        member.save()
        
        messages.success(self.request, f"Invitation sent to {email}")
        
        if form.cleaned_data.get('send_invitation_email', True):
            messages.info(self.request, f"An invitation email has been sent to {email}")
        
        return redirect("accounts:hotel_members_list")
    
    def form_invalid(self, form):
        messages.error(self.request, "Please correct the errors below.")
        return super().form_invalid(form)


class HotelMemberBulkInviteView(LoginRequiredMixin, HotelMemberRequiredMixin, FormView):
    """Bulk invite multiple members"""
    template_name = "accounts/hotel_member_bulk_invite.html"
    form_class = HotelMemberBulkInviteForm
    
    def form_valid(self, form):
        hotel = get_active_hotel_for_user(self.request.user, request=self.request)
        emails = form.cleaned_data['emails']
        role = form.cleaned_data['role']
        
        invited_count = 0
        existing_count = 0
        
        for email in emails:
            user, created = User.objects.get_or_create(
                email=email,
                defaults={'username': email}
            )
            
            if HotelMember.objects.filter(hotel=hotel, user=user).exists():
                existing_count += 1
                continue
            
            member = HotelMember(
                user=user,
                hotel=hotel,
                role=role,
                invited_by=self.request.user,
                invitation_sent_at=timezone.now(),
                invitation_expires_at=timezone.now() + timezone.timedelta(days=7)
            )
            member.save()
            invited_count += 1
        
        messages.success(
            self.request,
            f"Invited {invited_count} new member(s). {existing_count} already existed."
        )
        
        return redirect("accounts:hotel_members_list")


class MemberActivityLogView(LoginRequiredMixin, HotelMemberRequiredMixin, ListView):
    """View activity logs for a specific member"""
    model = UserActivityLog
    template_name = "accounts/member_activity.html"
    context_object_name = "activities"
    paginate_by = 50
    
    def get_queryset(self):
        member = get_object_or_404(HotelMember, pk=self.kwargs['pk'])
        return UserActivityLog.objects.filter(
            user=member.user,
            hotel=member.hotel
        ).select_related('user').order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['member'] = get_object_or_404(HotelMember, pk=self.kwargs['pk'])
        return context


class MemberPerformanceUpdateView(LoginRequiredMixin, HotelMemberRequiredMixin, UpdateView):
    """Update member performance rating and notes"""
    model = HotelMember
    fields = ['performance_rating', 'performance_notes', 'last_review_date', 'next_review_date']
    template_name = "accounts/member_performance_form.html"
    
    def get_queryset(self):
        hotel = get_active_hotel_for_user(self.request.user, request=self.request)
        return HotelMember.objects.filter(hotel=hotel)
    
    def form_valid(self, form):
        if not form.cleaned_data.get('last_review_date'):
            form.instance.last_review_date = timezone.now().date()
        
        messages.success(self.request, "Performance rating updated successfully.")
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse("accounts:hotel_member_detail", kwargs={'pk': self.object.pk})


@login_required
@require_POST
def member_start_leave(request, pk):
    """Start leave period for a member"""
    require_hotel_role(request.user, {"admin", "general_manager", "operations_manager"})
    hotel = get_active_hotel_for_user(request.user, request=request)
    
    member = get_object_or_404(HotelMember, pk=pk, hotel=hotel)
    
    start_date = request.POST.get('start_date')
    end_date = request.POST.get('end_date')
    reason = request.POST.get('reason', '')
    
    if start_date and end_date:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        member.start_leave(start_date, end_date, reason)
        messages.success(request, f"Leave period started for {member.user.get_full_name()}")
    else:
        messages.error(request, "Please provide both start and end dates.")
    
    return redirect("accounts:hotel_member_detail", pk=pk)


@login_required
@require_POST
def member_end_leave(request, pk):
    """End leave period for a member"""
    require_hotel_role(request.user, {"admin", "general_manager", "operations_manager"})
    hotel = get_active_hotel_for_user(request.user, request=request)
    
    member = get_object_or_404(HotelMember, pk=pk, hotel=hotel)
    member.end_leave()
    messages.success(request, f"Leave period ended for {member.user.get_full_name()}")
    
    return redirect("accounts:hotel_member_detail", pk=pk)


class TeamManagementView(LoginRequiredMixin, HotelMemberRequiredMixin, TemplateView):
    """Team management dashboard"""
    template_name = "accounts/team_management.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hotel = get_active_hotel_for_user(self.request.user, request=self.request)
        
        members_by_role = {}
        for role_choice in HotelMember.Role.choices:
            role = role_choice[0]
            members = HotelMember.objects.filter(
                hotel=hotel, 
                role=role, 
                is_active=True
            ).select_related('user')
            if members.exists():
                members_by_role[role] = members
        
        context['members_by_role'] = members_by_role
        context['total_active'] = HotelMember.objects.filter(hotel=hotel, is_active=True).count()
        context['management_count'] = HotelMember.objects.management().filter(hotel=hotel).count()
        context['on_leave_count'] = HotelMember.objects.filter(hotel=hotel, is_on_leave=True).count()
        
        return context


class ShiftManagementView(LoginRequiredMixin, HotelMemberRequiredMixin, TemplateView):
    """Shift management dashboard"""
    template_name = "accounts/shift_management.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hotel = get_active_hotel_for_user(self.request.user, request=self.request)
        
        members_by_shift = {}
        for shift in HotelMember.ShiftPreference.choices:
            shift_value = shift[0]
            members = HotelMember.objects.filter(
                hotel=hotel,
                shift_preference=shift_value,
                is_active=True
            ).select_related('user')
            if members.exists():
                members_by_shift[shift_value] = members
        
        context['members_by_shift'] = members_by_shift
        return context


class StaffReportView(LoginRequiredMixin, HotelMemberRequiredMixin, TemplateView):
    """Staff reports and analytics"""
    template_name = "accounts/staff_report.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hotel = get_active_hotel_for_user(self.request.user, request=self.request)
        
        context['total_staff'] = HotelMember.objects.filter(hotel=hotel).count()
        context['active_staff'] = HotelMember.objects.filter(hotel=hotel, is_active=True).count()
        
        role_distribution = HotelMember.objects.filter(hotel=hotel).values('role').annotate(
            count=Count('id')
        ).order_by('-count')
        context['role_distribution'] = role_distribution
        
        employment_distribution = HotelMember.objects.filter(hotel=hotel).values('employment_type').annotate(
            count=Count('id')
        )
        context['employment_distribution'] = employment_distribution
        
        context['recent_hires'] = HotelMember.objects.filter(
            hotel=hotel, 
            hire_date__isnull=False
        ).order_by('-hire_date')[:10]
        
        context['upcoming_reviews'] = HotelMember.objects.filter(
            hotel=hotel,
            next_review_date__gte=timezone.now().date(),
            is_active=True
        ).order_by('next_review_date')[:10]
        
        return context


class PerformanceReportView(LoginRequiredMixin, HotelMemberRequiredMixin, TemplateView):
    """Performance reports and analytics"""
    template_name = "accounts/performance_report.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hotel = get_active_hotel_for_user(self.request.user, request=self.request)
        
        performance_stats = HotelMember.objects.filter(
            hotel=hotel,
            performance_rating__isnull=False
        ).aggregate(
            avg_rating=Coalesce(Avg('performance_rating'), D0),
            max_rating=Coalesce(Max('performance_rating'), D0),
            min_rating=Coalesce(Min('performance_rating'), D0),
            rated_count=Count('id')
        )
        context['performance_stats'] = performance_stats
        
        context['top_performers'] = HotelMember.objects.filter(
            hotel=hotel,
            performance_rating__gte=4.0,
            is_active=True
        ).select_related('user').order_by('-performance_rating')[:10]
        
        context['needs_improvement'] = HotelMember.objects.filter(
            hotel=hotel,
            performance_rating__lt=3.0,
            performance_rating__isnull=False,
            is_active=True
        ).select_related('user').order_by('performance_rating')[:10]
        
        context['recent_reviews'] = HotelMember.objects.filter(
            hotel=hotel,
            last_review_date__isnull=False
        ).order_by('-last_review_date')[:15]
        
        return context


@login_required
def member_search_api(request):
    """JSON API for searching members (for autocomplete)"""
    hotel = get_active_hotel_for_user(request.user, request=request)
    query = request.GET.get('q', '')
    
    members = HotelMember.objects.filter(
        hotel=hotel,
        is_active=True
    ).select_related('user')
    
    if query:
        members = members.filter(
            Q(user__email__icontains=query) |
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(employee_code__icontains=query)
        )
    
    results = [{
        'id': m.id,
        'name': m.user.get_full_name() or m.user.email,
        'email': m.user.email,
        'role': m.get_role_display(),
        'employee_code': m.employee_code,
        'avatar': m.user.profile.avatar.url if m.user.profile.avatar else None
    } for m in members[:20]]
    
    return JsonResponse({'results': results})


@login_required
def member_stats_api(request):
    """JSON API for member statistics"""
    hotel = get_active_hotel_for_user(request.user, request=request)
    
    stats = {
        'total': HotelMember.objects.filter(hotel=hotel).count(),
        'active': HotelMember.objects.filter(hotel=hotel, is_active=True).count(),
        'inactive': HotelMember.objects.filter(hotel=hotel, is_active=False).count(),
        'on_leave': HotelMember.objects.filter(hotel=hotel, is_on_leave=True).count(),
        'management': HotelMember.objects.management().filter(hotel=hotel).count(),
        'roles': list(HotelMember.objects.filter(hotel=hotel).values('role').annotate(
            count=Count('id')
        )),
    }
    
    return JsonResponse(stats)


def test_error_handling(request):
    """Test view for error handling (development only)"""
    try:
        error_type = request.GET.get('error', 'none')
        
        if error_type == 'database':
            raise Exception("Database connection error")
        elif error_type == 'permission':
            raise PermissionDenied("Test permission error")
        elif error_type == 'notfound':
            from django.http import Http404
            raise Http404("Test not found error")
        
        return render(request, "accounts/test_error.html", {
            'message': "No error triggered. Add ?error=database|permission|notfound to test."
        })
    except Exception as e:
        logger.error(f"Test error: {e}", exc_info=True)
        raise