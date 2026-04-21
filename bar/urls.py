from django.urls import path
from . import views

app_name = "bar"

urlpatterns = [
    path("categories/", views.BarCategoryListView.as_view(), name="category_list"),
    path("categories/new/", views.BarCategoryCreateView.as_view(), name="category_create"),
    path("categories/<int:pk>/edit/", views.BarCategoryUpdateView.as_view(), name="category_update"),

    path("items/", views.BarItemListView.as_view(), name="item_list"),
    path("items/new/", views.BarItemCreateView.as_view(), name="item_create"),
    path("items/<int:pk>/edit/", views.BarItemUpdateView.as_view(), name="item_update"),

    path("", views.BarOrderListView.as_view(), name="order_list"),
    path("new/", views.BarOrderCreateView.as_view(), name="order_create"),
    path("<int:pk>/", views.BarOrderDetailView.as_view(), name="order_detail"),
    path("<int:pk>/edit/", views.BarOrderUpdateView.as_view(), name="order_update"),

    path("<int:pk>/mark-paid/", views.bar_order_mark_paid, name="order_mark_paid"),
    path("<int:pk>/mark-served/", views.bar_order_mark_served, name="order_mark_served"),
    path("<int:pk>/cancel/", views.bar_order_cancel, name="order_cancel"),
]