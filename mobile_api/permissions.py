from rest_framework.permissions import BasePermission
from accounts.models import HotelMember


WAITER_ROLES = {
    HotelMember.Role.ADMIN,
    HotelMember.Role.GENERAL_MANAGER,
    HotelMember.Role.OPERATIONS_MANAGER,
    HotelMember.Role.RESTAURANT_MANAGER,
    HotelMember.Role.SERVER,
    HotelMember.Role.CHEF,
    HotelMember.Role.ACCOUNTANT,
}


class IsHotelWaiter(BasePermission):
    message = "You are not allowed to create orders for this hotel."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        hotel = getattr(obj, "hotel", None)
        if not hotel:
            return False
        return HotelMember.objects.filter(
            hotel=hotel,
            user=request.user,
            is_active=True,
            role__in=WAITER_ROLES,
        ).exists()
