# rooms/templatetags/math_filters.py
from django import template

register = template.Library()

@register.filter
def div(value, arg):
    """Divide value by argument"""
    try:
        return float(value) / float(arg)
    except (ValueError, ZeroDivisionError, TypeError):
        return 0

@register.filter
def mul(value, arg):
    """Multiply value by argument"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def sub(value, arg):
    """Subtract argument from value"""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return 0