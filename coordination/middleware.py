from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import connection, transaction
from django.utils import timezone


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


def set_remembered_session(session):
    session["remember_device"] = True
    session.set_expiry(
        timezone.now() + timedelta(days=settings.ETCS_REMEMBER_DEVICE_DAYS)
    )


class RememberDeviceMiddleware:
    """Renew remembered sessions at most monthly to avoid extra writes on every request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        renewal_window = timedelta(days=settings.ETCS_REMEMBER_DEVICE_DAYS - 30)
        if (
            request.method == "GET"
            and response.status_code == 200
            and request.user.is_authenticated
            and request.session.get("remember_device")
            and request.session.get_expiry_age() <= renewal_window.total_seconds()
        ):
            set_remembered_session(request.session)
        return response
