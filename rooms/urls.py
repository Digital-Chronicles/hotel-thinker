# rooms/urls.py
from django.urls import path
from . import views

app_name = "rooms"

urlpatterns = [
    # Dashboard
    path("manage/", views.RoomsManageDashboardView.as_view(), name="manage_dashboard"),

    # Room Types
    path("room-types/", views.RoomTypeListView.as_view(), name="roomtype_list"),
    path("room-types/new/", views.RoomTypeCreateView.as_view(), name="roomtype_create"),
    path("room-types/<int:pk>/edit/", views.RoomTypeUpdateView.as_view(), name="roomtype_update"),
    path("room-types/<int:pk>/delete/", views.roomtype_delete, name="roomtype_delete"),
    path("room-types/<int:pk>/toggle-active/", views.roomtype_toggle_active, name="roomtype_toggle_active"),

    # Rooms
    path("", views.RoomListView.as_view(), name="room_list"),
    path("new/", views.RoomCreateView.as_view(), name="room_create"),
    path("<int:pk>/", views.RoomDetailView.as_view(), name="room_detail"),
    path("<int:pk>/edit/", views.RoomUpdateView.as_view(), name="room_update"),
    path("<int:pk>/set-status/", views.room_set_status, name="room_set_status"),
    path("<int:pk>/toggle-active/", views.room_toggle_active, name="room_toggle_active"),
    path("bulk-status-update/", views.room_bulk_status_update, name="room_bulk_status_update"),

    # Room Images
    path("images/", views.RoomImageListView.as_view(), name="image_list"),
    path("images/upload/", views.room_image_upload, name="image_upload"),
    path("images/upload/<int:room_id>/", views.room_image_upload, name="image_upload_for_room"),
    path("images/bulk-upload/", views.room_image_bulk_upload, name="image_bulk_upload"),
    path("images/bulk-upload/<int:room_id>/", views.room_image_bulk_upload, name="image_bulk_upload_for_room"),
    path("images/<int:pk>/update/", views.room_image_update, name="image_update"),
    path("images/<int:pk>/delete/", views.room_image_delete, name="image_delete"),
    path("images/<int:pk>/set-primary/", views.room_image_set_primary, name="image_set_primary"),
    path("images/reorder/", views.room_image_reorder, name="image_reorder"),

    # Room Image Galleries
    path("galleries/", views.RoomImageGalleryListView.as_view(), name="gallery_list"),
    path("galleries/new/", views.RoomImageGalleryCreateView.as_view(), name="gallery_create"),
    path("galleries/<int:pk>/", views.RoomImageGalleryDetailView.as_view(), name="gallery_detail"),
    path("galleries/<int:pk>/edit/", views.RoomImageGalleryUpdateView.as_view(), name="gallery_update"),
    path("galleries/<int:pk>/delete/", views.room_image_gallery_delete, name="gallery_delete"),
    path("galleries/<int:pk>/add-images/", views.room_image_gallery_add_images, name="gallery_add_images"),
    path("galleries/<int:gallery_pk>/remove-image/<int:image_pk>/", views.room_image_gallery_remove_image, name="gallery_remove_image"),

    # ============================================================
    # ASSET MANAGEMENT URLS
    # ============================================================
    
    # Asset Categories
    path("asset-categories/", views.AssetCategoryListView.as_view(), name="asset_category_list"),
    path("asset-categories/create/", views.asset_category_create, name="asset_category_create"),
    
    # Assets
    path("assets/", views.AssetListView.as_view(), name="asset_list"),
    path("assets/new/", views.AssetCreateView.as_view(), name="asset_create"),
    path("assets/<int:pk>/", views.AssetDetailView.as_view(), name="asset_detail"),
    path("assets/<int:pk>/edit/", views.AssetUpdateView.as_view(), name="asset_update"),
    path("assets/<int:pk>/delete/", views.asset_delete, name="asset_delete"),
    path("assets/<int:pk>/calculate-depreciation/", views.asset_calculate_depreciation, name="asset_calculate_depreciation"),
    path("assets/bulk-depreciation/", views.asset_bulk_depreciation, name="asset_bulk_depreciation"),
    
    # ============================================================
    # LIABILITY MANAGEMENT URLS
    # ============================================================
    
    # Liabilities
    path("liabilities/", views.LiabilityListView.as_view(), name="liability_list"),
    path("liabilities/new/", views.LiabilityCreateView.as_view(), name="liability_create"),
    path("liabilities/<int:pk>/", views.LiabilityDetailView.as_view(), name="liability_detail"),
    path("liabilities/<int:pk>/edit/", views.LiabilityUpdateView.as_view(), name="liability_update"),
    path("liabilities/<int:pk>/delete/", views.liability_delete, name="liability_delete"),
    path("liabilities/<int:pk>/pay/", views.liability_make_payment, name="liability_pay"),
    path("liabilities/<int:pk>/mark-paid/", views.liability_mark_paid, name="liability_mark_paid"),
    
    # ============================================================
    # FINANCIAL DASHBOARD URLS
    # ============================================================
    
    path("financial-dashboard/", views.RoomsFinancialDashboardView.as_view(), name="financial_dashboard"),

    # API Endpoints
    path("api/rooms/", views.room_list_api, name="room_list_api"),
    path("api/rooms/<int:room_id>/images/", views.room_images_api, name="room_images_api"),
]