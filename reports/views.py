from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.utils.dateparse import parse_date

from .services import get_profit_and_loss_data


class ReportsHomeView(LoginRequiredMixin, TemplateView):
    template_name = "reports/index.html"


class ProfitAndLossReportView(LoginRequiredMixin, TemplateView):
    template_name = "reports/profit_and_loss.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        start_date = parse_date(self.request.GET.get("start_date", ""))
        end_date = parse_date(self.request.GET.get("end_date", ""))

        report = get_profit_and_loss_data(start_date=start_date, end_date=end_date)

        context["report"] = report
        context["start_date"] = start_date
        context["end_date"] = end_date
        return context