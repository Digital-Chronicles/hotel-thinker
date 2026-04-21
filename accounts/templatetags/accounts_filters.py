# accounts/templatetags/accounts_filters.py
from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Get an item from a dictionary by key"""
    if dictionary is None:
        return 0
    return dictionary.get(key, 0)

@register.filter
def get_role_count(role_counts, role):
    """Get count for a specific role"""
    if not role_counts:
        return 0
    return role_counts.get(role, 0)