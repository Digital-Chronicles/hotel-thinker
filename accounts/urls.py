# accounts/urls.py

from django.urls import path
from django.views.generic import RedirectView
from django.conf import settings

from . import views

app_name = "accounts"

urlpatterns = [
    # Profile redirect (for compatibility with /accounts/profile/)
    path("profile/", RedirectView.as_view(pattern_name="accounts:my_profile", permanent=False), name="profile_redirect"),
    
    # Dashboard / Profile
    path("dashboard/", views.dashboard, name="dashboard"),
    path("me/", views.my_profile, name="my_profile"),
    path("me/dashboard/", views.MemberDashboardView.as_view(), name="member_dashboard"),
    path("me/preferences/", views.profile_preferences, name="profile_preferences"),
    
    # Hotel members (staff)
    path("members/", views.HotelMembersListView.as_view(), name="hotel_members_list"),
    path("members/<int:pk>/", views.HotelMemberDetailView.as_view(), name="hotel_member_detail"),
    path("members/<int:pk>/edit/", views.HotelMemberEditView.as_view(), name="hotel_member_edit"),
    path("members/<int:pk>/permissions/", views.HotelMemberPermissionView.as_view(), name="hotel_member_permissions"),
    path("members/<int:pk>/toggle-active/", views.hotel_member_toggle_active, name="hotel_member_toggle_active"),
    path("members/<int:pk>/resend-invitation/", views.resend_invitation, name="resend_invitation"),
    
    # Member add views - ADD THESE URL PATTERNS
    path("members/add/", views.HotelMemberAddView.as_view(), name="hotel_member_add"),
    path("members/direct-add/", views.HotelMemberAddView.as_view(), name="hotel_member_direct_add"),  # Add this alias
    path("members/quick-add/", views.HotelMemberQuickAddView.as_view(), name="hotel_member_quick_add"),
    path("members/bulk-add/", views.HotelMemberBulkAddView.as_view(), name="hotel_member_bulk_add"),
    path("members/invite/", views.HotelMemberInviteView.as_view(), name="hotel_member_invite"),
    
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
    
    # Activity logs
    path("activity/", views.HotelActivityLogView.as_view(), name="hotel_activity"),
    
    # API-like endpoints (JSON responses)
    path("api/members/search/", views.member_search_api, name="member_search_api"),
    path("api/members/stats/", views.member_stats_api, name="member_stats_api"),
]

# Add conditional URLs for development
if settings.DEBUG:
    urlpatterns += [
        path("test/error-test/", views.test_error_handling, name="test_error"),
    ]