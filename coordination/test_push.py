import base64
import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    Activity,
    Club,
    Notification,
    Profile,
    PushDelivery,
    PushSubscription,
)
from .push import deliver, payload


def encode(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


@override_settings(
    VAPID_PUBLIC_KEY="test-public",
    VAPID_PRIVATE_KEY="test-private",
    VAPID_ADMIN_EMAIL="test@example.test",
    SECURE_SSL_REDIRECT=False,
)
class PushTests(TestCase):
    def setUp(self):
        self.club = Club.objects.create(name="نادي أول")
        other_club = Club.objects.create(name="نادي ثانٍ")
        self.member = User.objects.create_user("member")
        self.other = User.objects.create_user("other")
        Profile.objects.create(
            user=self.member, club=self.club, role="club", verified=True
        )
        Profile.objects.create(
            user=self.other, club=other_club, role="club", verified=True
        )
        self.activity = Activity.objects.create(
            club=self.club, creator=self.member, kind="event", title="عنوان خاص"
        )
        self.data = {
            "endpoint": "https://fcm.googleapis.com/fcm/send/test-device",
            "keys": {"p256dh": encode(b"\x04" + bytes(64)), "auth": encode(bytes(16))},
        }

    def register(self, client, data=None, **headers):
        return client.post(
            reverse("push_subscribe"),
            data or self.data,
            content_type="application/json",
            **headers,
        )

    def test_subscription_is_private_and_requires_csrf(self):
        self.client.force_login(self.member)
        self.assertEqual(self.register(self.client).status_code, 200)
        device = PushSubscription.objects.get()
        self.client.force_login(self.other)
        page = self.client.get(reverse("push_preferences"))
        self.assertNotContains(page, self.data["endpoint"])
        self.assertEqual(self.client.get(reverse("push_key")).json()["endpoints"], [])
        self.assertEqual(
            self.client.post(
                reverse("push_preferences"), {"action": "remove", "device": device.pk}
            ).status_code,
            404,
        )
        self.assertEqual(self.register(self.client).status_code, 200)
        self.assertEqual(self.register(self.client).status_code, 200)
        self.assertEqual(
            PushSubscription.objects.filter(endpoint=device.endpoint).count(), 2
        )
        self.client.post(
            reverse("push_unsubscribe"), self.data, content_type="application/json"
        )
        self.assertFalse(PushSubscription.objects.filter(user=self.other).exists())
        device.refresh_from_db()
        self.assertEqual(device.user, self.member)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.member)
        self.assertEqual(self.register(csrf_client).status_code, 403)

    def test_endpoint_validation_limits_outbound_destinations(self):
        self.client.force_login(self.member)
        for endpoint in (
            "http://fcm.googleapis.com/test",
            "https://127.0.0.1/test",
            "https://fcm.googleapis.com@other.example/test",
            "https://fcm.googleapis.com:99/test",
        ):
            self.assertEqual(
                self.register(
                    self.client, {**self.data, "endpoint": endpoint}
                ).status_code,
                400,
            )

    def test_payload_uses_public_copy_and_authorizes_before_delivery(self):
        for user, suffix in [(self.member, "mine"), (self.other, "other")]:
            self.client.force_login(user)
            self.assertEqual(
                self.register(
                    self.client,
                    {**self.data, "endpoint": self.data["endpoint"] + suffix},
                ).status_code,
                200,
            )
        secret = "تفاصيل سرية وميزانية 5000 وسبب رفض خاص"
        with patch("coordination.push.send_push") as send:
            send.side_effect = lambda user, *, subscriptions, **kwargs: {
                device.pk: "sent" for device in subscriptions
            }
            with self.captureOnCommitCallbacks(execute=True):
                own = Notification.objects.create(
                    user=self.member,
                    text=secret,
                    activity=self.activity,
                    push_event="reject",
                )
                foreign = Notification.objects.create(
                    user=self.other,
                    text=secret,
                    activity=self.activity,
                    push_event="reject",
                )
            send.assert_called_once()
            args, kwargs = send.call_args
            self.assertEqual(args, (self.member,))
            self.assertEqual(len(kwargs["subscriptions"]), 1)
            self.assertNotIn(secret, kwargs["body"])
            self.assertNotIn(self.activity.title, kwargs["body"])
            self.assertEqual(
                kwargs["url"], reverse("activity", args=[self.activity.pk])
            )
            self.assertNotIn(secret, json.dumps(payload(own), ensure_ascii=False))
            self.assertEqual(
                PushDelivery.objects.get(notification=foreign).outcome, "skipped"
            )
            deliver(PushDelivery.objects.get(notification=own).pk, self.member.pk)
            send.assert_called_once()

    def test_retry_only_failed_devices_and_removes_expired_subscriptions(self):
        self.client.force_login(self.member)
        self.register(self.client)
        self.register(
            self.client, {**self.data, "endpoint": self.data["endpoint"] + "-second"}
        )
        first, second = list(PushSubscription.objects.order_by("pk"))
        with patch(
            "coordination.push.send_push",
            side_effect=[
                {first.pk: "sent", second.pk: "retry"},
                {second.pk: "expired"},
            ],
        ) as send:
            with self.captureOnCommitCallbacks(execute=True):
                note = Notification.objects.create(
                    user=self.member, text="تذكير", push_event="reminder"
                )
            job = PushDelivery.objects.get(notification=note)
            self.assertEqual(job.pending, [second.pk])
            PushDelivery.objects.filter(pk=job.pk).update(next_attempt=timezone.now())
            deliver(job.pk, self.member.pk)
            self.assertEqual(
                [device.pk for device in send.call_args.kwargs["subscriptions"]],
                [second.pk],
            )
            self.assertFalse(PushSubscription.objects.filter(pk=second.pk).exists())
            first.refresh_from_db()
            self.assertIsNotNone(first.last_success)

    def test_pwa_is_public_and_scoped_to_root(self):
        manifest = self.client.get(reverse("pwa_manifest"))
        self.assertEqual(manifest.json()["dir"], "rtl")
        self.assertEqual(manifest.json()["scope"], "/")
        worker = self.client.get(reverse("pwa_worker"))
        self.assertEqual(worker["Service-Worker-Allowed"], "/")
        script = b"".join(worker.streaming_content)
        self.assertIn(b"notificationclick", script)
        self.assertNotIn(b"caches.open", script)
