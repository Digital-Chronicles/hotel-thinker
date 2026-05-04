# finance/urls.py
from django.urls import path
from . import views

app_name = "finance"

urlpatterns = [
    # Dashboard
    path("", views.DashboardView.as_view(), name="dashboard"),
    
    # =========================================================
    # Invoices
    # =========================================================
    path("invoices/", views.InvoiceListView.as_view(), name="invoice_list"),
    path("invoices/create/", views.InvoiceCreateView.as_view(), name="invoice_create"),
    path("invoices/<int:pk>/", views.InvoiceDetailView.as_view(), name="invoice_detail"),
    path("invoices/<int:pk>/edit/", views.InvoiceUpdateView.as_view(), name="invoice_update"),
    path("invoices/<int:pk>/issue/", views.invoice_issue, name="invoice_issue"),
    path("invoices/<int:pk>/send/", views.invoice_send, name="invoice_send"),
    path("invoices/<int:pk>/void/", views.invoice_void, name="invoice_void"),
    path("invoices/<int:pk>/pay/", views.invoice_record_payment, name="invoice_pay"),
    
    # =========================================================
    # Expenses
    # =========================================================
    path("expenses/", views.ExpenseListView.as_view(), name="expense_list"),
    path("expenses/create/", views.ExpenseCreateView.as_view(), name="expense_create"),
    path("expenses/<int:pk>/", views.ExpenseDetailView.as_view(), name="expense_detail"),
    path("expenses/<int:pk>/edit/", views.ExpenseUpdateView.as_view(), name="expense_update"),
    path("expenses/<int:pk>/approve/", views.expense_approve, name="expense_approve"),
    path("expenses/<int:pk>/reject/", views.expense_reject, name="expense_reject"),
    path("expenses/<int:pk>/pay/", views.expense_mark_paid, name="expense_pay"),
    
    # =========================================================
    # Financial Periods
    # =========================================================
    path("periods/", views.PeriodListView.as_view(), name="period_list"),
    path("periods/create/", views.PeriodCreateView.as_view(), name="period_create"),
    path("periods/<int:pk>/", views.PeriodDetailView.as_view(), name="period_detail"),
    path("periods/<int:pk>/close/", views.period_close, name="period_close"),
    
    # =========================================================
    # Accounts (Chart of Accounts)
    # =========================================================
    path("accounts/", views.AccountListView.as_view(), name="account_list"),
    path("accounts/create/", views.AccountCreateView.as_view(), name="account_create"),
    path("accounts/<int:pk>/", views.AccountDetailView.as_view(), name="account_detail"),
    path("accounts/<int:pk>/edit/", views.AccountUpdateView.as_view(), name="account_update"),
    path("accounts/<int:pk>/delete/", views.account_delete, name="account_delete"),
    
    # =========================================================
    # Cash Accounts
    # =========================================================
    path("cash-accounts/", views.CashAccountListView.as_view(), name="cash_account_list"),
    path("cash-accounts/create/", views.CashAccountCreateView.as_view(), name="cash_account_create"),
    path("cash-accounts/<int:pk>/", views.CashAccountDetailView.as_view(), name="cash_account_detail"),
    path("cash-accounts/<int:pk>/edit/", views.CashAccountUpdateView.as_view(), name="cash_account_update"),
    path("cash-accounts/<int:pk>/delete/", views.cash_account_delete, name="cash_account_delete"),
    
    # =========================================================
    # Vendors
    # =========================================================
    path("vendors/", views.VendorListView.as_view(), name="vendor_list"),
    path("vendors/create/", views.VendorCreateView.as_view(), name="vendor_create"),
    path("vendors/<int:pk>/", views.VendorDetailView.as_view(), name="vendor_detail"),
    path("vendors/<int:pk>/edit/", views.VendorUpdateView.as_view(), name="vendor_update"),
    path("vendors/<int:pk>/delete/", views.vendor_delete, name="vendor_delete"),
    
    # =========================================================
    # Assets
    # =========================================================
    path("assets/", views.AssetListView.as_view(), name="asset_list"),
    path("assets/create/", views.AssetCreateView.as_view(), name="asset_create"),
    path("assets/<int:pk>/", views.AssetDetailView.as_view(), name="asset_detail"),
    path("assets/<int:pk>/edit/", views.AssetUpdateView.as_view(), name="asset_update"),
    path("assets/<int:pk>/delete/", views.asset_delete, name="asset_delete"),
    
    # =========================================================
    # Liabilities
    # =========================================================
    path("liabilities/", views.LiabilityListView.as_view(), name="liability_list"),
    path("liabilities/create/", views.LiabilityCreateView.as_view(), name="liability_create"),
    path("liabilities/<int:pk>/", views.LiabilityDetailView.as_view(), name="liability_detail"),
    path("liabilities/<int:pk>/edit/", views.LiabilityUpdateView.as_view(), name="liability_update"),
    path("liabilities/<int:pk>/delete/", views.liability_delete, name="liability_delete"),
    
    # =========================================================
    # Journal Entries
    # =========================================================
    path("journals/", views.JournalListView.as_view(), name="journal_list"),
    path("journals/create/", views.JournalEntryCreateView.as_view(), name="journal_create"),
    path("journals/<int:pk>/", views.JournalDetailView.as_view(), name="journal_detail"),
    path("journals/<int:pk>/edit/", views.JournalEntryUpdateView.as_view(), name="journal_update"),
    path("journals/<int:pk>/post/", views.journal_post, name="journal_post"),
    path("journals/<int:pk>/delete/", views.journal_delete, name="journal_delete"),
    path("journals/<int:journal_pk>/lines/add/", views.journal_line_add, name="journal_line_add"),
    path("journal-lines/<int:line_pk>/delete/", views.journal_line_delete, name="journal_line_delete"),
    
    # =========================================================
    # Financial Reports
    # =========================================================
    path("reports/profit-loss/", views.ProfitLossView.as_view(), name="profit_loss"),
    path("reports/cash-flow/", views.CashFlowView.as_view(), name="cash_flow"),
    path("reports/balance-sheet/", views.BalanceSheetView.as_view(), name="balance_sheet"),
    path("reports/trial-balance/", views.TrialBalanceView.as_view(), name="trial_balance"),
]