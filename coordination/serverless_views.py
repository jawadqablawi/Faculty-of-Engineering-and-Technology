import secrets
from django.conf import settings
from django.core.management import call_command
from django.db import connection, transaction
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from .models import Profile


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
    call_command("reminders")
    call_command("deliver_email")
    return JsonResponse({"status": "processed"})
