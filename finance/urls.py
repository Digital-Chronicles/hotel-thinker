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
    # Vendors (FULL CRUD)
    # =========================
    path("vendors/", views.VendorListView.as_view(), name="vendor_list"),
    path("vendors/create/", views.VendorCreateView.as_view(), name="vendor_create"),
    path("vendors/<int:pk>/", views.VendorDetailView.as_view(), name="vendor_detail"),
    path("vendors/<int:pk>/edit/", views.VendorUpdateView.as_view(), name="vendor_edit"),
    path("vendors/<int:pk>/delete/", views.vendor_delete, name="vendor_delete"),


    # =========================
    # Assets (FULL CRUD)
    # =========================
    path("assets/", views.AssetListView.as_view(), name="asset_list"),
    path("assets/create/", views.AssetCreateView.as_view(), name="asset_create"),
    path("assets/<int:pk>/", views.AssetDetailView.as_view(), name="asset_detail"),
    path("assets/<int:pk>/edit/", views.AssetUpdateView.as_view(), name="asset_edit"),
    path("assets/<int:pk>/delete/", views.asset_delete, name="asset_delete"),


    # =========================
    # Liabilities (FULL CRUD)
    # =========================
    path("liabilities/", views.LiabilityListView.as_view(), name="liability_list"),
    path("liabilities/create/", views.LiabilityCreateView.as_view(), name="liability_create"),
    path("liabilities/<int:pk>/", views.LiabilityDetailView.as_view(), name="liability_detail"),
    path("liabilities/<int:pk>/edit/", views.LiabilityUpdateView.as_view(), name="liability_edit"),
    path("liabilities/<int:pk>/delete/", views.liability_delete, name="liability_delete"),


    # =========================
    # Journals (FULL CRUD + Lines)
    # =========================
    path("journals/", views.JournalListView.as_view(), name="journal_list"),
    path("journals/create/", views.JournalEntryCreateView.as_view(), name="journal_create"),
    path("journals/<int:pk>/", views.JournalDetailView.as_view(), name="journal_detail"),
    path("journals/<int:pk>/edit/", views.JournalEntryUpdateView.as_view(), name="journal_edit"),
    path("journals/<int:pk>/delete/", views.journal_delete, name="journal_delete"),
    path("journals/<int:pk>/post/", views.journal_post, name="journal_post"),
    
    # Journal Lines (nested)
    path("journals/<int:journal_pk>/line/add/", views.journal_line_add, name="journal_line_add"),
    path("journal-lines/<int:line_pk>/delete/", views.journal_line_delete, name="journal_line_delete"),


    # =========================
    # Financial Reports
    # =========================
    path("reports/profit-loss/", views.ProfitLossView.as_view(), name="profit_loss"),
    path("reports/cash-flow/", views.CashFlowView.as_view(), name="cash_flow"),
    path("reports/balance-sheet/", views.BalanceSheetView.as_view(), name="balance_sheet"),
]