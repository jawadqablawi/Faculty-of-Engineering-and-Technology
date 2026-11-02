from django.core.management.base import BaseCommand
from django.db import connection, transaction
from coordination.models import Activity, Profile
from coordination.scheduling import sync_calendar


class Command(BaseCommand):
    help = "Rebuild the safe faculty calendar using an active coordinator context."

    @transaction.atomic
    def handle(self, *args, **kwargs):
        profile = Profile.objects.filter(
            role="coordinator", verified=True, user__is_active=True
        ).first()
        if connection.vendor == "postgresql" and profile:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('etcs.user_id',%s,true)", [str(profile.user_id)]
                )
        for pk in Activity.objects.values_list("pk", flat=True):
            sync_calendar(pk)
        self.stdout.write("Calendar projection rebuilt")
