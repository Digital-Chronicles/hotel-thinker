# hotels/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import (
    Hotel, HotelChain, HotelCategory, HotelSetting, 
    HotelImage, HotelDocument, HotelReview, 
    HotelContactPerson, HotelBankDetail, HotelAmenity,
    HotelAmenityMapping
)


@admin.register(HotelChain)
class HotelChainAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "hotels_count", "created_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at", "updated_at")
    ordering = ("name",)
    
    fieldsets = (
        ("Basic Information", {
            "fields": ("name", "slug", "logo", "website", "description")
        }),
        ("Address", {
            "fields": ("headquarters_address",)
        }),
        ("Status", {
            "fields": ("is_active",)
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
    
    def hotels_count(self, obj):
        count = obj.hotels.count()
        url = reverse("admin:hotels_hotel_changelist") + f"?hotel_chain__id={obj.id}"
        return format_html('<a href="{}">{} Hotels</a>', url, count)
    hotels_count.short_description = "Hotels"


@admin.register(HotelCategory)
class HotelCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "star_rating_range", "icon_display", "hotels_count")
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("name",)
    
    fieldsets = (
        ("Basic Information", {
            "fields": ("name", "slug", "description", "icon")
        }),
        ("Star Rating Range", {
            "fields": ("star_rating_min", "star_rating_max"),
            "description": "Define the typical star rating range for this category"
        }),
    )
    
    def star_rating_range(self, obj):
        if obj.star_rating_min and obj.star_rating_max:
            return f"{obj.star_rating_min} - {obj.star_rating_max} ★"
        elif obj.star_rating_min:
            return f"{obj.star_rating_min}+ ★"
        elif obj.star_rating_max:
            return f"Up to {obj.star_rating_max} ★"
        return "Not specified"
    star_rating_range.short_description = "Star Rating Range"
    
    def icon_display(self, obj):
        if obj.icon:
            return format_html('<i class="{}"></i> {}', obj.icon, obj.icon)
        return "-"
    icon_display.short_description = "Icon"
    
    def hotels_count(self, obj):
        count = obj.hotels.count()
        url = reverse("admin:hotels_hotel_changelist") + f"?category__id={obj.id}"
        return format_html('<a href="{}">{} Hotels</a>', url, count)
    hotels_count.short_description = "Hotels"


@admin.register(Hotel)
class HotelAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "hotel_chain_display", "city", "country", 
                   "star_rating_display", "is_active", "is_verified", "is_featured", "total_rooms")
    list_filter = ("is_active", "is_verified", "is_featured", "is_published", 
                  "country", "city", "star_rating", "hotel_chain", "category")
    search_fields = ("name", "slug", "email", "phone", "city", "country", "address_line1")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at", "updated_at", "slug")
    ordering = ("name",)
    list_editable = ("is_active", "is_verified", "is_featured")
    list_per_page = 25
    
    fieldsets = (
        ("Basic Information", {
            "fields": ("name", "slug", "hotel_chain", "category", "star_rating", 
                      "total_rooms", "total_floors")
        }),
        ("Contact Information", {
            "fields": ("email", "phone", "phone_alt", "whatsapp", "website")
        }),
        ("Address & Location", {
            "fields": ("address_line1", "address_line2", "city", "state", 
                      "postal_code", "country", "latitude", "longitude"),
            "classes": ("wide",)
        }),
        ("Business Details", {
            "fields": ("tax_number", "business_registration", "year_established", 
                      "number_of_employees"),
            "classes": ("collapse",)
        }),
        ("Descriptions", {
            "fields": ("short_description", "description", "meta_description", "meta_keywords"),
        }),
        ("Branding", {
            "fields": ("logo", "logo_light", "favicon", "cover_image", 
                      "brand_color_primary", "brand_color_secondary"),
            "classes": ("collapse",)
        }),
        ("Social Media", {
            "fields": ("facebook_url", "instagram_url", "twitter_url", 
                      "linkedin_url", "youtube_url", "tripadvisor_url"),
            "classes": ("collapse",)
        }),
        ("Business Hours & Policies", {
            "fields": ("check_in_time", "check_out_time", "reception_open_time", 
                      "reception_close_time", "cancellation_policy", "payment_policy", 
                      "house_rules", "child_policy", "pet_policy"),
            "classes": ("collapse",)
        }),
        ("Status", {
            "fields": ("is_active", "is_featured", "is_verified", "is_published", "created_by")
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
    
    def hotel_chain_display(self, obj):
        if obj.hotel_chain:
            return format_html('<a href="{}">{}</a>', 
                             reverse("admin:hotels_hotelchain_change", args=[obj.hotel_chain.id]),
                             obj.hotel_chain.name)
        return "-"
    hotel_chain_display.short_description = "Hotel Chain"
    
    def star_rating_display(self, obj):
        if obj.star_rating:
            stars = "★" * int(obj.star_rating)
            return format_html('<span style="color: #fbbf24;">{}</span> ({})', stars, obj.star_rating)
        return "-"
    star_rating_display.short_description = "Star Rating"
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('hotel_chain', 'category')
    
    actions = ['make_active', 'make_inactive', 'make_verified', 'make_unverified', 'make_featured', 'make_unfeatured']
    
    def make_active(self, request, queryset):
        queryset.update(is_active=True)
    make_active.short_description = "Mark selected hotels as active"
    
    def make_inactive(self, request, queryset):
        queryset.update(is_active=False)
    make_inactive.short_description = "Mark selected hotels as inactive"
    
    def make_verified(self, request, queryset):
        queryset.update(is_verified=True)
    make_verified.short_description = "Mark selected hotels as verified"
    
    def make_unverified(self, request, queryset):
        queryset.update(is_verified=False)
    make_unverified.short_description = "Mark selected hotels as unverified"
    
    def make_featured(self, request, queryset):
        queryset.update(is_featured=True)
    make_featured.short_description = "Mark selected hotels as featured"
    
    def make_unfeatured(self, request, queryset):
        queryset.update(is_featured=False)
    make_unfeatured.short_description = "Mark selected hotels as unfeatured"


@admin.register(HotelSetting)
class HotelSettingAdmin(admin.ModelAdmin):
    list_display = ("hotel_link", "phone_number", "email", "currency", 
                   "enable_online_booking", "updated_at")
    search_fields = ("hotel__name", "phone_number", "email", "address")
    ordering = ("hotel__name",)
    readonly_fields = ("created_at", "updated_at")
    
    fieldsets = (
        ("About", {
            "fields": ("short_description", "about_description")
        }),
        ("Contact Information", {
            "fields": ("address", "phone_number", "email", "emergency_contact")
        }),
        ("Branding", {
            "fields": ("brand_color", "logo", "logo_light", "favicon"),
            "classes": ("collapse",)
        }),
        ("Business Hours", {
            "fields": ("check_in_time", "check_out_time", "reception_open_time", "reception_close_time"),
            "classes": ("collapse",)
        }),
        ("Policies", {
            "fields": ("cancellation_policy", "payment_policy", "house_rules"),
            "classes": ("collapse",)
        }),
        ("Tax & Currency", {
            "fields": ("default_tax_rate", "tax_number", "currency", "currency_symbol"),
            "classes": ("collapse",)
        }),
        ("Social Media", {
            "fields": ("instagram", "twitter", "facebook", "linkedin", "youtube"),
            "classes": ("collapse",)
        }),
        ("API Keys", {
            "fields": ("google_maps_api_key", "payment_gateway_key", 
                      "payment_gateway_secret", "sms_api_key", "email_api_key"),
            "classes": ("collapse",)
        }),
        ("Features", {
            "fields": ("enable_online_booking", "enable_restaurant_ordering", "enable_loyalty_program")
        }),
        ("Notifications", {
            "fields": ("send_booking_confirmation_email", "send_booking_confirmation_sms",
                      "send_checkin_reminder", "send_checkout_reminder"),
            "classes": ("collapse",)
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
    
    def hotel_link(self, obj):
        return format_html('<a href="{}">{}</a>', 
                         reverse("admin:hotels_hotel_change", args=[obj.hotel.id]),
                         obj.hotel.name)
    hotel_link.short_description = "Hotel"


@admin.register(HotelImage)
class HotelImageAdmin(admin.ModelAdmin):
    list_display = ("thumbnail_preview", "hotel_link", "category", "order", 
                   "is_primary", "is_featured", "uploaded_at")
    list_filter = ("category", "is_primary", "is_featured", "uploaded_at")
    search_fields = ("hotel__name", "title", "alt_text", "caption")
    readonly_fields = ("uploaded_at", "updated_at")
    ordering = ("hotel", "order", "-uploaded_at")
    list_editable = ("order", "is_primary", "is_featured")
    
    fieldsets = (
        ("Image Information", {
            "fields": ("hotel", "image", "category", "title", "alt_text", "caption")
        }),
        ("Display Settings", {
            "fields": ("order", "is_primary", "is_featured")
        }),
        ("Metadata", {
            "fields": ("uploaded_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
    
    def thumbnail_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="50" height="50" style="object-fit: cover; border-radius: 4px;" />', 
                             obj.image.url)
        return "No Image"
    thumbnail_preview.short_description = "Preview"
    
    def hotel_link(self, obj):
        return format_html('<a href="{}">{}</a>', 
                         reverse("admin:hotels_hotel_change", args=[obj.hotel.id]),
                         obj.hotel.name)
    hotel_link.short_description = "Hotel"


@admin.register(HotelDocument)
class HotelDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "hotel_link", "document_type", "is_verified", 
                   "expiry_status", "issue_date", "expiry_date")
    list_filter = ("document_type", "is_verified", "issue_date", "expiry_date")
    search_fields = ("title", "hotel__name", "description")
    readonly_fields = ("uploaded_at", "updated_at", "verified_at")
    ordering = ("-uploaded_at",)
    
    fieldsets = (
        ("Document Information", {
            "fields": ("hotel", "document_type", "title", "file", "description")
        }),
        ("Validity Period", {
            "fields": ("issue_date", "expiry_date")
        }),
        ("Verification", {
            "fields": ("is_verified", "verified_by", "verified_at")
        }),
        ("Metadata", {
            "fields": ("uploaded_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
    
    def hotel_link(self, obj):
        return format_html('<a href="{}">{}</a>', 
                         reverse("admin:hotels_hotel_change", args=[obj.hotel.id]),
                         obj.hotel.name)
    hotel_link.short_description = "Hotel"
    
    def expiry_status(self, obj):
        if obj.is_expired:
            return format_html('<span style="color: #dc2626; font-weight: bold;">⚠ Expired</span>')
        return format_html('<span style="color: #10b981;">✓ Valid</span>')
    expiry_status.short_description = "Status"
    
    actions = ['mark_verified', 'mark_unverified']
    
    def mark_verified(self, request, queryset):
        updated = queryset.update(is_verified=True)
        self.message_user(request, f"{updated} documents marked as verified.")
    mark_verified.short_description = "Mark selected documents as verified"
    
    def mark_unverified(self, request, queryset):
        updated = queryset.update(is_verified=False)
        self.message_user(request, f"{updated} documents marked as unverified.")
    mark_unverified.short_description = "Mark selected documents as unverified"


@admin.register(HotelReview)
class HotelReviewAdmin(admin.ModelAdmin):
    list_display = ("hotel_link", "guest_name", "overall_rating_display", 
                   "title_preview", "is_approved", "is_verified_stay", "created_at")
    list_filter = ("is_approved", "is_verified_stay", "overall_rating", "created_at")
    search_fields = ("hotel__name", "guest_name", "guest_email", "title", "review_text")
    readonly_fields = ("created_at", "updated_at", "hotel_response_date", "average_rating")
    ordering = ("-created_at",)
    
    fieldsets = (
        ("Review Information", {
            "fields": ("hotel", "guest_name", "guest_email", "title", "review_text", 
                      "pros", "cons")
        }),
        ("Ratings", {
            "fields": ("overall_rating", "cleanliness_rating", "comfort_rating", 
                      "location_rating", "staff_rating", "facilities_rating", "value_rating",
                      "average_rating")
        }),
        ("Stay Details", {
            "fields": ("stay_date_from", "stay_date_to", "room_number")
        }),
        ("Verification", {
            "fields": ("is_verified_stay", "is_approved")
        }),
        ("Hotel Response", {
            "fields": ("hotel_response", "hotel_response_date", "responded_by")
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
    
    def hotel_link(self, obj):
        return format_html('<a href="{}">{}</a>', 
                         reverse("admin:hotels_hotel_change", args=[obj.hotel.id]),
                         obj.hotel.name)
    hotel_link.short_description = "Hotel"
    
    def overall_rating_display(self, obj):
        stars = "★" * int(obj.overall_rating)
        empty_stars = "☆" * (5 - int(obj.overall_rating))
        return format_html('<span style="color: #fbbf24;">{}{}</span> ({})', 
                         stars, empty_stars, obj.overall_rating)
    overall_rating_display.short_description = "Rating"
    
    def title_preview(self, obj):
        if len(obj.title) > 50:
            return obj.title[:47] + "..."
        return obj.title
    title_preview.short_description = "Title"
    
    actions = ['approve_reviews', 'unapprove_reviews', 'mark_verified_stays']
    
    def approve_reviews(self, request, queryset):
        updated = queryset.update(is_approved=True)
        self.message_user(request, f"{updated} reviews approved.")
    approve_reviews.short_description = "Approve selected reviews"
    
    def unapprove_reviews(self, request, queryset):
        updated = queryset.update(is_approved=False)
        self.message_user(request, f"{updated} reviews unapproved.")
    unapprove_reviews.short_description = "Unapprove selected reviews"
    
    def mark_verified_stays(self, request, queryset):
        updated = queryset.update(is_verified_stay=True)
        self.message_user(request, f"{updated} reviews marked as verified stays.")
    mark_verified_stays.short_description = "Mark as verified stays"


@admin.register(HotelContactPerson)
class HotelContactPersonAdmin(admin.ModelAdmin):
    list_display = ("name", "hotel_link", "position", "email", "phone", "is_primary")
    list_filter = ("position", "is_primary")
    search_fields = ("name", "email", "phone", "hotel__name")
    ordering = ("hotel__name", "name")
    list_editable = ("is_primary",)
    
    fieldsets = (
        ("Contact Person Information", {
            "fields": ("hotel", "name", "position", "email", "phone", "phone_alt", "is_primary")
        }),
    )
    
    def hotel_link(self, obj):
        return format_html('<a href="{}">{}</a>', 
                         reverse("admin:hotels_hotel_change", args=[obj.hotel.id]),
                         obj.hotel.name)
    hotel_link.short_description = "Hotel"
    
    def save_model(self, request, obj, change, form):
        if obj.is_primary:
            HotelContactPerson.objects.filter(hotel=obj.hotel, is_primary=True).exclude(pk=obj.pk).update(is_primary=False)
        super().save_model(request, obj, change, form)


@admin.register(HotelBankDetail)
class HotelBankDetailAdmin(admin.ModelAdmin):
    list_display = ("bank_name", "hotel_link", "account_holder_name", 
                   "account_number_masked", "is_primary")
    list_filter = ("is_primary",)
    search_fields = ("bank_name", "account_holder_name", "account_number", "hotel__name")
    ordering = ("hotel__name", "bank_name")
    list_editable = ("is_primary",)
    
    fieldsets = (
        ("Bank Account Information", {
            "fields": ("hotel", "bank_name", "account_holder_name", "account_number", 
                      "routing_number", "swift_code", "iban", "is_primary")
        }),
    )
    
    def hotel_link(self, obj):
        return format_html('<a href="{}">{}</a>', 
                         reverse("admin:hotels_hotel_change", args=[obj.hotel.id]),
                         obj.hotel.name)
    hotel_link.short_description = "Hotel"
    
    def account_number_masked(self, obj):
        if obj.account_number:
            masked = "*" * (len(str(obj.account_number)) - 4) + str(obj.account_number)[-4:]
            return masked
        return "-"
    account_number_masked.short_description = "Account Number"
    
    def save_model(self, request, obj, change, form):
        if obj.is_primary:
            HotelBankDetail.objects.filter(hotel=obj.hotel, is_primary=True).exclude(pk=obj.pk).update(is_primary=False)
        super().save_model(request, obj, change, form)


@admin.register(HotelAmenity)
class HotelAmenityAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "category", "icon_display", "is_paid", "hotels_count")
    list_filter = ("category", "is_paid")
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("category", "name")
    
    fieldsets = (
        ("Amenity Information", {
            "fields": ("name", "slug", "category", "icon", "is_paid", "description")
        }),
    )
    
    def icon_display(self, obj):
        if obj.icon:
            return format_html('<i class="{}"></i> {}', obj.icon, obj.icon)
        return "-"
    icon_display.short_description = "Icon"
    
    def hotels_count(self, obj):
        count = obj.hotel_mappings.filter(is_available=True).count()
        url = reverse("admin:hotels_hotelamenitymapping_changelist") + f"?amenity__id={obj.id}"
        if count > 0:
            return format_html('<a href="{}">{}</a>', url, count)
        return "0"
    hotels_count.short_description = "Hotels"


@admin.register(HotelAmenityMapping)
class HotelAmenityMappingAdmin(admin.ModelAdmin):
    list_display = ("hotel_link", "amenity_name", "is_available", "charge_amount_display")
    list_filter = ("is_available", "amenity__category")
    search_fields = ("hotel__name", "amenity__name", "additional_info")
    ordering = ("hotel__name", "amenity__name")
    list_editable = ("is_available",)
    
    fieldsets = (
        ("Amenity Mapping", {
            "fields": ("hotel", "amenity", "is_available", "additional_info", "charge_amount")
        }),
    )
    
    def hotel_link(self, obj):
        return format_html('<a href="{}">{}</a>', 
                         reverse("admin:hotels_hotel_change", args=[obj.hotel.id]),
                         obj.hotel.name)
    hotel_link.short_description = "Hotel"
    
    def amenity_name(self, obj):
        return obj.amenity.name
    amenity_name.short_description = "Amenity"
    
    def charge_amount_display(self, obj):
        if obj.charge_amount:
            return f"${obj.charge_amount}"
        return "-"
    charge_amount_display.short_description = "Charge Amount"


# Custom admin site configuration
admin.site.site_header = "Hotel Management System"
admin.site.site_title = "Hotel Admin Portal"
admin.site.index_title = "Welcome to Hotel Management Portal"