# rooms/models.py

from django.db import models
from hotels.models import Hotel


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