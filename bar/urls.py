from django.urls import path
from . import views

app_name = "bar"

urlpatterns = [
    # Categories
    path("categories/", views.BarCategoryListView.as_view(), name="category_list"),
    path("categories/new/", views.BarCategoryCreateView.as_view(), name="category_create"),
    path("categories/<int:pk>/edit/", views.BarCategoryUpdateView.as_view(), name="category_update"),

    # Items
    path("items/", views.BarItemListView.as_view(), name="item_list"),
    path("items/new/", views.BarItemCreateView.as_view(), name="item_create"),
    path("items/<int:pk>/edit/", views.BarItemUpdateView.as_view(), name="item_update"),

    # Orders
    path("", views.BarOrderListView.as_view(), name="order_list"),
    path("new/", views.BarOrderCreateView.as_view(), name="order_create"),
    path("<int:pk>/", views.BarOrderDetailView.as_view(), name="order_detail"),
    
    # AJAX endpoints for order items (must come before edit/ to avoid conflicts)
    path("<int:pk>/items/add/", views.bar_order_add_item_ajax, name="order_add_item"),
    path("<int:pk>/items/<int:item_id>/remove/", views.bar_order_remove_item_ajax, name="order_remove_item"),
    path("<int:pk>/items/<int:item_id>/update-qty/", views.bar_order_update_item_qty_ajax, name="order_update_item_qty"),
    path("<int:pk>/items/refresh/", views.bar_order_refresh_items, name="order_refresh_items"),
    # Order workflow
    path("<int:pk>/edit/", views.BarOrderUpdateView.as_view(), name="order_update"),
    path("<int:pk>/mark-paid/", views.bar_order_mark_paid, name="order_mark_paid"),
    path("<int:pk>/mark-served/", views.bar_order_mark_served, name="order_mark_served"),
    path("<int:pk>/mark-billed/", views.bar_order_mark_billed, name="order_mark_billed"),
    path("<int:pk>/cancel/", views.bar_order_cancel, name="order_cancel"),
]