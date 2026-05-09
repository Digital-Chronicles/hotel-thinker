# rooms/templatetags/currency_filters.py
from django import template

register = template.Library()

@register.filter
def format_ugx(value):
    """Format number as UGX currency with commas"""
    try:
        value = float(value)
        # Format with commas for thousands
        formatted = f"{value:,.0f}"
        return formatted
    except (ValueError, TypeError):
        return "0"