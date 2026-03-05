# hotel_thinker/utils.py
from __future__ import annotations

from typing import Optional

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest

from accounts.models import HotelMember
from hotels.models import Hotel


ACTIVE_HOTEL_SESSION_KEY = "active_hotel_id"


def get_active_hotel_for_user(user, request: Optional[HttpRequest] = None) -> Hotel:
    """
    Returns the active hotel for the logged-in user.

    Priority:
    1) If request is provided and request.session[ACTIVE_HOTEL_SESSION_KEY] is set,
       try to use that hotel (must be active membership + active hotel).
    2) Otherwise, fall back to the user's first active membership.

    Raises PermissionDenied if:
    - user not authenticated
    - no active membership found
    - hotel is inactive
    """
    if not getattr(user, "is_authenticated", False):
        raise PermissionDenied("Please login to continue.")

    memberships = getattr(user, "hotel_memberships", None)
    if memberships is None:
        raise PermissionDenied("Hotel memberships are not configured for this user.")

    # 1) Session-selected hotel (optional)
    if request is not None:
        active_hotel_id = request.session.get(ACTIVE_HOTEL_SESSION_KEY)
        if active_hotel_id:
            m = (
                memberships.filter(is_active=True, hotel_id=active_hotel_id)
                .select_related("hotel")
                .first()
            )
            if m and m.hotel_id:
                if not m.hotel.is_active:
                    raise PermissionDenied("This hotel is currently inactive.")
                return m.hotel

    # 2) Fallback to first active membership
    m = memberships.filter(is_active=True).select_related("hotel").first()
    if not m or not m.hotel_id:
        raise PermissionDenied("You do not belong to any active hotel.")

    if not m.hotel.is_active:
        raise PermissionDenied("This hotel is currently inactive.")

    return m.hotel


def get_active_membership(user, hotel: Optional[Hotel] = None) -> HotelMember:
    """
    Returns the user's active HotelMember membership.
    If hotel is provided, returns membership for that hotel.
    """
    if not getattr(user, "is_authenticated", False):
        raise PermissionDenied("Please login to continue.")

    qs = getattr(user, "hotel_memberships", None)
    if qs is None:
        raise PermissionDenied("Hotel memberships are not configured for this user.")

    if user.is_superuser:
        # Superuser might not have a membership; guard only if hotel is required.
        if hotel is None:
            m = qs.filter(is_active=True).select_related("hotel").first()
            if m:
                return m
        raise PermissionDenied("Superuser has no active hotel membership configured.")

    if hotel is not None:
        m = qs.filter(is_active=True, hotel=hotel).select_related("hotel").first()
    else:
        m = qs.filter(is_active=True).select_related("hotel").first()

    if not m:
        raise PermissionDenied("No active hotel membership found.")

    if not m.hotel.is_active:
        raise PermissionDenied("This hotel is currently inactive.")

    return m


def require_hotel_role(user, allowed_roles: set[str], hotel: Optional[Hotel] = None) -> HotelMember:
    """
    Role guard. Superuser bypasses role checks.

    Example:
        require_hotel_role(request.user, {"admin", "general_manager"})
    """
    if getattr(user, "is_superuser", False):
        # If you want superusers to also be tied to a hotel, remove this bypass.
        return get_active_membership(user, hotel=hotel)

    m = get_active_membership(user, hotel=hotel)
    if m.role not in allowed_roles:
        raise PermissionDenied("You do not have permission to perform this action.")
    return m


def require_section_access(user, section: str, hotel: Optional[Hotel] = None) -> HotelMember:
    """
    Permission guard based on HotelMember boolean fields:
    - can_access_front_desk
    - can_access_housekeeping
    - can_access_restaurant
    - can_access_finance
    - can_access_maintenance
    - can_access_reports

    Usage:
        hotel = get_active_hotel_for_user(request.user, request=request)
        require_section_access(request.user, "finance", hotel=hotel)

    Superuser bypasses section checks.
    """
    if getattr(user, "is_superuser", False):
        return get_active_membership(user, hotel=hotel)

    valid_sections = {
        "front_desk",
        "housekeeping",
        "restaurant",
        "finance",
        "maintenance",
        "reports",
    }
    if section not in valid_sections:
        raise PermissionDenied(f"Unknown section '{section}'.")

    m = get_active_membership(user, hotel=hotel)
    flag_name = f"can_access_{section}"
    if not hasattr(m, flag_name):
        raise PermissionDenied(f"Section permission '{flag_name}' is not configured on HotelMember.")

    if not getattr(m, flag_name):
        raise PermissionDenied(f"You do not have access to {section.replace('_', ' ')}.")
    return m


def set_active_hotel(request: HttpRequest, hotel: Hotel) -> None:
    """
    Stores the active hotel in session.
    You can call this from a "switch hotel" view later.
    """
    request.session[ACTIVE_HOTEL_SESSION_KEY] = str(hotel.pk)
    request.session.modified = True