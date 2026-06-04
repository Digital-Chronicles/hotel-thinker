from django.urls import include, path
from rest_framework.routers import DefaultRouter
from . import views

app_name = "mobile_api"

router = DefaultRouter()
router.register(r"admin/hotels", views.SuperuserHotelViewSet, basename="admin-hotels")
router.register(r"admin/room-types", views.SuperuserRoomTypeViewSet, basename="admin-room-types")
router.register(r"admin/rooms", views.SuperuserRoomViewSet, basename="admin-rooms")
router.register(r"admin/menu-categories", views.SuperuserMenuCategoryViewSet, basename="admin-menu-categories")
router.register(r"admin/menu-items", views.SuperuserMenuItemViewSet, basename="admin-menu-items")


urlpatterns = [
    path("admin/register-hotel/", views.HotelRegistrationAPIView.as_view(), name="admin_register_hotel"),
    path("", include(router.urls)),
    # Authentication
    path("login/", views.LoginAPIView.as_view(), name="login"),
    path("me/", views.MeAPIView.as_view(), name="me"),
    
    # User Profile
    path("profile/", views.UserProfileAPIView.as_view(), name="user_profile"),
    path("profile/update/", views.UpdateProfileAPIView.as_view(), name="update_profile"),
    path("profile/change-password/", views.ChangePasswordAPIView.as_view(), name="change_password"),
    
    # Statistics
    path("statistics/dashboard/", views.DashboardStatisticsAPIView.as_view(), name="dashboard_stats"),
    path("statistics/restaurant/", views.RestaurantStatisticsAPIView.as_view(), name="restaurant_stats"),
    path("statistics/bar/", views.BarStatisticsAPIView.as_view(), name="bar_stats"),
    
    # Restaurant
    path("restaurant/menu/", views.RestaurantMenuAPIView.as_view(), name="restaurant_menu"),
    path("restaurant/tables/", views.RestaurantTablesAPIView.as_view(), name="restaurant_tables"),
    path("restaurant/orders/", views.RestaurantOrderListCreateAPIView.as_view(), name="restaurant_orders"),
    path("restaurant/orders/<int:pk>/", views.RestaurantOrderDetailAPIView.as_view(), name="restaurant_order_detail"),
    path("restaurant/orders/<int:pk>/status/", views.RestaurantOrderStatusAPIView.as_view(), name="restaurant_order_status"),
    
    # Bar
    path("bar/items/", views.BarItemsAPIView.as_view(), name="bar_items"),
    path("bar/orders/", views.BarOrderListCreateAPIView.as_view(), name="bar_orders"),
    path("bar/orders/<int:pk>/", views.BarOrderDetailAPIView.as_view(), name="bar_order_detail"),
    path("bar/orders/<int:pk>/status/", views.BarOrderStatusAPIView.as_view(), name="bar_order_status"),

    # User Statistics 
    path("users/stats/", views.UserStatisticsAPIView.as_view(), name="user_stats"),
]