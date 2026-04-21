# rooms/forms.py
from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError
from django.utils.safestring import mark_safe
from .models import RoomType, Room, RoomImage, RoomImageGallery


# Tailwind helper styles
TW_INPUT = (
    "w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm "
    "placeholder-slate-400 shadow-sm "
    "focus:outline-none focus:ring-2 focus:ring-slate-300 focus:border-slate-300"
)
TW_SELECT = TW_INPUT
TW_TEXTAREA = (
    "w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm "
    "placeholder-slate-400 shadow-sm "
    "focus:outline-none focus:ring-2 focus:ring-slate-300 focus:border-slate-300"
)
TW_CHECKBOX = (
    "h-4 w-4 rounded border-slate-300 text-slate-900 "
    "focus:ring-2 focus:ring-slate-300"
)
TW_FILE_INPUT = (
    "w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm "
    "file:mr-4 file:py-1 file:px-3 file:rounded-lg file:border-0 "
    "file:text-sm file:bg-slate-50 file:text-slate-700 "
    "hover:file:bg-slate-100"
)


# Custom widget for multiple file upload
class MultipleFileInput(forms.ClearableFileInput):
    """Custom widget that supports multiple file uploads"""
    allow_multiple_selected = True
    
    def __init__(self, attrs=None):
        default_attrs = {'multiple': True}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)
    
    def value_from_datadict(self, data, files, name):
        """Handle multiple file uploads"""
        if hasattr(files, 'getlist'):
            return files.getlist(name)
        return [files.get(name)] if files.get(name) else []


class MultipleFileField(forms.FileField):
    """Custom file field for multiple uploads"""
    widget = MultipleFileInput
    
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('widget', MultipleFileInput(attrs={
            "class": TW_FILE_INPUT,
            "accept": "image/jpeg,image/png,image/webp",
        }))
        super().__init__(*args, **kwargs)
    
    def clean(self, data, initial=None):
        """Validate multiple files"""
        if not data:
            if self.required:
                raise ValidationError(self.error_messages['required'])
            return []
        
        # Handle list of files
        if isinstance(data, list):
            cleaned_data = []
            for file in data:
                if file:
                    cleaned_data.append(super().clean(file, initial))
            return cleaned_data
        return [super().clean(data, initial)] if data else []


class RoomTypeForm(forms.ModelForm):
    class Meta:
        model = RoomType
        fields = ["name", "description", "base_price"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Apply Tailwind classes
        self.fields["name"].widget.attrs.update({
            "class": TW_INPUT,
            "placeholder": "e.g. Single, Double, Deluxe",
        })
        self.fields["description"].widget.attrs.update({
            "class": TW_TEXTAREA,
            "placeholder": "Short description (optional)",
        })
        self.fields["base_price"].widget.attrs.update({
            "class": TW_INPUT,
            "placeholder": "0.00",
            "inputmode": "decimal",
        })

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise ValidationError("Room type name is required.")
        return name

    def clean_base_price(self):
        base_price = self.cleaned_data.get("base_price")
        if base_price is not None and base_price < 0:
            raise ValidationError("Base price cannot be negative.")
        return base_price


class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = ["room_type", "number", "floor", "status", "is_active"]

    def __init__(self, *args, hotel=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Hotel filter
        if hotel is not None:
            self.fields["room_type"].queryset = RoomType.objects.filter(hotel=hotel).order_by("name")

        # Tailwind classes
        self.fields["room_type"].widget.attrs.update({
            "class": TW_SELECT,
        })
        self.fields["number"].widget.attrs.update({
            "class": TW_INPUT,
            "placeholder": "e.g. 101, A-01",
        })
        self.fields["floor"].widget.attrs.update({
            "class": TW_INPUT,
            "placeholder": "e.g. 1st floor (optional)",
        })
        self.fields["status"].widget.attrs.update({
            "class": TW_SELECT,
        })

        # Checkbox styling
        self.fields["is_active"].widget.attrs.update({
            "class": TW_CHECKBOX,
        })

    def clean_number(self):
        number = (self.cleaned_data.get("number") or "").strip()
        if not number:
            raise ValidationError("Room number is required.")
        return number


class RoomImageForm(forms.ModelForm):
    """Form for uploading and editing room images"""
    
    class Meta:
        model = RoomImage
        fields = [
            "image", "category", "title", "alt_text", "caption",
            "order", "is_primary", "is_featured", "is_active"
        ]
        widgets = {
            "caption": forms.Textarea(attrs={"rows": 2}),
        }
    
    def __init__(self, *args, room=None, room_type=None, hotel=None, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Store references for save method
        self.room = room
        self.room_type = room_type
        self.hotel = hotel
        
        # Apply Tailwind classes
        self.fields["image"].widget.attrs.update({
            "class": TW_FILE_INPUT,
            "accept": "image/jpeg,image/png,image/webp",
        })
        self.fields["category"].widget.attrs.update({
            "class": TW_SELECT,
        })
        self.fields["title"].widget.attrs.update({
            "class": TW_INPUT,
            "placeholder": "e.g. Deluxe Suite Bedroom View",
        })
        self.fields["alt_text"].widget.attrs.update({
            "class": TW_INPUT,
            "placeholder": "Brief description for SEO",
        })
        self.fields["caption"].widget.attrs.update({
            "class": TW_TEXTAREA,
            "placeholder": "Additional details about this image...",
        })
        self.fields["order"].widget.attrs.update({
            "class": TW_INPUT,
            "type": "number",
            "min": 0,
            "placeholder": "0",
        })
        
        # Checkbox styling
        checkbox_fields = ["is_primary", "is_featured", "is_active"]
        for field in checkbox_fields:
            self.fields[field].widget.attrs.update({
                "class": TW_CHECKBOX,
            })
    
    def clean_image(self):
        """Validate image file size and dimensions"""
        image = self.cleaned_data.get("image")
        if image:
            # Check file size (max 10MB)
            if image.size > 10 * 1024 * 1024:
                raise ValidationError("Image file too large (max 10MB).")
            
            # Optional: Check image dimensions (if PIL is available)
            try:
                from PIL import Image
                img = Image.open(image)
                width, height = img.size
                
                # Store dimensions for later use
                self.cleaned_data["_width"] = width
                self.cleaned_data["_height"] = height
                self.cleaned_data["_file_size"] = image.size
                
                # Minimum dimensions (e.g., 800x600)
                if width < 800 or height < 600:
                    raise ValidationError(
                        f"Image too small (minimum 800x600 pixels). "
                        f"Current size: {width}x{height} pixels."
                    )
                
                # Maximum dimensions (optional, for performance)
                if width > 4000 or height > 4000:
                    raise ValidationError(
                        f"Image too large (maximum 4000x4000 pixels). "
                        f"Current size: {width}x{height} pixels."
                    )
                    
            except ImportError:
                # PIL not installed, skip dimension validation
                pass
            except Exception as e:
                # If image processing fails, just warn but don't block upload
                pass
        
        return image
    
    def save(self, commit=True):
        """Override save to populate room, room_type, and hotel"""
        instance = super().save(commit=False)
        
        # Set relationships
        if self.room:
            instance.room = self.room
        if self.room_type:
            instance.room_type = self.room_type
        if self.hotel:
            instance.hotel = self.hotel
        elif self.room:
            instance.hotel = self.room.hotel
        
        # Set image metadata if available
        if hasattr(self, '_width'):
            instance.width = self._width
            instance.height = self._height
            instance.file_size = self._file_size
        
        if commit:
            instance.save()
            self.save_m2m()
        
        return instance


class RoomImageGalleryForm(forms.ModelForm):
    """Form for creating and editing image galleries"""
    
    class Meta:
        model = RoomImageGallery
        fields = ["name", "description", "room_type", "images", "order", "is_active"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "images": forms.SelectMultiple(attrs={"size": 10}),
        }
    
    def __init__(self, *args, hotel=None, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.hotel = hotel
        
        # Filter room types by hotel
        if hotel is not None:
            self.fields["room_type"].queryset = RoomType.objects.filter(hotel=hotel).order_by("name")
            self.fields["images"].queryset = RoomImage.objects.filter(
                hotel=hotel, is_active=True
            ).select_related("room", "room_type")
        
        # Apply Tailwind classes
        self.fields["name"].widget.attrs.update({
            "class": TW_INPUT,
            "placeholder": "e.g. Deluxe Suite Collection",
        })
        self.fields["description"].widget.attrs.update({
            "class": TW_TEXTAREA,
            "placeholder": "Gallery description (optional)",
        })
        self.fields["room_type"].widget.attrs.update({
            "class": TW_SELECT,
        })
        self.fields["images"].widget.attrs.update({
            "class": "w-full rounded-xl border border-slate-200 bg-white px-3 py-2 "
                     "text-sm focus:outline-none focus:ring-2 focus:ring-slate-300",
        })
        self.fields["order"].widget.attrs.update({
            "class": TW_INPUT,
            "type": "number",
            "min": 0,
            "placeholder": "0",
        })
        self.fields["is_active"].widget.attrs.update({
            "class": TW_CHECKBOX,
        })
    
    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise ValidationError("Gallery name is required.")
        return name
    
    def save(self, commit=True):
        """Override save to populate hotel"""
        instance = super().save(commit=False)
        
        if self.hotel:
            instance.hotel = self.hotel
        
        if commit:
            instance.save()
            self.save_m2m()
        
        return instance


class BulkRoomImageUploadForm(forms.Form):
    """Form for bulk uploading multiple room images at once"""
    
    images = MultipleFileField(
        required=True,
        label="Select Images",
        help_text="Select multiple images (JPG, PNG, WebP, max 10MB each)"
    )
    category = forms.ChoiceField(
        choices=RoomImage.IMAGE_CATEGORIES,
        initial="overall",
        widget=forms.Select(attrs={"class": TW_SELECT})
    )
    set_as_primary = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={"class": TW_CHECKBOX}),
        help_text="Set first image as primary for the room"
    )
    
    def clean_images(self):
        """Validate multiple images"""
        images = self.cleaned_data.get("images", [])
        
        if not images:
            raise ValidationError("Please select at least one image.")
        
        if len(images) > 20:
            raise ValidationError("Maximum 20 images per bulk upload.")
        
        for image in images:
            if image.size > 10 * 1024 * 1024:
                raise ValidationError(f"Image {image.name} exceeds 10MB limit.")
        
        return images


class RoomImageFilterForm(forms.Form):
    """Form for filtering room images in admin/list views"""
    
    category = forms.ChoiceField(
        required=False,
        choices=[("", "All Categories")] + list(RoomImage.IMAGE_CATEGORIES),
        widget=forms.Select(attrs={"class": TW_SELECT})
    )
    is_primary = forms.ChoiceField(
        required=False,
        choices=[
            ("", "All Images"),
            ("true", "Primary Only"),
            ("false", "Non-Primary Only"),
        ],
        widget=forms.Select(attrs={"class": TW_SELECT})
    )
    is_featured = forms.ChoiceField(
        required=False,
        choices=[
            ("", "All Images"),
            ("true", "Featured Only"),
            ("false", "Non-Featured Only"),
        ],
        widget=forms.Select(attrs={"class": TW_SELECT})
    )
    is_active = forms.ChoiceField(
        required=False,
        choices=[
            ("", "All Status"),
            ("true", "Active Only"),
            ("false", "Inactive Only"),
        ],
        widget=forms.Select(attrs={"class": TW_SELECT})
    )