# accounts/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.db.models import Count, Q
from .models import Profile, HotelMember, UserActivityLog


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone", "gender", "city", "country", "is_active", "last_active")
    list_filter = ("gender", "is_active", "language", "country", "notification_email")
    search_fields = ("user__username", "user__email", "user__first_name", "user__last_name", 
                    "phone", "employee_id", "city", "department")
    readonly_fields = ("created_at", "updated_at", "last_active", "last_ip_address")
    list_select_related = ("user",)
    
    fieldsets = (
        (_("User Information"), {
            "fields": ("user", "employee_id", "job_title", "department")
        }),
        (_("Personal Information"), {
            "fields": ("phone", "alternative_phone", "gender", "date_of_birth")
        }),
        (_("Address"), {
            "fields": ("address_line1", "address_line2", "city", "state", "postal_code", "country")
        }),
        (_("Preferences"), {
            "fields": ("language", "timezone")
        }),
        (_("Notifications"), {
            "fields": ("notification_email", "notification_sms", "notification_push", "notification_digest")
        }),
        (_("Avatar"), {
            "fields": ("avatar",)
        }),
        (_("Metadata"), {
            "fields": ("last_active", "last_ip_address", "last_login_device", "created_at", "updated_at"),
            "classes": ("collapse",)
        }),
        (_("Status"), {
            "fields": ("is_active", "deleted_at")
        }),
    )
    
    actions = ["soft_delete_selected", "restore_selected", "activate_selected", "deactivate_selected"]
    
    def soft_delete_selected(self, request, queryset):
        for profile in queryset:
            profile.soft_delete()
        self.message_user(request, _("{} profiles were soft deleted.").format(queryset.count()))
    soft_delete_selected.short_description = _("Soft delete selected profiles")
    
    def restore_selected(self, request, queryset):
        for profile in queryset:
            profile.restore()
        self.message_user(request, _("{} profiles were restored.").format(queryset.count()))
    restore_selected.short_description = _("Restore selected profiles")
    
    def activate_selected(self, request, queryset):
        queryset.update(is_active=True, deleted_at=None)
        self.message_user(request, _("{} profiles were activated.").format(queryset.count()))
    activate_selected.short_description = _("Activate selected profiles")
    
    def deactivate_selected(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, _("{} profiles were deactivated.").format(queryset.count()))
    deactivate_selected.short_description = _("Deactivate selected profiles")
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user")
    
    def user_full_name(self, obj):
        return obj.user.get_full_name() or obj.user.username
    user_full_name.short_description = _("Full Name")
    user_full_name.admin_order_field = "user__first_name"


class HotelMemberInline(admin.TabularInline):
    model = HotelMember
    extra = 0
    fields = ("hotel", "role", "permission_level", "is_active", "is_primary_contact")
    readonly_fields = ("joined_at", "invitation_accepted_at", "employee_code")
    show_change_link = True
    can_delete = False


@admin.register(HotelMember)
class HotelMemberAdmin(admin.ModelAdmin):
    list_display = ("hotel_link", "user_link", "role_badge", "permission_level", 
                   "employment_type", "is_active_badge", "is_primary_contact_badge", 
                   "joined_at", "last_accessed")
    list_filter = ("role", "permission_level", "is_active", "employment_type", 
                  "shift_preference", "is_primary_contact", "is_on_leave", "hotel")
    search_fields = ("hotel__name", "user__username", "user__email", "user__first_name", 
                    "user__last_name", "employee_code", "work_phone", "work_email")
    readonly_fields = ("joined_at", "invitation_sent_at", "invitation_accepted_at", 
                      "terminated_at", "employee_code", "profile_picture_thumbnail_preview")
    list_select_related = ("hotel", "user", "invited_by", "terminated_by")
    list_per_page = 25
    date_hierarchy = "joined_at"
    
    fieldsets = (
        (_("Hotel & User"), {
            "fields": ("hotel", "user", "role", "permission_level")
        }),
        (_("Profile Picture"), {
            "fields": ("profile_picture", "profile_picture_thumbnail_preview"),
            "classes": ("collapse",)
        }),
        (_("Contact Information"), {
            "fields": ("work_phone", "work_email", "emergency_contact_name", 
                      "emergency_contact_phone", "emergency_contact_relationship")
        }),
        (_("Employment Information"), {
            "fields": ("employment_type", "employee_code", "hire_date", 
                      "contract_start_date", "contract_end_date", "probation_end_date")
        }),
        (_("Work Schedule"), {
            "fields": ("shift_preference", "default_shift_start", "default_shift_end", 
                      "max_weekly_hours", "overtime_allowed")
        }),
        (_("Compensation"), {
            "fields": ("hourly_rate", "salary", "currency"),
            "classes": ("collapse",)
        }),
        (_("Permissions"), {
            "fields": ("department_access", "can_manage_bookings", "can_manage_rooms",
                      "can_manage_inventory", "can_manage_staff", "can_view_financials",
                      "can_manage_reports", "can_manage_settings")
        }),
        (_("Deprecated Permissions"), {
            "fields": ("can_access_front_desk", "can_access_housekeeping", 
                      "can_access_restaurant", "can_access_finance", 
                      "can_access_maintenance", "can_access_reports"),
            "classes": ("collapse",)
        }),
        (_("Status & Leave"), {
            "fields": ("is_active", "is_primary_contact", "is_on_leave", 
                      "leave_start_date", "leave_end_date", "leave_reason")
        }),
        (_("Training & Performance"), {
            "fields": ("training_completed", "certifications", "last_training_date",
                      "next_training_due", "performance_rating", "last_review_date",
                      "next_review_date", "performance_notes"),
            "classes": ("collapse",)
        }),
        (_("Recognition"), {
            "fields": ("badges", "years_of_service_awards", "special_skills", "languages_spoken"),
            "classes": ("collapse",)
        }),
        (_("Invitation & Audit"), {
            "fields": ("invited_by", "invitation_sent_at", "invitation_accepted_at", 
                      "invitation_expires_at", "joined_at", "last_accessed", "notes")
        }),
        (_("Termination"), {
            "fields": ("terminated_at", "terminated_by", "termination_reason", "eligible_for_rehire"),
            "classes": ("collapse",)
        }),
    )
    
    actions = ["resend_invitations", "terminate_selected", "activate_selected", 
              "deactivate_selected", "start_leave_selected", "end_leave_selected"]
    
    def hotel_link(self, obj):
        url = reverse("admin:hotels_hotel_change", args=[obj.hotel.id])
        return format_html('<a href="{}">{}</a>', url, obj.hotel.name)
    hotel_link.short_description = _("Hotel")
    hotel_link.admin_order_field = "hotel__name"
    
    def user_link(self, obj):
        url = reverse("admin:auth_user_change", args=[obj.user.id])
        return format_html('<a href="{}">{}</a>', url, obj.user.get_full_name() or obj.user.email)
    user_link.short_description = _("User")
    user_link.admin_order_field = "user__first_name"
    
    def role_badge(self, obj):
        colors = {
            "admin": "red",
            "general_manager": "purple",
            "operations_manager": "orange",
            "front_desk_manager": "blue",
            "front_desk": "green",
            "housekeeping_manager": "teal",
            "housekeeper": "cyan",
            "restaurant_manager": "indigo",
            "server": "pink",
            "chef": "brown",
            "accountant": "gold",
            "maintenance": "gray",
            "security": "dark",
            "viewer": "light",
        }
        color = colors.get(obj.role, "default")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 0.8em;">{}</span>',
            self._get_color_code(color),
            obj.get_role_display()
        )
    role_badge.short_description = _("Role")
    
    def _get_color_code(self, color):
        colors_map = {
            "red": "#dc3545", "purple": "#6f42c1", "orange": "#fd7e14",
            "blue": "#0d6efd", "green": "#198754", "teal": "#20c997",
            "cyan": "#0dcaf0", "indigo": "#6610f2", "pink": "#d63384",
            "brown": "#8B4513", "gold": "#ffc107", "gray": "#6c757d",
            "dark": "#212529", "light": "#f8f9fa"
        }
        return colors_map.get(color, "#6c757d")
    
    def is_active_badge(self, obj):
        if not obj.is_active:
            return format_html('<span style="color: #dc3545;">✗ {}</span>', _("Inactive"))
        if obj.is_on_leave:
            return format_html('<span style="color: #ffc107;">⏱ {}</span>', _("On Leave"))
        return format_html('<span style="color: #198754;">✓ {}</span>', _("Active"))
    is_active_badge.short_description = _("Status")
    
    def is_primary_contact_badge(self, obj):
        if obj.is_primary_contact:
            return format_html('<span style="color: #0d6efd;">★ {}</span>', _("Primary"))
        return format_html('<span style="color: #6c757d;">☆</span>', _("Not Primary"))
    is_primary_contact_badge.short_description = _("Primary Contact")
    
    def profile_picture_thumbnail_preview(self, obj):
        if obj.profile_picture_thumbnail:
            return format_html('<img src="{}" width="100" height="100" style="border-radius: 50%;" />', 
                             obj.profile_picture_thumbnail.url)
        elif obj.profile_picture:
            return format_html('<img src="{}" width="100" height="100" style="border-radius: 50%;" />', 
                             obj.profile_picture.url)
        return _("No image")
    profile_picture_thumbnail_preview.short_description = _("Profile Picture Preview")
    
    def resend_invitations(self, request, queryset):
        for member in queryset.filter(invitation_accepted_at__isnull=True):
            member.resend_invitation(request.user)
        self.message_user(request, _("Invitations resent to {} members.").format(queryset.count()))
    resend_invitations.short_description = _("Resend invitations to selected members")
    
    def terminate_selected(self, request, queryset):
        for member in queryset.filter(is_active=True):
            member.terminate(request.user, _("Terminated via admin action"))
        self.message_user(request, _("{} members were terminated.").format(queryset.count()))
    terminate_selected.short_description = _("Terminate selected members")
    
    def activate_selected(self, request, queryset):
        queryset.update(is_active=True, terminated_at=None, termination_reason=None)
        self.message_user(request, _("{} members were activated.").format(queryset.count()))
    activate_selected.short_description = _("Activate selected members")
    
    def deactivate_selected(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, _("{} members were deactivated.").format(queryset.count()))
    deactivate_selected.short_description = _("Deactivate selected members")
    
    def start_leave_selected(self, request, queryset):
        from django.utils import timezone
        for member in queryset.filter(is_active=True, is_on_leave=False):
            member.start_leave(timezone.now().date(), 
                              timezone.now().date() + timezone.timedelta(days=30),
                              _("Admin initiated leave"))
        self.message_user(request, _("Leave started for {} members.").format(queryset.count()))
    start_leave_selected.short_description = _("Start leave for selected members (30 days)")
    
    def end_leave_selected(self, request, queryset):
        for member in queryset.filter(is_on_leave=True):
            member.end_leave()
        self.message_user(request, _("Leave ended for {} members.").format(queryset.count()))
    end_leave_selected.short_description = _("End leave for selected members")
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related("hotel", "user", "invited_by", "terminated_by")
    
    def save_model(self, request, obj, form, change):
        if not obj.pk and not obj.invited_by:
            obj.invited_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(UserActivityLog)
class UserActivityLogAdmin(admin.ModelAdmin):
    list_display = ("user_link", "action_badge", "hotel_link", "object_repr", 
                   "ip_address", "duration_ms", "created_at")
    list_filter = ("action", "request_method", "response_status", "created_at")
    search_fields = ("user__username", "user__email", "object_repr", "description", 
                    "ip_address", "request_path")
    readonly_fields = ("user", "hotel", "action", "content_type", "object_id", 
                      "object_repr", "description", "changes", "ip_address", 
                      "user_agent", "request_method", "request_path", 
                      "response_status", "duration_ms", "created_at")
    list_select_related = ("user", "hotel")
    list_per_page = 50
    date_hierarchy = "created_at"
    
    fieldsets = (
        (_("User & Action"), {
            "fields": ("user", "action", "hotel")
        }),
        (_("Object Information"), {
            "fields": ("content_type", "object_id", "object_repr")
        }),
        (_("Details"), {
            "fields": ("description", "changes")
        }),
        (_("Request Information"), {
            "fields": ("ip_address", "user_agent", "request_method", "request_path", 
                      "response_status", "duration_ms")
        }),
        (_("Metadata"), {
            "fields": ("created_at",)
        }),
    )
    
    def user_link(self, obj):
        url = reverse("admin:auth_user_change", args=[obj.user.id])
        return format_html('<a href="{}">{}</a>', url, obj.user.get_full_name() or obj.user.email)
    user_link.short_description = _("User")
    user_link.admin_order_field = "user__first_name"
    
    def hotel_link(self, obj):
        if obj.hotel:
            url = reverse("admin:hotels_hotel_change", args=[obj.hotel.id])
            return format_html('<a href="{}">{}</a>', url, obj.hotel.name)
        return "-"
    hotel_link.short_description = _("Hotel")
    hotel_link.admin_order_field = "hotel__name"
    
    def action_badge(self, obj):
        colors = {
            "login": "success",
            "logout": "secondary",
            "login_failed": "danger",
            "create": "primary",
            "update": "warning",
            "delete": "danger",
            "view": "info",
            "export": "success",
            "permission_change": "danger",
        }
        color = colors.get(obj.action, "secondary")
        return format_html(
            '<span class="badge bg-{}">{}</span>',
            color,
            obj.get_action_display()
        )
    action_badge.short_description = _("Action")
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        # Allow deletion for cleanup purposes
        return request.user.is_superuser


# Custom admin site header and title
admin.site.site_header = _("Hotel Management System Administration")
admin.site.site_title = _("Hotel Management Admin")
admin.site.index_title = _("Welcome to Hotel Management System")