import tempfile
from datetime import timedelta, time
from django.test import TestCase, override_settings, Client
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError, PermissionDenied
from django.core import mail
from django.urls import reverse
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

    def test_direct_club_account_logs_in_with_assigned_password_and_name(self):
        create_url = reverse("create_club_account")
        email = "new.manager@example.test"
        password = "Synthetic-temp-642!r"
        data = {
            "first_name": "مسؤول نادي البناء",
            "email": email.upper(),
            "club": self.civil.pk,
            "temporary_password": password,
        }
        for user in (self.a, self.deputy):
            self.login(user)
            self.assertEqual(self.client.post(create_url, data).status_code, 403)
        self.login(self.admin)
        self.assertRedirects(self.client.post(create_url, data), reverse("accounts"))
        self.assertEqual(mail.outbox, [])
        account = User.objects.get(email=email)
        self.assertTrue(account.check_password(password))
        self.assertEqual(account.profile.club, self.civil)
        self.assertEqual(account.profile.role, "club")
        self.assertFalse(account.is_staff)
        duplicate = self.client.post(create_url, data)
        self.assertContains(duplicate, "يوجد حساب لهذا البريد")
        self.assertNotContains(duplicate, password)
        self.assertEqual(User.objects.filter(email__iexact=email).count(), 1)

        for previously_pending in (False, True):
            account.profile.must_change_password = previously_pending
            account.profile.save(update_fields=["must_change_password"])
            client = Client()
            self.assertRedirects(
                client.post(
                    reverse("login"), {"username": email, "password": password}
                ),
                reverse("home"),
            )
            home = client.get(reverse("home"))
            self.assertContains(home, data["first_name"])
            self.assertNotContains(home, email)
            self.assertEqual(
                client.get(reverse("activity", args=[self.activity.pk])).status_code,
                404,
            )

    def test_direct_club_account_rejects_inactive_club(self):
        self.civil.active = False
        self.civil.save(update_fields=["active"])
        self.login(self.admin)
        email = "inactive.club@example.test"
        response = self.client.post(
            reverse("create_club_account"),
            {
                "first_name": "اسم المسؤول",
                "email": email,
                "club": self.civil.pk,
                "temporary_password": "Synthetic-temp-642!r",
            },
        )
        self.assertTrue(response.context["form"].errors.get("club"))
        self.assertFalse(User.objects.filter(email=email).exists())

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

    def test_simple_request_from_draft_to_official_calendar(self):
        self.login(self.a)
        payload = {
            "title": "المهارات الحياتية لسوق العمل",
            "description": "وصف خاص بمسؤول النادي",
            "date": str(timezone.localdate() + timedelta(days=7)),
            "venue": "قاعة الكلية",
            "club": self.civil.pk,
            "needs-TOTAL_FORMS": "2",
            "needs-INITIAL_FORMS": "0",
            "needs-0-item": "عصير",
            "needs-0-quantity": "100",
            "needs-1-item": "كاسات كرتون",
            "needs-1-quantity": "60",
            "needs-1-price": "500",
        }
        response = self.client.post("/new/event/", payload)
        self.assertEqual(response.status_code, 302)
        a = Activity.objects.get(title=payload["title"])
        self.assertEqual(a.club, self.computer)
        self.assertEqual(
            a.details["requirements"],
            [
                {"item": "عصير", "quantity": "100"},
                {"item": "كاسات كرتون", "quantity": "60"},
            ],
        )
        self.assertContains(self.client.get(response.url), "المطبوعات")
        upload_url = reverse("upload", args=[a.pk])
        for description in ("", "اطبع 60 نسخة"):
            self.client.post(
                upload_url,
                {
                    "file": SimpleUploadedFile("poster.pdf", b"%PDF-1.4\nPrint this"),
                    "description": description,
                },
            )
        attachment = a.attachments.get()
        self.assertEqual(attachment.print_description, "اطبع 60 نسخة")
        self.assertContains(self.client.get(response.url), attachment.print_description)

        coordinator = Client()
        coordinator.force_login(self.admin)
        self.assertNotContains(coordinator.get(reverse("requests")), a.title)
        self.login(self.a)
        self.client.post(reverse("action", args=[a.pk]), {"action": "submit"})
        dashboard = coordinator.get(reverse("home"))
        self.assertEqual(
            [status for status, _, _ in dashboard.context["stats"]],
            [
                "review",
                "council",
                "student_approved",
                "approved",
            ],
        )
        self.assertEqual(dashboard.context["stats"][0][2], 1)
        self.assertEqual(
            self.client.post(
                reverse("edit_activity", args=[a.pk]), payload
            ).status_code,
            403,
        )
        other = Client()
        other.force_login(self.b)
        self.assertEqual(other.get(response.url).status_code, 404)
        self.assertEqual(
            other.get(reverse("download", args=[attachment.pk])).status_code, 404
        )
        self.assertNotIn(
            a.title,
            [
                event["title"]
                for event in other.get(reverse("calendar")).context["events"]
            ],
        )
        for action, status in [
            ("forward", "council"),
            ("council_ok", "approvals"),
            ("student_ok", "student_approved"),
            ("university_ok", "approved"),
        ]:
            transition(self.admin, a.pk, action, "مرجع القرار")
            a.refresh_from_db()
            self.assertEqual(a.status, status)
            if status in {"council", "student_approved", "approved"}:
                counts = {
                    key: count
                    for key, _, count in coordinator.get(reverse("home")).context[
                        "stats"
                    ]
                }
                self.assertEqual(counts[status], 1)
            if status != "approved":
                self.assertNotIn(
                    a.title,
                    [
                        event["title"]
                        for event in other.get(reverse("calendar")).context["events"]
                    ],
                )
        calendar = other.get(reverse("calendar"))
        event = next(
            event for event in calendar.context["events"] if event["title"] == a.title
        )
        self.assertEqual(event["club__name"], self.computer.name)
        self.assertNotIn(a.description, event.values())
        self.assertNotIn(attachment.print_description, event.values())

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

    def test_simple_request_rejects_missing_required_fields(self):
        self.login(self.a)
        response = self.client.post(
            "/new/event/",
            {
                "title": "طلب ناقص",
                "needs-TOTAL_FORMS": 0,
                "needs-INITIAL_FORMS": 0,
            },
        )
        self.assertTrue(response.context["form"].errors.get("description"))
        self.assertFalse(Activity.objects.filter(title="طلب ناقص").exists())

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
