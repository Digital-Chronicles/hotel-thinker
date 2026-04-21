# accounts/urls.py
from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "accounts"

urlpatterns = [
    # Profile redirect (for compatibility with /accounts/profile/)
    path("profile/", RedirectView.as_view(pattern_name="accounts:my_profile", permanent=False), name="profile_redirect"),
    path("profile/", views.my_profile, name="profile"),  # Alternative direct mapping
    
    # Dashboard / Profile
    path("dashboard/", views.dashboard, name="dashboard"),
    path("me/", views.my_profile, name="my_profile"),
    path("me/dashboard/", views.HotelMemberDashboardView.as_view(), name="member_dashboard"),
    
    # Hotel members (staff)
    path("members/", views.HotelMembersListView.as_view(), name="hotel_members_list"),
    path("members/<int:pk>/", views.HotelMemberDetailView.as_view(), name="hotel_member_detail"),
    path("members/<int:pk>/edit/", views.HotelMemberUpdateView.as_view(), name="hotel_member_update"),
    path("members/<int:pk>/toggle-active/", views.hotel_member_toggle_active, name="hotel_member_toggle_active"),
    path("members/<int:pk>/resend-invitation/", views.resend_member_invitation, name="resend_invitation"),
    
    # Member management
    path("members/invite/", views.HotelMemberInviteView.as_view(), name="hotel_member_invite"),
    path("members/bulk-invite/", views.HotelMemberBulkInviteView.as_view(), name="hotel_member_bulk_invite"),
    
    # Member activity
    path("members/<int:pk>/activity/", views.MemberActivityLogView.as_view(), name="member_activity"),
    path("members/<int:pk>/performance/", views.MemberPerformanceUpdateView.as_view(), name="member_performance"),
    
    # Leave management
    path("members/<int:pk>/leave/start/", views.member_start_leave, name="member_start_leave"),
    path("members/<int:pk>/leave/end/", views.member_end_leave, name="member_end_leave"),
    
    # Team management
    path("team/", views.TeamManagementView.as_view(), name="team_management"),
    path("team/shifts/", views.ShiftManagementView.as_view(), name="shift_management"),
    
    # Reports
    path("reports/staff/", views.StaffReportView.as_view(), name="staff_report"),
    path("reports/performance/", views.PerformanceReportView.as_view(), name="performance_report"),
    
    # API-like endpoints (JSON responses)
    path("api/members/search/", views.member_search_api, name="member_search_api"),
    path("api/members/stats/", views.member_stats_api, name="member_stats_api"),
]

# Optional: Add conditional URLs for development
from django.conf import settings

if settings.DEBUG:
    urlpatterns += [
        path("test/error-test/", views.test_error_handling, name="test_error"),
    ]