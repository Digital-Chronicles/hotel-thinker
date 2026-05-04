from django.urls import path
from . import views

app_name = "bulk"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("import/", views.import_data, name="import"),
    path("export/", views.export_data, name="export"),
    path("template/", views.download_template, name="template"),
    path("model-fields/", views.model_fields, name="model_fields"),
]