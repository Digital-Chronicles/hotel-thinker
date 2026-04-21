from django.urls import path
from . import views

app_name = "finance"

urlpatterns = [

    # =========================
    # Dashboard
    # =========================
    path("", views.DashboardView.as_view(), name="dashboard"),


    # =========================
    # Invoices
    # =========================
    path("invoices/", views.InvoiceListView.as_view(), name="invoice_list"),
    path("invoices/<int:pk>/", views.InvoiceDetailView.as_view(), name="invoice_detail"),

    # Actions
    path("invoices/<int:pk>/issue/", views.invoice_issue, name="invoice_issue"),
    path("invoices/<int:pk>/send/", views.invoice_mark_sent, name="invoice_mark_sent"),
    path("invoices/<int:pk>/payment/", views.invoice_record_payment, name="invoice_record_payment"),


    # =========================
    # Expenses
    # =========================
    path("expenses/", views.ExpenseListView.as_view(), name="expense_list"),
    path("expenses/new/", views.ExpenseCreateView.as_view(), name="expense_create"),
    path("expenses/<int:pk>/", views.ExpenseDetailView.as_view(), name="expense_detail"),
    path("expenses/<int:pk>/edit/", views.ExpenseUpdateView.as_view(), name="expense_update"),

    # Actions
    path("expenses/<int:pk>/approve/", views.expense_approve, name="expense_approve"),
    path("expenses/<int:pk>/reject/", views.expense_reject, name="expense_reject"),
    path("expenses/<int:pk>/pay/", views.expense_mark_paid, name="expense_mark_paid"),


    # =========================
    # Financial Periods
    # =========================
    path("periods/", views.PeriodListView.as_view(), name="period_list"),
    path("periods/<int:pk>/", views.PeriodDetailView.as_view(), name="period_detail"),
    path("periods/<int:pk>/close/", views.period_close, name="period_close"),


    # =========================
    # Accounts
    # =========================
    path("accounts/", views.AccountListView.as_view(), name="account_list"),
    path("accounts/<int:pk>/", views.AccountDetailView.as_view(), name="account_detail"),


    # =========================
    # Vendors
    # =========================
    path("vendors/", views.VendorListView.as_view(), name="vendor_list"),
    path("vendors/<int:pk>/", views.VendorDetailView.as_view(), name="vendor_detail"),


    # =========================
    # Assets
    # =========================
    path("assets/", views.AssetListView.as_view(), name="asset_list"),
    path("assets/<int:pk>/", views.AssetDetailView.as_view(), name="asset_detail"),


    # =========================
    # Liabilities
    # =========================
    path("liabilities/", views.LiabilityListView.as_view(), name="liability_list"),
    path("liabilities/<int:pk>/", views.LiabilityDetailView.as_view(), name="liability_detail"),


    # =========================
    # Journals
    # =========================
    path("journals/", views.JournalListView.as_view(), name="journal_list"),
    path("journals/<int:pk>/", views.JournalDetailView.as_view(), name="journal_detail"),
    path("journals/<int:pk>/post/", views.journal_post, name="journal_post"),


    # =========================
    # Financial Reports (NEW 🔥)
    # =========================
    path("reports/profit-loss/", views.ProfitLossView.as_view(), name="profit_loss"),
    path("reports/cash-flow/", views.CashFlowView.as_view(), name="cash_flow"),
    path("reports/balance-sheet/", views.BalanceSheetView.as_view(), name="balance_sheet"),
]