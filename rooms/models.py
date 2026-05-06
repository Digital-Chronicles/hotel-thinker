# rooms/models.py

from django.db import models
from hotels.models import Hotel
from decimal import Decimal
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

class RoomType(models.Model):
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="room_types")
    name = models.CharField(max_length=120)  # e.g. Single, Double, Deluxe
    description = models.TextField(blank=True, null=True)
    base_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hotel", "name"], name="uniq_roomtype_name_per_hotel"),
        ]

    def __str__(self):
        return f"{self.name} ({self.hotel.name})"


class Room(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        OCCUPIED = "occupied", "Occupied"
        MAINTENANCE = "maintenance", "Maintenance"
        CLEANING = "cleaning", "Cleaning"

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="rooms")
    room_type = models.ForeignKey(RoomType, on_delete=models.PROTECT, related_name="rooms")

    number = models.CharField(max_length=50)  # e.g. 101, A-01
    floor = models.CharField(max_length=50, blank=True, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AVAILABLE)

    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hotel", "number"], name="uniq_room_number_per_hotel"),
        ]
        indexes = [
            models.Index(fields=["hotel", "status"]),
        ]

    def __str__(self):
        return f"Room {self.number} - {self.hotel.name}"
    

# rooms/models.py
class RoomImage(models.Model):
    """Model for storing room images with categories and ordering"""
    
    IMAGE_CATEGORIES = [
        ('overall', 'Overall View'),
        ('bedroom', 'Bedroom Area'),
        ('bathroom', 'Bathroom'),
        ('view', 'Window/View'),
        ('amenities', 'Amenities'),
        ('seating', 'Seating Area'),
        ('workspace', 'Workspace'),
        ('closet', 'Closet/Storage'),
        ('balcony', 'Balcony/Terrace'),
        ('other', 'Other'),
    ]
    
    # Relationships
    room = models.ForeignKey(
        Room, 
        on_delete=models.CASCADE, 
        related_name="images",
        help_text="Room this image belongs to"
    )
    room_type = models.ForeignKey(
        RoomType, 
        on_delete=models.CASCADE, 
        related_name="images",
        null=True, 
        blank=True,
        help_text="Room type this image represents (for gallery purposes)"
    )
    hotel = models.ForeignKey(
        Hotel, 
        on_delete=models.CASCADE, 
        related_name="room_images",
        help_text="Hotel this image belongs to (denormalized for faster queries)"
    )
    
    # Image data
    image = models.ImageField(
        upload_to='room_images/%Y/%m/%d/',
        help_text="Upload room image (JPG, PNG, WebP recommended)"
    )
    category = models.CharField(
        max_length=50, 
        choices=IMAGE_CATEGORIES, 
        default='overall',
        help_text="Category of the room image"
    )
    
    # Metadata
    title = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text="Image title for display"
    )
    alt_text = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text="SEO alternative text"
    )
    caption = models.TextField(
        blank=True, 
        null=True,
        help_text="Image caption/description"
    )
    
    # Display settings
    order = models.IntegerField(
        default=0, 
        help_text="Display order (lower numbers appear first)"
    )
    is_primary = models.BooleanField(
        default=False, 
        help_text="Set as primary image for this room"
    )
    is_featured = models.BooleanField(
        default=False, 
        help_text="Featured in room gallery/listing"
    )
    
    # Status
    is_active = models.BooleanField(
        default=True, 
        help_text="Whether this image is active and visible"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Image metadata (optional, for optimization)
    file_size = models.IntegerField(
        blank=True, 
        null=True, 
        help_text="File size in bytes"
    )
    width = models.IntegerField(
        blank=True, 
        null=True, 
        help_text="Image width in pixels"
    )
    height = models.IntegerField(
        blank=True, 
        null=True, 
        help_text="Image height in pixels"
    )
    
    class Meta:
        ordering = ['order', '-created_at']
        indexes = [
            models.Index(fields=['room', 'is_primary']),
            models.Index(fields=['room_type', 'is_featured']),
            models.Index(fields=['hotel', 'is_active']),
            models.Index(fields=['category']),
            models.Index(fields=['order']),
        ]
        verbose_name = "Room Image"
        verbose_name_plural = "Room Images"
    
    def __str__(self):
        room_identifier = f"Room {self.room.number}" if self.room else "Unknown Room"
        return f"{room_identifier} - {self.get_category_display()} ({self.order})"
    
    def save(self, *args, **kwargs):
        """Auto-populate hotel from room and handle primary image logic"""
        # Auto-populate hotel from room if not set
        if not self.hotel and self.room:
            self.hotel = self.room.hotel
        
        # If this image is set as primary, unset other primary images for the same room
        if self.is_primary and self.room:
            RoomImage.objects.filter(
                room=self.room,
                is_primary=True
            ).exclude(pk=self.pk).update(is_primary=False)
        
        super().save(*args, **kwargs)
    
    @property
    def thumbnail_url(self):
        """Return thumbnail URL (you can implement with sorl-thumbnail or easy-thumbnails)"""
        if self.image:
            return self.image.url
        return None
    
    @property
    def image_url(self):
        """Return full image URL"""
        if self.image:
            return self.image.url
        return None


class RoomImageGallery(models.Model):
    """Model for grouping room images into galleries"""
    
    name = models.CharField(max_length=255, help_text="Gallery name (e.g., 'Deluxe Suite Views')")
    slug = models.SlugField(max_length=255, blank=True, help_text="URL-friendly name")
    description = models.TextField(blank=True, null=True, help_text="Gallery description")
    
    # Relationships
    hotel = models.ForeignKey(
        Hotel, 
        on_delete=models.CASCADE, 
        related_name="image_galleries",
        help_text="Hotel this gallery belongs to"
    )
    room_type = models.ForeignKey(
        RoomType, 
        on_delete=models.CASCADE, 
        related_name="galleries",
        null=True,
        blank=True,
        help_text="Room type this gallery is for (optional)"
    )
    images = models.ManyToManyField(
        RoomImage, 
        related_name="galleries",
        blank=True,
        help_text="Images in this gallery"
    )
    
    # Display settings
    order = models.IntegerField(default=0, help_text="Display order")
    is_active = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order', 'name']
        indexes = [
            models.Index(fields=['hotel', 'is_active']),
            models.Index(fields=['slug']),
        ]
        verbose_name = "Room Image Gallery"
        verbose_name_plural = "Room Image Galleries"
    
    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.name} ({self.hotel.name})"
    

class AssetCategory(models.Model):
    """Categories for room assets"""
    
    ASSET_TYPES = [
        ('furniture', 'Furniture'),
        ('electronics', 'Electronics'),
        ('appliances', 'Appliances'),
        ('fixtures', 'Fixtures & Fittings'),
        ('linen', 'Linen & Textiles'),
        ('amenities', 'Amenities'),
        ('decor', 'Decor Items'),
        ('security', 'Security Equipment'),
        ('other', 'Other'),
    ]
    
    DEPRECIATION_METHODS = [
        ('straight_line', 'Straight Line'),
        ('declining_balance', 'Declining Balance'),
        ('double_declining', 'Double Declining Balance'),
        ('units_of_production', 'Units of Production'),
        ('none', 'No Depreciation'),
    ]
    
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    asset_type = models.CharField(max_length=50, choices=ASSET_TYPES, default='furniture')
    default_depreciation_method = models.CharField(
        max_length=50, 
        choices=DEPRECIATION_METHODS,
        default='straight_line'
    )
    default_useful_life_years = models.PositiveIntegerField(
        default=5,
        help_text="Default useful life in years"
    )
    default_salvage_value_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=10.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Default salvage value as percentage of purchase price"
    )
    hotel = models.ForeignKey(
        'hotels.Hotel',
        on_delete=models.CASCADE,
        related_name="asset_categories"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        verbose_name_plural = "Asset Categories"
        unique_together = [['hotel', 'name']]
    
    def __str__(self):
        return f"{self.name} ({self.get_asset_type_display()})"


class RoomAsset(models.Model):
    """Assets associated with a room or room type"""
    
    DEPRECIATION_METHODS = AssetCategory.DEPRECIATION_METHODS
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('maintenance', 'Under Maintenance'),
        ('broken', 'Broken/Unusable'),
        ('disposed', 'Disposed'),
        ('stolen', 'Stolen'),
        ('lost', 'Lost'),
    ]
    
    # Relationships
    hotel = models.ForeignKey(
        'hotels.Hotel',
        on_delete=models.CASCADE,
        related_name="room_assets"
    )
    room = models.ForeignKey(
        Room,
        on_delete=models.CASCADE,
        related_name="assets",
        null=True,
        blank=True,
        help_text="Specific room this asset belongs to"
    )
    room_type = models.ForeignKey(
        RoomType,
        on_delete=models.CASCADE,
        related_name="assets",
        null=True,
        blank=True,
        help_text="Room type template (for assets common to all rooms of this type)"
    )
    category = models.ForeignKey(
        AssetCategory,
        on_delete=models.PROTECT,
        related_name="assets"
    )
    
    # Asset details
    name = models.CharField(max_length=200, help_text="Asset name/description")
    serial_number = models.CharField(max_length=100, blank=True, null=True)
    model_number = models.CharField(max_length=100, blank=True, null=True)
    brand = models.CharField(max_length=100, blank=True, null=True)
    
    # Financials
    purchase_date = models.DateField(help_text="Date of purchase")
    purchase_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Original purchase price"
    )
    current_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Current depreciated value"
    )
    
    # Depreciation settings
    depreciation_method = models.CharField(
        max_length=50,
        choices=DEPRECIATION_METHODS,
        default='straight_line'
    )
    useful_life_years = models.PositiveIntegerField(
        default=5,
        help_text="Useful life in years for depreciation"
    )
    salvage_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Estimated salvage/residual value"
    )
    last_depreciation_date = models.DateField(
        null=True,
        blank=True,
        help_text="Last date depreciation was calculated"
    )
    total_depreciation = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Total depreciation accumulated"
    )
    
    # Maintenance tracking
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='active')
    purchase_invoice = models.FileField(
        upload_to='asset_invoices/%Y/%m/',
        blank=True,
        null=True
    )
    warranty_expiry = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-purchase_date', 'name']
        indexes = [
            models.Index(fields=['hotel', 'room']),
            models.Index(fields=['hotel', 'room_type']),
            models.Index(fields=['status']),
            models.Index(fields=['purchase_date']),
        ]
    
    def __str__(self):
        location = self.room.number if self.room else (self.room_type.name if self.room_type else "Template")
        return f"{self.name} - {location} ({self.get_status_display()})"
    
    def calculate_depreciation(self, as_of_date=None):
        """Calculate depreciation up to a given date"""
        if as_of_date is None:
            as_of_date = date.today()
        
        if self.depreciation_method == 'none' or self.status not in ['active', 'maintenance']:
            return 0
        
        if self.last_depreciation_date and self.last_depreciation_date >= as_of_date:
            return 0
        
        # Calculate months since purchase or last depreciation
        start_date = self.last_depreciation_date or self.purchase_date
        if start_date >= as_of_date:
            return 0
        
        months_elapsed = relativedelta(as_of_date, start_date).years * 12 + relativedelta(as_of_date, start_date).months
        
        # Calculate monthly depreciation based on method
        total_life_months = self.useful_life_years * 12
        remaining_value = self.purchase_price - self.total_depreciation
        
        if self.depreciation_method == 'straight_line':
            monthly_depreciation = (self.purchase_price - self.salvage_value) / total_life_months
            depreciation_amount = monthly_depreciation * months_elapsed
            
        elif self.depreciation_method == 'declining_balance':
            rate = 1 - (self.salvage_value / self.purchase_price) ** (1 / self.useful_life_years)
            monthly_rate = 1 - (1 - rate) ** (1/12)
            book_value = self.purchase_price - self.total_depreciation
            depreciation_amount = book_value * (1 - (1 - monthly_rate) ** months_elapsed)
            
        elif self.depreciation_method == 'double_declining':
            straight_rate = 1 / self.useful_life_years
            double_rate = straight_rate * 2
            monthly_rate = 1 - (1 - double_rate) ** (1/12)
            book_value = self.purchase_price - self.total_depreciation
            depreciation_amount = min(
                book_value * (1 - (1 - monthly_rate) ** months_elapsed),
                book_value - self.salvage_value
            )
        else:
            depreciation_amount = 0
        
        # Ensure we don't depreciate below salvage value
        max_depreciation = self.purchase_price - self.salvage_value
        new_total_depreciation = min(
            self.total_depreciation + depreciation_amount,
            max_depreciation
        )
        
        return new_total_depreciation - self.total_depreciation
    
    def update_current_value(self, as_of_date=None):
        """Update the current value based on depreciation"""
        depreciation_amount = self.calculate_depreciation(as_of_date)
        if depreciation_amount > 0:
            self.total_depreciation += depreciation_amount
            self.current_value = self.purchase_price - self.total_depreciation
            self.last_depreciation_date = as_of_date or date.today()
            self.save(update_fields=['current_value', 'total_depreciation', 'last_depreciation_date'])
        return self.current_value
    
    def get_appreciation_potential(self):
        """Calculate potential appreciation for collectible assets"""
        # For assets that might appreciate (art, antiques, etc.)
        if self.category.asset_type in ['decor', 'other']:
            age_years = relativedelta(date.today(), self.purchase_date).years
            # Simple appreciation calculation - can be customized
            appreciation_rate = 0.05  # 5% per year for collectibles
            appreciated_value = self.purchase_price * (1 + appreciation_rate) ** age_years
            return max(0, appreciated_value - self.current_value)
        return 0
    
    def get_annual_depreciation(self):
        """Get annual depreciation amount"""
        if self.depreciation_method == 'none':
            return 0
        
        total_depreciable = self.purchase_price - self.salvage_value
        
        if self.depreciation_method == 'straight_line':
            return total_depreciable / self.useful_life_years
        else:
            # For declining balance methods
            return self.current_value * (1 / self.useful_life_years)
    
    def save(self, *args, **kwargs):
        # Set current value on creation
        if not self.pk:
            self.current_value = self.purchase_price
            self.total_depreciation = 0
        
        # Auto-set room_type from room if not specified
        if self.room and not self.room_type:
            self.room_type = self.room.room_type
        
        super().save(*args, **kwargs)


class RoomLiability(models.Model):
    """Liabilities associated with rooms (loans, maintenance costs, etc.)"""
    
    LIABILITY_TYPES = [
        ('loan', 'Loan/Mortgage'),
        ('maintenance', 'Maintenance Debt'),
        ('renovation', 'Renovation Cost'),
        ('supplier', 'Supplier Debt'),
        ('tax', 'Tax Liability'),
        ('insurance', 'Insurance Premium'),
        ('other', 'Other'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('active', 'Active'),
        ('overdue', 'Overdue'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ]
    
    # Relationships
    hotel = models.ForeignKey(
        'hotels.Hotel',
        on_delete=models.CASCADE,
        related_name="room_liabilities"
    )
    room = models.ForeignKey(
        Room,
        on_delete=models.CASCADE,
        related_name="liabilities",
        null=True,
        blank=True
    )
    room_type = models.ForeignKey(
        RoomType,
        on_delete=models.CASCADE,
        related_name="liabilities",
        null=True,
        blank=True
    )
    
    # Liability details
    name = models.CharField(max_length=200)
    liability_type = models.CharField(max_length=50, choices=LIABILITY_TYPES)
    description = models.TextField(blank=True, null=True)
    
    # Financials
    principal_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    remaining_balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    interest_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Annual interest rate (%)"
    )
    
    # Dates
    start_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    paid_date = models.DateField(null=True, blank=True)
    
    # Payment tracking
    payment_frequency = models.CharField(
        max_length=20,
        choices=[
            ('monthly', 'Monthly'),
            ('quarterly', 'Quarterly'),
            ('annually', 'Annually'),
            ('one_time', 'One Time'),
        ],
        default='monthly'
    )
    monthly_payment = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Calculated monthly payment"
    )
    next_payment_date = models.DateField(null=True, blank=True)
    last_payment_date = models.DateField(null=True, blank=True)
    
    # Status
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    notes = models.TextField(blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-start_date', 'status']
        verbose_name_plural = "Room Liabilities"
        indexes = [
            models.Index(fields=['hotel', 'room']),
            models.Index(fields=['status']),
            models.Index(fields=['due_date']),
        ]
    
    def __str__(self):
        location = self.room.number if self.room else (self.room_type.name if self.room_type else "Hotel Level")
        return f"{self.name} - {location} ({self.get_liability_type_display()})"
    
    def calculate_monthly_payment(self):
        """Calculate monthly payment for loans"""
        if self.liability_type != 'loan' or self.interest_rate == 0:
            return self.principal_amount / 12  # Simple division for non-interest bearing
        
        monthly_rate = (self.interest_rate / 100) / 12
        # Assume 5 years default term if not specified
        term_months = 60
        
        if monthly_rate > 0:
            payment = self.principal_amount * (monthly_rate * (1 + monthly_rate) ** term_months) / ((1 + monthly_rate) ** term_months - 1)
        else:
            payment = self.principal_amount / term_months
        
        return payment
    
    def update_balance(self, payment_amount, payment_date=None):
        """Update remaining balance after payment"""
        if payment_date is None:
            payment_date = date.today()
        
        self.remaining_balance -= payment_amount
        self.last_payment_date = payment_date
        
        if self.remaining_balance <= 0:
            self.remaining_balance = 0
            self.status = 'paid'
            self.paid_date = payment_date
        
        self.save(update_fields=['remaining_balance', 'last_payment_date', 'status', 'paid_date'])
    
    def is_overdue(self):
        """Check if liability is overdue"""
        if self.status in ['paid', 'cancelled']:
            return False
        if self.due_date and self.due_date < date.today():
            return True
        if self.next_payment_date and self.next_payment_date < date.today():
            return True
        return False
    
    def save(self, *args, **kwargs):
        if not self.pk:
            self.remaining_balance = self.principal_amount
            self.monthly_payment = self.calculate_monthly_payment()
        
        # Update status for overdue
        if self.is_overdue() and self.status not in ['paid', 'cancelled']:
            self.status = 'overdue'
        
        super().save(*args, **kwargs)


class AssetDepreciationSchedule(models.Model):
    """Historical record of asset depreciation calculations"""
    
    asset = models.ForeignKey(RoomAsset, on_delete=models.CASCADE, related_name="depreciation_schedule")
    calculation_date = models.DateField(auto_now_add=True)
    period_start = models.DateField()
    period_end = models.DateField()
    depreciation_amount = models.DecimalField(max_digits=12, decimal_places=2)
    accumulated_depreciation = models.DecimalField(max_digits=12, decimal_places=2)
    book_value_before = models.DecimalField(max_digits=12, decimal_places=2)
    book_value_after = models.DecimalField(max_digits=12, decimal_places=2)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-calculation_date']
        unique_together = [['asset', 'period_start', 'period_end']]
    
    def __str__(self):
        return f"{self.asset.name} - {self.period_start} to {self.period_end}"


class LiabilityPayment(models.Model):
    """Track individual payments against liabilities"""
    
    liability = models.ForeignKey(RoomLiability, on_delete=models.CASCADE, related_name="payments")
    payment_date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reference_number = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-payment_date']
    
    def __str__(self):
        return f"Payment of {self.amount} for {self.liability.name} on {self.payment_date}"
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update liability balance
        self.liability.update_balance(self.amount, self.payment_date)

