# accounts/views.py

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional
from datetime import datetime, date
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q, Sum, Avg, Max, Min, F
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods, require_POST
from django.views.generic import (
    ListView, UpdateView, TemplateView, DetailView, CreateView, FormView, DeleteView
)

from hotel_thinker.utils import get_active_hotel_for_user, require_hotel_role
from .forms import (
    ProfileForm, HotelMemberAddForm, HotelMemberInviteForm, 
    HotelMemberBulkAddForm, HotelMemberEditForm, 
    ProfilePreferencesForm, HotelMemberPermissionForm,
    HotelMemberQuickAddForm
)
from .models import HotelMember, Profile, UserActivityLog

import logging

logger = logging.getLogger(__name__)
User = get_user_model()
D0 = Decimal("0.00")


# ============================================================================
# Mixins
# ============================================================================

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


class HotelContextMixin:
    """Mixin to provide hotel context to views"""
    
    def get_hotel(self):
        """Get the active hotel for the current user"""
        return get_active_hotel_for_user(self.request.user, request=self.request)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['hotel'] = self.get_hotel()
        return context


class HotelMemberPermissionsMixin:
    """Mixin to check member-specific permissions"""
    
    def check_member_permission(self, member):
        """Check if current user can manage the given member"""
        if member.user == self.request.user:
            return False
        return True


# ============================================================================
# Dashboard Views
# ============================================================================

class DashboardSection:
    """Helper class to manage dashboard sections"""
    
    def __init__(self, request: HttpRequest, hotel, today: date, month_start: date):
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
            "on_leave_members": members_qs.filter(is_on_leave=True).count(),
            "recent_members": members_qs.order_by("-joined_at")[:6],
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
            })
        except (ImportError, Exception) as e:
            self._log_error("rooms_summary", e)
            self._add_empty_room_context()
        
        return self
    
    def _add_empty_room_context(self):
        self.context.update({
            "total_rooms": 0, "total_room_types": 0, "occupied_rooms": 0,
            "available_rooms": 0, "reserved_rooms": 0, "cleaning_rooms": 0,
            "maintenance_rooms": 0, "occupancy_rate": 0,
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
            })
        except (ImportError, Exception) as e:
            self._log_error("bookings_summary", e)
            self._add_empty_booking_context()
        
        return self
    
    def _add_empty_booking_context(self):
        self.context.update({
            "total_bookings": 0, "active_bookings": 0, 
            "today_checkins": 0, "today_checkouts": 0,
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
            )
            monthly_expenses = expenses_qs.aggregate(
                total=Coalesce(Sum('total_amount'), D0)
            )['total']
            
            invoices_qs = Invoice.objects.filter(hotel=self.hotel)
            overdue_invoices = invoices_qs.filter(
                due_date__lt=self.today,
                total_amount__gt=0,
            ).exclude(status__in=[Invoice.Status.PAID, Invoice.Status.VOID]).count()
            
            self.context.update({
                "today_revenue": today_revenue,
                "monthly_revenue": monthly_revenue,
                "monthly_expenses": monthly_expenses,
                "net_monthly_position": monthly_revenue - monthly_expenses,
                "overdue_invoices": overdue_invoices,
            })
        except (ImportError, Exception) as e:
            self._log_error("finance_summary", e)
            self._add_empty_finance_context()
        
        return self
    
    def _add_empty_finance_context(self):
        self.context.update({
            "today_revenue": D0, "monthly_revenue": D0, "monthly_expenses": D0,
            "net_monthly_position": D0, "overdue_invoices": 0,
        })
    
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
    
    context.update(builder.context)
    
    return render(request, "accounts/dashboard.html", context)


# ============================================================================
# Profile Views
# ============================================================================

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


@login_required
def profile_preferences(request: HttpRequest) -> HttpResponse:
    """Update user notification preferences"""
    profile = get_object_or_404(Profile, user=request.user)
    
    if request.method == "POST":
        form = ProfilePreferencesForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, _("Preferences updated successfully."))
            return redirect("accounts:my_profile")
    else:
        form = ProfilePreferencesForm(instance=profile)
    
    return render(request, "accounts/profile_preferences.html", {"form": form})


# ============================================================================
# Hotel Member List Views
# ============================================================================

@method_decorator(login_required, name="dispatch")
class HotelMembersListView(HotelContextMixin, ListView):
    """List all hotel members with filtering and search"""
    
    model = HotelMember
    template_name = "accounts/hotel_members_list.html"
    context_object_name = "members"
    paginate_by = 50
    
    def get_queryset(self):
        hotel = self.get_hotel()
        
        qs = HotelMember.objects.filter(hotel=hotel)
        qs = qs.select_related("user", "invited_by")
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
        hotel = self.get_hotel()
        
        context['current_role'] = self.request.GET.get('role', '')
        context['current_status'] = self.request.GET.get('status', '')
        context['search_query'] = self.request.GET.get('q', '')
        context['role_choices'] = HotelMember.Role.choices
        
        # Stats cards
        context['total_members'] = HotelMember.objects.filter(hotel=hotel).count()
        context['active_count'] = HotelMember.objects.filter(hotel=hotel, is_active=True).count()
        context['inactive_count'] = HotelMember.objects.filter(hotel=hotel, is_active=False).count()
        context['on_leave_count'] = HotelMember.objects.filter(hotel=hotel, is_on_leave=True).count()
        
        # Management count
        management_roles = ['admin', 'general_manager', 'operations_manager', 
                           'front_desk_manager', 'housekeeping_manager', 'restaurant_manager']
        context['management_count'] = HotelMember.objects.filter(
            hotel=hotel, role__in=management_roles, is_active=True
        ).count()
        
        return context


@method_decorator(login_required, name="dispatch")
class HotelMemberDetailView(LoginRequiredMixin, HotelContextMixin, DetailView):
    """Detailed view of a single hotel member"""
    
    model = HotelMember
    template_name = "accounts/hotel_member_detail.html"
    context_object_name = "member"
    
    def get_queryset(self):
        hotel = self.get_hotel()
        return HotelMember.objects.filter(hotel=hotel).select_related(
            "user", "invited_by", "terminated_by"
        ).prefetch_related("user__profile")
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context['recent_activity'] = UserActivityLog.objects.filter(
            user=self.object.user,
            hotel=self.get_hotel()
        )[:20]
        
        context['member_stats'] = {
            'days_since_joined': (timezone.now().date() - self.object.joined_at.date()).days if self.object.joined_at else 0,
            'is_management': self.object.is_management,
            'years_of_service': self.object.years_of_service,
            'can_edit': self.object.user != self.request.user,
        }
        
        return context


# ============================================================================
# Hotel Member Create/Add Views
# ============================================================================

@method_decorator(login_required, name="dispatch")
class HotelMemberAddView(LoginRequiredMixin, HotelMemberRequiredMixin, HotelContextMixin, CreateView):
    """Add a new member to the hotel - creates user account automatically"""
    
    model = HotelMember
    form_class = HotelMemberAddForm
    template_name = "accounts/hotel_member_add.html"
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['hotel'] = self.get_hotel()
        kwargs['created_by'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        """Save the member and handle success"""
        member = form.save()
        
        # Log the activity
        self._log_activity(member)
        
        # Show success message
        if hasattr(member, '_user_created') and member._user_created:
            messages.success(
                self.request,
                _("Member {name} added successfully. A new user account has been created.").format(
                    name=member.user.get_full_name() or member.user.email
                )
            )
        else:
            messages.success(
                self.request,
                _("Member {name} added successfully.").format(
                    name=member.user.get_full_name() or member.user.email
                )
            )
        
        # Send welcome email if requested
        if form.cleaned_data.get('send_welcome_email', True):
            self._send_welcome_email(member, getattr(member, '_generated_password', None))
            messages.info(self.request, _("A welcome email has been sent to {email}.").format(
                email=member.user.email
            ))
        
        return redirect("accounts:hotel_members_list")
    
    def form_invalid(self, form):
        """Handle invalid form"""
        messages.error(self.request, _("Please correct the errors below."))
        return super().form_invalid(form)
    
    def _log_activity(self, member):
        """Log the add member activity"""
        try:
            UserActivityLog.log(
                user=self.request.user,
                action=UserActivityLog.Action.CREATE,
                hotel=self.get_hotel(),
                content_type='HotelMember',
                object_id=str(member.pk),
                object_repr=str(member),
                description=f"Added member {member.user.email} to hotel"
            )
        except Exception as e:
            logger.error(f"Failed to log activity: {e}")
    
    def _send_welcome_email(self, member, password):
        """Send welcome email with login details"""
        from django.core.mail import send_mail
        from django.conf import settings
        from django.contrib.sites.shortcuts import get_current_site
        
        if not password:
            return
        
        subject = f"Welcome to {member.hotel.name} - Your Account Details"
        
        login_url = settings.LOGIN_URL if hasattr(settings, 'LOGIN_URL') else '/accounts/login/'
        current_site = get_current_site(self.request)
        full_login_url = f"http://{current_site.domain}{login_url}"
        
        message = f"""
Hello {member.user.get_full_name() or member.user.email},

You have been added as a team member at {member.hotel.name}.

Your account details:
--------------------
Email: {member.user.email}
Password: {password}
Role: {member.get_role_display()}

Please login here: {full_login_url}

For security reasons, please change your password after your first login.

Best regards,
{member.hotel.name} Management Team
        """
        
        try:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [member.user.email],
                fail_silently=False,
            )
            logger.info(f"Welcome email sent to {member.user.email}")
        except Exception as e:
            logger.error(f"Failed to send welcome email to {member.user.email}: {e}")


@method_decorator(login_required, name="dispatch")
class HotelMemberQuickAddView(LoginRequiredMixin, HotelMemberRequiredMixin, HotelContextMixin, FormView):
    """Quick add a member with minimal information"""
    
    form_class = HotelMemberQuickAddForm
    template_name = "accounts/hotel_member_quick_add.html"
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['hotel'] = self.get_hotel()
        kwargs['created_by'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        member = form.save()
        
        if hasattr(member, '_generated_password'):
            self._send_welcome_email(member, member._generated_password)
        
        messages.success(self.request, _("Member added successfully."))
        return redirect("accounts:hotel_members_list")
    
    def _send_welcome_email(self, member, password):
        """Send welcome email"""
        from django.core.mail import send_mail
        from django.conf import settings
        
        subject = f"Welcome to {member.hotel.name}"
        message = f"""
Hello,

You have been added as a {member.get_role_display()} at {member.hotel.name}.

Login Email: {member.user.email}
Password: {password}

Please login and change your password.
        """
        
        try:
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [member.user.email])
        except Exception as e:
            logger.error(f"Failed to send email: {e}")


@method_decorator(login_required, name="dispatch")
class HotelMemberInviteView(LoginRequiredMixin, HotelMemberRequiredMixin, HotelContextMixin, CreateView):
    """Invite a new member to the hotel (requires invitation acceptance)"""
    
    model = HotelMember
    form_class = HotelMemberInviteForm
    template_name = "accounts/hotel_member_invite.html"
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['hotel'] = self.get_hotel()
        kwargs['created_by'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        member = form.save()
        
        # Send invitation email if requested
        if form.cleaned_data.get('send_invitation_email', True):
            self._send_invitation_email(member)
            messages.success(
                self.request,
                _("Invitation sent to {email}.").format(email=member.user.email)
            )
        else:
            messages.success(
                self.request,
                _("Invitation created for {email}. No email was sent.").format(email=member.user.email)
            )
        
        return redirect("accounts:hotel_members_list")
    
    def _send_invitation_email(self, member):
        """Send invitation email with acceptance link"""
        from django.core.mail import send_mail
        from django.conf import settings
        from django.contrib.sites.shortcuts import get_current_site
        
        subject = f"Invitation to join {member.hotel.name}"
        
        accept_url = reverse('accounts:accept_invitation', kwargs={'token': member.invitation_token})
        current_site = get_current_site(self.request)
        full_accept_url = f"http://{current_site.domain}{accept_url}"
        
        message = f"""
Hello,

You have been invited to join {member.hotel.name} as a {member.get_role_display()}.

Click the link below to accept your invitation:
{full_accept_url}

This invitation expires in 7 days.

Best regards,
{member.hotel.name} Team
        """
        
        try:
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [member.user.email])
        except Exception as e:
            logger.error(f"Failed to send invitation: {e}")


@method_decorator(login_required, name="dispatch")
class HotelMemberBulkAddView(LoginRequiredMixin, HotelMemberRequiredMixin, HotelContextMixin, FormView):
    """Bulk add multiple members at once"""
    
    form_class = HotelMemberBulkAddForm
    template_name = "accounts/hotel_member_bulk_add.html"
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['hotel'] = self.get_hotel()
        kwargs['created_by'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        members = form.save()
        
        messages.success(
            self.request,
            _("Successfully added {count} member(s).").format(count=len(members))
        )
        
        return redirect("accounts:hotel_members_list")
    
    def form_invalid(self, form):
        messages.error(self.request, _("Please correct the errors below."))
        return super().form_invalid(form)


# ============================================================================
# Hotel Member Edit/Update Views
# ============================================================================

@method_decorator(login_required, name="dispatch")
class HotelMemberEditView(LoginRequiredMixin, HotelMemberRequiredMixin, HotelContextMixin, UpdateView):
    """Edit an existing hotel member"""
    
    model = HotelMember
    form_class = HotelMemberEditForm
    template_name = "accounts/hotel_member_edit.html"
    context_object_name = "member"
    
    def get_queryset(self):
        hotel = self.get_hotel()
        return HotelMember.objects.filter(hotel=hotel)
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['hotel'] = self.get_hotel()
        return kwargs
    
    def form_valid(self, form):
        response = super().form_valid(form)
        
        self._log_activity()
        messages.success(self.request, _("Member updated successfully."))
        
        return response
    
    def form_invalid(self, form):
        messages.error(self.request, _("Please correct the errors below."))
        return super().form_invalid(form)
    
    def _log_activity(self):
        """Log the edit activity"""
        try:
            UserActivityLog.log(
                user=self.request.user,
                action=UserActivityLog.Action.UPDATE,
                hotel=self.get_hotel(),
                content_type='HotelMember',
                object_id=str(self.object.pk),
                object_repr=str(self.object),
                description=f"Updated member {self.object.user.email}"
            )
        except Exception as e:
            logger.error(f"Failed to log activity: {e}")
    
    def get_success_url(self):
        return reverse("accounts:hotel_member_detail", kwargs={'pk': self.object.pk})


@method_decorator(login_required, name="dispatch")
class HotelMemberPermissionView(LoginRequiredMixin, HotelMemberRequiredMixin, HotelContextMixin, UpdateView):
    """Update member permissions only"""
    
    model = HotelMember
    form_class = HotelMemberPermissionForm
    template_name = "accounts/hotel_member_permissions.html"
    context_object_name = "member"
    
    def get_queryset(self):
        hotel = self.get_hotel()
        return HotelMember.objects.filter(hotel=hotel)
    
    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, _("Permissions updated successfully."))
        return response
    
    def get_success_url(self):
        return reverse("accounts:hotel_member_detail", kwargs={'pk': self.object.pk})


# ============================================================================
# Hotel Member Actions (Toggle, Leave, Terminate)
# ============================================================================

@login_required
@require_http_methods(["POST"])
def hotel_member_toggle_active(request: HttpRequest, pk: int) -> HttpResponse:
    """Toggle member active status"""
    require_hotel_role(request.user, {"admin", "general_manager", "operations_manager"})
    hotel = get_active_hotel_for_user(request.user, request=request)
    
    member = get_object_or_404(HotelMember, pk=pk, hotel=hotel)
    
    # Prevent self-deactivation
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
        messages.success(request, _("Member '{email}' has been reactivated.").format(email=member.user.email))
    
    # Log activity
    _log_member_action(request.user, hotel, member, "toggled_active")
    
    return redirect("accounts:hotel_members_list")


@login_required
@require_POST
def member_start_leave(request: HttpRequest, pk: int) -> HttpResponse:
    """Start leave period for a member"""
    require_hotel_role(request.user, {"admin", "general_manager", "operations_manager"})
    hotel = get_active_hotel_for_user(request.user, request=request)
    
    member = get_object_or_404(HotelMember, pk=pk, hotel=hotel)
    
    start_date_str = request.POST.get('start_date')
    end_date_str = request.POST.get('end_date')
    reason = request.POST.get('reason', '')
    
    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            
            member.start_leave(start_date, end_date, reason)
            messages.success(request, _("Leave period started for {name}.").format(
                name=member.user.get_full_name() or member.user.email
            ))
            _log_member_action(request.user, hotel, member, f"started leave from {start_date} to {end_date}")
        except ValueError:
            messages.error(request, _("Invalid date format."))
    else:
        messages.error(request, _("Please provide both start and end dates."))
    
    return redirect("accounts:hotel_member_detail", pk=pk)


@login_required
@require_POST
def member_end_leave(request: HttpRequest, pk: int) -> HttpResponse:
    """End leave period for a member"""
    require_hotel_role(request.user, {"admin", "general_manager", "operations_manager"})
    hotel = get_active_hotel_for_user(request.user, request=request)
    
    member = get_object_or_404(HotelMember, pk=pk, hotel=hotel)
    member.end_leave()
    
    messages.success(request, _("Leave period ended for {name}.").format(
        name=member.user.get_full_name() or member.user.email
    ))
    _log_member_action(request.user, hotel, member, "ended leave")
    
    return redirect("accounts:hotel_member_detail", pk=pk)


@login_required
@require_POST
def resend_invitation(request: HttpRequest, pk: int) -> HttpResponse:
    """Resend invitation email to a pending member"""
    require_hotel_role(request.user, {"admin", "general_manager", "operations_manager"})
    hotel = get_active_hotel_for_user(request.user, request=request)
    
    member = get_object_or_404(HotelMember, pk=pk, hotel=hotel, invitation_accepted_at__isnull=True)
    
    member.resend_invitation(request.user)
    messages.success(request, _("Invitation resent to {email}.").format(email=member.user.email))
    
    return redirect("accounts:hotel_members_list")


def _log_member_action(user, hotel, member, action_description):
    """Helper to log member actions"""
    try:
        UserActivityLog.log(
            user=user,
            action=UserActivityLog.Action.UPDATE,
            hotel=hotel,
            content_type='HotelMember',
            object_id=str(member.pk),
            object_repr=str(member),
            description=action_description
        )
    except Exception:
        pass


# ============================================================================
# Reports and Analytics Views
# ============================================================================

class TeamManagementView(LoginRequiredMixin, HotelMemberRequiredMixin, HotelContextMixin, TemplateView):
    """Team management dashboard"""
    template_name = "accounts/team_management.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hotel = self.get_hotel()
        
        members_by_role = {}
        for role_value, role_label in HotelMember.Role.choices:
            members = HotelMember.objects.filter(
                hotel=hotel, role=role_value, is_active=True
            ).select_related('user')
            if members.exists():
                members_by_role[role_value] = {
                    'label': role_label,
                    'members': members
                }
        
        context['members_by_role'] = members_by_role
        context['total_active'] = HotelMember.objects.filter(hotel=hotel, is_active=True).count()
        context['management_count'] = HotelMember.objects.filter(
            hotel=hotel, role__in=['admin', 'general_manager', 'operations_manager'], is_active=True
        ).count()
        context['on_leave_count'] = HotelMember.objects.filter(hotel=hotel, is_on_leave=True).count()
        
        return context


class StaffReportView(LoginRequiredMixin, HotelMemberRequiredMixin, HotelContextMixin, TemplateView):
    """Staff reports and analytics"""
    template_name = "accounts/staff_report.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hotel = self.get_hotel()
        
        # Basic stats
        context['total_staff'] = HotelMember.objects.filter(hotel=hotel).count()
        context['active_staff'] = HotelMember.objects.filter(hotel=hotel, is_active=True).count()
        
        # Role distribution
        role_distribution = HotelMember.objects.filter(hotel=hotel).values('role').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Add role labels
        role_map = dict(HotelMember.Role.choices)
        for item in role_distribution:
            item['role_label'] = role_map.get(item['role'], item['role'])
        
        context['role_distribution'] = role_distribution
        
        # Employment type distribution
        employment_distribution = HotelMember.objects.filter(hotel=hotel).values('employment_type').annotate(
            count=Count('id')
        )
        employment_map = dict(HotelMember.EmploymentType.choices)
        for item in employment_distribution:
            item['type_label'] = employment_map.get(item['employment_type'], item['employment_type'])
        
        context['employment_distribution'] = employment_distribution
        
        # Recent hires
        context['recent_hires'] = HotelMember.objects.filter(
            hotel=hotel, hire_date__isnull=False
        ).select_related('user').order_by('-hire_date')[:10]
        
        # Upcoming reviews
        context['upcoming_reviews'] = HotelMember.objects.filter(
            hotel=hotel, next_review_date__gte=timezone.now().date(), is_active=True
        ).select_related('user').order_by('next_review_date')[:10]
        
        return context


class PerformanceReportView(LoginRequiredMixin, HotelMemberRequiredMixin, HotelContextMixin, TemplateView):
    """Performance reports and analytics"""
    template_name = "accounts/performance_report.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hotel = self.get_hotel()
        
        # Performance statistics
        performance_stats = HotelMember.objects.filter(
            hotel=hotel, performance_rating__isnull=False
        ).aggregate(
            avg_rating=Coalesce(Avg('performance_rating'), D0),
            max_rating=Coalesce(Max('performance_rating'), D0),
            min_rating=Coalesce(Min('performance_rating'), D0),
            rated_count=Count('id')
        )
        context['performance_stats'] = performance_stats
        
        # Top performers (rating >= 4.0)
        context['top_performers'] = HotelMember.objects.filter(
            hotel=hotel, performance_rating__gte=4.0, is_active=True
        ).select_related('user').order_by('-performance_rating')[:10]
        
        # Needs improvement (rating < 3.0)
        context['needs_improvement'] = HotelMember.objects.filter(
            hotel=hotel, performance_rating__lt=3.0, performance_rating__isnull=False, is_active=True
        ).select_related('user').order_by('performance_rating')[:10]
        
        # Recent reviews
        context['recent_reviews'] = HotelMember.objects.filter(
            hotel=hotel, last_review_date__isnull=False
        ).select_related('user').order_by('-last_review_date')[:15]
        
        return context


# ============================================================================
# Activity Log Views
# ============================================================================

class MemberActivityLogView(LoginRequiredMixin, HotelMemberRequiredMixin, HotelContextMixin, ListView):
    """View activity logs for a specific member"""
    
    model = UserActivityLog
    template_name = "accounts/member_activity.html"
    context_object_name = "activities"
    paginate_by = 50
    
    def get_queryset(self):
        member = get_object_or_404(HotelMember, pk=self.kwargs['pk'])
        return UserActivityLog.objects.filter(
            user=member.user,
            hotel=self.get_hotel()
        ).select_related('user').order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['member'] = get_object_or_404(HotelMember, pk=self.kwargs['pk'])
        return context


class HotelActivityLogView(LoginRequiredMixin, HotelMemberRequiredMixin, HotelContextMixin, ListView):
    """View all activity logs for the hotel"""
    
    model = UserActivityLog
    template_name = "accounts/hotel_activity.html"
    context_object_name = "activities"
    paginate_by = 50
    
    def get_queryset(self):
        return UserActivityLog.objects.filter(
            hotel=self.get_hotel()
        ).select_related('user').order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add filter options
        context['action_choices'] = UserActivityLog.Action.choices
        
        # Summary stats
        context['total_activities'] = self.get_queryset().count()
        context['today_activities'] = self.get_queryset().filter(
            created_at__date=timezone.now().date()
        ).count()
        
        return context


# ============================================================================
# API Views
# ============================================================================

@login_required
def member_search_api(request: HttpRequest) -> JsonResponse:
    """JSON API for searching members (for autocomplete)"""
    hotel = get_active_hotel_for_user(request.user, request=request)
    query = request.GET.get('q', '')
    
    members = HotelMember.objects.filter(
        hotel=hotel, is_active=True
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
        'avatar': m.user.profile.avatar.url if hasattr(m.user, 'profile') and m.user.profile.avatar else None
    } for m in members[:20]]
    
    return JsonResponse({'results': results})


@login_required
def member_stats_api(request: HttpRequest) -> JsonResponse:
    """JSON API for member statistics"""
    hotel = get_active_hotel_for_user(request.user, request=request)
    
    roles_data = list(HotelMember.objects.filter(hotel=hotel).values('role').annotate(
        count=Count('id')
    ))
    
    # Add role labels
    role_map = dict(HotelMember.Role.choices)
    for item in roles_data:
        item['label'] = role_map.get(item['role'], item['role'])
    
    stats = {
        'total': HotelMember.objects.filter(hotel=hotel).count(),
        'active': HotelMember.objects.filter(hotel=hotel, is_active=True).count(),
        'inactive': HotelMember.objects.filter(hotel=hotel, is_active=False).count(),
        'on_leave': HotelMember.objects.filter(hotel=hotel, is_on_leave=True).count(),
        'management': HotelMember.objects.filter(
            hotel=hotel, role__in=['admin', 'general_manager', 'operations_manager'], is_active=True
        ).count(),
        'roles': roles_data,
    }
    
    return JsonResponse(stats)


# ============================================================================
# Member Dashboard View
# ============================================================================

class MemberDashboardView(LoginRequiredMixin, HotelContextMixin, TemplateView):
    """Individual member's personal dashboard"""
    template_name = "accounts/member_dashboard.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hotel = self.get_hotel()
        
        context['membership'] = get_object_or_404(
            HotelMember, user=self.request.user, hotel=hotel
        )
        context['profile'] = get_object_or_404(Profile, user=self.request.user)
        
        # Recent activity for this member
        context['recent_activity'] = UserActivityLog.objects.filter(
            user=self.request.user,
            hotel=hotel
        )[:20]
        
        return context


# ============================================================================
# Performance Review Views
# ============================================================================

@method_decorator(login_required, name="dispatch")
class MemberPerformanceUpdateView(LoginRequiredMixin, HotelMemberRequiredMixin, HotelContextMixin, UpdateView):
    """Update member performance rating and notes"""
    
    model = HotelMember
    fields = ['performance_rating', 'performance_notes', 'last_review_date', 'next_review_date']
    template_name = "accounts/member_performance_form.html"
    context_object_name = "member"
    
    def get_queryset(self):
        hotel = self.get_hotel()
        return HotelMember.objects.filter(hotel=hotel)
    
    def form_valid(self, form):
        if not form.cleaned_data.get('last_review_date'):
            form.instance.last_review_date = timezone.now().date()
        
        response = super().form_valid(form)
        messages.success(self.request, _("Performance rating updated successfully."))
        
        _log_member_action(self.request.user, self.get_hotel(), self.object, "updated performance rating")
        
        return response
    
    def get_success_url(self):
        return reverse("accounts:hotel_member_detail", kwargs={'pk': self.object.pk})


# ============================================================================
# Test/Error Views (Development only)
# ============================================================================

def test_error_handling(request: HttpRequest) -> HttpResponse:
    """Test view for error handling (development only)"""
    if not settings.DEBUG:
        raise PermissionDenied("This view is only available in development mode.")
    
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

# Add this to your accounts/views.py after the TeamManagementView class

# ============================================================================
# Shift Management Views
# ============================================================================

class ShiftManagementView(LoginRequiredMixin, HotelMemberRequiredMixin, HotelContextMixin, TemplateView):
    """Shift management dashboard - view staff organized by shift preferences"""
    template_name = "accounts/shift_management.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hotel = self.get_hotel()
        
        # Organize members by shift preference
        members_by_shift = {}
        shift_counts = {}
        
        for shift_value, shift_label in HotelMember.ShiftPreference.choices:
            members = HotelMember.objects.filter(
                hotel=hotel,
                shift_preference=shift_value,
                is_active=True
            ).select_related('user', 'user__profile').order_by('user__first_name', 'user__last_name')
            
            if members.exists():
                members_by_shift[shift_value] = {
                    'label': shift_label,
                    'members': members,
                    'count': members.count()
                }
                shift_counts[shift_value] = members.count()
            else:
                members_by_shift[shift_value] = {
                    'label': shift_label,
                    'members': [],
                    'count': 0
                }
                shift_counts[shift_value] = 0
        
        # Get members with custom shift times
        custom_shift_members = HotelMember.objects.filter(
            hotel=hotel,
            is_active=True,
            default_shift_start__isnull=False,
            default_shift_end__isnull=False
        ).select_related('user', 'user__profile').order_by('default_shift_start')
        
        context['members_by_shift'] = members_by_shift
        context['shift_counts'] = shift_counts
        context['custom_shift_members'] = custom_shift_members
        context['total_active'] = HotelMember.objects.filter(hotel=hotel, is_active=True).count()
        
        # Shift statistics
        context['morning_shift_count'] = shift_counts.get('morning', 0)
        context['afternoon_shift_count'] = shift_counts.get('afternoon', 0)
        context['night_shift_count'] = shift_counts.get('night', 0)
        context['rotating_shift_count'] = shift_counts.get('rotating', 0)
        context['flexible_shift_count'] = shift_counts.get('flexible', 0)
        
        # Get members currently on leave (not available for shifts)
        context['on_leave_members'] = HotelMember.objects.filter(
            hotel=hotel,
            is_on_leave=True,
            is_active=True
        ).select_related('user')
        
        return context


class ShiftAssignmentView(LoginRequiredMixin, HotelMemberRequiredMixin, HotelContextMixin, TemplateView):
    """View for managing shift assignments (more detailed than preferences)"""
    template_name = "accounts/shift_assignments.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hotel = self.get_hotel()
        
        # Get date from query param or default to today
        selected_date = self.request.GET.get('date')
        if selected_date:
            try:
                context['selected_date'] = datetime.strptime(selected_date, '%Y-%m-%d').date()
            except ValueError:
                context['selected_date'] = timezone.now().date()
        else:
            context['selected_date'] = timezone.now().date()
        
        # Get all active members
        active_members = HotelMember.objects.filter(
            hotel=hotel,
            is_active=True,
            is_on_leave=False
        ).select_related('user', 'user__profile').order_by('user__first_name')
        
        # Group members by shift preference for easy display
        morning_members = []
        afternoon_members = []
        night_members = []
        flexible_members = []
        
        for member in active_members:
            member_data = {
                'id': member.id,
                'name': member.user.get_full_name() or member.user.email,
                'email': member.user.email,
                'role': member.get_role_display(),
                'shift_preference': member.shift_preference,
                'default_shift_start': member.default_shift_start,
                'default_shift_end': member.default_shift_end,
                'avatar': member.user.profile.avatar.url if hasattr(member.user, 'profile') and member.user.profile.avatar else None,
            }
            
            if member.shift_preference == 'morning':
                morning_members.append(member_data)
            elif member.shift_preference == 'afternoon':
                afternoon_members.append(member_data)
            elif member.shift_preference == 'night':
                night_members.append(member_data)
            else:
                flexible_members.append(member_data)
        
        context['morning_members'] = morning_members
        context['afternoon_members'] = afternoon_members
        context['night_members'] = night_members
        context['flexible_members'] = flexible_members
        
        # Statistics
        context['total_morning'] = len(morning_members)
        context['total_afternoon'] = len(afternoon_members)
        context['total_night'] = len(night_members)
        context['total_flexible'] = len(flexible_members)
        context['total_active_staff'] = active_members.count()
        
        return context


@method_decorator(login_required, name="dispatch")
class MemberShiftUpdateView(LoginRequiredMixin, HotelMemberRequiredMixin, HotelContextMixin, UpdateView):
    """Update a member's shift preferences"""
    
    model = HotelMember
    fields = ['shift_preference', 'default_shift_start', 'default_shift_end', 'max_weekly_hours']
    template_name = "accounts/member_shift_update.html"
    context_object_name = "member"
    
    def get_queryset(self):
        hotel = self.get_hotel()
        return HotelMember.objects.filter(hotel=hotel)
    
    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, _("Shift preferences updated successfully."))
        
        # Log the activity
        try:
            UserActivityLog.log(
                user=self.request.user,
                action=UserActivityLog.Action.UPDATE,
                hotel=self.get_hotel(),
                content_type='HotelMember',
                object_id=str(self.object.pk),
                object_repr=str(self.object),
                description=f"Updated shift preferences for {self.object.user.email}"
            )
        except Exception:
            pass
        
        return response
    
    def get_success_url(self):
        # Return to shift management or member detail
        next_url = self.request.POST.get('next') or self.request.GET.get('next')
        if next_url:
            return next_url
        return reverse("accounts:shift_management", kwargs={'pk': self.object.pk})