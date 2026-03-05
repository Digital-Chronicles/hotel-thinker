# hotels/views.py
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from hotel_thinker.utils import get_active_hotel_for_user, require_hotel_role
from .models import HotelSetting
from .forms import HotelSettingForm


@login_required
def hotel_detail(request):
    hotel = get_active_hotel_for_user(request.user)
    settings_obj, _ = HotelSetting.objects.get_or_create(hotel=hotel)

    return render(
        request,
        "hotels/hotel_detail.html",
        {
            "hotel": hotel,
            "settings": settings_obj,
        },
    )


@login_required
def hotel_settings(request):
    require_hotel_role(request.user, {"admin", "general_manager"})

    hotel = get_active_hotel_for_user(request.user)
    settings_obj, _ = HotelSetting.objects.get_or_create(hotel=hotel)

    if request.method == "POST":
        form = HotelSettingForm(request.POST, request.FILES, instance=settings_obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Hotel settings updated.")
            return redirect("hotels:settings")
        messages.error(request, "Please correct the errors below.")
    else:
        form = HotelSettingForm(instance=settings_obj)

    return render(request, "hotels/hotel_settings.html", {"hotel": hotel, "form": form, "settings": settings_obj})