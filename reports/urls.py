from django.urls import path
from . import views

app_name = "reports"

urlpatterns = [
    path("", views.ReportsHomeView.as_view(), name="index"),
    path("profit-and-loss/", views.ProfitAndLossReportView.as_view(), name="profit_and_loss"),
]