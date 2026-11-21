import json
from datetime import timedelta
from io import BytesIO, StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from .documents import optimize_image
from .models import Activity, Attachment, Club, Notification, Profile, StoredDocument


@override_settings(
    SECURE_SSL_REDIRECT=False,
    ETCS_MAX_REQUEST_ATTACHMENTS=2,
    STORAGES={
        "default": {"BACKEND": "coordination.storage.DatabaseStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
)
class BudgetTests(TestCase):
    def setUp(self):
        self.club = Club.objects.create(name="نادي اختباري")
        self.member = User.objects.create_user("member")
        self.coordinator = User.objects.create_user("coordinator")
        Profile.objects.create(
            user=self.member, verified=True, role="club", club=self.club
        )
        Profile.objects.create(user=self.coordinator, verified=True, role="coordinator")
        self.activity = Activity.objects.create(
            club=self.club, creator=self.member, kind="event", title="طلب اختباري"
        )

    def test_same_request_reuses_file_and_enforces_cap(self):
        self.client.force_login(self.member)
        url = reverse("upload", args=[self.activity.pk])
        for label in ("first", "second", "third"):
            self.client.post(
                url,
                {"file": SimpleUploadedFile(label + ".pdf", b"%PDF-1.4\nsynthetic")},
            )
        self.assertEqual(StoredDocument.objects.count(), 1)
        self.assertEqual(Attachment.objects.filter(activity=self.activity).count(), 2)
        self.assertEqual(Attachment.objects.values("file").distinct().count(), 1)

    @override_settings(ETCS_UPLOAD_IMAGE_MAX_EDGE=64)
    def test_image_reduction_preserves_png_transparency(self):
        buffer = BytesIO()
        Image.effect_noise((180, 200), 65).convert("RGBA").save(buffer, "PNG")
        original = ContentFile(buffer.getvalue(), name="transparent.png")
        result = optimize_image(original)
        with Image.open(result) as output:
            self.assertEqual(output.mode, "RGBA")
            self.assertLessEqual(max(output.size), 64)
        self.assertLess(result.size, original.size)

    def test_retention_preview_never_deletes(self):
        now = timezone.now()
        session = Session.objects.create(
            session_key="expired-synthetic",
            session_data="",
            expire_date=now - timedelta(days=1),
        )
        notice = Notification.objects.create(
            user=self.member, text="إشعار تجريبي", read=True
        )
        Notification.objects.filter(pk=notice.pk).update(
            created=now - timedelta(days=200)
        )
        output = StringIO()
        call_command("retention_preview", "--dry-run", stdout=output)
        result = json.loads(output.getvalue())
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["expired_sessions"], 1)
        self.assertEqual(result["old_read_notifications"], 1)
        self.assertTrue(Session.objects.filter(pk=session.pk).exists())
        self.assertTrue(Notification.objects.filter(pk=notice.pk).exists())

    def test_storage_size_is_coordinator_only(self):
        url = reverse("database_budget")
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.coordinator)
        with patch(
            "coordination.budget_views.storage_usage",
            return_value={"size": 850000000, "percent": 85, "tables": []},
        ):
            self.assertContains(self.client.get(url), 'class="message error"')
