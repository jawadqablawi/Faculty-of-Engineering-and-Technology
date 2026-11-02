import sqlite3, shutil, os, subprocess
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
        dest.mkdir(parents=True, mode=0o700)
        database = settings.DATABASES["default"]
        if database["ENGINE"] == "django.db.backends.sqlite3":
            source = sqlite3.connect(str(database["NAME"]))
            target = sqlite3.connect(str(dest / "db.sqlite3"))
            try:
                source.backup(target)
            finally:
                source.close()
                target.close()
            os.chmod(dest / "db.sqlite3", 0o600)
        elif database["ENGINE"] == "django.db.backends.postgresql":
            env = os.environ.copy()
            env["PGPASSWORD"] = database.get("PASSWORD", "")
            env["PGSSLMODE"] = database.get("OPTIONS", {}).get("sslmode", "require")
            args = [
                "pg_dump",
                "--format=custom",
                "--no-owner",
                "--host",
                database["HOST"],
                "--port",
                str(database.get("PORT", 5432)),
                "--username",
                database["USER"],
                "--file",
                str(dest / "database.dump"),
                database["NAME"],
            ]
            try:
                subprocess.run(args, env=env, check=True, capture_output=True)
            except (OSError, subprocess.CalledProcessError):
                raise CommandError(
                    "PostgreSQL backup failed. Use maintenance credentials and a compatible pg_dump version; no credentials or provider output printed."
                )
            os.chmod(dest / "database.dump", 0o600)
        else:
            raise CommandError("Unsupported database backend")
        if settings.MEDIA_ROOT.exists():
            shutil.copytree(settings.MEDIA_ROOT, dest / "private_media")
        self.stdout.write(
            "Database and private media backed up. For consistency, pause uploads during backup. Store configuration and secrets separately in secure storage."
        )
