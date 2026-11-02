from django.db import connection, transaction
from django.core.exceptions import ImproperlyConfigured


class DatabaseIdentityMiddleware:
    """Transaction-local PostgreSQL identity; never retained on pooled connections."""

    def __init__(self, get_response):
        self.get_response = get_response
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT rolsuper,rolbypassrls OR EXISTS(SELECT 1 FROM pg_roles elevated WHERE elevated.rolbypassrls AND pg_has_role(current_user,elevated.oid,'MEMBER')) FROM pg_roles WHERE rolname=current_user"
            )
            role = cursor.fetchone()
            if role and (role[0] or role[1]):
                raise ImproperlyConfigured(
                    "RLS web processes must use a non-superuser role without BYPASSRLS"
                )

    def __call__(self, request):
        user_id = str(request.user.pk) if request.user.is_authenticated else ""
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('etcs.user_id', %s, true)", [user_id])
            return self.get_response(request)
