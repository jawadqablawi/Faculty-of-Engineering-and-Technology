import tempfile
from datetime import timedelta, time
from django.test import TestCase, override_settings, Client
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.utils import timezone
from .models import *
from .services import transition


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
)
class WorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("bootstrap", verbosity=0)
        cls.computer = Club.objects.get(name="نادي هندسة الحاسوب")
        cls.civil = Club.objects.get(name="نادي البناء والمدني والمعماري")

        def user(email, role, club=None):
            u = User.objects.create_user(email, email, "Synthetic-test-pass-837!")
            Profile.objects.create(user=u, role=role, club=club, verified=True)
            return u

        cls.admin = user("coordinator@example.test", "coordinator")
        cls.deputy = user("deputy@example.test", "deputy")
        cls.a = user("computer@example.test", "club", cls.computer)
        cls.b = user("civil@example.test", "club", cls.civil)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.media = override_settings(MEDIA_ROOT=self.tmp.name)
        self.media.enable()
        self.addCleanup(self.media.disable)
        self.addCleanup(self.tmp.cleanup)
        self.activity = Activity.objects.create(
            club=self.computer,
            creator=self.a,
            kind="event",
            title="مسابقة البرمجة",
            description="فعالية اختبار اصطناعية",
            objectives="التعلم",
            organizer="فريق الاختبار",
            contact="organizer@example.test",
            audience="الطلبة",
            participants=20,
            date=timezone.localdate() + timedelta(days=10),
            start=time(10),
            end=time(12),
            venue="قاعة 101",
        )

    def login(self, user):
        self.client.force_login(user)

    def test_anonymous_login_rtl(self):
        self.assertEqual(self.client.get("/requests/").status_code, 302)
        r = self.client.get("/login/")
        self.assertContains(r, 'dir="rtl"')
        self.assertContains(r, "البريد الإلكتروني")

    def test_cross_club_urls_files_and_actions(self):
        f = Attachment.objects.create(
            activity=self.activity,
            file=SimpleUploadedFile("test.pdf", b"%PDF-1.4\n"),
            name="test.pdf",
            uploader=self.a,
        )
        self.login(self.b)
        for path in [
            f"/requests/{self.activity.pk}/",
            f"/requests/{self.activity.pk}/edit/",
            f"/files/{f.pk}/",
        ]:
            self.assertEqual(self.client.get(path).status_code, 404, path)
        self.assertEqual(
            self.client.post(
                f"/requests/{self.activity.pk}/action/", {"action": "preliminary"}
            ).status_code,
            404,
        )
        self.assertNotContains(self.client.get("/requests/"), "مسابقة البرمجة")
        self.login(self.a)
        self.assertEqual(self.client.get(f"/files/{f.pk}/").status_code, 200)
        with self.assertRaises(PermissionDenied):
            transition(self.b, self.activity.pk, "submit")
        with self.assertRaises(ValidationError):
            transition(self.a, self.activity.pk, "preliminary")

    def test_workflow_revisions_approval_and_report(self):
        a = transition(self.a, self.activity.pk, "submit")
        self.assertEqual(a.status, "review")
        self.assertTrue(a.number.startswith("EVT-"))
        with self.assertRaises(ValidationError):
            transition(self.admin, a.pk, "university_ok", "evidence")
        with self.assertRaises(ValidationError):
            transition(self.admin, a.pk, "changes")
        transition(self.admin, a.pk, "changes", "عدل التفاصيل")
        transition(self.a, a.pk, "submit")
        transition(self.admin, a.pk, "preliminary")
        with self.assertRaises(ValidationError):
            transition(self.admin, a.pk, "forward", "reference")
        Letter.objects.create(activity=a, subject="طلب", body="نص")
        transition(self.admin, a.pk, "forward", "outgoing-1")
        transition(self.admin, a.pk, "council_ok", "council-1")
        a = transition(self.admin, a.pk, "university_ok", "university-1")
        self.assertTrue(a.council_approved and a.university_approved)
        with self.assertRaises(ValidationError):
            transition(self.admin, a.pk, "complete")
        Report.objects.create(
            activity=a,
            actual_date=a.date,
            location=a.venue,
            attendees=19,
            summary="تم النشاط",
            outcomes="التعلم",
        )
        transition(self.admin, a.pk, "complete")
        self.assertEqual(History.objects.filter(activity=a).count(), 8)
        self.assertTrue(Notification.objects.filter(user=self.a).exists())
        self.assertTrue(Audit.objects.exists())

    def test_deputy_requires_module_and_explicit_scope(self):
        self.login(self.deputy)
        self.assertEqual(
            self.client.get(f"/requests/{self.activity.pk}/").status_code, 404
        )
        p = self.deputy.profile
        p.modules = ["requests"]
        p.save()
        self.assertEqual(
            self.client.get(f"/requests/{self.activity.pk}/").status_code, 404
        )
        p.clubs.add(self.computer)
        self.assertEqual(
            self.client.get(f"/requests/{self.activity.pk}/").status_code, 200
        )
        self.assertEqual(self.client.get("/operations/cases/").status_code, 403)

    def test_club_cannot_read_cases_or_manage_users(self):
        self.login(self.a)
        for path in [
            "/operations/cases/",
            "/operations/tasks/",
            "/operations/clubs/",
            "/manage/invite/",
            "/manage/accounts/",
            "/reports/",
        ]:
            self.assertEqual(self.client.get(path).status_code, 403, path)

    def test_disabled_account_revoked(self):
        self.login(self.a)
        self.a.is_active = False
        self.a.save()
        self.assertEqual(self.client.get("/requests/").status_code, 302)

    def test_forms_save_real_draft_and_ignore_forged_club(self):
        self.login(self.a)
        payload = {
            "title": "طلب محفوظ",
            "participants": "12",
            "club": self.civil.pk,
            "req-TOTAL_FORMS": "1",
            "req-INITIAL_FORMS": "0",
            "req-0-category": "حواسيب",
            "req-0-item": "حاسوب",
            "req-0-quantity": "2",
            "req-0-price": "30",
            "req-0-unit": "جهاز",
        }
        payload.update(
            {
                f"{key}-{suffix}": value
                for key in ["program", "speakers", "partners"]
                for suffix, value in [("TOTAL_FORMS", "1"), ("INITIAL_FORMS", "0")]
            }
        )
        r = self.client.post("/new/event/", payload)
        self.assertEqual(r.status_code, 302)
        a = Activity.objects.get(title="طلب محفوظ")
        self.assertEqual(a.club, self.computer)
        self.assertEqual(a.budget, 60)
        self.assertContains(self.client.get(r.url), "طلب محفوظ")
        self.assertEqual(self.client.get(f"/requests/{a.pk}/edit/").status_code, 200)
        a.status = "review"
        a.save()
        self.assertEqual(
            self.client.post(f"/requests/{a.pk}/edit/", payload).status_code, 403
        )

    def test_online_form_and_required_sessions(self):
        self.login(self.a)
        self.assertEqual(self.client.get("/new/online/").status_code, 200)
        a = self.activity
        a.kind = "online"
        a.venue = ""
        a.platform = "Zoom"
        a.save()
        with self.assertRaises(ValidationError):
            transition(self.a, a.pk, "submit")
        a.details = {
            "presenter": "مقدم اصطناعي",
            "sessions": [
                {"title": "جلسة", "date": str(a.date), "start": "10:00", "end": "12:00"}
            ],
        }
        a.save()
        a = transition(self.a, a.pk, "submit")
        self.assertTrue(a.number.startswith("ONL-"))

    def test_upload_validation_and_csrf(self):
        self.login(self.a)
        r = self.client.post(
            f"/requests/{self.activity.pk}/upload/",
            {"file": SimpleUploadedFile("bad.pdf", b"<script>bad</script>")},
        )
        self.assertEqual(r.status_code, 302)
        self.assertFalse(Attachment.objects.exists())
        self.client.post(
            f"/requests/{self.activity.pk}/upload/",
            {"file": SimpleUploadedFile("ok.pdf", b"%PDF-1.4\n")},
        )
        self.assertEqual(Attachment.objects.count(), 1)
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.a)
        self.assertEqual(
            secure.post(
                f"/requests/{self.activity.pk}/action/", {"action": "submit"}
            ).status_code,
            403,
        )

    def test_calendar_sanitization(self):
        a = self.activity
        a.status = "approved"
        a.details = {"notes": "CONFIDENTIAL"}
        a.meeting_url = "https://example.test/private"
        a.save()
        self.login(self.b)
        r = self.client.get("/calendar/")
        self.assertEqual(r.context["events"][0]["title"], a.title)
        self.assertNotContains(r, "CONFIDENTIAL")
        self.assertNotContains(r, "example.test/private")
        self.assertNotContains(r, a.contact)
        self.assertContains(self.client.get("/calendar/export/"), "BEGIN:VCALENDAR")

    def test_pdf_excel_and_admin_pages(self):
        self.login(self.admin)
        for path in [
            "/",
            "/requests/",
            "/operations/cases/",
            "/operations/clubs/",
            "/operations/tasks/",
            "/operations/meetings/",
            "/operations/ideas/",
            "/reports/",
            "/manage/accounts/",
            "/manage/invite/",
            "/notifications/",
        ]:
            self.assertEqual(self.client.get(path).status_code, 200, path)
        r = self.client.get("/reports/?export=xlsx")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(b"".join(r.streaming_content).startswith(b"PK"))
        l = Letter.objects.create(
            activity=self.activity, subject="طلب اختبار", body="كتاب عربي"
        )
        r = self.client.get(f"/letters/{l.pk}/?pdf=1")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.content.startswith(b"%PDF"))
        self.assertTrue(
            self.client.get("/reports/?export=pdf").content.startswith(b"%PDF")
        )

    def test_invitation_one_time_and_verification(self):
        inv = Invitation.objects.create(
            email="new@example.test",
            role="club",
            club=self.computer,
            expires=timezone.now() + timedelta(days=1),
        )
        url = f"/accept/{inv.token}/"
        self.assertEqual(self.client.get(url).status_code, 200)
        r = self.client.post(
            url,
            {
                "new_password1": "Unique-Secret-for-testing-134!",
                "new_password2": "Unique-Secret-for-testing-134!",
            },
        )
        self.assertEqual(r.status_code, 302)
        u = User.objects.get(email=inv.email)
        self.assertTrue(u.profile.verified)
        self.assertTrue(u.check_password("Unique-Secret-for-testing-134!"))
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_reminders_are_idempotent(self):
        Task.objects.create(
            title="مهمة اختبار", assigned=self.a, due=timezone.localdate()
        )
        call_command("reminders")
        call_command("reminders")
        self.assertEqual(Notification.objects.filter(user=self.a).count(), 1)

    def test_submission_validation_and_rejection_reason(self):
        a = self.activity
        a.description = ""
        a.save()
        with self.assertRaises(ValidationError):
            transition(self.a, a.pk, "submit")
        a.description = "وصف"
        a.save()
        transition(self.a, a.pk, "submit")
        with self.assertRaises(ValidationError):
            transition(self.admin, a.pk, "reject")
        transition(self.admin, a.pk, "reject", "سبب الرفض المسجل")
        self.login(self.a)
        self.assertContains(self.client.get(f"/requests/{a.pk}/"), "سبب الرفض المسجل")

    def test_sparse_draft_and_autosave_repeatability(self):
        self.login(self.a)
        payload = {
            "title": "مسودة جزئية",
            "participants": "0",
            "autosave": "1",
            "req-TOTAL_FORMS": "1",
            "req-INITIAL_FORMS": "0",
            "req-0-category": "",
            "req-0-price": "0",
        }
        payload.update(
            {
                f"{key}-{suffix}": value
                for key in ["program", "speakers", "partners"]
                for suffix, value in [("TOTAL_FORMS", "1"), ("INITIAL_FORMS", "0")]
            }
        )
        response = self.client.post("/new/event/", payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["saved"])
        payload["title"] = "مسودة معدلة"
        self.client.post(data["url"], payload)
        self.assertEqual(
            Activity.objects.filter(title="مسودة معدلة", club=self.computer).count(), 1
        )

    def test_password_reset_uses_configured_mail_backend(self):
        from django.core import mail

        response = self.client.post("/password-reset/", {"email": self.a.email})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/reset/", mail.outbox[0].body)

    def test_case_confidentiality_and_permissions_ui(self):
        case = Case.objects.create(
            subject="قضية اختبار سرية",
            category="أكاديمية",
            description="بيانات اختبار",
            assigned=self.admin,
        )
        self.login(self.deputy)
        p = self.deputy.profile
        p.modules = ["cases"]
        p.save()
        self.assertNotContains(self.client.get("/operations/cases/"), case.subject)
        self.assertEqual(
            self.client.get(f"/operations/cases/{case.pk}/").status_code, 404
        )
        self.assertEqual(
            self.client.get(f"/manage/permissions/{self.a.pk}/").status_code, 403
        )
        self.login(self.admin)
        self.assertEqual(
            self.client.get(f"/manage/permissions/{self.deputy.pk}/").status_code, 200
        )
        response = self.client.post(
            f"/manage/permissions/{self.deputy.pk}/",
            {"role": "deputy", "clubs": [self.computer.pk], "modules": ["requests"]},
        )
        self.assertEqual(response.status_code, 302)
        self.deputy.profile.refresh_from_db()
        self.assertEqual(self.deputy.profile.modules, ["requests"])

    def test_report_corrections_block_closure(self):
        a = self.activity
        a.status = "approved"
        a.save()
        Report.objects.create(
            activity=a,
            actual_date=a.date,
            location="اختبار",
            attendees=10,
            summary="ملخص",
            outcomes="نتائج",
        )
        self.login(self.admin)
        r = self.client.post(
            f"/requests/{a.pk}/report/corrections/", {"note": "أكمل النتائج"}
        )
        self.assertEqual(r.status_code, 302)
        with self.assertRaises(ValidationError):
            transition(self.admin, a.pk, "complete")
        self.login(self.a)
        self.assertContains(self.client.get(f"/requests/{a.pk}/"), "أكمل النتائج")
        self.client.post(
            f"/requests/{a.pk}/report/",
            {
                "actual_date": str(a.date),
                "location": "اختبار",
                "attendees": "10",
                "summary": "ملخص مصحح",
                "outcomes": "النتائج",
                "costs": "0",
            },
        )
        self.assertEqual(transition(self.admin, a.pk, "complete").status, "completed")

    def test_auditor_needs_explicit_record_grant(self):
        auditor = User.objects.create_user(
            "auditor@example.test", email="auditor@example.test"
        )
        p = Profile.objects.create(
            user=auditor, role="auditor", verified=True, modules=["reports"]
        )
        p.clubs.add(self.computer)
        self.login(auditor)
        self.assertEqual(
            self.client.get(f"/requests/{self.activity.pk}/").status_code, 404
        )
        p.authorized_activities.add(self.activity)
        self.assertEqual(
            self.client.get(f"/requests/{self.activity.pk}/").status_code, 200
        )
        self.assertEqual(
            self.client.post(
                f"/requests/{self.activity.pk}/action/", {"action": "preliminary"}
            ).status_code,
            403,
        )

    def test_retention_control_coordinator_only(self):
        c = Case.objects.create(
            subject="بيانات اختبار قديمة",
            category="عامة",
            description="محتوى سري",
            notes="ملاحظة",
            assigned=self.admin,
            status="مغلق",
        )
        self.login(self.admin)
        self.client.post(f"/cases/{c.pk}/anonymize/")
        c.refresh_from_db()
        self.assertEqual(c.description, "محتوى سري")
        Case.objects.filter(pk=c.pk).update(
            created=timezone.now() - timedelta(days=400)
        )
        self.login(self.a)
        self.assertEqual(self.client.post(f"/cases/{c.pk}/anonymize/").status_code, 403)
        self.login(self.admin)
        self.client.post(f"/cases/{c.pk}/anonymize/")
        c.refresh_from_db()
        self.assertEqual(c.notes, "")
        self.assertNotEqual(c.description, "محتوى سري")

    def test_restricted_operations_reports_and_exports(self):
        Case.objects.create(
            subject="تقرير قضية اصطناعية",
            category="عامة",
            description="سري",
            assigned=self.admin,
        )
        self.login(self.a)
        for kind in ["cases", "letters", "tasks"]:
            self.assertEqual(
                self.client.get(f"/reports/operations/{kind}/?export=xlsx").status_code,
                403,
            )
        self.login(self.admin)
        for kind in ["cases", "letters", "tasks"]:
            self.assertEqual(
                self.client.get(f"/reports/operations/{kind}/").status_code, 200
            )
            response = self.client.get(f"/reports/operations/{kind}/?export=xlsx")
            self.assertTrue(b"".join(response.streaming_content).startswith(b"PK"))
        self.assertTrue(
            self.client.get("/reports/operations/cases/?export=pdf").content.startswith(
                b"%PDF"
            )
        )
        for mode in ["pending", "completed", "online", "archive"]:
            self.assertEqual(
                self.client.get("/reports/", {"mode": mode}).status_code, 200
            )
