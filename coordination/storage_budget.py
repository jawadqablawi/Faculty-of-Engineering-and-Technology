from datetime import timedelta

from django.conf import settings
from django.contrib.sessions.models import Session
from django.db import connection
from django.utils import timezone

from .models import Activity, EmailDelivery, Notification, PushDelivery


def storage_usage():
    if connection.vendor != "postgresql":
        return None
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_database_size(current_database())")
        size = cursor.fetchone()[0]
        cursor.execute("""
            SELECT relname, pg_total_relation_size(relid) AS bytes
            FROM pg_stat_user_tables
            WHERE schemaname = 'public'
            ORDER BY bytes DESC, relname
            LIMIT 10
        """)
        tables = cursor.fetchall()
    percent = 100 * size / max(settings.ETCS_STORAGE_BUDGET_BYTES, 1)
    return {"size": size, "percent": percent, "tables": tables}


def retention_preview():
    now = timezone.now()
    deliveries = now - timedelta(days=max(1, settings.ETCS_RETENTION_DELIVERY_DAYS))
    read = now - timedelta(days=max(1, settings.ETCS_RETENTION_READ_DAYS))
    drafts = now - timedelta(days=max(1, settings.ETCS_RETENTION_DRAFT_DAYS))
    return {
        "expired_sessions": Session.objects.filter(expire_date__lt=now).count(),
        "old_read_notifications": Notification.objects.filter(
            read=True, created__lt=read
        )
        .exclude(pushdelivery__outcome="pending")
        .exclude(email_delivery__sent__isnull=True, email_delivery__isnull=False)
        .count(),
        "old_push_deliveries": PushDelivery.objects.filter(
            notification__created__lt=deliveries
        )
        .exclude(outcome="pending")
        .count(),
        "old_unsent_email": EmailDelivery.objects.filter(
            sent__isnull=True, attempts__gt=0, last_attempt__lt=deliveries
        ).count(),
        "old_drafts_for_review": Activity.objects.filter(
            status="draft", updated__lt=drafts, submitted__isnull=True
        ).count(),
    }
