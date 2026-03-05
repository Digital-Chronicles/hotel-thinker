from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django.core.validators import URLValidator


class Hotel(models.Model):
    """Hotel/Central entity for multi-tenant architecture"""
    
    name = models.CharField(max_length=255, unique=True, db_index=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    
    # Contact information
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=30, blank=True, null=True)
    website = models.URLField(blank=True, null=True, validators=[URLValidator()])
    
    # Address
    address_line1 = models.CharField(max_length=255, blank=True, null=True)
    address_line2 = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    postal_code = models.CharField(max_length=20, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    
    # Business details
    tax_number = models.CharField(max_length=50, blank=True, null=True)
    business_registration = models.CharField(max_length=50, blank=True, null=True)
    
    # Branding
    logo = models.ImageField(upload_to='hotel_logos/', blank=True, null=True)
    favicon = models.ImageField(upload_to='hotel_favicons/', blank=True, null=True)
    
    # Status
    is_active = models.BooleanField(default=True, db_index=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['slug']),
            models.Index(fields=['is_active']),
        ]
        ordering = ['name']
        verbose_name = _("Hotel")
        verbose_name_plural = _("Hotels")

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or "hotel"
            slug = base
            counter = 1
            while Hotel.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                counter += 1
                slug = f"{base}-{counter}"
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    @property
    def full_address(self):
        """Return formatted full address"""
        parts = [self.address_line1, self.address_line2, self.city, self.state, self.postal_code, self.country]
        return ', '.join(filter(None, parts))


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
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Hotel Setting")
        verbose_name_plural = _("Hotel Settings")

    def __str__(self):
        return f"Settings for {self.hotel.name}"