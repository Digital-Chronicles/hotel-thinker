from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.validators import RegexValidator, EmailValidator, MinLengthValidator
from django.contrib.auth import get_user_model
from hotels.models import Hotel

import uuid


class Profile(models.Model):
    """Extended user profile with professional contact information"""
    
    class Gender(models.TextChoices):
        MALE = "male", _("Male")
        FEMALE = "female", _("Female")
        OTHER = "other", _("Other")
        PREFER_NOT_TO_SAY = "prefer_not_to_say", _("Prefer not to say")

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile"
    )
    
    # Personal Information
    phone = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        validators=[RegexValidator(r'^\+?1?\d{9,15}$', message=_("Enter a valid phone number."))]
    )
    alternative_phone = models.CharField(max_length=30, blank=True, null=True)
    gender = models.CharField(max_length=20, choices=Gender.choices, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    
    # Professional Information
    job_title = models.CharField(max_length=100, blank=True, null=True)
    department = models.CharField(max_length=100, blank=True, null=True)
    employee_id = models.CharField(max_length=50, blank=True, null=True, unique=True)
    
    # Address
    address_line1 = models.CharField(max_length=255, blank=True, null=True)
    address_line2 = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    postal_code = models.CharField(max_length=20, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    
    # Preferences
    language = models.CharField(
        max_length=10,
        default='en',
        choices=[
            ('en', _('English')),
            ('fr', _('French')),
            ('es', _('Spanish')),
            ('ar', _('Arabic')),
            ('zh', _('Chinese')),
            ('ru', _('Russian')),
        ]
    )
    timezone = models.CharField(max_length=50, default='UTC')
    notification_email = models.BooleanField(default=True)
    notification_sms = models.BooleanField(default=False)
    notification_push = models.BooleanField(default=True)
    
    # Metadata
    last_active = models.DateTimeField(blank=True, null=True)
    last_ip_address = models.GenericIPAddressField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'employee_id']),
            models.Index(fields=['phone']),
            models.Index(fields=['last_active']),
        ]
        verbose_name = _("Profile")
        verbose_name_plural = _("Profiles")

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username}'s Profile"

    def update_last_active(self, ip_address=None):
        """Update user's last active timestamp"""
        self.last_active = timezone.now()
        if ip_address:
            self.last_ip_address = ip_address
        self.save(update_fields=['last_active', 'last_ip_address'])

    @property
    def full_address(self):
        """Return formatted full address"""
        parts = [self.address_line1, self.address_line2, self.city, self.state, self.postal_code, self.country]
        return ', '.join(filter(None, parts))


class HotelMember(models.Model):
    """Advanced hotel membership with granular permissions and audit trail"""
    
    class Role(models.TextChoices):
        ADMIN = "admin", _("Administrator")
        GENERAL_MANAGER = "general_manager", _("General Manager")
        OPERATIONS_MANAGER = "operations_manager", _("Operations Manager")
        FRONT_DESK_MANAGER = "front_desk_manager", _("Front Desk Manager")
        FRONT_DESK = "front_desk", _("Front Desk Staff")
        HOUSEKEEPING_MANAGER = "housekeeping_manager", _("Housekeeping Manager")
        HOUSEKEEPER = "housekeeper", _("Housekeeper")
        RESTAURANT_MANAGER = "restaurant_manager", _("Restaurant Manager")
        SERVER = "server", _("Server")
        CHEF = "chef", _("Chef")
        ACCOUNTANT = "accountant", _("Accountant")
        MAINTENANCE = "maintenance", _("Maintenance")
        VIEWER = "viewer", _("Viewer Only")

    class PermissionLevel(models.TextChoices):
        FULL = "full", _("Full Access")
        READ_WRITE = "read_write", _("Read & Write")
        READ_ONLY = "read_only", _("Read Only")
        RESTRICTED = "restricted", _("Restricted")

    hotel = models.ForeignKey(
        Hotel,
        on_delete=models.CASCADE,
        related_name="members"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="hotel_memberships"
    )
    
    # Role and permissions
    role = models.CharField(max_length=30, choices=Role.choices, default=Role.VIEWER)
    permission_level = models.CharField(
        max_length=20,
        choices=PermissionLevel.choices,
        default=PermissionLevel.READ_WRITE
    )
    
    # Department/Section access
    can_access_front_desk = models.BooleanField(default=False)
    can_access_housekeeping = models.BooleanField(default=False)
    can_access_restaurant = models.BooleanField(default=False)
    can_access_finance = models.BooleanField(default=False)
    can_access_maintenance = models.BooleanField(default=False)
    can_access_reports = models.BooleanField(default=False)
    
    # Status
    is_active = models.BooleanField(default=True)
    is_primary_contact = models.BooleanField(
        default=False,
        help_text=_("Primary contact for this hotel")
    )
    
    # Audit trail
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invited_members"
    )
    invitation_sent_at = models.DateTimeField(null=True, blank=True)
    invitation_accepted_at = models.DateTimeField(null=True, blank=True)
    joined_at = models.DateTimeField(auto_now_add=True)
    last_accessed = models.DateTimeField(null=True, blank=True)
    
    # Notes
    notes = models.TextField(blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["hotel", "user"],
                name="uniq_user_per_hotel"
            ),
        ]
        indexes = [
            models.Index(fields=["hotel", "role", "is_active"]),
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["hotel", "last_accessed"]),
        ]
        ordering = ['hotel__name', 'role', 'user__email']
        verbose_name = _("Hotel Member")
        verbose_name_plural = _("Hotel Members")

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.email} @ {self.hotel.name} ({self.get_role_display()})"

    def accept_invitation(self):
        """Mark invitation as accepted"""
        self.invitation_accepted_at = timezone.now()
        self.is_active = True
        self.save(update_fields=['invitation_accepted_at', 'is_active'])

    def update_last_accessed(self):
        """Update last accessed timestamp"""
        self.last_accessed = timezone.now()
        self.save(update_fields=['last_accessed'])

    @property
    def is_management(self):
        """Check if member has management role"""
        management_roles = [
            self.Role.ADMIN,
            self.Role.GENERAL_MANAGER,
            self.Role.OPERATIONS_MANAGER,
            self.Role.FRONT_DESK_MANAGER,
            self.Role.HOUSEKEEPING_MANAGER,
            self.Role.RESTAURANT_MANAGER,
        ]
        return self.role in management_roles


class UserActivityLog(models.Model):
    """Track user activities across the system"""
    
    class Action(models.TextChoices):
        LOGIN = "login", _("Login")
        LOGOUT = "logout", _("Logout")
        CREATE = "create", _("Create")
        UPDATE = "update", _("Update")
        DELETE = "delete", _("Delete")
        VIEW = "view", _("View")
        EXPORT = "export", _("Export")
        PRINT = "print", _("Print")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="activities"
    )
    hotel = models.ForeignKey(
        Hotel,
        on_delete=models.CASCADE,
        related_name="user_activities",
        null=True,
        blank=True
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    content_type = models.CharField(max_length=100, blank=True, null=True)
    object_id = models.CharField(max_length=50, blank=True, null=True)
    object_repr = models.CharField(max_length=200, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['hotel', '-created_at']),
            models.Index(fields=['action', 'created_at']),
        ]
        ordering = ['-created_at']
        verbose_name = _("User Activity Log")
        verbose_name_plural = _("User Activity Logs")

    def __str__(self):
        return f"{self.user} - {self.action} at {self.created_at}"