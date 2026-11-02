from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Notification, EmailDelivery


@receiver(post_save, sender=Notification)
def queue_notification_email(sender, instance, created, **kwargs):
    if created and settings.ETCS_EMAIL_NOTIFICATIONS:
        EmailDelivery.objects.get_or_create(notification=instance)


from django.db.models.signals import post_delete
from .models import Activity, EventDate, WorkshopSession


@receiver(post_save, sender=Activity)
def update_activity_calendar(sender, instance, **kwargs):
    from .scheduling import sync_calendar

    sync_calendar(instance.pk)


@receiver(post_save, sender=EventDate)
@receiver(post_delete, sender=EventDate)
@receiver(post_save, sender=WorkshopSession)
@receiver(post_delete, sender=WorkshopSession)
def update_session_calendar(sender, instance, **kwargs):
    from .scheduling import sync_calendar

    sync_calendar(instance.activity_id)


from django.db.models.signals import pre_save
from django.db import connection


@receiver(pre_save, sender=Notification)
def bind_cron_notification_sender(sender, instance, **kwargs):
    if not instance.sender_id and connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT NULLIF(current_setting('etcs.user_id',true),'')::bigint"
            )
            instance.sender_id = cursor.fetchone()[0]
