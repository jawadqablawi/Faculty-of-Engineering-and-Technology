from django.core.exceptions import ImproperlyConfigured
from django.db import connection, transaction
from django.shortcuts import redirect


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


class TemporaryPasswordMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.resolver_match.view_name in {"first_password_change", "logout"}:
            return None
        if request.user.is_authenticated:
            profile = getattr(request.user, "profile", None)
            if profile and profile.must_change_password:
                return redirect("first_password_change")
        return None
