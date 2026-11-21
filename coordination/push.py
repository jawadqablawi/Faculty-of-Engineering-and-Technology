import base64
import json
import logging
import re
from contextvars import ContextVar
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import connection, transaction
from django.urls import reverse
from django.utils import timezone

from .access import activities, profile
from .models import Notification, PushDelivery, PushPreference, PushSubscription

logger = logging.getLogger(__name__)
defer_immediate = ContextVar("defer_push", default=False)
MAX_DEVICES = 5
MAX_ATTEMPTS = 5

MESSAGES = {
    "submit": "طلب جديد بانتظار المراجعة.",
    "resubmit": "أعيد إرسال طلب بعد التعديل.",
    "received": "تم استلام طلبك وهو قيد المراجعة.",
    "preliminary": "سُجّلت موافقة أولية على طلبك.",
    "changes": "طُلبت تعديلات على طلبك.",
    "reject": "رُفض الطلب. افتح الموقع للاطلاع على السبب.",
    "forward": "رُفع الطلب إلى المجلس.",
    "council_ok": "سُجّلت موافقة المجلس.",
    "student_ok": "سُجّلت موافقة شؤون الطلبة.",
    "university_ok": "اعتُمد الطلب رسميًا.",
    "letter": "سُجّل كتاب رسمي مرتبط بطلبك.",
    "report": "وَرَد تقرير ختامي للمراجعة.",
    "report_corrections": "طُلب تعديل التقرير الختامي.",
    "final_report": "تذكير بتقديم التقرير الختامي.",
    "reminder": "لديك تذكير في نظام التنسيق.",
    "comment": "أضيف تعليق إلى طلب.",
    "cancel": "أُلغي النشاط.",
    "withdraw": "سُحب الطلب.",
    "complete": "أُغلق الطلب بعد اكتماله.",
    "task": "أُسندت إليك مهمة.",
}


def configured():
    return all(
        (
            settings.VAPID_PUBLIC_KEY,
            settings.VAPID_PRIVATE_KEY,
            settings.VAPID_ADMIN_EMAIL,
        )
    )


def validate_endpoint(value):
    if not isinstance(value, str) or len(value) > 2048 or not value.isascii():
        return False
    if any(ord(char) <= 32 for char in value):
        return False
    try:
        url = urlsplit(value)
        host = url.hostname or ""
        return (
            url.scheme == "https"
            and url.port in (None, 443)
            and not (url.username or url.password or url.fragment)
            and url.netloc.lower() in (host, host + ":443")
            and bool(url.path.strip("/"))
            and (
                host
                in {
                    "fcm.googleapis.com",
                    "updates.push.services.mozilla.com",
                    "push.services.mozilla.com",
                    "web.push.apple.com",
                }
                or host.endswith(".push.apple.com")
                or host.endswith(".notify.windows.com")
            )
        )
    except ValueError:
        return False


def valid_key(value, size, prefix=None):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,90}", value):
        return False
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        return len(decoded) == size and (prefix is None or decoded[0] == prefix)
    except ValueError:
        return False


def enqueue(notification):
    if not configured():
        return
    try:
        with transaction.atomic():
            job = PushDelivery.objects.create(notification=notification)
            if not defer_immediate.get():
                transaction.on_commit(lambda: deliver(job.pk, notification.user_id))
    except Exception:
        logger.warning("Unable to enqueue Web Push notification id=%s", notification.pk)


def payload(notification):
    event = notification.push_event
    category = (
        "new_requests"
        if event in {"submit", "resubmit"}
        else "reminders"
        if event in {"reminder", "final_report"}
        else "status_changes"
    )
    activity_id = notification.activity_id
    url = (
        reverse("activity", args=[activity_id])
        if activity_id
        else reverse("notifications")
    )
    tag = (
        f"etcs-{notification.user_id}-{activity_id}-{category}"
        if activity_id
        else f"etcs-{notification.pk}"
    )
    return category, {
        "title": "نظام تنسيق الكلية",
        "body": MESSAGES.get(event, "لديك تحديث في نظام التنسيق."),
        "url": url,
        "tag": tag,
    }


def send_push(user, title, body, url, tag, *, subscriptions):
    from py_vapid import Vapid
    from pywebpush import WebPushException, webpush
    from requests import Session

    class PushSession(Session):
        def request(self, *args, **kwargs):
            kwargs["allow_redirects"] = False
            return super().request(*args, **kwargs)

    results = {}
    try:
        vapid = Vapid.from_string(settings.VAPID_PRIVATE_KEY)
    except Exception:
        logger.warning("Web Push VAPID configuration is invalid")
        return {device.pk: "retry" for device in subscriptions}
    with PushSession() as session:
        for device in subscriptions:
            if device.user_id != user.pk or not validate_endpoint(device.endpoint):
                results[device.pk] = "invalid"
                continue
            try:
                response = webpush(
                    subscription_info={
                        "endpoint": device.endpoint,
                        "keys": {"p256dh": device.p256dh, "auth": device.auth},
                    },
                    data=json.dumps(
                        dict(
                            title=title, body=body, url=url, tag=tag, recipient=user.pk
                        ),
                        ensure_ascii=False,
                    ),
                    vapid_private_key=vapid,
                    vapid_claims={"sub": "mailto:" + settings.VAPID_ADMIN_EMAIL},
                    timeout=2,
                    ttl=3600,
                    requests_session=session,
                )
                outcome = "sent" if 200 <= response.status_code < 300 else "invalid"
            except WebPushException as error:
                status = (
                    error.response.status_code if error.response is not None else None
                )
                logger.info("Web Push device=%s provider_status=%s", device.pk, status)
                if status in (404, 410):
                    outcome = "expired"
                elif status is None or status in (408, 429) or status >= 500:
                    outcome = "retry"
                else:
                    outcome = "invalid"
            except Exception as error:
                logger.info(
                    "Web Push device=%s failure_type=%s",
                    device.pk,
                    type(error).__name__,
                )
                outcome = "retry"
            results[device.pk] = outcome
    return results


def deliver(job_id, recipient_id):
    if not configured():
        return
    try:
        with transaction.atomic():
            if connection.vendor == "postgresql":
                # Only trusted server code calls this function, with IDs from a saved notification.
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT set_config('etcs.user_id', %s, true)",
                        [str(recipient_id)],
                    )
            job = (
                PushDelivery.objects.select_for_update(skip_locked=True, of=("self",))
                .filter(
                    pk=job_id,
                    notification__user_id=recipient_id,
                    outcome="pending",
                    next_attempt__lte=timezone.now(),
                )
                .first()
            )
            if not job:
                return
            note = Notification.objects.select_related("user").get(
                pk=job.notification_id
            )
            try:
                profile(note.user)
                authorized = (
                    not note.activity_id
                    or activities(note.user).filter(pk=note.activity_id).exists()
                )
            except PermissionDenied:
                authorized = False
            category, message = payload(note)
            preference = PushPreference.objects.filter(user=note.user).first()
            if (
                not authorized
                or preference
                and not (preference.enabled and getattr(preference, category))
            ):
                job.outcome = "skipped"
                job.save(update_fields=["outcome"])
                return
            devices = PushSubscription.objects.filter(
                user=note.user, active=True
            ).order_by("pk")
            if job.initialized:
                devices = devices.filter(pk__in=job.pending)
            results = send_push(
                note.user, **message, subscriptions=list(devices[:MAX_DEVICES])
            )
            for device_id, outcome in results.items():
                logger.info(
                    "Web Push delivery=%s device=%s outcome=%s",
                    job.pk,
                    device_id,
                    outcome,
                )
                matched = devices.filter(pk=device_id)
                if outcome == "expired":
                    matched.delete()
                if outcome == "sent":
                    matched.update(last_success=timezone.now())
            job.initialized = True
            job.attempts += 1
            job.pending = [key for key, value in results.items() if value == "retry"]
            if job.pending and job.attempts < MAX_ATTEMPTS:
                job.next_attempt = timezone.now() + timedelta(minutes=2**job.attempts)
            else:
                job.outcome = (
                    "failed"
                    if job.pending or "invalid" in results.values()
                    else "sent"
                    if "sent" in results.values()
                    else "skipped"
                )
            job.save(
                update_fields=[
                    "initialized",
                    "attempts",
                    "pending",
                    "next_attempt",
                    "outcome",
                ]
            )
    except Exception:
        logger.warning("Web Push attempt failed for delivery id=%s", job_id)


def schedule_retries():
    if not configured():
        return
    due = list(
        PushDelivery.objects.filter(
            outcome="pending",
            next_attempt__lte=timezone.now(),
        )
        .order_by("next_attempt", "pk")
        .values_list("pk", "notification__user_id")[:100]
    )

    def retry():
        from time import monotonic

        deadline = monotonic() + 35
        for job_id, recipient_id in due:
            if monotonic() >= deadline:
                break
            deliver(job_id, recipient_id)

    transaction.on_commit(retry)
