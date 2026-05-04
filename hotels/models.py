# hotels/models.py

from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django.core.validators import URLValidator, MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models.signals import pre_save
from django.dispatch import receiver
import uuid


class HotelChain(models.Model):
    """Hotel chain/group for managing multiple hotels under one brand"""
    
    name = models.CharField(max_length=255, unique=True, db_index=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    logo = models.ImageField(upload_to='hotel_chains/logos/', blank=True, null=True)
    website = models.URLField(blank=True, null=True, validators=[URLValidator()])
    description = models.TextField(blank=True, null=True)
    headquarters_address = models.TextField(blank=True, null=True)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        verbose_name = _("Hotel Chain")
        verbose_name_plural = _("Hotel Chains")
    
    def save(self, *args, **kwargs):
        if not self.slug or self._state.adding:
            self.slug = self.generate_unique_slug()
        elif self.pk:
            # Check if name changed
            original = HotelChain.objects.get(pk=self.pk)
            if original.name != self.name:
                self.slug = self.generate_unique_slug()
        super().save(*args, **kwargs)
    
    def generate_unique_slug(self):
        """Generate unique slug for hotel chain"""
        base_slug = slugify(self.name)
        slug = base_slug
        counter = 1
        while HotelChain.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        return slug
    
    def __str__(self):
        return self.name


class HotelCategory(models.Model):
    """Category/classification of hotels (Luxury, Budget, Boutique, etc.)"""
    
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True)
    description = models.TextField(blank=True, null=True)
    star_rating_min = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    star_rating_max = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    icon = models.CharField(max_length=50, blank=True, null=True, help_text="Font awesome icon class")
    
    class Meta:
        verbose_name_plural = _("Hotel Categories")
        ordering = ['name']
    
    def save(self, *args, **kwargs):
        if not self.slug or self._state.adding:
            self.slug = slugify(self.name)
        elif self.pk:
            # Check if name changed
            original = HotelCategory.objects.get(pk=self.pk)
            if original.name != self.name:
                self.slug = slugify(self.name)
        super().save(*args, **kwargs)
    
    def __str__(self):
        return self.name


class Hotel(models.Model):
    """Hotel/Central entity for multi-tenant architecture"""
    
    # Basic Information
    name = models.CharField(max_length=255, unique=True, db_index=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    
    # Relationships
    hotel_chain = models.ForeignKey(
        HotelChain,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hotels"
    )
    category = models.ForeignKey(
        HotelCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hotels"
    )
    
    # Contact information
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=30, blank=True, null=True)
    phone_alt = models.CharField(max_length=30, blank=True, null=True, verbose_name=_("Alternative Phone"))
    whatsapp = models.CharField(max_length=30, blank=True, null=True)
    website = models.URLField(blank=True, null=True, validators=[URLValidator()])
    
    # Address Details
    address_line1 = models.CharField(max_length=255, blank=True, null=True)
    address_line2 = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    state = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    postal_code = models.CharField(max_length=20, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    
    # Geographic Coordinates
    latitude = models.DecimalField(
        max_digits=10, 
        decimal_places=7, 
        blank=True, 
        null=True,
        help_text=_("Latitude for map location")
    )
    longitude = models.DecimalField(
        max_digits=10, 
        decimal_places=7, 
        blank=True, 
        null=True,
        help_text=_("Longitude for map location")
    )
    
    # Business details
    tax_number = models.CharField(max_length=50, blank=True, null=True)
    business_registration = models.CharField(max_length=50, blank=True, null=True)
    year_established = models.IntegerField(null=True, blank=True)
    number_of_employees = models.IntegerField(null=True, blank=True)
    
    # Hotel Details
    star_rating = models.DecimalField(
        max_digits=3, 
        decimal_places=1, 
        blank=True, 
        null=True,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        help_text=_("Hotel star rating (0-5)")
    )
    total_rooms = models.IntegerField(default=0, help_text=_("Total number of rooms"))
    total_floors = models.IntegerField(default=1, help_text=_("Number of floors"))
    
    # Descriptions
    short_description = models.CharField(
        max_length=500, 
        blank=True, 
        null=True,
        help_text=_("Brief description for listings")
    )
    description = models.TextField(
        blank=True, 
        null=True,
        help_text=_("Detailed hotel description")
    )
    meta_description = models.CharField(
        max_length=160, 
        blank=True, 
        null=True,
        help_text=_("SEO meta description")
    )
    meta_keywords = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text=_("SEO keywords")
    )
    
    # Branding
    logo = models.ImageField(upload_to='hotel_logos/', blank=True, null=True)
    logo_light = models.ImageField(upload_to='hotel_logos/', blank=True, null=True)
    favicon = models.ImageField(upload_to='hotel_favicons/', blank=True, null=True)
    cover_image = models.ImageField(upload_to='hotel_covers/', blank=True, null=True)
    brand_color_primary = models.CharField(
        max_length=7, 
        blank=True, 
        null=True,
        help_text=_("Primary brand color (hex)")
    )
    brand_color_secondary = models.CharField(
        max_length=7, 
        blank=True, 
        null=True,
        help_text=_("Secondary brand color (hex)")
    )
    
    # Status and Flags
    is_active = models.BooleanField(default=True, db_index=True)
    is_featured = models.BooleanField(default=False, help_text=_("Featured on homepage"))
    is_verified = models.BooleanField(default=False, help_text=_("Verified hotel"))
    is_published = models.BooleanField(default=True, db_index=True)
    
    # Social Media
    facebook_url = models.URLField(blank=True, null=True, validators=[URLValidator()])
    instagram_url = models.URLField(blank=True, null=True, validators=[URLValidator()])
    twitter_url = models.URLField(blank=True, null=True, validators=[URLValidator()])
    linkedin_url = models.URLField(blank=True, null=True, validators=[URLValidator()])
    youtube_url = models.URLField(blank=True, null=True, validators=[URLValidator()])
    tripadvisor_url = models.URLField(blank=True, null=True, validators=[URLValidator()])
    
    # Business Hours
    check_in_time = models.TimeField(default="14:00")
    check_out_time = models.TimeField(default="11:00")
    reception_open_time = models.TimeField(default="00:00")
    reception_close_time = models.TimeField(default="23:59")
    
    # Policies
    cancellation_policy = models.TextField(blank=True, null=True)
    payment_policy = models.TextField(blank=True, null=True)
    house_rules = models.TextField(blank=True, null=True)
    child_policy = models.TextField(blank=True, null=True)
    pet_policy = models.TextField(blank=True, null=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_hotels'
    )
    
    class Meta:
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['slug']),
            models.Index(fields=['is_active']),
            models.Index(fields=['is_published']),
            models.Index(fields=['city', 'country']),
            models.Index(fields=['star_rating']),
            models.Index(fields=['latitude', 'longitude']),
        ]
        ordering = ['name']
        verbose_name = _("Hotel")
        verbose_name_plural = _("Hotels")

    def save(self, *args, **kwargs):
        # Check if this is a new instance or if name has changed
        if self._state.adding:
            # New hotel, generate slug
            self.slug = self.generate_unique_slug()
        else:
            # Existing hotel, check if name changed
            try:
                original = Hotel.objects.get(pk=self.pk)
                if original.name != self.name:
                    # Name changed, generate new slug
                    self.slug = self.generate_unique_slug()
                    # Optionally: Store old slug for redirect handling
                    self._old_slug = original.slug
            except Hotel.DoesNotExist:
                # This shouldn't happen, but just in case
                self.slug = self.generate_unique_slug()
        
        super().save(*args, **kwargs)

    def generate_unique_slug(self):
        """Generate unique slug for hotel"""
        base_slug = slugify(self.name) or "hotel"
        slug = base_slug
        counter = 1
        # Keep the slug under 255 characters
        while Hotel.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            suffix = f"-{counter}"
            # Truncate base slug if needed to keep total length under 255
            max_base_length = 255 - len(suffix)
            truncated_base = base_slug[:max_base_length]
            slug = f"{truncated_base}{suffix}"
            counter += 1
        return slug

    def __str__(self):
        return self.name

    @property
    def full_address(self):
        """Return formatted full address"""
        parts = [self.address_line1, self.address_line2, self.city, self.state, self.postal_code, self.country]
        return ', '.join(filter(None, parts))
    
    @property
    def location_coordinates(self):
        """Return coordinates as tuple"""
        if self.latitude and self.longitude:
            return (float(self.latitude), float(self.longitude))
        return None
    
    @property
    def star_display(self):
        """Return star rating as integer for display"""
        if self.star_rating:
            return int(self.star_rating)
        return 0


# Signal to handle slug updates and create redirects
@receiver(pre_save, sender=Hotel)
def hotel_pre_save_handler(sender, instance, **kwargs):
    """Handle slug changes and store old slug for redirects"""
    if not instance._state.adding and instance.pk:
        try:
            old_instance = sender.objects.get(pk=instance.pk)
            if old_instance.slug != instance.slug:
                # You can store this in a Redirect model if you have one
                instance._old_slug = old_instance.slug
        except sender.DoesNotExist:
            pass


class HotelAmenity(models.Model):
    """Amenities offered by hotels"""
    
    AMENITY_CATEGORIES = [
        ('general', _('General')),
        ('room', _('Room')),
        ('bathroom', _('Bathroom')),
        ('food_drink', _('Food & Drink')),
        ('internet', _('Internet')),
        ('entertainment', _('Entertainment')),
        ('services', _('Services')),
        ('business', _('Business')),
        ('safety', _('Safety & Security')),
        ('accessibility', _('Accessibility')),
        ('parking', _('Parking & Transport')),
        ('pool_spa', _('Pool & Spa')),
        ('fitness', _('Fitness')),
        ('family', _('Family Friendly')),
        ('outdoor', _('Outdoor')),
    ]
    
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True)
    category = models.CharField(max_length=50, choices=AMENITY_CATEGORIES, default='general')
    icon = models.CharField(max_length=50, blank=True, null=True, help_text=_("Font awesome icon class"))
    is_paid = models.BooleanField(default=False, help_text=_("Whether this amenity requires additional payment"))
    description = models.CharField(max_length=255, blank=True, null=True)
    
    class Meta:
        verbose_name_plural = _("Amenities")
        ordering = ['category', 'name']
    
    def save(self, *args, **kwargs):
        if not self.slug or self._state.adding:
            self.slug = slugify(self.name)
        elif self.pk:
            # Check if name changed
            original = HotelAmenity.objects.get(pk=self.pk)
            if original.name != self.name:
                self.slug = slugify(self.name)
        super().save(*args, **kwargs)
    
    def __str__(self):
        return self.name


class HotelAmenityMapping(models.Model):
    """Mapping table for hotel amenities with additional details"""
    
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='amenity_mappings')
    amenity = models.ForeignKey(HotelAmenity, on_delete=models.CASCADE, related_name='hotel_mappings')
    is_available = models.BooleanField(default=True)
    additional_info = models.CharField(max_length=255, blank=True, null=True)
    charge_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    class Meta:
        unique_together = ['hotel', 'amenity']
        verbose_name = _("Hotel Amenity")
        verbose_name_plural = _("Hotel Amenities")
    
    def __str__(self):
        return f"{self.hotel.name} - {self.amenity.name}"


class HotelImage(models.Model):
    """Model for handling hotel images with categories"""
    
    IMAGE_CATEGORIES = [
        ('exterior', _('Exterior')),
        ('interior', _('Interior')),
        ('lobby', _('Lobby')),
        ('reception', _('Reception')),
        ('room', _('Room')),
        ('suite', _('Suite')),
        ('bathroom', _('Bathroom')),
        ('restaurant', _('Restaurant')),
        ('bar', _('Bar/Lounge')),
        ('pool', _('Pool')),
        ('spa', _('Spa')),
        ('gym', _('Gym/Fitness')),
        ('conference', _('Conference/Banquet')),
        ('event', _('Event Space')),
        ('parking', _('Parking')),
        ('view', _('View')),
        ('food', _('Food & Dining')),
        ('other', _('Other')),
    ]
    
    hotel = models.ForeignKey(
        Hotel,
        on_delete=models.CASCADE,
        related_name='images'
    )
    
    image = models.ImageField(upload_to='hotel_gallery/%Y/%m/%d/')
    category = models.CharField(max_length=50, choices=IMAGE_CATEGORIES, default='other')
    title = models.CharField(max_length=255, blank=True, null=True)
    alt_text = models.CharField(max_length=255, blank=True, null=True, help_text=_("SEO alt text"))
    caption = models.CharField(max_length=500, blank=True, null=True)
    
    # Ordering and display
    order = models.IntegerField(default=0, help_text=_("Display order (lower numbers first)"))
    is_primary = models.BooleanField(default=False, help_text=_("Set as primary image for this category"))
    is_featured = models.BooleanField(default=False, help_text=_("Featured in gallery"))
    
    # Metadata
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    file_size = models.IntegerField(blank=True, null=True, help_text=_("File size in bytes"))
    
    class Meta:
        ordering = ['order', '-uploaded_at']
        indexes = [
            models.Index(fields=['hotel', 'category']),
            models.Index(fields=['is_primary']),
            models.Index(fields=['is_featured']),
        ]
        verbose_name = _("Hotel Image")
        verbose_name_plural = _("Hotel Images")
    
    def __str__(self):
        return f"{self.hotel.name} - {self.get_category_display()} - {self.order}"
    
    def save(self, *args, **kwargs):
        # If this image is set as primary, unset other primary images in same category
        if self.is_primary:
            HotelImage.objects.filter(
                hotel=self.hotel,
                category=self.category,
                is_primary=True
            ).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)


class HotelDocument(models.Model):
    """Legal and business documents for hotels"""
    
    DOCUMENT_TYPES = [
        ('registration', _('Business Registration')),
        ('tax_certificate', _('Tax Certificate')),
        ('license', _('Operating License')),
        ('insurance', _('Insurance Certificate')),
        ('contract', _('Contract')),
        ('identification', _('Identification')),
        ('other', _('Other')),
    ]
    
    hotel = models.ForeignKey(
        Hotel,
        on_delete=models.CASCADE,
        related_name='documents'
    )
    
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPES)
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to='hotel_documents/%Y/%m/%d/')
    description = models.TextField(blank=True, null=True)
    
    # Verification
    is_verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_documents'
    )
    verified_at = models.DateTimeField(blank=True, null=True)
    
    # Validity
    issue_date = models.DateField(blank=True, null=True)
    expiry_date = models.DateField(blank=True, null=True)
    
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = _("Hotel Document")
        verbose_name_plural = _("Hotel Documents")
    
    def __str__(self):
        return f"{self.hotel.name} - {self.get_document_type_display()}"
    
    @property
    def is_expired(self):
        if self.expiry_date:
            return self.expiry_date < timezone.now().date()
        return False


class HotelReview(models.Model):
    """Customer reviews and ratings for hotels"""
    
    hotel = models.ForeignKey(
        Hotel,
        on_delete=models.CASCADE,
        related_name='reviews'
    )
    
    guest_name = models.CharField(max_length=255)
    guest_email = models.EmailField()
    
    # Ratings (1-5)
    overall_rating = models.DecimalField(max_digits=2, decimal_places=1, validators=[MinValueValidator(1), MaxValueValidator(5)])
    cleanliness_rating = models.DecimalField(max_digits=2, decimal_places=1, validators=[MinValueValidator(1), MaxValueValidator(5)], null=True, blank=True)
    comfort_rating = models.DecimalField(max_digits=2, decimal_places=1, validators=[MinValueValidator(1), MaxValueValidator(5)], null=True, blank=True)
    location_rating = models.DecimalField(max_digits=2, decimal_places=1, validators=[MinValueValidator(1), MaxValueValidator(5)], null=True, blank=True)
    staff_rating = models.DecimalField(max_digits=2, decimal_places=1, validators=[MinValueValidator(1), MaxValueValidator(5)], null=True, blank=True)
    facilities_rating = models.DecimalField(max_digits=2, decimal_places=1, validators=[MinValueValidator(1), MaxValueValidator(5)], null=True, blank=True)
    value_rating = models.DecimalField(max_digits=2, decimal_places=1, validators=[MinValueValidator(1), MaxValueValidator(5)], null=True, blank=True)
    
    # Review content
    title = models.CharField(max_length=255)
    review_text = models.TextField()
    pros = models.TextField(blank=True, null=True, help_text=_("What did you like?"))
    cons = models.TextField(blank=True, null=True, help_text=_("What could be improved?"))
    
    # Stay details
    stay_date_from = models.DateField()
    stay_date_to = models.DateField()
    room_number = models.CharField(max_length=50, blank=True, null=True)
    
    # Verification
    is_verified_stay = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=False, help_text=_("Approved for public display"))
    
    # Response from hotel
    hotel_response = models.TextField(blank=True, null=True)
    hotel_response_date = models.DateTimeField(blank=True, null=True)
    responded_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='review_responses'
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['hotel', 'is_approved']),
            models.Index(fields=['overall_rating']),
            models.Index(fields=['-created_at']),
        ]
        verbose_name = _("Hotel Review")
        verbose_name_plural = _("Hotel Reviews")
    
    def __str__(self):
        return f"{self.hotel.name} - {self.guest_name} - {self.overall_rating}★"
    
    @property
    def average_rating(self):
        ratings = [
            self.cleanliness_rating,
            self.comfort_rating,
            self.location_rating,
            self.staff_rating,
            self.facilities_rating,
            self.value_rating
        ]
        valid_ratings = [r for r in ratings if r is not None]
        if valid_ratings:
            return sum(valid_ratings) / len(valid_ratings)
        return self.overall_rating


class HotelContactPerson(models.Model):
    """Contact persons for hotel management"""
    
    hotel = models.ForeignKey(
        Hotel,
        on_delete=models.CASCADE,
        related_name='contact_persons'
    )
    
    POSITION_CHOICES = [
        ('general_manager', _('General Manager')),
        ('reservation_manager', _('Reservation Manager')),
        ('front_office_manager', _('Front Office Manager')),
        ('sales_manager', _('Sales Manager')),
        ('owner', _('Owner')),
        ('other', _('Other')),
    ]
    
    name = models.CharField(max_length=255)
    position = models.CharField(max_length=50, choices=POSITION_CHOICES)
    email = models.EmailField()
    phone = models.CharField(max_length=30)
    phone_alt = models.CharField(max_length=30, blank=True, null=True)
    is_primary = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-is_primary', 'name']
        verbose_name = _("Contact Person")
        verbose_name_plural = _("Contact Persons")
    
    def save(self, *args, **kwargs):
        if self.is_primary:
            HotelContactPerson.objects.filter(
                hotel=self.hotel,
                is_primary=True
            ).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.name} - {self.get_position_display()} ({self.hotel.name})"


class HotelBankDetail(models.Model):
    """Bank account details for hotel payments"""
    
    hotel = models.ForeignKey(
        Hotel,
        on_delete=models.CASCADE,
        related_name='bank_details'
    )
    
    bank_name = models.CharField(max_length=255)
    account_holder_name = models.CharField(max_length=255)
    account_number = models.CharField(max_length=100)
    routing_number = models.CharField(max_length=100, blank=True, null=True)
    swift_code = models.CharField(max_length=20, blank=True, null=True)
    iban = models.CharField(max_length=50, blank=True, null=True)
    is_primary = models.BooleanField(default=False)
    
    class Meta:
        verbose_name = _("Bank Detail")
        verbose_name_plural = _("Bank Details")
    
    def save(self, *args, **kwargs):
        if self.is_primary:
            HotelBankDetail.objects.filter(
                hotel=self.hotel,
                is_primary=True
            ).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.bank_name} - {self.account_holder_name} ({self.hotel.name})"


class HotelSetting(models.Model):
    """Hotel-specific settings and configuration"""
    
    hotel = models.OneToOneField(
        Hotel,
        on_delete=models.CASCADE,
        related_name="settings"
    )
    
    # About and description
    about_description = models.TextField(blank=True, null=True)
    short_description = models.CharField(max_length=500, blank=True, null=True)
    
    # Contact information
    address = models.CharField(max_length=255, blank=True, null=True)
    phone_number = models.CharField(max_length=30, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    emergency_contact = models.CharField(max_length=30, blank=True, null=True)
    
    # Branding
    logo = models.ImageField(upload_to="hotel_logos/", blank=True, null=True)
    logo_light = models.ImageField(upload_to="hotel_logos/", blank=True, null=True)
    favicon = models.ImageField(upload_to="hotel_favicons/", blank=True, null=True)
    brand_color = models.CharField(max_length=7, blank=True, null=True, help_text=_("Hex color code"))
    
    # Social media
    instagram = models.CharField(max_length=3060, blank=True, null=True)
    twitter = models.CharField(max_length=3060, blank=True, null=True)
    facebook = models.CharField(max_length=3060, blank=True, null=True)
    linkedin = models.CharField(max_length=3060, blank=True, null=True)
    youtube = models.CharField(max_length=3060, blank=True, null=True)
    
    # Business hours
    check_in_time = models.TimeField(default="14:00")
    check_out_time = models.TimeField(default="11:00")
    reception_open_time = models.TimeField(default="00:00")
    reception_close_time = models.TimeField(default="23:59")
    
    # Policies
    cancellation_policy = models.TextField(blank=True, null=True)
    payment_policy = models.TextField(blank=True, null=True)
    house_rules = models.TextField(blank=True, null=True)
    
    # Tax settings
    default_tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_number = models.CharField(max_length=50, blank=True, null=True)
    
    # Currency
    currency = models.CharField(max_length=3, default='USD')
    currency_symbol = models.CharField(max_length=5, default='$')
    
    # API keys
    google_maps_api_key = models.CharField(max_length=3060, blank=True, null=True)
    payment_gateway_key = models.CharField(max_length=3060, blank=True, null=True)
    payment_gateway_secret = models.CharField(max_length=3060, blank=True, null=True)
    sms_api_key = models.CharField(max_length=3060, blank=True, null=True)
    email_api_key = models.CharField(max_length=3060, blank=True, null=True)
    
    # Features
    enable_online_booking = models.BooleanField(default=True)
    enable_restaurant_ordering = models.BooleanField(default=True)
    enable_loyalty_program = models.BooleanField(default=False)
    
    # Notification Settings
    send_booking_confirmation_email = models.BooleanField(default=True)
    send_booking_confirmation_sms = models.BooleanField(default=False)
    send_checkin_reminder = models.BooleanField(default=True)
    send_checkout_reminder = models.BooleanField(default=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Hotel Setting")
        verbose_name_plural = _("Hotel Settings")

    def __str__(self):
        return f"Settings for {self.hotel.name}"