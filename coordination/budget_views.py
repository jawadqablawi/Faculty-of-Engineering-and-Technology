from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render

from .access import profile
from .storage_budget import storage_usage


@login_required
def database_budget(request):
    if profile(request.user).role != "coordinator":
        raise PermissionDenied
    return render(
        request, "coordination/database_budget.html", {"usage": storage_usage()}
    )
