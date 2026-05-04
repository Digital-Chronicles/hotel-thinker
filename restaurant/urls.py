from django.urls import path
from . import views

app_name = "restaurant"

urlpatterns = [
    # Orders - more specific patterns first
    path("new/", views.OrderCreateView.as_view(), name="order_create"),
    path("", views.OrderListView.as_view(), name="order_list"),
    
    # Order detail and nested operations
    path("<int:pk>/", views.OrderDetailView.as_view(), name="order_detail"),
    
    # Order workflow (must come before generic pattern matches)
    path("<int:pk>/set-status/", views.order_set_status, name="order_set_status"),
    path("<int:pk>/bill/", views.order_bill, name="order_bill"),
    path("<int:pk>/pay/", views.order_pay, name="order_pay"),
    path("<int:pk>/receipt/", views.receipt_print, name="receipt_print"),
    
    # AJAX endpoints for order items
    path("<int:pk>/items/add/", views.order_add_item_ajax, name="order_add_item"),
    path("<int:pk>/items/<int:item_id>/remove/", views.order_remove_item_ajax, name="order_remove_item"),
    path("<int:pk>/items/<int:item_id>/update-qty/", views.order_update_item_qty_ajax, name="order_update_item_qty"),
    
    # API endpoints
    path("api/menu-items/", views.menu_items_api, name="menu_items_api"),
    path("api/orders/stats/", views.order_stats_api, name="order_stats_api"),  # Optional: add stats endpoint
    
    # Manager section - all under /manage/ prefix
    path("manage/", views.RestaurantManageDashboardView.as_view(), name="manage_dashboard"),
    
    # Dining Areas
    path("manage/areas/", views.DiningAreaListView.as_view(), name="area_list"),
    path("manage/areas/new/", views.DiningAreaCreateView.as_view(), name="area_create"),
    path("manage/areas/<int:pk>/edit/", views.DiningAreaUpdateView.as_view(), name="area_update"),
    path("manage/areas/<int:pk>/delete/", views.DiningAreaDeleteView.as_view(), name="area_delete"),  # Optional: delete view
    
    # Tables
    path("manage/tables/", views.TableListView.as_view(), name="table_list"),
    path("manage/tables/new/", views.TableCreateView.as_view(), name="table_create"),
    path("manage/tables/<int:pk>/edit/", views.TableUpdateView.as_view(), name="table_update"),
    path("manage/tables/<int:pk>/delete/", views.TableDeleteView.as_view(), name="table_delete"),  # Optional: delete view
    
    # Menu Categories
    path("manage/categories/", views.MenuCategoryListView.as_view(), name="category_list"),
    path("manage/categories/new/", views.MenuCategoryCreateView.as_view(), name="category_create"),
    path("manage/categories/<int:pk>/edit/", views.MenuCategoryUpdateView.as_view(), name="category_update"),
    path("manage/categories/<int:pk>/delete/", views.MenuCategoryDeleteView.as_view(), name="category_delete"),  # Optional: delete view
    
    # Menu Items
    path("manage/items/", views.MenuItemListView.as_view(), name="item_list"),
    path("manage/items/new/", views.MenuItemCreateView.as_view(), name="item_create"),
    path("manage/items/<int:pk>/edit/", views.MenuItemUpdateView.as_view(), name="item_update"),
    path("manage/items/<int:pk>/delete/", views.MenuItemDeleteView.as_view(), name="item_delete"),  # Optional: delete view
    path("manage/items/<int:pk>/toggle-status/", views.menu_item_toggle_status, name="item_toggle_status"),  # Quick active/inactive toggle
]