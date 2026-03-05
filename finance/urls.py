# finance/urls.py
from django.urls import path
from . import views

app_name = "finance"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    # Invoices
    path("invoices/", views.InvoiceListView.as_view(), name="invoice_list"),
    path("invoices/<int:pk>/", views.InvoiceDetailView.as_view(), name="invoice_detail"),
    path("invoices/<int:pk>/issue/", views.invoice_issue, name="invoice_issue"),
    path("invoices/<int:pk>/record-payment/", views.invoice_record_payment, name="invoice_record_payment"),

    # Expenses
    path("expenses/", views.ExpenseListView.as_view(), name="expense_list"),
    path("expenses/new/", views.ExpenseCreateView.as_view(), name="expense_create"),
    path("expenses/<int:pk>/approve/", views.expense_approve, name="expense_approve"),
    path("expenses/<int:pk>/reject/", views.expense_reject, name="expense_reject"),
    path("expenses/<int:pk>/mark-paid/", views.expense_mark_paid, name="expense_mark_paid"),

    # Financial Periods
    path("periods/", views.PeriodListView.as_view(), name="period_list"),
]