from __future__ import annotations

from django.core.paginator import Paginator
from django.db.models import Avg, Count, Min, Max, Q, Prefetch, F
from django.shortcuts import get_object_or_404, render

from hotels.models import (
    Hotel,
    HotelAmenityMapping,
    HotelCategory,
    HotelImage,
    HotelReview,
    HotelSetting,
)
from rooms.models import Room, RoomImage, RoomType


def _hotel_base_queryset():
    """Base queryset for hotels with common annotations and prefetches"""
    return (
        Hotel.objects.filter(is_active=True, is_published=True)
        .select_related("category", "hotel_chain", "settings")
        .prefetch_related(
            Prefetch(
                "images",
                queryset=HotelImage.objects.filter(is_primary=True).order_by("order", "-uploaded_at")[:1],
                to_attr="prefetched_images",
            ),
            Prefetch(
                "amenity_mappings",
                queryset=HotelAmenityMapping.objects.filter(is_available=True).select_related("amenity"),
                to_attr="prefetched_amenities",
            ),
        )
        .annotate(
            reviews_count=Count(
                "reviews",
                filter=Q(reviews__is_approved=True),
                distinct=True,
            ),
            avg_rating=Avg(
                "reviews__overall_rating",
                filter=Q(reviews__is_approved=True),
            ),
            room_types_count=Count("room_types", distinct=True),
            rooms_count=Count("rooms", filter=Q(rooms__is_active=True), distinct=True),
            min_price=Min("room_types__base_price"),
        )
    )


def public_home(request):
    """Home page view with featured hotels, stats, and popular destinations"""
    hotels_qs = _hotel_base_queryset()

    featured_hotels = list(hotels_qs.filter(is_featured=True).order_by("-is_verified", "name")[:6])
    latest_hotels = list(hotels_qs.order_by("-created_at")[:6])
    top_rated_hotels = list(hotels_qs.filter(avg_rating__isnull=False).order_by(
        "-avg_rating", "-reviews_count", "name"
    )[:6])
    
    # Add image_url and brand colors to hotels
    for hotel in featured_hotels + latest_hotels + top_rated_hotels:
        if hasattr(hotel, 'prefetched_images') and hotel.prefetched_images:
            hotel.image_url = hotel.prefetched_images[0].image.url
        elif hotel.cover_image:
            hotel.image_url = hotel.cover_image.url
        else:
            hotel.image_url = None
            
        # Add brand colors (ensure they have default values if None)
        hotel.brand_color_primary = hotel.brand_color_primary or "#3B82F6"
        hotel.brand_color_secondary = hotel.brand_color_secondary or "#10B981"

    popular_cities = (
        Hotel.objects.filter(is_active=True, is_published=True)
        .exclude(city__isnull=True)
        .exclude(city__exact="")
        .values("city", "country")
        .annotate(total=Count("id"))
        .order_by("-total", "city")[:8]
    )

    categories = (
        HotelCategory.objects.annotate(
            hotels_count=Count(
                "hotels",
                filter=Q(hotels__is_active=True, hotels__is_published=True),
                distinct=True,
            )
        )
        .filter(hotels_count__gt=0)
        .order_by("name")
    )

    stats = {
        "total_hotels": Hotel.objects.filter(is_active=True, is_published=True).count(),
        "total_rooms": Room.objects.filter(
            hotel__is_active=True,
            hotel__is_published=True,
            is_active=True,
        ).count(),
        "total_reviews": HotelReview.objects.filter(
            hotel__is_active=True,
            hotel__is_published=True,
            is_approved=True,
        ).count(),
        "featured_count": Hotel.objects.filter(
            is_active=True,
            is_published=True,
            is_featured=True,
        ).count(),
    }

    return render(
        request,
        "public_site/home.html",
        {
            "featured_hotels": featured_hotels,
            "latest_hotels": latest_hotels,
            "top_rated_hotels": top_rated_hotels,
            "popular_cities": popular_cities,
            "categories": categories,
            "stats": stats,
        },
    )


def public_hotels_list(request):
    """Hotel listing page with filtering and pagination"""
    hotels_qs = _hotel_base_queryset().order_by("-is_featured", "-is_verified", "name")

    # Get filter parameters
    q = (request.GET.get("q") or "").strip()
    city = (request.GET.get("city") or "").strip()
    country = (request.GET.get("country") or "").strip()
    category = (request.GET.get("category") or "").strip()
    min_rating = (request.GET.get("min_rating") or "").strip()
    featured = (request.GET.get("featured") or "").strip()
    
    # Get star ratings (can be multiple)
    star_ratings = request.GET.getlist("star_rating")
    
    # Get max price
    max_price = request.GET.get("max_price")

    # Apply filters
    if q:
        hotels_qs = hotels_qs.filter(
            Q(name__icontains=q)
            | Q(city__icontains=q)
            | Q(country__icontains=q)
            | Q(short_description__icontains=q)
            | Q(description__icontains=q)
        )

    if city:
        hotels_qs = hotels_qs.filter(city__iexact=city)

    if country:
        hotels_qs = hotels_qs.filter(country__iexact=country)

    if category:
        hotels_qs = hotels_qs.filter(category__slug=category)

    if min_rating:
        try:
            min_rating_val = float(min_rating)
            if 0 <= min_rating_val <= 5:
                hotels_qs = hotels_qs.filter(avg_rating__gte=min_rating_val)
        except (TypeError, ValueError):
            pass

    if star_ratings:
        # Convert star ratings to integers and filter
        star_values = []
        for rating in star_ratings:
            try:
                rating_int = int(rating)
                if 1 <= rating_int <= 5:
                    star_values.append(rating_int)
            except ValueError:
                pass
        if star_values:
            hotels_qs = hotels_qs.filter(star_rating__in=star_values)
    
    if max_price:
        try:
            max_price_val = float(max_price)
            if max_price_val > 0:
                hotels_qs = hotels_qs.filter(min_price__lte=max_price_val)
        except (TypeError, ValueError):
            pass

    if featured in {"1", "true", "yes"}:
        hotels_qs = hotels_qs.filter(is_featured=True)

    # Apply sorting
    sort_by = request.GET.get("sort", "recommended")
    if sort_by == "price_asc":
        hotels_qs = hotels_qs.filter(min_price__isnull=False).order_by("min_price", "name")
    elif sort_by == "price_desc":
        hotels_qs = hotels_qs.filter(min_price__isnull=False).order_by("-min_price", "name")
    elif sort_by == "rating_desc":
        hotels_qs = hotels_qs.filter(avg_rating__isnull=False).order_by("-avg_rating", "-reviews_count", "name")
    elif sort_by == "newest":
        hotels_qs = hotels_qs.order_by("-created_at", "name")
    else:  # recommended
        hotels_qs = hotels_qs.order_by("-is_featured", "-is_verified", "-avg_rating", "name")

    # Pagination
    paginator = Paginator(hotels_qs, 12)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Process each hotel in the page to add image_url and brand colors
    hotels_list = []
    for hotel in page_obj.object_list:
        # Add image URL
        if hasattr(hotel, 'prefetched_images') and hotel.prefetched_images:
            hotel.image_url = hotel.prefetched_images[0].image.url
        elif hotel.cover_image:
            hotel.image_url = hotel.cover_image.url
        else:
            hotel.image_url = None
        
        # Add brand colors
        hotel.brand_color_primary = hotel.brand_color_primary or "#3B82F6"
        hotel.brand_color_secondary = hotel.brand_color_secondary or "#10B981"
        
        hotels_list.append(hotel)

    # Get filter options for sidebar
    filter_categories = (
        HotelCategory.objects.annotate(
            hotels_count=Count(
                "hotels",
                filter=Q(hotels__is_active=True, hotels__is_published=True),
                distinct=True,
            )
        )
        .filter(hotels_count__gt=0)
        .order_by("name")
    )

    available_cities = list(
        Hotel.objects.filter(is_active=True, is_published=True)
        .exclude(city__isnull=True)
        .exclude(city__exact="")
        .values_list("city", flat=True)
        .distinct()
        .order_by("city")
    )

    available_countries = list(
        Hotel.objects.filter(is_active=True, is_published=True)
        .exclude(country__isnull=True)
        .exclude(country__exact="")
        .values_list("country", flat=True)
        .distinct()
        .order_by("country")
    )

    # Prepare context for template
    context = {
        "page_obj": page_obj,
        "hotels": hotels_list,
        "categories": filter_categories,
        "available_cities": available_cities,
        "available_countries": available_countries,
        "q": q,
        "selected_city": city,
        "selected_country": country,
        "selected_category": category,
        "selected_min_rating": min_rating,
        "selected_featured": featured,
        "selected_star_ratings": star_ratings,
        "selected_sort": sort_by,
        "max_price": max_price,
    }
    
    return render(request, "public_site/hotels_list.html", context)


def public_hotel_profile(request, slug):
    """Hotel public profile page with all details"""
    # Get hotel with related data
    hotel = get_object_or_404(
        _hotel_base_queryset().prefetch_related(
            'contact_persons',
            'bank_details'
        ), 
        slug=slug
    )
    
    # Add brand colors to hotel
    hotel.brand_color_primary = hotel.brand_color_primary or "#3B82F6"
    hotel.brand_color_secondary = hotel.brand_color_secondary or "#10B981"
    
    # Add image URL to hotel
    if hasattr(hotel, 'prefetched_images') and hotel.prefetched_images:
        hotel.image_url = hotel.prefetched_images[0].image.url
    elif hotel.cover_image:
        hotel.image_url = hotel.cover_image.url
    else:
        hotel.image_url = None
    
    # Get or create hotel settings
    settings_obj, _ = HotelSetting.objects.get_or_create(hotel=hotel)
    
    # Add brand color from settings
    settings_obj.brand_color = settings_obj.brand_color or "#3B82F6"

    # Get amenities
    amenities = (
        HotelAmenityMapping.objects.filter(hotel=hotel, is_available=True)
        .select_related("amenity")
        .order_by("amenity__category", "amenity__name")
    )

    # Get gallery images (all images)
    gallery = list(HotelImage.objects.filter(hotel=hotel).order_by("order", "-uploaded_at")[:16])
    
    # Get cover image
    cover_image = None
    if gallery:
        cover_image = next((img for img in gallery if img.is_primary), gallery[0])
    elif hotel.cover_image:
        cover_image = hotel.cover_image

    # FIXED: Removed 'is_active' filter since RoomType doesn't have this field
    room_types = list(
        RoomType.objects.filter(hotel=hotel)  # Removed is_active=True
        .annotate(
            rooms_count=Count("rooms", filter=Q(rooms__is_active=True), distinct=True),
            min_price=F("base_price"),
            max_price=F("base_price"),
        )
        .order_by("name")
    )

    # Get all rooms
    all_rooms = list(
        Room.objects.filter(hotel=hotel, is_active=True)
        .select_related("room_type")
        .prefetch_related(
            Prefetch(
                "images",
                queryset=RoomImage.objects.filter(is_active=True).order_by(
                    "-is_primary", "order", "-created_at"
                ),
                to_attr="prefetched_images",
            )
        )
        .order_by("room_type__name", "number")
    )

    featured_rooms = all_rooms[:8]
    
    # Add image URLs to rooms
    for room in all_rooms + featured_rooms:
        if hasattr(room, 'prefetched_images') and room.prefetched_images:
            room.image_url = room.prefetched_images[0].image.url
        else:
            room.image_url = None

    # Get recent reviews
    recent_reviews = list(
        HotelReview.objects.filter(hotel=hotel, is_approved=True)
        .order_by("-created_at")[:6]
    )

    # Get review summary
    review_summary = HotelReview.objects.filter(
        hotel=hotel,
        is_approved=True,
    ).aggregate(
        avg_rating=Avg("overall_rating"),
        cleanliness=Avg("cleanliness_rating"),
        comfort=Avg("comfort_rating"),
        location=Avg("location_rating"),
        staff=Avg("staff_rating"),
        facilities=Avg("facilities_rating"),
        value=Avg("value_rating"),
        total_reviews=Count("id"),
    )
    
    # Ensure numeric values are floats or None
    for key in review_summary:
        if review_summary[key] is not None:
            review_summary[key] = round(float(review_summary[key]), 1)

    # Get related hotels
    related_hotels_qs = (
        _hotel_base_queryset()
        .exclude(pk=hotel.pk)
        .filter(Q(city=hotel.city) | Q(category=hotel.category))
        .order_by("-is_featured", "-is_verified", "name")[:4]
    )
    
    related_hotels = []
    for related in related_hotels_qs:
        # Add image URL
        if hasattr(related, 'prefetched_images') and related.prefetched_images:
            related.image_url = related.prefetched_images[0].image.url
        elif related.cover_image:
            related.image_url = related.cover_image.url
        else:
            related.image_url = None
        
        # Add brand colors
        related.brand_color_primary = related.brand_color_primary or "#3B82F6"
        related.brand_color_secondary = related.brand_color_secondary or "#10B981"
        
        related_hotels.append(related)

    # Get contact persons
    primary_contact = hotel.contact_persons.filter(is_primary=True).first()
    other_contacts = list(
        hotel.contact_persons.exclude(pk=primary_contact.pk)
        if primary_contact
        else hotel.contact_persons.all()
    )

    # Room status choices
    room_status_choices = []
    if hasattr(Room, 'Status') and hasattr(Room.Status, 'choices'):
        room_status_choices = Room.Status.choices

    return render(
        request,
        "public_site/hotel_profile.html",
        {
            "hotel": hotel,
            "settings": settings_obj,
            "amenities": amenities,
            "gallery": gallery,
            "cover_image": cover_image,
            "room_types": room_types,
            "all_rooms": all_rooms,
            "featured_rooms": featured_rooms,
            "recent_reviews": recent_reviews,
            "review_summary": review_summary,
            "related_hotels": related_hotels,
            "primary_contact": primary_contact,
            "other_contacts": other_contacts,
            "room_statuses": room_status_choices,
        },
    )


def public_hotel_gallery(request, slug):
    """Hotel gallery page with category filtering"""
    hotel = get_object_or_404(
        Hotel.objects.filter(is_active=True, is_published=True), 
        slug=slug
    )
    
    # Add brand colors to hotel
    hotel.brand_color_primary = hotel.brand_color_primary or "#3B82F6"
    hotel.brand_color_secondary = hotel.brand_color_secondary or "#10B981"
    
    category = (request.GET.get("category") or "").strip()

    images_qs = HotelImage.objects.filter(hotel=hotel).order_by("order", "-uploaded_at")
    if category:
        images_qs = images_qs.filter(category=category)

    paginator = Paginator(images_qs, 18)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    gallery_categories = list(
        HotelImage.objects.filter(hotel=hotel)
        .values_list("category", flat=True)
        .distinct()
    )

    # Image category choices
    image_category_choices = getattr(HotelImage, "IMAGE_CATEGORIES", [])
    if not image_category_choices:
        image_category_choices = [
            ('exterior', 'Exterior'),
            ('interior', 'Interior'),
            ('room', 'Room'),
            ('suite', 'Suite'),
            ('dining', 'Dining'),
            ('pool', 'Pool'),
            ('spa', 'Spa'),
            ('gym', 'Gym'),
            ('event', 'Event'),
            ('other', 'Other'),
        ]

    return render(
        request,
        "public_site/hotel_gallery.html",
        {
            "hotel": hotel,
            "images": page_obj.object_list,
            "page_obj": page_obj,
            "selected_category": category,
            "gallery_categories": gallery_categories,
            "image_category_choices": image_category_choices,
        },
    )


def public_hotel_reviews(request, slug):
    """Hotel reviews page with pagination"""
    hotel = get_object_or_404(
        Hotel.objects.filter(is_active=True, is_published=True), 
        slug=slug
    )
    
    # Add brand colors to hotel
    hotel.brand_color_primary = hotel.brand_color_primary or "#3B82F6"
    hotel.brand_color_secondary = hotel.brand_color_secondary or "#10B981"

    reviews_qs = HotelReview.objects.filter(
        hotel=hotel,
        is_approved=True,
    ).order_by("-created_at")

    paginator = Paginator(reviews_qs, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    review_summary = HotelReview.objects.filter(
        hotel=hotel,
        is_approved=True,
    ).aggregate(
        avg_rating=Avg("overall_rating"),
        cleanliness=Avg("cleanliness_rating"),
        comfort=Avg("comfort_rating"),
        location=Avg("location_rating"),
        staff=Avg("staff_rating"),
        facilities=Avg("facilities_rating"),
        value=Avg("value_rating"),
        total_reviews=Count("id"),
    )
    
    # Ensure numeric values are floats or None
    for key in review_summary:
        if review_summary[key] is not None:
            review_summary[key] = round(float(review_summary[key]), 1)
    
    # Calculate rating distribution if needed
    rating_distribution = {}
    for rating in range(1, 6):
        rating_distribution[rating] = HotelReview.objects.filter(
            hotel=hotel,
            is_approved=True,
            overall_rating=rating
        ).count()

    return render(
        request,
        "public_site/hotel_reviews.html",
        {
            "hotel": hotel,
            "reviews": page_obj.object_list,
            "page_obj": page_obj,
            "review_summary": review_summary,
            "rating_distribution": rating_distribution,
        },
    )


def public_about(request):
    """About page with statistics"""
    stats = {
        "total_hotels": Hotel.objects.filter(is_active=True, is_published=True).count(),
        "total_rooms": Room.objects.filter(
            hotel__is_active=True,
            hotel__is_published=True,
            is_active=True,
        ).count(),
        "total_reviews": HotelReview.objects.filter(
            hotel__is_active=True,
            hotel__is_published=True,
            is_approved=True,
        ).count(),
        "average_rating": HotelReview.objects.filter(
            hotel__is_active=True,
            hotel__is_published=True,
            is_approved=True,
        ).aggregate(avg=Avg("overall_rating"))["avg"],
    }
    
    if stats["average_rating"]:
        stats["average_rating"] = round(float(stats["average_rating"]), 1)

    return render(request, "public_site/about.html", {"stats": stats})