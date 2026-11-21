from django import template

from coordination.request_tracking import compact_progress

register = template.Library()
register.filter("compact_progress", compact_progress)
