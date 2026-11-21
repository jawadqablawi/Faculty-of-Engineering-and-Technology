import secrets

from django.conf import settings
from django.core.management import call_command
from django.db import connection, transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from .models import Notification, Profile
from .push import defer_immediate, schedule_retries
from .storage_budget import retention_preview, storage_usage


@require_GET
@transaction.atomic
def cron_reminders(request):
    expected = settings.ETCS_CRON_SECRET
    provided = request.headers.get("Authorization", "")
    if not expected or not secrets.compare_digest(provided, "Bearer " + expected):
        return JsonResponse({"error": "unauthorized"}, status=401)
    owner = Profile.objects.filter(
        role="coordinator", verified=True, user__is_active=True
    ).first()
    if not owner:
        return JsonResponse({"error": "coordinator_not_configured"}, status=503)
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('etcs.user_id',%s,true)", [str(owner.user_id)]
            )
    token = defer_immediate.set(True)
    try:
        call_command("reminders")
        usage = storage_usage()
        month = timezone.localdate().strftime("%Y-%m")
        if usage and usage["percent"] >= 80:
            Notification.objects.get_or_create(
                key=f"storage-budget:{month}:{owner.user_id}",
                defaults={
                    "user_id": owner.user_id,
                    "text": "تجاوز تخزين قاعدة البيانات 80% من الميزانية.",
                },
            )
        if timezone.localdate().day == 1:
            retention_preview_result = retention_preview()
        else:
            retention_preview_result = None
    finally:
        defer_immediate.reset(token)
    schedule_retries()
    call_command("deliver_email")
    return JsonResponse(
        {"status": "processed", "retention_preview": retention_preview_result}
    )
