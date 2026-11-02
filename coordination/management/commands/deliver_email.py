from datetime import timedelta
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.utils import timezone
from coordination.models import EmailDelivery


class Command(BaseCommand):
    help = "Deliver queued optional notification emails; failed deliveries are retried without rolling back user actions."

    def handle(self, *args, **kwargs):
        if settings.EMAIL_BACKEND.endswith("console.EmailBackend"):
            self.stdout.write(
                "Console backend: no notification emails marked as delivered"
            )
            return
        cutoff = timezone.now() - timedelta(minutes=5)
        ids = list(
            EmailDelivery.objects.filter(
                sent__isnull=True, attempts__lt=10
            ).values_list("pk", flat=True)[:100]
        )
        delivered = 0
        for pk in ids:
            with transaction.atomic():
                q = (
                    EmailDelivery.objects.select_for_update(skip_locked=True)
                    if connection.vendor == "postgresql"
                    else EmailDelivery.objects.select_for_update()
                )
                item = (
                    q.select_related("notification__user")
                    .filter(pk=pk, sent__isnull=True)
                    .first()
                )
                if not item or item.last_attempt and item.last_attempt > cutoff:
                    continue
                user = item.notification.user
                if not user.is_active or not user.email:
                    continue
                item.attempts += 1
                item.last_attempt = timezone.now()
                try:
                    count = send_mail(
                        "تنبيه من نظام تنسيق الكلية",
                        item.notification.text
                        + "\nيرجى تسجيل الدخول إلى النظام لمتابعة التفاصيل.",
                        None,
                        [user.email],
                    )
                    if count == 1:
                        item.sent = timezone.now()
                        delivered += 1
                except Exception:
                    # Do not log SMTP responses: they can contain credentials or provider details.
                    pass
                item.save(update_fields=["attempts", "last_attempt", "sent"])
        self.stdout.write(f"Notification emails delivered: {delivered}")
