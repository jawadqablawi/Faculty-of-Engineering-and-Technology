import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .access import profile
from .models import PushPreference, PushSubscription
from .push import MAX_DEVICES, configured, valid_key, validate_endpoint


def read_json(request):
    if request.content_type != "application/json" or len(request.body) > 4096:
        return {}
    try:
        data = json.loads(request.body)
    except (ValueError, UnicodeError):
        return {}
    return data if isinstance(data, dict) else {}


@login_required
@never_cache
@require_GET
def public_key(request):
    profile(request.user)
    return JsonResponse(
        {
            "public_key": settings.VAPID_PUBLIC_KEY if configured() else "",
            "endpoints": list(
                PushSubscription.objects.filter(
                    user=request.user, active=True
                ).values_list("endpoint", flat=True)
            ),
        }
    )


@login_required
@never_cache
@require_POST
def subscribe(request):
    profile(request.user)
    if not configured():
        return JsonResponse({"error": "unavailable"}, status=503)
    data = read_json(request)
    endpoint, keys = data.get("endpoint"), data.get("keys")
    if not (
        validate_endpoint(endpoint)
        and isinstance(keys, dict)
        and valid_key(keys.get("p256dh"), 65, 4)
        and valid_key(keys.get("auth"), 16)
    ):
        return JsonResponse({"error": "invalid_subscription"}, status=400)
    try:
        with transaction.atomic():
            User.objects.select_for_update().get(pk=request.user.pk)
            owned = PushSubscription.objects.filter(user=request.user)
            existing = owned.filter(endpoint=endpoint).exists()
            if not existing and owned.count() >= MAX_DEVICES:
                return JsonResponse({"error": "device_limit"}, status=409)
            owned.update_or_create(
                user=request.user,
                endpoint=endpoint,
                defaults={
                    "p256dh": keys["p256dh"],
                    "auth": keys["auth"],
                    "active": True,
                    "user_agent": request.headers.get("User-Agent", "")[:300],
                },
            )
    except IntegrityError:
        return JsonResponse({"error": "endpoint_unavailable"}, status=409)
    return JsonResponse({"active": True})


@login_required
@never_cache
@require_POST
def unsubscribe(request):
    profile(request.user)
    endpoint = read_json(request).get("endpoint")
    if not validate_endpoint(endpoint):
        return JsonResponse({"error": "invalid_subscription"}, status=400)
    PushSubscription.objects.filter(user=request.user, endpoint=endpoint).delete()
    return JsonResponse({"active": False})


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def preferences(request):
    profile(request.user)
    devices = PushSubscription.objects.filter(user=request.user)
    if request.method == "POST":
        if request.POST.get("action") == "remove":
            try:
                device_id = int(request.POST.get("device", ""))
            except ValueError:
                raise Http404
            get_object_or_404(devices, pk=device_id).delete()
            messages.success(request, "تمت إزالة الجهاز.")
        elif request.POST.get("action") == "save":
            fields = ("enabled", "new_requests", "status_changes", "reminders")
            PushPreference.objects.update_or_create(
                user=request.user,
                defaults={field: field in request.POST for field in fields},
            )
            messages.success(request, "تم حفظ تفضيلات الإشعارات.")
        return redirect("push_preferences")
    preference = PushPreference.objects.filter(user=request.user).first()
    return render(
        request,
        "coordination/push_preferences.html",
        {
            "preference": preference or PushPreference(user=request.user),
            "devices": devices.order_by("-created"),
        },
    )
