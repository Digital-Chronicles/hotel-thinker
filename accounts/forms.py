# accounts/forms.py

from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import Profile, HotelMember


BASE_INPUT = "w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
BASE_SELECT = "w-full rounded-lg border border-gray-300 bg-white px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
BASE_TEXTAREA = "w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
BASE_FILE_INPUT = "w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500 file:mr-4 file:rounded-lg file:border-0 file:bg-indigo-50 file:px-4 file:py-2 file:text-indigo-700 hover:file:bg-indigo-100"


class ProfileForm(forms.ModelForm):
    """Form for updating user profile information"""
    
    confirm_email = forms.EmailField(
        required=False,
        label=_("Confirm Email"),
        widget=forms.EmailInput(attrs={"placeholder": _("Confirm your email address")})
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
        
        # Add confirm_email field for email verification if user exists
        if self.user and self.user.email:
            self.fields['confirm_email'].initial = self.user.email
            self.fields['confirm_email'].required = True
        
        # Apply consistent Tailwind classes
        for name, field in self.fields.items():
            widget = field.widget
            
            # Skip if widget already has custom classes
            if widget.attrs.get('class') and name != 'avatar':
                continue
            
            # Add appropriate classes based on widget type
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
            
            # Add helpful placeholders
            if name == "phone" and not widget.attrs.get("placeholder"):
                widget.attrs["placeholder"] = _("+2567XXXXXXXX")
            elif name == "alternative_phone" and not widget.attrs.get("placeholder"):
                widget.attrs["placeholder"] = _("+2567XXXXXXXX")
            elif name == "employee_id" and not widget.attrs.get("placeholder"):
                widget.attrs["placeholder"] = _("EMP-XXXXXX")
            elif name == "postal_code" and not widget.attrs.get("placeholder"):
                widget.attrs["placeholder"] = _("e.g., 12345")
    
    def clean_confirm_email(self):
        """Validate email confirmation"""
        email = self.cleaned_data.get('email') if hasattr(self, 'cleaned_data') else None
        
        # Get email from user if not in cleaned_data
        if not email and self.user:
            email = self.user.email
        
        confirm_email = self.cleaned_data.get('confirm_email')
        
        if email and confirm_email and email != confirm_email:
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
            # Check if employee_id exists for another profile
            existing = Profile.objects.exclude(pk=self.instance.pk).filter(employee_id=employee_id)
            if existing.exists():
                raise ValidationError(_("This employee ID is already in use."))
        return employee_id
    
    def save(self, commit=True):
        """Save the profile and update user email if changed"""
        profile = super().save(commit=False)
        
        if commit:
            profile.save()
            # Update user email if changed and confirm_email matches
            if self.user and self.cleaned_data.get('confirm_email'):
                new_email = self.cleaned_data.get('confirm_email')
                if self.user.email != new_email:
                    self.user.email = new_email
                    self.user.save(update_fields=['email'])
        
        return profile


class HotelMemberForm(forms.ModelForm):
    """Form for creating and updating hotel memberships"""
    
    class Meta:
        model = HotelMember
        fields = [
            # Basic Information
            "role",
            "permission_level",
            "employment_type",
            "shift_preference",
            "default_shift_start",
            "default_shift_end",
            "max_weekly_hours",
            "overtime_allowed",
            
            # Contact & Profile
            "profile_picture",
            "work_phone",
            "work_email",
            "emergency_contact_name",
            "emergency_contact_phone",
            "emergency_contact_relationship",
            
            # Employment Details
            "employee_code",
            "hire_date",
            "contract_start_date",
            "contract_end_date",
            "probation_end_date",
            
            # Compensation
            "hourly_rate",
            "salary",
            "currency",
            
            # Permissions
            "can_manage_bookings",
            "can_manage_rooms",
            "can_manage_inventory",
            "can_manage_staff",
            "can_view_financials",
            "can_manage_reports",
            "can_manage_settings",
            
            # Legacy Permissions (backward compatibility)
            "can_access_front_desk",
            "can_access_housekeeping",
            "can_access_restaurant",
            "can_access_finance",
            "can_access_maintenance",
            "can_access_reports",
            
            # Status
            "is_active",
            "is_primary_contact",
            "is_on_leave",
            "leave_start_date",
            "leave_end_date",
            "leave_reason",
            
            # Performance
            "performance_rating",
            "performance_notes",
            
            # Other
            "notes",
            "special_skills",
            "languages_spoken",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
            "performance_notes": forms.Textarea(attrs={"rows": 2}),
            "special_skills": forms.Textarea(attrs={"rows": 2}),
            "leave_reason": forms.Textarea(attrs={"rows": 2}),
            "default_shift_start": forms.TimeInput(attrs={"type": "time"}),
            "default_shift_end": forms.TimeInput(attrs={"type": "time"}),
            "hire_date": forms.DateInput(attrs={"type": "date"}),
            "contract_start_date": forms.DateInput(attrs={"type": "date"}),
            "contract_end_date": forms.DateInput(attrs={"type": "date"}),
            "probation_end_date": forms.DateInput(attrs={"type": "date"}),
            "leave_start_date": forms.DateInput(attrs={"type": "date"}),
            "leave_end_date": forms.DateInput(attrs={"type": "date"}),
            "profile_picture": forms.ClearableFileInput(attrs={"class": BASE_FILE_INPUT}),
            "languages_spoken": forms.SelectMultiple(attrs={"class": BASE_SELECT}),
        }
    
    def __init__(self, *args, **kwargs):
        self.hotel = kwargs.pop('hotel', None)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Make employee_code read-only for existing instances
        if self.instance and self.instance.pk and self.instance.employee_code:
            self.fields['employee_code'].widget.attrs['readonly'] = True
            self.fields['employee_code'].help_text = _("Employee code is auto-generated and cannot be changed.")
        
        # Set currency choices (common currencies)
        self.fields['currency'].choices = [
            ('USD', _('USD - US Dollar')),
            ('EUR', _('EUR - Euro')),
            ('GBP', _('GBP - British Pound')),
            ('UGX', _('UGX - Ugandan Shilling')),
            ('KES', _('KES - Kenyan Shilling')),
            ('TZS', _('TZS - Tanzanian Shilling')),
            ('RWF', _('RWF - Rwandan Franc')),
        ]
        
        # Language choices for languages_spoken
        self.fields['languages_spoken'].choices = Profile.Language.choices
        
        # Conditional field requirements based on employment type
        if self.instance and self.instance.employment_type:
            if self.instance.employment_type in [HotelMember.EmploymentType.CONTRACT, HotelMember.EmploymentType.TEMPORARY]:
                self.fields['contract_start_date'].required = True
                self.fields['contract_end_date'].required = True
        
        # Apply consistent Tailwind classes
        for name, field in self.fields.items():
            widget = field.widget
            
            # Skip if widget already has custom classes
            if widget.attrs.get('class') and name != 'profile_picture':
                continue
            
            # Add appropriate classes based on widget type
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
            elif isinstance(widget, forms.ClearableFileInput):
                widget.attrs.setdefault("class", BASE_FILE_INPUT)
            
            # Add helpful placeholders
            if name == "work_phone" and not widget.attrs.get("placeholder"):
                widget.attrs["placeholder"] = _("+2567XXXXXXXX")
            elif name == "employee_code" and not widget.attrs.get("placeholder"):
                widget.attrs["placeholder"] = _("Auto-generated")
            elif name == "hourly_rate" and not widget.attrs.get("placeholder"):
                widget.attrs["placeholder"] = _("0.00")
            elif name == "salary" and not widget.attrs.get("placeholder"):
                widget.attrs["placeholder"] = _("0.00")
            elif name == "performance_rating" and not widget.attrs.get("placeholder"):
                widget.attrs["placeholder"] = _("0.00 - 5.00")
                widget.attrs["step"] = "0.01"
                widget.attrs["min"] = "0"
                widget.attrs["max"] = "5"
            elif name == "max_weekly_hours" and not widget.attrs.get("placeholder"):
                widget.attrs["placeholder"] = _("40")
    
    def clean(self):
        """Cross-field validation"""
        cleaned_data = super().clean()
        
        # Validate contract dates
        contract_start = cleaned_data.get('contract_start_date')
        contract_end = cleaned_data.get('contract_end_date')
        
        if contract_start and contract_end and contract_end < contract_start:
            self.add_error('contract_end_date', _("Contract end date cannot be before start date."))
        
        # Validate leave dates
        is_on_leave = cleaned_data.get('is_on_leave')
        leave_start = cleaned_data.get('leave_start_date')
        leave_end = cleaned_data.get('leave_end_date')
        
        if is_on_leave:
            if not leave_start or not leave_end:
                self.add_error('leave_start_date', _("Both start and end dates are required when on leave."))
            elif leave_end < leave_start:
                self.add_error('leave_end_date', _("Leave end date cannot be before start date."))
        
        # Validate probation end date
        probation_end = cleaned_data.get('probation_end_date')
        hire_date = cleaned_data.get('hire_date')
        
        if probation_end and hire_date and probation_end < hire_date:
            self.add_error('probation_end_date', _("Probation end date cannot be before hire date."))
        
        # Validate shift times
        shift_start = cleaned_data.get('default_shift_start')
        shift_end = cleaned_data.get('default_shift_end')
        
        if shift_start and shift_end and shift_end <= shift_start:
            self.add_error('default_shift_end', _("Shift end time must be after shift start time."))
        
        # Validate performance rating
        performance_rating = cleaned_data.get('performance_rating')
        if performance_rating and (performance_rating < 0 or performance_rating > 5):
            self.add_error('performance_rating', _("Performance rating must be between 0 and 5."))
        
        # Validate primary contact uniqueness
        is_primary_contact = cleaned_data.get('is_primary_contact')
        if is_primary_contact and self.hotel:
            existing = HotelMember.objects.filter(
                hotel=self.hotel,
                is_primary_contact=True,
                is_active=True
            ).exclude(pk=self.instance.pk)
            if existing.exists():
                self.add_error('is_primary_contact', _("This hotel already has a primary contact."))
        
        return cleaned_data
    
    def clean_employee_code(self):
        """Validate employee code uniqueness"""
        employee_code = self.cleaned_data.get('employee_code')
        if employee_code and not self.instance.pk:  # Only for new instances
            if HotelMember.objects.filter(employee_code=employee_code).exists():
                raise ValidationError(_("This employee code already exists."))
        return employee_code
    
    def clean_work_email(self):
        """Validate work email format"""
        work_email = self.cleaned_data.get('work_email')
        if work_email:
            from django.core.validators import validate_email
            try:
                validate_email(work_email)
            except ValidationError:
                raise ValidationError(_("Enter a valid email address."))
        return work_email
    
    def save(self, commit=True):
        """Save the hotel member with additional logic"""
        member = super().save(commit=False)
        
        # Set hotel if provided
        if self.hotel and not member.hotel_id:
            member.hotel = self.hotel
        
        # Set invited_by for new members
        if not member.pk and self.user:
            member.invited_by = self.user
            member.invitation_sent_at = timezone.now()
            member.invitation_expires_at = timezone.now() + timezone.timedelta(days=7)
        
        if commit:
            member.save()
            self.save_m2m()  # Save many-to-many relationships
        
        return member


class HotelMemberInviteForm(HotelMemberForm):
    """Form for inviting new members to a hotel"""
    
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
    send_invitation_email = forms.BooleanField(
        label=_("Send invitation email"),
        initial=True,
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"})
    )
    
    class Meta(HotelMemberForm.Meta):
        fields = HotelMemberForm.Meta.fields + ['email', 'first_name', 'last_name', 'send_invitation_email']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make role required for invitations
        self.fields['role'].required = True
        # Set default role
        if not self.instance.role:
            self.fields['role'].initial = HotelMember.Role.VIEWER
    
    def clean_email(self):
        """Check if user already exists or has pending invitation"""
        email = self.cleaned_data.get('email')
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        # Check if user exists
        if User.objects.filter(email=email).exists():
            user = User.objects.get(email=email)
            # Check if already a member of this hotel
            if HotelMember.objects.filter(hotel=self.hotel, user=user).exists():
                raise ValidationError(_("This user is already a member of this hotel."))
        
        return email


class HotelMemberBulkInviteForm(forms.Form):
    """Form for bulk inviting multiple members"""
    
    emails = forms.CharField(
        label=_("Email Addresses"),
        widget=forms.Textarea(attrs={
            "class": BASE_TEXTAREA,
            "rows": 5,
            "placeholder": _("Enter one email address per line\n\nuser1@example.com\nuser2@example.com")
        }),
        help_text=_("Enter one email address per line")
    )
    role = forms.ChoiceField(
        choices=HotelMember.Role.choices,
        initial=HotelMember.Role.VIEWER,
        widget=forms.Select(attrs={"class": BASE_SELECT})
    )
    send_invitation_email = forms.BooleanField(
        label=_("Send invitation emails"),
        initial=True,
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"})
    )
    
    def clean_emails(self):
        """Parse and validate email list"""
        emails_text = self.cleaned_data.get('emails', '')
        emails = [email.strip() for email in emails_text.split('\n') if email.strip()]
        
        if not emails:
            raise ValidationError(_("Please provide at least one email address."))
        
        # Validate email format
        from django.core.validators import validate_email
        for email in emails:
            try:
                validate_email(email)
            except ValidationError:
                raise ValidationError(_(f"'{email}' is not a valid email address."))
        
        return emails


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
        for name, field in self.fields.items():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", BASE_SELECT)