"""Noninteractive first deployment. Credentials come only from private Vercel settings."""

import os
from django.core.management import BaseCommand, CommandError, call_command
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db import transaction
from coordination.models import Profile


class Command(BaseCommand):
    help = "Migrate, seed clubs and optionally create the initial coordinator from private environment variables."

    def handle(self, *args, **kwargs):
        if (
            os.environ.get("VERCEL_ENV") in ["preview", "development"]
            and os.environ.get("ETCS_ALLOW_PREVIEW_WRITE") != "1"
        ):
            raise CommandError(
                "Preview builds must use a separate database and explicit ETCS_ALLOW_PREVIEW_WRITE=1; production data was not changed"
            )
        call_command("migrate", interactive=False)
        call_command("bootstrap")
        if not Profile.objects.filter(
            role="coordinator", user__is_active=True
        ).exists():
            email = os.environ.get("ETCS_OWNER_EMAIL", "").strip().lower()
            password = os.environ.get("ETCS_OWNER_PASSWORD", "")
            if not email or not password:
                raise CommandError(
                    "Set ETCS_OWNER_EMAIL and ETCS_OWNER_PASSWORD in private Vercel environment settings for the first deployment"
                )
            user = User(username=email, email=email, is_staff=True, is_superuser=True)
            try:
                validate_email(email)
                if len(email) > 150:
                    raise ValidationError("Email too long")
                validate_password(password, user)
            except ValidationError:
                raise CommandError(
                    "Initial owner email/password did not pass validation; no credential values printed"
                )
            if User.objects.filter(username=email).exists():
                raise CommandError(
                    "Owner email already belongs to an existing account; no account or password was overwritten"
                )
            with transaction.atomic():
                user.set_password(password)
                user.save()
                Profile.objects.create(user=user, role="coordinator", verified=True)
            self.stdout.write("Initial coordinator created. Password was not printed.")
        call_command("rebuild_calendar")
        if os.environ.get("VERCEL") == "1":
            from django.conf import settings
            from django.db import connection, DatabaseError
            from psycopg import sql
            import hashlib, hmac, re

            role = os.environ.get("ETCS_RUNTIME_ROLE", "etcs_vercel_web")
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", role):
                raise CommandError("Invalid runtime database role name")
            password = hmac.new(
                settings.SECRET_KEY.encode(),
                ("etcs-runtime:" + role).encode(),
                hashlib.sha256,
            ).hexdigest()
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=%s",
                        [role],
                    )
                    row = cursor.fetchone()
                    if row and (row[0] or row[1]):
                        raise CommandError(
                            "Existing runtime role is privileged; refusing to use it"
                        )
                    if not row:
                        cursor.execute(
                            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                                sql.Identifier(role), sql.Literal(password)
                            )
                        )
                    else:
                        cursor.execute(
                            sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                                sql.Identifier(role), sql.Literal(password)
                            )
                        )
                call_command("grant_web_role", role)
            except DatabaseError:
                raise CommandError(
                    "Runtime database role could not be prepared. Verify that the project owner connection can create SQL roles. No credential values printed."
                )
        self.stdout.write("Vercel database preparation complete")
