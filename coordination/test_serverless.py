from io import StringIO
import os
from unittest.mock import patch
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from .tests import WorkflowTests
from .models import StoredDocument, CalendarEntry, Profile


@override_settings(
    SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False
)
class ServerlessTests(TestCase):
    setUpTestData = classmethod(WorkflowTests.setUpTestData.__func__)
    setUp = WorkflowTests.setUp
    login = WorkflowTests.login

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "coordination.storage.DatabaseStorage"},
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
            },
        }
    )
    def test_private_files_persist_in_database_and_remain_scoped(self):
        from .models import Attachment
        from .storage import DatabaseStorage

        self.login(self.a)
        self.client.post(
            f"/requests/{self.activity.pk}/upload/",
            {
                "file": SimpleUploadedFile(
                    "serverless.pdf", b"%PDF-1.4\nPersistent test data"
                )
            },
        )
        file = Attachment.objects.get()
        self.assertEqual(
            bytes(StoredDocument.objects.get(name=file.file.name).data),
            b"%PDF-1.4\nPersistent test data",
        )
        self.assertEqual(
            DatabaseStorage().open(file.file.name).read(),
            b"%PDF-1.4\nPersistent test data",
        )
        self.assertEqual(self.client.get(f"/files/{file.pk}/").status_code, 200)
        self.login(self.b)
        self.assertEqual(self.client.get(f"/files/{file.pk}/").status_code, 404)

    @override_settings(ETCS_PDF_BACKEND="fpdf")
    def test_arabic_pdf_requires_no_native_weasyprint_libraries(self):
        from .models import Letter

        self.login(self.admin)
        letter = Letter.objects.create(
            activity=self.activity, subject="طلب فعالية علمية", body="هذا نص عربي فعلي"
        )
        self.assertTrue(
            self.client.get(f"/letters/{letter.pk}/?pdf=1").content.startswith(b"%PDF")
        )
        self.assertTrue(
            self.client.get("/reports/?export=pdf").content.startswith(b"%PDF")
        )
        self.assertTrue(
            self.client.get(
                "/reports/operations/letters/?export=pdf"
            ).content.startswith(b"%PDF")
        )

    @override_settings(ETCS_CRON_SECRET="synthetic-cron-test-secret")
    def test_scheduled_job_rejects_public_access(self):
        self.assertEqual(self.client.get("/cron/reminders/").status_code, 401)
        self.assertEqual(
            self.client.get(
                "/cron/reminders/", HTTP_AUTHORIZATION="Bearer wrong"
            ).status_code,
            401,
        )
        self.assertEqual(
            self.client.get(
                "/cron/reminders/",
                HTTP_AUTHORIZATION="Bearer synthetic-cron-test-secret",
            ).status_code,
            200,
        )

    def test_calendar_projection_only_contains_approved_fields(self):
        activity = self.activity
        self.assertFalse(CalendarEntry.objects.exists())
        activity.status = "approved"
        activity.save()
        entry = CalendarEntry.objects.get(activity=activity)
        self.assertEqual(entry.title, activity.title)
        self.assertFalse(hasattr(entry, "description"))
        self.assertNotEqual(entry.venue_key, activity.venue)
        activity.status = "cancelled"
        activity.save()
        self.assertFalse(CalendarEntry.objects.exists())

    def test_first_deployment_does_not_reset_existing_owner(self):
        Profile.objects.filter(role="coordinator").update(role="deputy")
        values = {
            "ETCS_OWNER_EMAIL": "vercel-owner@example.test",
            "ETCS_OWNER_PASSWORD": "Private-synthetic-owner-497!",
            "VERCEL_ENV": "production",
        }
        with (
            patch.dict(os.environ, values),
            patch("coordination.management.commands.vercel_prepare.call_command"),
        ):
            call_command("vercel_prepare", stdout=StringIO())
        user = Profile.objects.get(role="coordinator").user
        self.assertTrue(user.check_password(values["ETCS_OWNER_PASSWORD"]))
        old_hash = user.password
        values["ETCS_OWNER_PASSWORD"] = "Another-synthetic-password-643!"
        with (
            patch.dict(os.environ, values),
            patch("coordination.management.commands.vercel_prepare.call_command"),
        ):
            call_command("vercel_prepare", stdout=StringIO())
        user.refresh_from_db()
        self.assertEqual(user.password, old_hash)

    def test_preview_build_cannot_migrate_production_data_implicitly(self):
        with (
            patch.dict(os.environ, {"VERCEL_ENV": "preview"}),
            patch(
                "coordination.management.commands.vercel_prepare.call_command"
            ) as nested,
        ):
            with self.assertRaises(CommandError):
                call_command("vercel_prepare", stdout=StringIO())
            nested.assert_not_called()
