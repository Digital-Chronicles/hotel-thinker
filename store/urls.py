from django.urls import path

from . import views

app_name = "store"

urlpatterns = [
    # Categories
    path("categories/", views.StoreCategoryListView.as_view(), name="category_list"),
    path("categories/new/", views.StoreCategoryCreateView.as_view(), name="category_create"),
    path("categories/<int:pk>/edit/", views.StoreCategoryUpdateView.as_view(), name="category_update"),

    # Items
    path("items/", views.StoreItemListView.as_view(), name="item_list"),
    path("items/new/", views.StoreItemCreateView.as_view(), name="item_create"),
    path("items/<int:pk>/edit/", views.StoreItemUpdateView.as_view(), name="item_update"),

    # Suppliers
    path("suppliers/", views.StoreSupplierListView.as_view(), name="supplier_list"),
    path("suppliers/new/", views.StoreSupplierCreateView.as_view(), name="supplier_create"),
    path("suppliers/<int:pk>/edit/", views.StoreSupplierUpdateView.as_view(), name="supplier_update"),

    # Purchase Orders
    path("purchase-orders/", views.StorePurchaseOrderListView.as_view(), name="purchase_order_list"),
    path("purchase-orders/new/", views.StorePurchaseOrderCreateView.as_view(), name="purchase_order_create"),
    path("purchase-orders/<int:pk>/", views.StorePurchaseOrderDetailView.as_view(), name="purchase_order_detail"),
    path("purchase-orders/<int:pk>/edit/", views.StorePurchaseOrderUpdateView.as_view(), name="purchase_order_update"),
    path("purchase-orders/<int:pk>/approve/", views.store_purchase_order_approve, name="purchase_order_approve"),

    # Goods Receipts
    path("goods-receipts/", views.StoreGoodsReceiptListView.as_view(), name="goods_receipt_list"),
    path("goods-receipts/new/", views.StoreGoodsReceiptCreateView.as_view(), name="goods_receipt_create"),
    path("goods-receipts/<int:pk>/", views.StoreGoodsReceiptDetailView.as_view(), name="goods_receipt_detail"),

    # Sales
    path("", views.StoreSaleListView.as_view(), name="sale_list"),
    path("new/", views.StoreSaleCreateView.as_view(), name="sale_create"),
    path("<int:pk>/", views.StoreSaleDetailView.as_view(), name="sale_detail"),
    path("<int:pk>/edit/", views.StoreSaleUpdateView.as_view(), name="sale_update"),
    path("<int:pk>/mark-paid/", views.store_sale_mark_paid, name="sale_mark_paid"),
    path("<int:pk>/cancel/", views.store_sale_cancel, name="sale_cancel"),
]