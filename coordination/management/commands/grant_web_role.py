from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Grant existing restricted PostgreSQL login the web permissions (never grant to a superuser/table owner)."

    def add_arguments(self, parser):
        parser.add_argument("role")

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            raise CommandError("PostgreSQL required")
        name = options["role"]
        with connection.cursor() as c:
            c.execute(
                "SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=%s", [name]
            )
            row = c.fetchone()
            if not row or row[0] or row[1]:
                raise CommandError(
                    "Role must exist and must not be superuser or bypass RLS"
                )
            c.execute(
                "SELECT 1 FROM pg_tables WHERE schemaname='public' AND tableowner=%s LIMIT 1",
                [name],
            )
            if c.fetchone():
                raise CommandError("Web role must not own tables")
            role = connection.ops.quote_name(name)
            c.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
            c.execute(
                f"GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO {role}"
            )
            c.execute(f"GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}")
            c.execute(
                f"REVOKE UPDATE,DELETE ON public.coordination_audit,public.coordination_history,public.coordination_letterhistory FROM {role}"
            )
            c.execute(f"REVOKE CREATE ON SCHEMA public FROM {role}")
        self.stdout.write(
            "Restricted web role granted. Enable ETCS_RLS=1 for web processes only. Run migrations and reminders with maintenance credentials."
        )
