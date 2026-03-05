from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST
from django.views.generic import ListView, UpdateView

from hotel_thinker.utils import get_active_hotel_for_user, require_hotel_role
from .forms import HotelMemberForm, ProfileForm
from .models import HotelMember, Profile


@login_required
def dashboard(request):
    hotel = get_active_hotel_for_user(request.user)
    return render(request, "accounts/dashboard.html", {"hotel": hotel})


@login_required
def my_profile(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("accounts:my_profile")
    else:
        form = ProfileForm(instance=profile)

    return render(request, "accounts/my_profile.html", {"form": form, "profile": profile})


@method_decorator(login_required, name="dispatch")
class HotelMembersListView(ListView):
    model = HotelMember
    template_name = "accounts/hotel_members_list.html"
    context_object_name = "members"
    paginate_by = 50

    def get_queryset(self):
        hotel = get_active_hotel_for_user(self.request.user)
        return (
            HotelMember.objects.filter(hotel=hotel)
            .select_related("user", "hotel")
            .order_by("-is_active", "role", "user__email")
        )


@method_decorator(login_required, name="dispatch")
class HotelMemberUpdateView(UpdateView):
    model = HotelMember
    form_class = HotelMemberForm
    template_name = "accounts/hotel_member_form.html"
    context_object_name = "member"

    def dispatch(self, request, *args, **kwargs):
        require_hotel_role(request.user, {"admin", "general_manager", "operations_manager"})
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        hotel = get_active_hotel_for_user(self.request.user)
        return HotelMember.objects.filter(hotel=hotel).select_related("user")

    def form_valid(self, form):
        messages.success(self.request, "Member updated.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("accounts:hotel_members_list")


@login_required
@require_POST
def hotel_member_toggle_active(request, pk: int):
    require_hotel_role(request.user, {"admin", "general_manager", "operations_manager"})
    hotel = get_active_hotel_for_user(request.user)

    member = get_object_or_404(HotelMember, pk=pk, hotel=hotel)
    member.is_active = not member.is_active
    member.save(update_fields=["is_active"])

    messages.success(request, f"Member {'activated' if member.is_active else 'disabled'}.")
    return redirect("accounts:hotel_members_list")