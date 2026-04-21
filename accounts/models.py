# accounts/models.py

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.validators import RegexValidator, MinLengthValidator, MaxLengthValidator
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.db.models import Q, F
from hotels.models import Hotel

import uuid
import logging

logger = logging.getLogger(__name__)


class Profile(models.Model):
    """Extended user profile with professional contact information"""
    
    class Gender(models.TextChoices):
        MALE = "male", _("Male")
        FEMALE = "female", _("Female")
        OTHER = "other", _("Other")
        PREFER_NOT_TO_SAY = "prefer_not_to_say", _("Prefer not to say")
    
    class Language(models.TextChoices):
        ENGLISH = "en", _("English")
        FRENCH = "fr", _("French")
        SPANISH = "es", _("Spanish")
        ARABIC = "ar", _("Arabic")
        CHINESE = "zh", _("Chinese")
        RUSSIAN = "ru", _("Russian")
        GERMAN = "de", _("German")
        ITALIAN = "it", _("Italian")
        PORTUGUESE = "pt", _("Portuguese")
        JAPANESE = "ja", _("Japanese")
        KOREAN = "ko", _("Korean")

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
        validators=[
            RegexValidator(
                regex=r'^\+?1?\d{9,15}$',
                message=_("Enter a valid phone number (9-15 digits, optional + prefix).")
            )
        ],
        db_index=True,
        verbose_name=_("Phone Number")
    )
    alternative_phone = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        validators=[RegexValidator(r'^\+?1?\d{9,15}$', message=_("Enter a valid phone number."))],
        verbose_name=_("Alternative Phone")
    )
    gender = models.CharField(
        max_length=20,
        choices=Gender.choices,
        blank=True,
        null=True,
        db_index=True
    )
    date_of_birth = models.DateField(
        blank=True,
        null=True,
        verbose_name=_("Date of Birth")
    )
    
    # Professional Information
    job_title = models.CharField(max_length=100, blank=True, null=True, verbose_name=_("Job Title"))
    department = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    employee_id = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
        verbose_name=_("Employee ID")
    )
    
    # Address
    address_line1 = models.CharField(max_length=255, blank=True, null=True)
    address_line2 = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    postal_code = models.CharField(max_length=20, blank=True, null=True)
    country = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        default='US',
        db_index=True
    )
    
    # Preferences
    language = models.CharField(
        max_length=10,
        default=Language.ENGLISH,
        choices=Language.choices,
        db_index=True
    )
    timezone = models.CharField(
        max_length=50,
        default='UTC',
        help_text=_("User's preferred timezone for date/time display")
    )
    
    # Notification Preferences
    notification_email = models.BooleanField(default=True, verbose_name=_("Email Notifications"))
    notification_sms = models.BooleanField(default=False, verbose_name=_("SMS Notifications"))
    notification_push = models.BooleanField(default=True, verbose_name=_("Push Notifications"))
    notification_digest = models.BooleanField(default=True, verbose_name=_("Daily Digest"))
    
    # Avatar/Profile Image
    avatar = models.ImageField(
        upload_to='profile_avatars/%Y/%m/%d/',
        blank=True,
        null=True,
        max_length=500,
        verbose_name=_("Profile Picture")
    )
    
    # Metadata
    last_active = models.DateTimeField(blank=True, null=True, db_index=True)
    last_ip_address = models.GenericIPAddressField(blank=True, null=True)
    last_login_device = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Soft delete
    is_active = models.BooleanField(default=True, db_index=True)
    deleted_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'employee_id'], name='profile_user_emp_idx'),
            models.Index(fields=['phone'], name='profile_phone_idx'),
            models.Index(fields=['last_active'], name='profile_active_idx'),
            models.Index(fields=['department', 'job_title'], name='profile_dept_job_idx'),
            models.Index(fields=['city', 'country'], name='profile_location_idx'),
            models.Index(fields=['is_active', '-created_at'], name='profile_active_created_idx'),
        ]
        verbose_name = _("Profile")
        verbose_name_plural = _("Profiles")
        ordering = ['user__last_name', 'user__first_name']

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username}'s Profile"

    def clean(self):
        """Validate model data"""
        super().clean()
        if self.date_of_birth and self.date_of_birth > timezone.now().date():
            raise ValidationError({'date_of_birth': _("Date of birth cannot be in the future.")})
        
        if self.employee_id and Profile.objects.filter(employee_id=self.employee_id).exclude(pk=self.pk).exists():
            raise ValidationError({'employee_id': _("Employee ID already exists.")})

    def save(self, *args, **kwargs):
        """Override save to perform additional actions"""
        self.full_clean()
        super().save(*args, **kwargs)

    def update_last_active(self, ip_address=None, device_info=None):
        """Update user's last active timestamp with device tracking"""
        self.last_active = timezone.now()
        if ip_address:
            self.last_ip_address = ip_address
        if device_info:
            self.last_login_device = device_info
        self.save(update_fields=['last_active', 'last_ip_address', 'last_login_device'])

    def soft_delete(self):
        """Soft delete the profile"""
        self.is_active = False
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_active', 'deleted_at'])

    def restore(self):
        """Restore a soft-deleted profile"""
        self.is_active = True
        self.deleted_at = None
        self.save(update_fields=['is_active', 'deleted_at'])

    @property
    def full_address(self):
        """Return formatted full address"""
        parts = filter(None, [
            self.address_line1, self.address_line2, self.city,
            self.state, self.postal_code, self.country
        ])
        return ', '.join(parts)

    @property
    def get_phone_e164(self):
        """Return phone number in E.164 format if possible"""
        if self.phone:
            # Add your phone number formatting logic here
            return self.phone
        return None

    @property
    def age(self):
        """Calculate user's age from date of birth"""
        if self.date_of_birth:
            today = timezone.now().date()
            return today.year - self.date_of_birth.year - (
                (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
            )
        return None


class HotelMemberManager(models.Manager):
    """Custom manager for HotelMember model"""
    
    def active(self):
        """Return only active memberships"""
        return self.filter(is_active=True)
    
    def for_hotel(self, hotel_id):
        """Return members for a specific hotel"""
        return self.filter(hotel_id=hotel_id, is_active=True)
    
    def for_user(self, user):
        """Return memberships for a specific user"""
        return self.filter(user=user, is_active=True)
    
    def management(self):
        """Return only management roles"""
        management_roles = [
            HotelMember.Role.ADMIN,
            HotelMember.Role.GENERAL_MANAGER,
            HotelMember.Role.OPERATIONS_MANAGER,
            HotelMember.Role.FRONT_DESK_MANAGER,
            HotelMember.Role.HOUSEKEEPING_MANAGER,
            HotelMember.Role.RESTAURANT_MANAGER,
        ]
        return self.filter(role__in=management_roles, is_active=True)
    
    def pending_invitations(self):
        """Return pending invitations"""
        return self.filter(
            invitation_accepted_at__isnull=True,
            invitation_sent_at__isnull=False,
            is_active=False
        )


# accounts/models.py (HotelMember section)

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
        SECURITY = "security", _("Security Staff")
        VIEWER = "viewer", _("Viewer Only")

    class PermissionLevel(models.TextChoices):
        FULL = "full", _("Full Access")
        READ_WRITE = "read_write", _("Read & Write")
        READ_ONLY = "read_only", _("Read Only")
        RESTRICTED = "restricted", _("Restricted")
    
    class EmploymentType(models.TextChoices):
        FULL_TIME = "full_time", _("Full Time")
        PART_TIME = "part_time", _("Part Time")
        CONTRACT = "contract", _("Contract")
        SEASONAL = "seasonal", _("Seasonal")
        INTERN = "intern", _("Intern")
        TEMPORARY = "temporary", _("Temporary")
        ON_CALL = "on_call", _("On Call")
    
    class ShiftPreference(models.TextChoices):
        MORNING = "morning", _("Morning (6 AM - 2 PM)")
        AFTERNOON = "afternoon", _("Afternoon (2 PM - 10 PM)")
        NIGHT = "night", _("Night (10 PM - 6 AM)")
        ROTATING = "rotating", _("Rotating")
        FLEXIBLE = "flexible", _("Flexible")

    # Relationships
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
    
    # Profile Picture (hotel-specific)
    profile_picture = models.ImageField(
        upload_to='hotel_members/%Y/%m/%d/',
        blank=True,
        null=True,
        max_length=500,
        verbose_name=_("Profile Picture"),
        help_text=_("Hotel-specific profile picture (overrides global profile picture)")
    )
    profile_picture_thumbnail = models.ImageField(
        upload_to='hotel_members/thumbnails/%Y/%m/%d/',
        blank=True,
        null=True,
        max_length=500,
        verbose_name=_("Profile Picture Thumbnail")
    )
    
    # Contact Information (hotel-specific)
    work_phone = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        validators=[RegexValidator(r'^\+?1?\d{9,15}$', message=_("Enter a valid phone number."))],
        verbose_name=_("Work Phone"),
        help_text=_("Hotel-specific work phone number")
    )
    work_email = models.EmailField(
        blank=True,
        null=True,
        verbose_name=_("Work Email"),
        help_text=_("Hotel-specific email address")
    )
    emergency_contact_name = models.CharField(max_length=200, blank=True, null=True)
    emergency_contact_phone = models.CharField(max_length=30, blank=True, null=True)
    emergency_contact_relationship = models.CharField(max_length=100, blank=True, null=True)
    
    # Employment Information
    employment_type = models.CharField(
        max_length=20,
        choices=EmploymentType.choices,
        default=EmploymentType.FULL_TIME,
        db_index=True
    )
    employee_code = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
        verbose_name=_("Employee Code"),
        help_text=_("Unique employee identifier within the system")
    )
    hire_date = models.DateField(null=True, blank=True, db_index=True)
    contract_start_date = models.DateField(null=True, blank=True)
    contract_end_date = models.DateField(null=True, blank=True)
    probation_end_date = models.DateField(null=True, blank=True)
    
    # Work Schedule
    shift_preference = models.CharField(
        max_length=20,
        choices=ShiftPreference.choices,
        default=ShiftPreference.FLEXIBLE
    )
    default_shift_start = models.TimeField(null=True, blank=True)
    default_shift_end = models.TimeField(null=True, blank=True)
    max_weekly_hours = models.PositiveSmallIntegerField(default=40, null=True, blank=True)
    overtime_allowed = models.BooleanField(default=False)
    
    # Compensation (sensitive, could be moved to separate model)
    hourly_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Hourly Rate")
    )
    salary = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Annual Salary")
    )
    currency = models.CharField(max_length=3, default='USD', blank=True, null=True)
    
    # Role and permissions
    role = models.CharField(
        max_length=30,
        choices=Role.choices,
        default=Role.VIEWER,
        db_index=True
    )
    permission_level = models.CharField(
        max_length=20,
        choices=PermissionLevel.choices,
        default=PermissionLevel.READ_WRITE
    )
    
    # Department/Section access (simplified with bitmask or JSON)
    department_access = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("JSON field storing department-specific permissions")
    )
    
    # Specific permissions for different modules
    can_manage_bookings = models.BooleanField(default=False)
    can_manage_rooms = models.BooleanField(default=False)
    can_manage_inventory = models.BooleanField(default=False)
    can_manage_staff = models.BooleanField(default=False)
    can_view_financials = models.BooleanField(default=False)
    can_manage_reports = models.BooleanField(default=False)
    can_manage_settings = models.BooleanField(default=False)
    
    # Deprecated fields - kept for backward compatibility
    can_access_front_desk = models.BooleanField(default=False)
    can_access_housekeeping = models.BooleanField(default=False)
    can_access_restaurant = models.BooleanField(default=False)
    can_access_finance = models.BooleanField(default=False)
    can_access_maintenance = models.BooleanField(default=False)
    can_access_reports = models.BooleanField(default=False)
    
    # Status
    is_active = models.BooleanField(default=True, db_index=True)
    is_primary_contact = models.BooleanField(
        default=False,
        help_text=_("Primary contact for this hotel"),
        db_index=True
    )
    is_on_leave = models.BooleanField(default=False)
    leave_start_date = models.DateField(null=True, blank=True)
    leave_end_date = models.DateField(null=True, blank=True)
    leave_reason = models.TextField(blank=True, null=True)
    
    # Training and Certification
    training_completed = models.JSONField(
        default=list,
        blank=True,
        help_text=_("List of completed training modules")
    )
    certifications = models.JSONField(
        default=list,
        blank=True,
        help_text=_("List of certifications with expiry dates")
    )
    last_training_date = models.DateField(null=True, blank=True)
    next_training_due = models.DateField(null=True, blank=True)
    
    # Performance
    performance_rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Performance rating from 0.00 to 5.00")
    )
    last_review_date = models.DateField(null=True, blank=True)
    next_review_date = models.DateField(null=True, blank=True)
    performance_notes = models.TextField(blank=True, null=True)
    
    # Audit trail
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invited_members"
    )
    invitation_sent_at = models.DateTimeField(null=True, blank=True, db_index=True)
    invitation_accepted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    invitation_expires_at = models.DateTimeField(null=True, blank=True)
    joined_at = models.DateTimeField(auto_now_add=True, db_index=True)
    last_accessed = models.DateTimeField(null=True, blank=True, db_index=True)
    
    # Termination tracking
    terminated_at = models.DateTimeField(null=True, blank=True)
    terminated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="terminated_memberships"
    )
    termination_reason = models.TextField(blank=True, null=True)
    eligible_for_rehire = models.BooleanField(default=True)
    
    # Badges and Recognition
    badges = models.JSONField(
        default=list,
        blank=True,
        help_text=_("List of badges earned")
    )
    years_of_service_awards = models.JSONField(
        default=list,
        blank=True,
        help_text=_("Years of service awards received")
    )
    
    # Notes
    notes = models.TextField(blank=True, null=True)
    special_skills = models.TextField(blank=True, null=True)
    languages_spoken = models.JSONField(default=list, blank=True)

    objects = HotelMemberManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["hotel", "user"],
                name="uniq_user_per_hotel"
            ),
            models.UniqueConstraint(
                fields=["employee_code"],
                condition=models.Q(employee_code__isnull=False),
                name="uniq_employee_code"
            ),
            models.CheckConstraint(
                condition=Q(invitation_accepted_at__isnull=True) | Q(invitation_accepted_at__gte=F('invitation_sent_at')),
                name="invitation_accepted_after_sent"
            ),
            models.CheckConstraint(
                condition=Q(contract_end_date__isnull=True) | Q(contract_end_date__gte=F('contract_start_date')),
                name="contract_end_after_start"
            ),
            models.CheckConstraint(
                condition=Q(leave_end_date__isnull=True) | Q(leave_end_date__gte=F('leave_start_date')),
                name="leave_end_after_start"
            ),
        ]
        indexes = [
            models.Index(fields=["hotel", "role", "is_active"], name="hotel_role_active_idx"),
            models.Index(fields=["user", "is_active"], name="user_active_idx"),
            models.Index(fields=["hotel", "last_accessed"], name="hotel_last_access_idx"),
            models.Index(fields=["role", "permission_level"], name="role_permission_idx"),
            models.Index(fields=["employee_code"], name="employee_code_idx"),
            models.Index(fields=["hire_date", "is_active"], name="hire_date_active_idx"),
            models.Index(fields=["hotel", "employment_type"], name="employment_type_idx"),
            models.Index(fields=["shift_preference"], name="shift_preference_idx"),
            models.Index(fields=["performance_rating"], name="performance_rating_idx"),
            models.Index(fields=["next_training_due"], name="training_due_idx"),
        ]
        ordering = ['hotel__name', 'role', 'user__email']
        verbose_name = _("Hotel Member")
        verbose_name_plural = _("Hotel Members")

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.email} @ {self.hotel.name} ({self.get_role_display()})"

    def clean(self):
        """Validate model data"""
        super().clean()
        
        # Ensure primary contact is unique per hotel
        if self.is_primary_contact:
            existing = HotelMember.objects.filter(
                hotel=self.hotel,
                is_primary_contact=True,
                is_active=True
            ).exclude(pk=self.pk)
            if existing.exists():
                raise ValidationError({
                    'is_primary_contact': _("This hotel already has a primary contact.")
                })
        
        # Validate invitation dates
        if self.invitation_accepted_at and self.invitation_sent_at:
            if self.invitation_accepted_at < self.invitation_sent_at:
                raise ValidationError({
                    'invitation_accepted_at': _("Invitation cannot be accepted before it was sent.")
                })
        
        # Check invitation expiry
        if self.invitation_expires_at and self.invitation_expires_at < timezone.now():
            if not self.invitation_accepted_at:
                raise ValidationError({
                    'invitation_expires_at': _("Cannot send invitation that has already expired.")
                })
        
        # Validate contract dates
        if self.contract_start_date and self.contract_end_date:
            if self.contract_end_date < self.contract_start_date:
                raise ValidationError({
                    'contract_end_date': _("Contract end date cannot be before start date.")
                })
        
        # Validate leave dates
        if self.is_on_leave and self.leave_start_date and self.leave_end_date:
            if self.leave_end_date < self.leave_start_date:
                raise ValidationError({
                    'leave_end_date': _("Leave end date cannot be before start date.")
                })
        
        # Validate performance rating range
        if self.performance_rating:
            if self.performance_rating < 0 or self.performance_rating > 5:
                raise ValidationError({
                    'performance_rating': _("Performance rating must be between 0 and 5.")
                })

    def save(self, *args, **kwargs):
        """Override save to perform additional actions"""
        self.full_clean()
        
        # Auto-set primary contact if first member
        if not HotelMember.objects.filter(hotel=self.hotel, is_active=True).exists():
            self.is_primary_contact = True
            self.role = self.Role.ADMIN
        
        # Auto-generate employee code if not provided
        if not self.employee_code and self.is_active:
            self.employee_code = self.generate_employee_code()
        
        super().save(*args, **kwargs)
        
        # Generate thumbnail after saving if profile picture exists
        if self.profile_picture and not self.profile_picture_thumbnail:
            self.generate_thumbnail()

    def generate_employee_code(self):
        """Generate a unique employee code"""
        hotel_code = self.hotel.code if hasattr(self.hotel, 'code') else str(self.hotel.id)[:4]
        year = timezone.now().year
        count = HotelMember.objects.filter(hotel=self.hotel).count() + 1
        return f"{hotel_code}-{year}-{count:04d}"

    def generate_thumbnail(self):
        """Generate thumbnail from profile picture"""
        from PIL import Image
        from io import BytesIO
        from django.core.files.base import ContentFile
        import os
        
        if not self.profile_picture:
            return
        
        try:
            img = Image.open(self.profile_picture.path)
            img.thumbnail((150, 150), Image.Resampling.LANCZOS)
            
            thumb_io = BytesIO()
            img_format = os.path.splitext(self.profile_picture.name)[1].lower()
            
            if img_format in ['.jpg', '.jpeg']:
                img.save(thumb_io, 'JPEG', quality=85)
            elif img_format == '.png':
                img.save(thumb_io, 'PNG')
            else:
                img.save(thumb_io, 'JPEG', quality=85)
            
            thumb_filename = f"thumb_{self.profile_picture.name}"
            self.profile_picture_thumbnail.save(
                thumb_filename,
                ContentFile(thumb_io.getvalue()),
                save=False
            )
            self.save(update_fields=['profile_picture_thumbnail'])
        except Exception as e:
            logger.error(f"Failed to generate thumbnail for {self}: {e}")

    def accept_invitation(self):
        """Mark invitation as accepted"""
        if self.invitation_expires_at and self.invitation_expires_at < timezone.now():
            raise ValidationError(_("This invitation has expired."))
        
        self.invitation_accepted_at = timezone.now()
        self.is_active = True
        self.save(update_fields=['invitation_accepted_at', 'is_active'])
        logger.info(f"Invitation accepted: {self.user.email} for hotel {self.hotel.name}")

    def update_last_accessed(self):
        """Update last accessed timestamp"""
        self.last_accessed = timezone.now()
        self.save(update_fields=['last_accessed'])

    def terminate(self, terminated_by, reason=None, eligible_for_rehire=True):
        """Terminate a hotel membership"""
        self.is_active = False
        self.terminated_at = timezone.now()
        self.terminated_by = terminated_by
        self.termination_reason = reason
        self.eligible_for_rehire = eligible_for_rehire
        self.is_on_leave = False
        self.save(update_fields=[
            'is_active', 'terminated_at', 'terminated_by', 
            'termination_reason', 'eligible_for_rehire', 'is_on_leave'
        ])
        logger.info(f"Membership terminated: {self.user.email} from {self.hotel.name} by {terminated_by.email}")

    def resend_invitation(self, invited_by):
        """Resend invitation email"""
        self.invitation_sent_at = timezone.now()
        self.invited_by = invited_by
        self.invitation_expires_at = timezone.now() + timezone.timedelta(days=7)
        self.save(update_fields=['invitation_sent_at', 'invited_by', 'invitation_expires_at'])

    def start_leave(self, start_date, end_date, reason):
        """Start leave period"""
        self.is_on_leave = True
        self.leave_start_date = start_date
        self.leave_end_date = end_date
        self.leave_reason = reason
        self.save(update_fields=['is_on_leave', 'leave_start_date', 'leave_end_date', 'leave_reason'])
        logger.info(f"Leave started for {self.user.email} from {start_date} to {end_date}")

    def end_leave(self):
        """End leave period"""
        self.is_on_leave = False
        self.leave_start_date = None
        self.leave_end_date = None
        self.save(update_fields=['is_on_leave', 'leave_start_date', 'leave_end_date'])
        logger.info(f"Leave ended for {self.user.email}")

    def add_certification(self, name, issued_date, expiry_date=None, issuing_authority=""):
        """Add a certification"""
        certification = {
            'name': name,
            'issued_date': issued_date.isoformat() if issued_date else None,
            'expiry_date': expiry_date.isoformat() if expiry_date else None,
            'issuing_authority': issuing_authority
        }
        certifications = self.certifications or []
        certifications.append(certification)
        self.certifications = certifications
        self.save(update_fields=['certifications'])

    def update_performance_rating(self, rating, review_date=None, notes=None):
        """Update performance rating"""
        self.performance_rating = rating
        self.last_review_date = review_date or timezone.now().date()
        if notes:
            self.performance_notes = notes
        self.save(update_fields=['performance_rating', 'last_review_date', 'performance_notes'])

    @property
    def is_management(self):
        """Check if member has management role"""
        management_roles = {
            self.Role.ADMIN,
            self.Role.GENERAL_MANAGER,
            self.Role.OPERATIONS_MANAGER,
            self.Role.FRONT_DESK_MANAGER,
            self.Role.HOUSEKEEPING_MANAGER,
            self.Role.RESTAURANT_MANAGER,
        }
        return self.role in management_roles

    @property
    def has_full_access(self):
        """Check if member has full access permissions"""
        return self.permission_level == self.PermissionLevel.FULL

    @property
    def can_manage_team(self):
        """Check if member can manage other team members"""
        return self.role in [self.Role.ADMIN, self.Role.GENERAL_MANAGER, self.Role.OPERATIONS_MANAGER]

    @property
    def is_invitation_pending(self):
        """Check if invitation is still pending"""
        return not self.invitation_accepted_at and self.invitation_sent_at and not self.is_active

    @property
    def contract_status(self):
        """Get contract status"""
        if not self.contract_start_date:
            return "no_contract"
        if self.contract_end_date and self.contract_end_date < timezone.now().date():
            return "expired"
        if self.contract_start_date > timezone.now().date():
            return "future"
        return "active"

    @property
    def is_on_probation(self):
        """Check if member is still on probation"""
        if self.probation_end_date:
            return timezone.now().date() < self.probation_end_date
        return False

    @property
    def years_of_service(self):
        """Calculate years of service"""
        if self.hire_date:
            today = timezone.now().date()
            years = today.year - self.hire_date.year
            if (today.month, today.day) < (self.hire_date.month, self.hire_date.day):
                years -= 1
            return years
        return 0


class UserActivityLogManager(models.Manager):
    """Custom manager for UserActivityLog"""
    
    def for_user(self, user, days=30):
        """Get recent activities for a user"""
        cutoff = timezone.now() - timezone.timedelta(days=days)
        return self.filter(user=user, created_at__gte=cutoff)
    
    def for_hotel(self, hotel, days=30):
        """Get recent activities for a hotel"""
        cutoff = timezone.now() - timezone.timedelta(days=days)
        return self.filter(hotel=hotel, created_at__gte=cutoff)
    
    def log_action(self, user, action, **kwargs):
        """Helper method to log user actions"""
        return self.create(user=user, action=action, **kwargs)


class UserActivityLog(models.Model):
    """Track user activities across the system with enhanced tracking"""
    
    class Action(models.TextChoices):
        LOGIN = "login", _("Login")
        LOGOUT = "logout", _("Logout")
        LOGIN_FAILED = "login_failed", _("Login Failed")
        CREATE = "create", _("Create")
        UPDATE = "update", _("Update")
        DELETE = "delete", _("Delete")
        VIEW = "view", _("View")
        EXPORT = "export", _("Export")
        PRINT = "print", _("Print")
        DOWNLOAD = "download", _("Download")
        UPLOAD = "upload", _("Upload")
        SHARE = "share", _("Share")
        PERMISSION_CHANGE = "permission_change", _("Permission Change")

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
        blank=True,
        db_index=True
    )
    action = models.CharField(max_length=20, choices=Action.choices, db_index=True)
    
    # Object tracking
    content_type = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    object_id = models.CharField(max_length=50, blank=True, null=True, db_index=True)
    object_repr = models.CharField(max_length=200, blank=True, null=True)
    
    # Additional context
    description = models.TextField(blank=True, null=True)
    changes = models.JSONField(default=dict, blank=True, help_text=_("Stores before/after state for updates"))
    
    # Request metadata
    ip_address = models.GenericIPAddressField(blank=True, null=True, db_index=True)
    user_agent = models.TextField(blank=True, null=True)
    request_method = models.CharField(max_length=10, blank=True, null=True)
    request_path = models.CharField(max_length=500, blank=True, null=True)
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    
    # Performance tracking
    duration_ms = models.PositiveIntegerField(null=True, blank=True, help_text=_("Request duration in milliseconds"))
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = UserActivityLogManager()

    class Meta:
        indexes = [
            models.Index(fields=['user', '-created_at'], name='user_activity_idx'),
            models.Index(fields=['hotel', '-created_at'], name='hotel_activity_idx'),
            models.Index(fields=['action', 'created_at'], name='action_date_idx'),
            models.Index(fields=['content_type', 'object_id'], name='object_tracking_idx'),
            models.Index(fields=['ip_address', 'created_at'], name='ip_date_idx'),
            models.Index(fields=['-created_at'], name='recent_activity_idx'),
        ]
        ordering = ['-created_at']
        verbose_name = _("User Activity Log")
        verbose_name_plural = _("User Activity Logs")

    def __str__(self):
        return f"{self.user} - {self.get_action_display()} at {self.created_at.strftime('%Y-%m-%d %H:%M:%S')}"

    @classmethod
    def log(cls, user, action, **kwargs):
        """Convenience method to create a log entry"""
        return cls.objects.log_action(user, action, **kwargs)