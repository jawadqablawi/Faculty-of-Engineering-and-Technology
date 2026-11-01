import sqlite3, shutil, os
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Create a consistent SQLite backup and private media copy in a NEW directory."
    )

    def add_arguments(self, parser):
        parser.add_argument("destination")

    def handle(self, *args, **options):
        dest = Path(options["destination"]).resolve()
        if dest.exists():
            raise CommandError("Destination must not already exist")
        if settings.DATABASES["default"]["ENGINE"] != "django.db.backends.sqlite3":
            raise CommandError("This command supports SQLite only")
        dest.mkdir(parents=True, mode=0o700)
        source = sqlite3.connect(str(settings.DATABASES["default"]["NAME"]))
        target = sqlite3.connect(str(dest / "db.sqlite3"))
        try:
            source.backup(target)
        finally:
            source.close()
            target.close()
        os.chmod(dest / "db.sqlite3", 0o600)
        if settings.MEDIA_ROOT.exists():
            shutil.copytree(settings.MEDIA_ROOT, dest / "private_media")
        self.stdout.write(
            "Database and private media backed up. For consistency, pause uploads during backup. Store configuration and secrets separately in secure storage."
        )
