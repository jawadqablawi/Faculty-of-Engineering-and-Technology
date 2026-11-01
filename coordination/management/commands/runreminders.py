import time
from django.core.management import BaseCommand, call_command
from django.db import close_old_connections


class Command(BaseCommand):
    help = "Run the idempotent reminder job every five minutes; supervise this process in production."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        while True:
            close_old_connections()
            call_command("reminders")
            if options["once"]:
                return
            try:
                time.sleep(300)
            except KeyboardInterrupt:
                return
