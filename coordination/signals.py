from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Notification, EmailDelivery


@receiver(post_save, sender=Notification)
def queue_notification_email(sender, instance, created, **kwargs):
    if created and settings.ETCS_EMAIL_NOTIFICATIONS:
        EmailDelivery.objects.get_or_create(notification=instance)
