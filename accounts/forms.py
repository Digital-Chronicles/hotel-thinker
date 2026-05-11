# accounts/forms.py

from __future__ import annotations

import logging

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.translation import gettext_lazy as _

from .models import Profile, HotelMember

logger = logging.getLogger(__name__)
User = get_user_model()


BASE_INPUT = "w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
BASE_SELECT = "w-full rounded-lg border border-gray-300 bg-white px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
BASE_TEXTAREA = "w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
BASE_FILE_INPUT = "w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500 file:mr-4 file:rounded-lg file:border-0 file:bg-indigo-50 file:px-4 file:py-2 file:text-indigo-700 hover:file:bg-indigo-100"


class ProfileForm(forms.ModelForm):
    confirm_email = forms.EmailField(
        required=False,
        label=_("Confirm Email"),
        widget=forms.EmailInput(
            attrs={
                "placeholder": _("Confirm your email address"),
                "class": BASE_INPUT,
            }
        ),
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
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        if self.user and self.user.email:
            self.fields["confirm_email"].initial = self.user.email
            self.fields["confirm_email"].required = True

        self._apply_widget_classes()
        self._add_placeholders()

    def _apply_widget_classes(self):
        for name, field in self.fields.items():
            widget = field.widget

            if widget.attrs.get("class") and name != "avatar":
                continue

            if isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("class", BASE_TEXTAREA)
                widget.attrs.setdefault("rows", 3)
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", BASE_SELECT)
            elif isinstance(widget, (forms.TextInput, forms.EmailInput, forms.NumberInput, forms.DateInput)):
                widget.attrs.setdefault("class", BASE_INPUT)
            elif isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault(
                    "class",
                    "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500",
                )
            elif isinstance(widget, forms.ClearableFileInput):
                widget.attrs.setdefault("class", BASE_FILE_INPUT)

    def _add_placeholders(self):
        placeholders = {
            "phone": _("+2567XXXXXXXX"),
            "alternative_phone": _("+2567XXXXXXXX"),
            "employee_id": _("EMP-XXXXXX"),
            "postal_code": _("e.g., 12345"),
        }

        for field_name, placeholder in placeholders.items():
            if field_name in self.fields:
                widget = self.fields[field_name].widget
                widget.attrs.setdefault("placeholder", placeholder)

    def clean_confirm_email(self):
        confirm_email = self.cleaned_data.get("confirm_email")

        if self.user and self.user.email and confirm_email:
            if self.user.email != confirm_email:
                raise ValidationError(_("Email addresses do not match."))

        return confirm_email

    def clean_date_of_birth(self):
        date_of_birth = self.cleaned_data.get("date_of_birth")

        if date_of_birth and date_of_birth > timezone.now().date():
            raise ValidationError(_("Date of birth cannot be in the future."))

        return date_of_birth

    def clean_employee_id(self):
        employee_id = self.cleaned_data.get("employee_id")

        if employee_id:
            exists = Profile.objects.exclude(pk=self.instance.pk).filter(employee_id=employee_id).exists()
            if exists:
                raise ValidationError(_("This employee ID is already in use."))

        return employee_id

    def save(self, commit=True):
        profile = super().save(commit=False)

        if commit:
            profile.save()

            if self.user and self.cleaned_data.get("confirm_email"):
                new_email = self.cleaned_data["confirm_email"]

                if self.user.email != new_email:
                    self.user.email = new_email
                    self.user.save(update_fields=["email"])

        return profile


class BaseHotelMemberForm(forms.ModelForm):
    email = forms.EmailField(
        label=_("Email Address"),
        widget=forms.EmailInput(
            attrs={
                "class": BASE_INPUT,
                "placeholder": _("user@example.com"),
            }
        ),
    )

    first_name = forms.CharField(
        label=_("First Name"),
        max_length=150,
        widget=forms.TextInput(attrs={"class": BASE_INPUT}),
    )

    last_name = forms.CharField(
        label=_("Last Name"),
        max_length=150,
        widget=forms.TextInput(attrs={"class": BASE_INPUT}),
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
        self.hotel = kwargs.pop("hotel", None)
        self.created_by = kwargs.pop("created_by", None)
        super().__init__(*args, **kwargs)

        self.fields["email"].required = True
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["role"].required = True

        if not self.instance.pk and not self.instance.role:
            self.fields["role"].initial = HotelMember.Role.VIEWER

        self._apply_widget_classes()
        self._add_placeholders()

    def _apply_widget_classes(self):
        for name, field in self.fields.items():
            if name in ["email", "first_name", "last_name"]:
                continue

            widget = field.widget

            if widget.attrs.get("class"):
                continue

            if isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("class", BASE_TEXTAREA)
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", BASE_SELECT)
            elif isinstance(widget, (forms.TextInput, forms.EmailInput, forms.DateInput, forms.NumberInput)):
                widget.attrs.setdefault("class", BASE_INPUT)
            elif isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault(
                    "class",
                    "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500",
                )

    def _add_placeholders(self):
        placeholders = {
            "work_phone": _("+2567XXXXXXXX"),
            "work_email": _("staff@example.com"),
        }

        for field_name, placeholder in placeholders.items():
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.setdefault("placeholder", placeholder)

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()

        try:
            validate_email(email)
        except ValidationError:
            raise ValidationError(_("Enter a valid email address."))

        if self.hotel:
            exists = HotelMember.objects.filter(
                hotel=self.hotel,
                user__email=email,
            ).exclude(pk=self.instance.pk).exists()

            if exists:
                raise ValidationError(_("A user with this email is already a member of this hotel."))

        return email

    def _get_or_create_user(self):
        email = self.cleaned_data["email"].strip().lower()
        first_name = self.cleaned_data["first_name"].strip()
        last_name = self.cleaned_data["last_name"].strip()

        try:
            user = User.objects.get(email=email)
            created = False
        except User.DoesNotExist:
            password = get_random_string(12)

            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
            )

            created = True
            self._generated_password = password

        if not created:
            updated_fields = []

            if user.first_name != first_name:
                user.first_name = first_name
                updated_fields.append("first_name")

            if user.last_name != last_name:
                user.last_name = last_name
                updated_fields.append("last_name")

            if updated_fields:
                user.save(update_fields=updated_fields)

        return user, created

    def _generate_employee_code(self):
        if not self.hotel:
            return None

        hotel_code = getattr(self.hotel, "code", None) or str(self.hotel.id)[:4]
        year = timezone.now().year
        count = HotelMember.objects.filter(hotel=self.hotel).count() + 1

        return f"{hotel_code}-{year}-{count:04d}"

    @transaction.atomic
    def save(self, commit=True):
        member = super().save(commit=False)

        user, user_created = self._get_or_create_user()
        member.user = user

        if self.hotel:
            member.hotel = self.hotel

        if not member.pk:
            member.joined_at = timezone.now()
            member.is_active = True
            member.invitation_accepted_at = timezone.now()

            if self.created_by:
                member.invited_by = self.created_by

        if not member.employee_code:
            member.employee_code = self._generate_employee_code()

        if commit:
            member.save()
            self.save_m2m()

            if user_created:
                Profile.objects.get_or_create(user=user)

        member._user_created = user_created

        if hasattr(self, "_generated_password"):
            member._generated_password = self._generated_password

        return member


class HotelMemberAddForm(BaseHotelMemberForm):
    send_welcome_email = forms.BooleanField(
        label=_("Send welcome email with login details"),
        initial=True,
        required=False,
        widget=forms.CheckboxInput(
            attrs={
                "class": "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500",
            }
        ),
    )

    class Meta(BaseHotelMemberForm.Meta):
        fields = BaseHotelMemberForm.Meta.fields + ["send_welcome_email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["email"].help_text = _(
            "If a user with this email does not exist, an account will be automatically created."
        )

    def clean(self):
        cleaned_data = super().clean()

        is_on_leave = cleaned_data.get("is_on_leave")
        leave_start = cleaned_data.get("leave_start_date")
        leave_end = cleaned_data.get("leave_end_date")

        if is_on_leave and (not leave_start or not leave_end):
            self.add_error("leave_start_date", _("Both start and end dates are required when on leave."))

        contract_start = cleaned_data.get("contract_start_date")
        contract_end = cleaned_data.get("contract_end_date")

        if contract_start and contract_end and contract_end < contract_start:
            self.add_error("contract_end_date", _("Contract end date cannot be before start date."))

        return cleaned_data


class HotelMemberInviteForm(BaseHotelMemberForm):
    send_invitation_email = forms.BooleanField(
        label=_("Send invitation email"),
        initial=True,
        required=False,
        widget=forms.CheckboxInput(
            attrs={
                "class": "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500",
            }
        ),
    )

    class Meta(BaseHotelMemberForm.Meta):
        fields = BaseHotelMemberForm.Meta.fields + ["send_invitation_email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["email"].help_text = _(
            "An invitation email will be sent to this address. The user will need to accept it to join."
        )

    @transaction.atomic
    def save(self, commit=True):
        member = super().save(commit=False)

        member.is_active = False
        member.invitation_sent_at = timezone.now()
        member.invitation_expires_at = timezone.now() + timezone.timedelta(days=7)
        member.invitation_accepted_at = None

        if commit:
            member.save()
            self.save_m2m()

        return member


class HotelMemberBulkAddForm(forms.Form):
    members_data = forms.CharField(
        label=_("Members Data"),
        widget=forms.Textarea(
            attrs={
                "class": BASE_TEXTAREA,
                "rows": 8,
                "placeholder": _(
                    "Enter one member per line with comma-separated values:\n\n"
                    "email,first_name,last_name,role\n"
                    "john@example.com,John,Doe,front_desk\n"
                    "jane@example.com,Jane,Smith,housekeeper"
                ),
            }
        ),
        help_text=_(
            "Format: email, first_name, last_name, role\n"
            "Roles: admin, general_manager, front_desk, housekeeper, server, viewer, etc."
        ),
    )

    default_role = forms.ChoiceField(
        choices=HotelMember.Role.choices,
        required=False,
        initial=HotelMember.Role.VIEWER,
        widget=forms.Select(attrs={"class": BASE_SELECT}),
        help_text=_("Default role for members without a specified role"),
    )

    send_welcome_emails = forms.BooleanField(
        label=_("Send welcome emails"),
        initial=True,
        required=False,
        widget=forms.CheckboxInput(
            attrs={
                "class": "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        self.hotel = kwargs.pop("hotel", None)
        self.created_by = kwargs.pop("created_by", None)
        super().__init__(*args, **kwargs)

    def clean_members_data(self):
        data = self.cleaned_data.get("members_data", "")
        lines = [line.strip() for line in data.splitlines() if line.strip()]

        if not lines:
            raise ValidationError(_("Please provide at least one member."))

        valid_roles = [choice[0] for choice in HotelMember.Role.choices]
        default_role = self.cleaned_data.get("default_role") or HotelMember.Role.VIEWER

        members = []
        errors = []

        for line_num, line in enumerate(lines, 1):
            parts = [part.strip() for part in line.split(",")]

            if len(parts) < 3:
                errors.append(f"Line {line_num}: Need at least email, first_name, last_name.")
                continue

            email = parts[0].lower()
            first_name = parts[1]
            last_name = parts[2]
            role = parts[3] if len(parts) > 3 and parts[3] else default_role

            try:
                validate_email(email)
            except ValidationError:
                errors.append(f"Line {line_num}: Invalid email address '{email}'.")
                continue

            if role not in valid_roles:
                errors.append(
                    f"Line {line_num}: Invalid role '{role}'. Valid roles: {', '.join(valid_roles)}."
                )
                continue

            if self.hotel and HotelMember.objects.filter(hotel=self.hotel, user__email=email).exists():
                errors.append(f"Line {line_num}: User '{email}' is already a member of this hotel.")
                continue

            members.append(
                {
                    "email": email,
                    "first_name": first_name,
                    "last_name": last_name,
                    "role": role,
                    "line_num": line_num,
                }
            )

        if errors:
            raise ValidationError("\n".join(errors))

        return members

    @transaction.atomic
    def save(self):
        members = self.cleaned_data["members_data"]
        created_members = []
        errors = []

        for member_data in members:
            try:
                user, created = User.objects.get_or_create(
                    email=member_data["email"],
                    defaults={
                        "username": member_data["email"],
                        "first_name": member_data["first_name"],
                        "last_name": member_data["last_name"],
                    },
                )

                if not created:
                    user.first_name = member_data["first_name"]
                    user.last_name = member_data["last_name"]
                    user.save(update_fields=["first_name", "last_name"])

                Profile.objects.get_or_create(user=user)

                hotel_member = HotelMember.objects.create(
                    hotel=self.hotel,
                    user=user,
                    role=member_data["role"],
                    is_active=True,
                    joined_at=timezone.now(),
                    invited_by=self.created_by,
                    invitation_accepted_at=timezone.now(),
                )

                if not hotel_member.employee_code:
                    hotel_code = getattr(self.hotel, "code", None) or str(self.hotel.id)[:4]
                    count = HotelMember.objects.filter(hotel=self.hotel).count()
                    hotel_member.employee_code = f"{hotel_code}-{timezone.now().year}-{count:04d}"
                    hotel_member.save(update_fields=["employee_code"])

                if created:
                    password = get_random_string(12)
                    user.set_password(password)
                    user.save(update_fields=["password"])
                    hotel_member._generated_password = password

                created_members.append(hotel_member)

            except Exception as e:
                errors.append(f"Error adding {member_data['email']}: {str(e)}")
                logger.exception("Bulk add error for %s", member_data["email"])

        if errors:
            raise ValidationError("\n".join(errors))

        return created_members


class HotelMemberEditForm(forms.ModelForm):
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
        self.hotel = kwargs.pop("hotel", None)
        super().__init__(*args, **kwargs)

        if self.instance and getattr(self.instance, "employee_code", None):
            self.fields["employee_code"] = forms.CharField(
                initial=self.instance.employee_code,
                disabled=True,
                required=False,
                widget=forms.TextInput(attrs={"class": BASE_INPUT, "readonly": True}),
                label=_("Employee Code"),
            )

        if "languages_spoken" in self.fields:
            self.fields["languages_spoken"].choices = Profile.Language.choices

        if "currency" in self.fields:
            self.fields["currency"].choices = [
                ("USD", _("USD - US Dollar")),
                ("EUR", _("EUR - Euro")),
                ("GBP", _("GBP - British Pound")),
                ("UGX", _("UGX - Ugandan Shilling")),
                ("KES", _("KES - Kenyan Shilling")),
                ("TZS", _("TZS - Tanzanian Shilling")),
                ("RWF", _("RWF - Rwandan Franc")),
            ]

        self._apply_widget_classes()

    def _apply_widget_classes(self):
        for name, field in self.fields.items():
            if name == "employee_code":
                continue

            widget = field.widget

            if widget.attrs.get("class"):
                continue

            if isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("class", BASE_TEXTAREA)
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs.setdefault("class", BASE_SELECT)
            elif isinstance(
                widget,
                (
                    forms.TextInput,
                    forms.EmailInput,
                    forms.NumberInput,
                    forms.DateInput,
                    forms.TimeInput,
                ),
            ):
                widget.attrs.setdefault("class", BASE_INPUT)
            elif isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault(
                    "class",
                    "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500",
                )

    def clean(self):
        cleaned_data = super().clean()

        contract_start = cleaned_data.get("contract_start_date")
        contract_end = cleaned_data.get("contract_end_date")

        if contract_start and contract_end and contract_end < contract_start:
            self.add_error("contract_end_date", _("Contract end date cannot be before start date."))

        is_on_leave = cleaned_data.get("is_on_leave")
        leave_start = cleaned_data.get("leave_start_date")
        leave_end = cleaned_data.get("leave_end_date")

        if is_on_leave:
            if not leave_start or not leave_end:
                self.add_error("leave_start_date", _("Both start and end dates are required when on leave."))
            elif leave_end < leave_start:
                self.add_error("leave_end_date", _("Leave end date cannot be before start date."))

        probation_end = cleaned_data.get("probation_end_date")
        hire_date = cleaned_data.get("hire_date")

        if probation_end and hire_date and probation_end < hire_date:
            self.add_error("probation_end_date", _("Probation end date cannot be before hire date."))

        shift_start = cleaned_data.get("default_shift_start")
        shift_end = cleaned_data.get("default_shift_end")

        if shift_start and shift_end and shift_end <= shift_start:
            self.add_error("default_shift_end", _("Shift end time must be after shift start time."))

        performance_rating = cleaned_data.get("performance_rating")

        if performance_rating is not None and (performance_rating < 0 or performance_rating > 5):
            self.add_error("performance_rating", _("Performance rating must be between 0 and 5."))

        is_primary_contact = cleaned_data.get("is_primary_contact")
        hotel = self.hotel or getattr(self.instance, "hotel", None)

        if is_primary_contact and hotel:
            exists = HotelMember.objects.filter(
                hotel=hotel,
                is_primary_contact=True,
                is_active=True,
            ).exclude(pk=self.instance.pk).exists()

            if exists:
                self.add_error("is_primary_contact", _("This hotel already has a primary contact."))

        return cleaned_data


class ProfilePreferencesForm(forms.ModelForm):
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
            "notification_email": forms.CheckboxInput(
                attrs={"class": "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"}
            ),
            "notification_sms": forms.CheckboxInput(
                attrs={"class": "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"}
            ),
            "notification_push": forms.CheckboxInput(
                attrs={"class": "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"}
            ),
            "notification_digest": forms.CheckboxInput(
                attrs={"class": "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault(
                    "class",
                    BASE_SELECT if isinstance(field.widget, forms.Select) else BASE_INPUT,
                )


class HotelMemberPermissionForm(forms.ModelForm):
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
            "can_manage_bookings": forms.CheckboxInput(
                attrs={"class": "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"}
            ),
            "can_manage_rooms": forms.CheckboxInput(
                attrs={"class": "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"}
            ),
            "can_manage_inventory": forms.CheckboxInput(
                attrs={"class": "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"}
            ),
            "can_manage_staff": forms.CheckboxInput(
                attrs={"class": "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"}
            ),
            "can_view_financials": forms.CheckboxInput(
                attrs={"class": "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"}
            ),
            "can_manage_reports": forms.CheckboxInput(
                attrs={"class": "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"}
            ),
            "can_manage_settings": forms.CheckboxInput(
                attrs={"class": "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", BASE_SELECT)


class HotelMemberQuickAddForm(forms.Form):
    email = forms.EmailField(
        label=_("Email Address"),
        widget=forms.EmailInput(
            attrs={
                "class": BASE_INPUT,
                "placeholder": _("user@example.com"),
            }
        ),
    )

    role = forms.ChoiceField(
        choices=HotelMember.Role.choices,
        initial=HotelMember.Role.VIEWER,
        widget=forms.Select(attrs={"class": BASE_SELECT}),
    )

    send_welcome = forms.BooleanField(
        label=_("Send welcome email"),
        initial=True,
        required=False,
        widget=forms.CheckboxInput(
            attrs={
                "class": "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        self.hotel = kwargs.pop("hotel", None)
        self.created_by = kwargs.pop("created_by", None)
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()

        try:
            validate_email(email)
        except ValidationError:
            raise ValidationError(_("Enter a valid email address."))

        if self.hotel and HotelMember.objects.filter(hotel=self.hotel, user__email=email).exists():
            raise ValidationError(_("This user is already a member of the hotel."))

        return email

    @transaction.atomic
    def save(self):
        email = self.cleaned_data["email"].strip().lower()
        role = self.cleaned_data["role"]

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "username": email,
            },
        )

        if created:
            password = get_random_string(12)
            user.set_password(password)
            user.save(update_fields=["password"])

            Profile.objects.get_or_create(user=user)
            user._generated_password = password

        hotel_member = HotelMember.objects.create(
            hotel=self.hotel,
            user=user,
            role=role,
            is_active=True,
            joined_at=timezone.now(),
            invited_by=self.created_by,
            invitation_accepted_at=timezone.now(),
        )

        if not hotel_member.employee_code and self.hotel:
            hotel_code = getattr(self.hotel, "code", None) or str(self.hotel.id)[:4]
            count = HotelMember.objects.filter(hotel=self.hotel).count()
            hotel_member.employee_code = f"{hotel_code}-{timezone.now().year}-{count:04d}"
            hotel_member.save(update_fields=["employee_code"])

        if created and hasattr(user, "_generated_password"):
            hotel_member._generated_password = user._generated_password

        return hotel_member