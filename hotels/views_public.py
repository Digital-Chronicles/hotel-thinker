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
                queryset=HotelImage.objects.order_by("order", "-uploaded_at"),
                to_attr="prefetched_images",
            )
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

    featured_hotels = hotels_qs.order_by("-is_featured", "-is_verified", "name")[:6]
    latest_hotels = hotels_qs.order_by("-created_at")[:6]
    top_rated_hotels = hotels_qs.filter(avg_rating__isnull=False).order_by(
        "-avg_rating", "-reviews_count", "name"
    )[:6]

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
            hotels_qs = hotels_qs.filter(avg_rating__gte=float(min_rating))
        except (TypeError, ValueError):
            pass

    if featured in {"1", "true", "yes"}:
        hotels_qs = hotels_qs.filter(is_featured=True)

    # Pagination
    paginator = Paginator(hotels_qs, 12)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

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

    available_cities = (
        Hotel.objects.filter(is_active=True, is_published=True)
        .exclude(city__isnull=True)
        .exclude(city__exact="")
        .values_list("city", flat=True)
        .distinct()
        .order_by("city")
    )

    available_countries = (
        Hotel.objects.filter(is_active=True, is_published=True)
        .exclude(country__isnull=True)
        .exclude(country__exact="")
        .values_list("country", flat=True)
        .distinct()
        .order_by("country")
    )

    return render(
        request,
        "public_site/hotels_list.html",
        {
            "page_obj": page_obj,
            "hotels": page_obj.object_list,
            "categories": filter_categories,
            "available_cities": available_cities,
            "available_countries": available_countries,
            "q": q,
            "selected_city": city,
            "selected_country": country,
            "selected_category": category,
            "selected_min_rating": min_rating,
            "selected_featured": featured,
        },
    )


def public_hotel_profile(request, slug):
    """
    One-page hotel public profile.
    Rooms and room details are loaded here and shown using pop-up modals in the template.
    """
    # Get hotel with related data
    hotel = get_object_or_404(
        _hotel_base_queryset().prefetch_related(
            'contact_persons',
            'bank_details'
        ), 
        slug=slug
    )
    
    # Get or create hotel settings
    settings_obj, _ = HotelSetting.objects.get_or_create(hotel=hotel)

    # Get amenities
    amenities = (
        HotelAmenityMapping.objects.filter(hotel=hotel, is_available=True)
        .select_related("amenity")
        .order_by("amenity__category", "amenity__name")
    )

    # Get gallery images
    gallery = HotelImage.objects.filter(hotel=hotel).order_by("order", "-uploaded_at")[:16]

    # Get room types with pricing (price is on RoomType model)
    room_types = (
        RoomType.objects.filter(hotel=hotel)
        .annotate(
            rooms_count=Count("rooms", filter=Q(rooms__is_active=True), distinct=True),
            min_price=F("base_price"),
            max_price=F("base_price"),
        )
        .order_by("name")
    )

    # Get all rooms
    all_rooms = (
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

    # Get recent reviews
    recent_reviews = (
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

    # Get related hotels
    related_hotels = (
        _hotel_base_queryset()
        .exclude(pk=hotel.pk)
        .filter(Q(city=hotel.city) | Q(category=hotel.category))
        .order_by("-is_featured", "-is_verified", "name")[:4]
    )

    # Get contact persons
    primary_contact = hotel.contact_persons.filter(is_primary=True).first()
    other_contacts = (
        hotel.contact_persons.exclude(pk=primary_contact.pk)
        if primary_contact
        else hotel.contact_persons.all()
    )

    return render(
        request,
        "public_site/hotel_profile.html",
        {
            "hotel": hotel,
            "settings": settings_obj,
            "amenities": amenities,
            "gallery": gallery,
            "room_types": room_types,
            "all_rooms": all_rooms,
            "featured_rooms": featured_rooms,
            "recent_reviews": recent_reviews,
            "review_summary": review_summary,
            "related_hotels": related_hotels,
            "primary_contact": primary_contact,
            "other_contacts": other_contacts,
            "room_statuses": getattr(Room, "Status", None).choices if hasattr(getattr(Room, "Status", None), "choices") else [],
        },
    )


def public_hotel_gallery(request, slug):
    """Hotel gallery page with category filtering"""
    hotel = get_object_or_404(_hotel_base_queryset(), slug=slug)
    category = (request.GET.get("category") or "").strip()

    images_qs = HotelImage.objects.filter(hotel=hotel).order_by("order", "-uploaded_at")
    if category:
        images_qs = images_qs.filter(category=category)

    paginator = Paginator(images_qs, 18)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    gallery_categories = (
        HotelImage.objects.filter(hotel=hotel)
        .values_list("category", flat=True)
        .distinct()
    )

    return render(
        request,
        "public_site/hotel_gallery.html",
        {
            "hotel": hotel,
            "images": page_obj.object_list,
            "page_obj": page_obj,
            "selected_category": category,
            "gallery_categories": gallery_categories,
            "image_category_choices": getattr(HotelImage, "IMAGE_CATEGORIES", []),
        },
    )


def public_hotel_reviews(request, slug):
    """Hotel reviews page with pagination"""
    hotel = get_object_or_404(_hotel_base_queryset(), slug=slug)

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

    return render(
        request,
        "public_site/hotel_reviews.html",
        {
            "hotel": hotel,
            "reviews": page_obj.object_list,
            "page_obj": page_obj,
            "review_summary": review_summary,
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
    }

    return render(request, "public_site/about.html", {"stats": stats})