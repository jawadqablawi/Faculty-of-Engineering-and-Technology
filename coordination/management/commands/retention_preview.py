import json

from django.core.management.base import BaseCommand

from coordination.storage_budget import retention_preview


class Command(BaseCommand):
    help = "Count retention candidates visible to the current database role. Never deletes rows."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Default; performs read-only counts."
        )

    def handle(self, *args, **options):
        self.stdout.write(
            json.dumps({"dry_run": True, **retention_preview()}, sort_keys=True)
        )
