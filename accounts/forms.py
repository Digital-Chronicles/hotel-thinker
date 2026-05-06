# accounts/forms.py

from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.crypto import get_random_string

from .models import Profile, HotelMember

import logging

logger = logging.getLogger(__name__)

User = get_user_model()

# CSS Classes (unchanged)
BASE_INPUT = "w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
BASE_SELECT = "w-full rounded-lg border border-gray-300 bg-white px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
BASE_TEXTAREA = "w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
BASE_FILE_INPUT = "w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500 file:mr-4 file:rounded-lg file:border-0 file:bg-indigo-50 file:px-4 file:py-2 file:text-indigo-700 hover:file:bg-indigo-100"


class ProfileForm(forms.ModelForm):
    """Form for updating user profile information"""
    
    confirm_email = forms.EmailField(
        required=False,
        label=_("Confirm Email"),
        widget=forms.EmailInput(attrs={"placeholder": _("Confirm your email address"), "class": BASE_INPUT})
    )
    
    class Meta:
        model = Profile
        fields = [
            "phone",
            "alternative_phone",
            "gender",
            "date_of_birth",
            "job_title",
            "department",
            "employee_id",
            "address_line1",
            "address_line2",
            "city",
            "state",
            "postal_code",
            "country",
            "language",
            "timezone",
            "notification_email",
            "notification_sms",
            "notification_push",
            "notification_digest",
            "avatar",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date", "class": BASE_INPUT}),
            "avatar": forms.ClearableFileInput(attrs={"class": BASE_FILE_INPUT}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if self.user and self.user.email:
            self.fields['confirm_email'].initial = self.user.email
            self.fields['confirm_email'].required = True
        
        self._apply_widget_classes()
        self._add_placeholders()
    
    def _apply_widget_classes(self):
        """Apply consistent Tailwind classes to all widgets"""
        for name, field in self.fields.items():
            widget = field.widget
            if widget.attrs.get('class') and name != 'avatar':
                continue
            
            if isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("class", BASE_TEXTAREA)
                widget.attrs.setdefault("rows", 3)
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", BASE_SELECT)
            elif isinstance(widget, (forms.TextInput, forms.EmailInput, forms.NumberInput, forms.DateInput)):
                widget.attrs.setdefault("class", BASE_INPUT)
            elif isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500")
            elif isinstance(widget, forms.ClearableFileInput):
                widget.attrs.setdefault("class", BASE_FILE_INPUT)
    
    def _add_placeholders(self):
        """Add helpful placeholders"""
        placeholders = {
            "phone": _("+2567XXXXXXXX"),
            "alternative_phone": _("+2567XXXXXXXX"),
            "employee_id": _("EMP-XXXXXX"),
            "postal_code": _("e.g., 12345"),
        }
        for field_name, placeholder in placeholders.items():
            if field_name in self.fields:
                widget = self.fields[field_name].widget
                if not widget.attrs.get("placeholder"):
                    widget.attrs["placeholder"] = placeholder
    
    def clean_confirm_email(self):
        """Validate email confirmation"""
        confirm_email = self.cleaned_data.get('confirm_email')
        
        if self.user and self.user.email and confirm_email:
            if self.user.email != confirm_email:
                raise ValidationError(_("Email addresses do not match."))
        
        return confirm_email
    
    def clean_date_of_birth(self):
        """Validate date of birth is not in the future"""
        date_of_birth = self.cleaned_data.get('date_of_birth')
        if date_of_birth and date_of_birth > timezone.now().date():
            raise ValidationError(_("Date of birth cannot be in the future."))
        return date_of_birth
    
    def clean_employee_id(self):
        """Validate employee ID uniqueness"""
        employee_id = self.cleaned_data.get('employee_id')
        if employee_id:
            existing = Profile.objects.exclude(pk=self.instance.pk).filter(employee_id=employee_id)
            if existing.exists():
                raise ValidationError(_("This employee ID is already in use."))
        return employee_id
    
    def save(self, commit=True):
        """Save the profile and update user email if changed"""
        profile = super().save(commit=False)
        
        if commit:
            profile.save()
            if self.user and self.cleaned_data.get('confirm_email'):
                new_email = self.cleaned_data.get('confirm_email')
                if self.user.email != new_email:
                    self.user.email = new_email
                    self.user.save(update_fields=['email'])
        
        return profile


class BaseHotelMemberForm(forms.ModelForm):
    """Base form for hotel member operations with user creation logic"""
    
    email = forms.EmailField(
        label=_("Email Address"),
        widget=forms.EmailInput(attrs={"class": BASE_INPUT, "placeholder": _("user@example.com")})
    )
    first_name = forms.CharField(
        label=_("First Name"),
        max_length=150,
        widget=forms.TextInput(attrs={"class": BASE_INPUT})
    )
    last_name = forms.CharField(
        label=_("Last Name"),
        max_length=150,
        widget=forms.TextInput(attrs={"class": BASE_INPUT})
    )
    
    class Meta:
        model = HotelMember
        fields = [
            "role",
            "permission_level",
            "employment_type",
            "shift_preference",
            "hire_date",
            "work_phone",
            "work_email",
            "can_manage_bookings",
            "can_manage_rooms",
            "can_manage_inventory",
            "can_manage_staff",
            "can_view_financials",
            "can_manage_reports",
            "notes",
        ]
        widgets = {
            "hire_date": forms.DateInput(attrs={"type": "date", "class": BASE_INPUT}),
            "notes": forms.Textarea(attrs={"rows": 3, "class": BASE_TEXTAREA}),
            "role": forms.Select(attrs={"class": BASE_SELECT}),
            "permission_level": forms.Select(attrs={"class": BASE_SELECT}),
            "employment_type": forms.Select(attrs={"class": BASE_SELECT}),
            "shift_preference": forms.Select(attrs={"class": BASE_SELECT}),
        }
    
    def __init__(self, *args, **kwargs):
        self.hotel = kwargs.pop('hotel', None)
        self.created_by = kwargs.pop('created_by', None)  # Current user adding the member
        super().__init__(*args, **kwargs)
        
        # Make required fields
        self.fields['email'].required = True
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True
        self.fields['role'].required = True
        
        # Set default role
        if not self.instance.role:
            self.fields['role'].initial = HotelMember.Role.VIEWER
        
        self._apply_widget_classes()
        self._add_placeholders()
    
    def _apply_widget_classes(self):
        """Apply consistent Tailwind classes to all widgets"""
        for name, field in self.fields.items():
            if name in ['email', 'first_name', 'last_name']:
                continue  # Already have classes applied
            
            widget = field.widget
            if widget.attrs.get('class'):
                continue
            
            if isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("class", BASE_TEXTAREA)
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", BASE_SELECT)
            elif isinstance(widget, (forms.TextInput, forms.EmailInput, forms.DateInput)):
                widget.attrs.setdefault("class", BASE_INPUT)
            elif isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500")
    
    def _add_placeholders(self):
        """Add helpful placeholders"""
        placeholders = {
            "work_phone": _("+2567XXXXXXXX"),
            "hourly_rate": _("0.00"),
            "salary": _("0.00"),
            "performance_rating": _("0.00 - 5.00"),
            "max_weekly_hours": _("40"),
        }
        for field_name, placeholder in placeholders.items():
            if field_name in self.fields:
                widget = self.fields[field_name].widget
                if not widget.attrs.get("placeholder"):
                    widget.attrs["placeholder"] = placeholder
                    
                    # Add extra attributes for numeric fields
                    if field_name == "performance_rating":
                        widget.attrs["step"] = "0.01"
                        widget.attrs["min"] = "0"
                        widget.attrs["max"] = "5"
    
    def clean_email(self):
        """Validate email and check if user already exists in this hotel"""
        email = self.cleaned_data.get('email', '').lower()
        
        # Validate email format
        try:
            validate_email(email)
        except ValidationError:
            raise ValidationError(_("Enter a valid email address."))
        
        # Check if user is already a member of this hotel
        if self.hotel:
            existing_member = HotelMember.objects.filter(
                hotel=self.hotel,
                user__email=email
            ).exclude(pk=self.instance.pk)
            
            if existing_member.exists():
                raise ValidationError(
                    _("A user with this email is already a member of this hotel.")
                )
        
        return email
    
    def _get_or_create_user(self):
        """Get existing user or create a new one"""
        email = self.cleaned_data['email'].lower()
        first_name = self.cleaned_data['first_name'].strip()
        last_name = self.cleaned_data['last_name'].strip()
        
        # Check if user exists
        try:
            user = User.objects.get(email=email)
            created = False
            logger.info(f"Existing user found: {email}")
        except User.DoesNotExist:
            # Create new user
            username = email  # Use email as username
            password = get_random_string(12)
            
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
            )
            created = True
            logger.info(f"New user created: {email}")
            
            # Store password for email notification
            self._generated_password = password
        
        # Update user details if they changed (for existing users)
        if not created:
            updated = False
            if user.first_name != first_name:
                user.first_name = first_name
                updated = True
            if user.last_name != last_name:
                user.last_name = last_name
                updated = True
            if updated:
                user.save(update_fields=['first_name', 'last_name'])
                logger.info(f"Updated user details for: {email}")
        
        return user, created
    
    @transaction.atomic
    def save(self, commit=True):
        """Save the hotel member with automatic user creation"""
        member = super().save(commit=False)
        
        # Create or get user
        user, user_created = self._get_or_create_user()
        member.user = user
        
        # Set hotel
        if self.hotel:
            member.hotel = self.hotel
        
        # Set invitation/creation metadata
        if not member.pk:  # New member
            member.joined_at = timezone.now()
            member.is_active = True  # Directly active for current flow
            member.invitation_accepted_at = timezone.now()
            
            if self.created_by:
                member.invited_by = self.created_by
        
        # Set default employee code if not provided
        if not member.employee_code:
            member.employee_code = self._generate_employee_code()
        
        if commit:
            member.save()
            self.save_m2m()
            
            # Create profile if user was newly created and doesn't have one
            if user_created:
                Profile.objects.get_or_create(user=user)
        
        # Store creation info for email sending
        member._user_created = user_created
        if hasattr(self, '_generated_password'):
            member._generated_password = self._generated_password
        
        return member
    
    def _generate_employee_code(self):
        """Generate a unique employee code"""
        if not self.hotel:
            return None
        
        hotel_code = getattr(self.hotel, 'code', str(self.hotel.id)[:4])
        year = timezone.now().year
        count = HotelMember.objects.filter(hotel=self.hotel).count() + 1
        return f"{hotel_code}-{year}-{count:04d}"


class HotelMemberAddForm(BaseHotelMemberForm):
    """Form for adding a new member to a hotel (creates user account if needed)"""
    
    send_welcome_email = forms.BooleanField(
        label=_("Send welcome email with login details"),
        initial=True,
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"})
    )
    
    class Meta(BaseHotelMemberForm.Meta):
        fields = BaseHotelMemberForm.Meta.fields + ['send_welcome_email']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add help text about user creation
        self.fields['email'].help_text = _(
            "If a user with this email doesn't exist, an account will be automatically created."
        )
    
    def clean(self):
        """Cross-field validation"""
        cleaned_data = super().clean()
        
        # Validate leave dates if on leave
        is_on_leave = cleaned_data.get('is_on_leave')
        leave_start = cleaned_data.get('leave_start_date')
        leave_end = cleaned_data.get('leave_end_date')
        
        if is_on_leave and (not leave_start or not leave_end):
            self.add_error('leave_start_date', _("Both start and end dates are required when on leave."))
        
        # Validate contract dates
        contract_start = cleaned_data.get('contract_start_date')
        contract_end = cleaned_data.get('contract_end_date')
        
        if contract_start and contract_end and contract_end < contract_start:
            self.add_error('contract_end_date', _("Contract end date cannot be before start date."))
        
        return cleaned_data


class HotelMemberInviteForm(BaseHotelMemberForm):
    """Form for inviting a new member (sends invitation email)"""
    
    send_invitation_email = forms.BooleanField(
        label=_("Send invitation email"),
        initial=True,
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"})
    )
    
    class Meta(BaseHotelMemberForm.Meta):
        fields = BaseHotelMemberForm.Meta.fields + ['send_invitation_email']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Override to make member inactive until invitation is accepted
        self.fields['email'].help_text = _(
            "An invitation email will be sent to this address. The user will need to accept the invitation to join."
        )
    
    @transaction.atomic
    def save(self, commit=True):
        """Save as pending invitation (inactive until accepted)"""
        member = super().save(commit=False)
        
        # Override: member is inactive until invitation accepted
        member.is_active = False
        member.invitation_sent_at = timezone.now()
        member.invitation_expires_at = timezone.now() + timezone.timedelta(days=7)
        member.invitation_accepted_at = None
        
        if commit:
            member.save()
            self.save_m2m()
        
        return member


class HotelMemberBulkAddForm(forms.Form):
    """Form for bulk adding multiple members"""
    
    members_data = forms.CharField(
        label=_("Members Data"),
        widget=forms.Textarea(attrs={
            "class": BASE_TEXTAREA,
            "rows": 8,
            "placeholder": _(
                "Enter one member per line with comma-separated values:\n\n"
                "email,first_name,last_name,role\n"
                "john@example.com,John,Doe,front_desk\n"
                "jane@example.com,Jane,Smith,housekeeper"
            )
        }),
        help_text=_(
            "Format: email, first_name, last_name, role\n"
            "Roles: admin, general_manager, front_desk, housekeeper, server, viewer, etc."
        )
    )
    default_role = forms.ChoiceField(
        choices=HotelMember.Role.choices,
        required=False,
        initial=HotelMember.Role.VIEWER,
        widget=forms.Select(attrs={"class": BASE_SELECT}),
        help_text=_("Default role for members without a specified role")
    )
    send_welcome_emails = forms.BooleanField(
        label=_("Send welcome emails"),
        initial=True,
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"})
    )
    
    def __init__(self, *args, **kwargs):
        self.hotel = kwargs.pop('hotel', None)
        self.created_by = kwargs.pop('created_by', None)
        super().__init__(*args, **kwargs)
        
        # Apply classes
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", field.widget.attrs.get("class", BASE_SELECT if isinstance(field.widget, forms.Select) else BASE_INPUT))
    
    def clean_members_data(self):
        """Parse and validate bulk members data"""
        data = self.cleaned_data.get('members_data', '')
        lines = [line.strip() for line in data.split('\n') if line.strip()]
        
        if not lines:
            raise ValidationError(_("Please provide at least one member."))
        
        members = []
        errors = []
        
        role_map = {role.value: role.value for role in HotelMember.Role}
        
        for line_num, line in enumerate(lines, 1):
            parts = [p.strip() for p in line.split(',')]
            
            if len(parts) < 3:
                errors.append(_(f"Line {line_num}: Need at least email, first_name, last_name"))
                continue
            
            email = parts[0].lower()
            first_name = parts[1]
            last_name = parts[2]
            role = parts[3] if len(parts) > 3 else self.cleaned_data.get('default_role', HotelMember.Role.VIEWER)
            
            # Validate email
            try:
                validate_email(email)
            except ValidationError:
                errors.append(_(f"Line {line_num}: Invalid email address '{email}'"))
                continue
            
            # Validate role
            if role not in role_map:
                errors.append(_(f"Line {line_num}: Invalid role '{role}'. Valid roles: {', '.join(role_map.keys())}"))
                continue
            
            # Check if already a member
            if self.hotel and HotelMember.objects.filter(hotel=self.hotel, user__email=email).exists():
                errors.append(_(f"Line {line_num}: User '{email}' is already a member of this hotel"))
                continue
            
            members.append({
                'email': email,
                'first_name': first_name,
                'last_name': last_name,
                'role': role,
                'line_num': line_num,
            })
        
        if errors:
            raise ValidationError('\n'.join(errors))
        
        return members
    
    @transaction.atomic
    def save(self):
        """Process bulk add of members"""
        members_data = self.cleaned_data['members_data']
        send_welcome = self.cleaned_data['send_welcome_emails']
        members = self.cleaned_data['members_data']  # Already parsed in clean
        
        created_members = []
        errors = []
        
        for member_data in members:
            try:
                # Create or get user
                user, created = User.objects.get_or_create(
                    email=member_data['email'],
                    defaults={
                        'username': member_data['email'],
                        'first_name': member_data['first_name'],
                        'last_name': member_data['last_name'],
                    }
                )
                
                if not created:
                    # Update existing user's name
                    user.first_name = member_data['first_name']
                    user.last_name = member_data['last_name']
                    user.save(update_fields=['first_name', 'last_name'])
                
                # Create profile if needed
                Profile.objects.get_or_create(user=user)
                
                # Create hotel member
                hotel_member = HotelMember.objects.create(
                    hotel=self.hotel,
                    user=user,
                    role=member_data['role'],
                    is_active=True,
                    joined_at=timezone.now(),
                    invited_by=self.created_by,
                    invitation_accepted_at=timezone.now(),
                )
                
                created_members.append(hotel_member)
                
                # Generate password for new users
                if created:
                    password = get_random_string(12)
                    user.set_password(password)
                    user.save()
                    hotel_member._generated_password = password
                
            except Exception as e:
                errors.append(_(f"Error adding {member_data['email']}: {str(e)}"))
                logger.error(f"Bulk add error for {member_data['email']}: {e}")
        
        if errors:
            raise ValidationError('\n'.join(errors))
        
        return created_members


class HotelMemberEditForm(forms.ModelForm):
    """Form for editing existing hotel member details"""
    
    class Meta:
        model = HotelMember
        fields = [
            "role",
            "permission_level",
            "employment_type",
            "shift_preference",
            "default_shift_start",
            "default_shift_end",
            "max_weekly_hours",
            "overtime_allowed",
            "work_phone",
            "work_email",
            "emergency_contact_name",
            "emergency_contact_phone",
            "emergency_contact_relationship",
            "hire_date",
            "contract_start_date",
            "contract_end_date",
            "probation_end_date",
            "hourly_rate",
            "salary",
            "currency",
            "can_manage_bookings",
            "can_manage_rooms",
            "can_manage_inventory",
            "can_manage_staff",
            "can_view_financials",
            "can_manage_reports",
            "can_manage_settings",
            "is_primary_contact",
            "is_on_leave",
            "leave_start_date",
            "leave_end_date",
            "leave_reason",
            "performance_rating",
            "performance_notes",
            "notes",
            "special_skills",
            "languages_spoken",
        ]
        widgets = {
            "default_shift_start": forms.TimeInput(attrs={"type": "time", "class": BASE_INPUT}),
            "default_shift_end": forms.TimeInput(attrs={"type": "time", "class": BASE_INPUT}),
            "hire_date": forms.DateInput(attrs={"type": "date", "class": BASE_INPUT}),
            "contract_start_date": forms.DateInput(attrs={"type": "date", "class": BASE_INPUT}),
            "contract_end_date": forms.DateInput(attrs={"type": "date", "class": BASE_INPUT}),
            "probation_end_date": forms.DateInput(attrs={"type": "date", "class": BASE_INPUT}),
            "leave_start_date": forms.DateInput(attrs={"type": "date", "class": BASE_INPUT}),
            "leave_end_date": forms.DateInput(attrs={"type": "date", "class": BASE_INPUT}),
            "notes": forms.Textarea(attrs={"rows": 3, "class": BASE_TEXTAREA}),
            "performance_notes": forms.Textarea(attrs={"rows": 2, "class": BASE_TEXTAREA}),
            "special_skills": forms.Textarea(attrs={"rows": 2, "class": BASE_TEXTAREA}),
            "leave_reason": forms.Textarea(attrs={"rows": 2, "class": BASE_TEXTAREA}),
            "role": forms.Select(attrs={"class": BASE_SELECT}),
            "permission_level": forms.Select(attrs={"class": BASE_SELECT}),
            "employment_type": forms.Select(attrs={"class": BASE_SELECT}),
            "shift_preference": forms.Select(attrs={"class": BASE_SELECT}),
            "currency": forms.Select(attrs={"class": BASE_SELECT}),
            "languages_spoken": forms.SelectMultiple(attrs={"class": BASE_SELECT}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Make employee code read-only
        if self.instance and self.instance.employee_code:
            self.fields['employee_code'] = forms.CharField(
                initial=self.instance.employee_code,
                disabled=True,
                required=False,
                widget=forms.TextInput(attrs={"class": BASE_INPUT, "readonly": True}),
                label=_("Employee Code")
            )
        
        # Set language choices
        if 'languages_spoken' in self.fields:
            self.fields['languages_spoken'].choices = Profile.Language.choices
        
        # Set currency choices
        self.fields['currency'].choices = [
            ('USD', _('USD - US Dollar')),
            ('EUR', _('EUR - Euro')),
            ('GBP', _('GBP - British Pound')),
            ('UGX', _('UGX - Ugandan Shilling')),
            ('KES', _('KES - Kenyan Shilling')),
            ('TZS', _('TZS - Tanzanian Shilling')),
            ('RWF', _('RWF - Rwandan Franc')),
        ]
        
        self._apply_widget_classes()
    
    def _apply_widget_classes(self):
        """Apply consistent Tailwind classes"""
        for name, field in self.fields.items():
            if name == 'employee_code':
                continue
            
            widget = field.widget
            if widget.attrs.get('class'):
                continue
            
            if isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("class", BASE_TEXTAREA)
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", BASE_SELECT)
            elif isinstance(widget, forms.SelectMultiple):
                widget.attrs.setdefault("class", BASE_SELECT)
            elif isinstance(widget, (forms.TextInput, forms.EmailInput, forms.NumberInput, forms.DateInput, forms.TimeInput)):
                widget.attrs.setdefault("class", BASE_INPUT)
            elif isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500")
    
    def clean(self):
        """Cross-field validation"""
        cleaned_data = super().clean()
        
        # Contract dates validation
        contract_start = cleaned_data.get('contract_start_date')
        contract_end = cleaned_data.get('contract_end_date')
        if contract_start and contract_end and contract_end < contract_start:
            self.add_error('contract_end_date', _("Contract end date cannot be before start date."))
        
        # Leave dates validation
        is_on_leave = cleaned_data.get('is_on_leave')
        leave_start = cleaned_data.get('leave_start_date')
        leave_end = cleaned_data.get('leave_end_date')
        
        if is_on_leave:
            if not leave_start or not leave_end:
                self.add_error('leave_start_date', _("Both start and end dates are required when on leave."))
            elif leave_end < leave_start:
                self.add_error('leave_end_date', _("Leave end date cannot be before start date."))
        
        # Probation validation
        probation_end = cleaned_data.get('probation_end_date')
        hire_date = cleaned_data.get('hire_date')
        if probation_end and hire_date and probation_end < hire_date:
            self.add_error('probation_end_date', _("Probation end date cannot be before hire date."))
        
        # Shift times validation
        shift_start = cleaned_data.get('default_shift_start')
        shift_end = cleaned_data.get('default_shift_end')
        if shift_start and shift_end and shift_end <= shift_start:
            self.add_error('default_shift_end', _("Shift end time must be after shift start time."))
        
        # Performance rating validation
        performance_rating = cleaned_data.get('performance_rating')
        if performance_rating and (performance_rating < 0 or performance_rating > 5):
            self.add_error('performance_rating', _("Performance rating must be between 0 and 5."))
        
        # Primary contact uniqueness
        is_primary_contact = cleaned_data.get('is_primary_contact')
        if is_primary_contact and self.instance.hotel:
            existing = HotelMember.objects.filter(
                hotel=self.instance.hotel,
                is_primary_contact=True,
                is_active=True
            ).exclude(pk=self.instance.pk)
            if existing.exists():
                self.add_error('is_primary_contact', _("This hotel already has a primary contact."))
        
        return cleaned_data


class ProfilePreferencesForm(forms.ModelForm):
    """Form for updating user notification preferences only"""
    
    class Meta:
        model = Profile
        fields = [
            "language",
            "timezone",
            "notification_email",
            "notification_sms",
            "notification_push",
            "notification_digest",
        ]
        widgets = {
            "language": forms.Select(attrs={"class": BASE_SELECT}),
            "timezone": forms.Select(attrs={"class": BASE_SELECT}),
            "notification_email": forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"}),
            "notification_sms": forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"}),
            "notification_push": forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"}),
            "notification_digest": forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", BASE_SELECT if isinstance(field.widget, forms.Select) else BASE_INPUT)


class HotelMemberPermissionForm(forms.ModelForm):
    """Form for updating member permissions only"""
    
    class Meta:
        model = HotelMember
        fields = [
            "role",
            "permission_level",
            "can_manage_bookings",
            "can_manage_rooms",
            "can_manage_inventory",
            "can_manage_staff",
            "can_view_financials",
            "can_manage_reports",
            "can_manage_settings",
        ]
        widgets = {
            "role": forms.Select(attrs={"class": BASE_SELECT}),
            "permission_level": forms.Select(attrs={"class": BASE_SELECT}),
            "can_manage_bookings": forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"}),
            "can_manage_rooms": forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"}),
            "can_manage_inventory": forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"}),
            "can_manage_staff": forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"}),
            "can_view_financials": forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"}),
            "can_manage_reports": forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"}),
            "can_manage_settings": forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", BASE_SELECT)


class HotelMemberQuickAddForm(forms.Form):
    """Simple form for quickly adding a member with minimal info"""
    
    email = forms.EmailField(
        label=_("Email Address"),
        widget=forms.EmailInput(attrs={"class": BASE_INPUT, "placeholder": _("user@example.com")})
    )
    role = forms.ChoiceField(
        choices=HotelMember.Role.choices,
        initial=HotelMember.Role.VIEWER,
        widget=forms.Select(attrs={"class": BASE_SELECT})
    )
    send_welcome = forms.BooleanField(
        label=_("Send welcome email"),
        initial=True,
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"})
    )
    
    def __init__(self, *args, **kwargs):
        self.hotel = kwargs.pop('hotel', None)
        self.created_by = kwargs.pop('created_by', None)
        super().__init__(*args, **kwargs)
    
    def clean_email(self):
        """Validate email and check existing membership"""
        email = self.cleaned_data.get('email', '').lower()
        
        try:
            validate_email(email)
        except ValidationError:
            raise ValidationError(_("Enter a valid email address."))
        
        if self.hotel and HotelMember.objects.filter(hotel=self.hotel, user__email=email).exists():
            raise ValidationError(_("This user is already a member of the hotel."))
        
        return email
    
    @transaction.atomic
    def save(self):
        """Create user and member with minimal info"""
        email = self.cleaned_data['email'].lower()
        role = self.cleaned_data['role']
        
        # Create or get user
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'username': email,
            }
        )
        
        if created:
            # Generate random password for new user
            password = get_random_string(12)
            user.set_password(password)
            user.save()
            Profile.objects.create(user=user)
            user._generated_password = password
        
        # Create hotel member
        hotel_member = HotelMember.objects.create(
            hotel=self.hotel,
            user=user,
            role=role,
            is_active=True,
            joined_at=timezone.now(),
            invited_by=self.created_by,
            invitation_accepted_at=timezone.now(),
        )
        
        if created and hasattr(user, '_generated_password'):
            hotel_member._generated_password = user._generated_password
        
        return hotel_member