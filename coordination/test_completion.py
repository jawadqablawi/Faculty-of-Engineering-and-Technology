from datetime import timedelta
from pathlib import Path
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from .tests import WorkflowTests
from .models import (
    Activity,
    Attachment,
    ApprovalRequirement,
    Case,
    CaseDocument,
    ClubPlan,
    Publication,
    Notification,
    EmailDelivery,
    Letter,
    WorkshopSession,
)
from .services import transition


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
)
class CompletionTests(TestCase):
    setUpTestData = classmethod(WorkflowTests.setUpTestData.__func__)
    setUp = WorkflowTests.setUp
    login = WorkflowTests.login

    def test_additional_approval_cannot_be_skipped(self):
        a = self.activity
        transition(self.a, a.pk, "submit")
        transition(self.admin, a.pk, "preliminary")
        requirement = ApprovalRequirement.objects.create(
            activity=a, office="إدارة المختبرات"
        )
        Letter.objects.create(activity=a, subject="طلب", body="دليل")
        transition(self.admin, a.pk, "forward", "مرجع إرسال")
        transition(self.admin, a.pk, "council_ok", "قرار المجلس")
        with self.assertRaises(ValidationError):
            transition(self.admin, a.pk, "university_ok", "قرار الجامعة")
        a.refresh_from_db()
        self.assertEqual(a.status, "approvals")
        self.assertFalse(a.university_approved)
        requirement.decision = "approved"
        requirement.evidence = "قرار المختبر"
        requirement.save()
        self.assertEqual(
            transition(self.admin, a.pk, "university_ok", "قرار الجامعة").status,
            "approved",
        )

    def test_attachment_versions_and_cross_club_replacement(self):
        self.login(self.a)
        url = f"/requests/{self.activity.pk}/upload/"
        self.client.post(
            url, {"file": SimpleUploadedFile("v1.pdf", b"%PDF-1.4\nfirst")}
        )
        first = Attachment.objects.get()
        self.client.post(
            url,
            {
                "file": SimpleUploadedFile("v2.pdf", b"%PDF-1.4\nsecond"),
                "supersedes": str(first.pk),
            },
        )
        second = Attachment.objects.get(supersedes=first)
        self.assertEqual(second.version, 2)
        self.assertNotEqual(first.checksum, second.checksum)
        self.assertTrue(Path(first.file.path).exists())
        self.client.post(
            url,
            {
                "file": SimpleUploadedFile("v3.pdf", b"%PDF-1.4\nthird"),
                "supersedes": str(first.pk),
            },
        )
        self.assertEqual(Attachment.objects.count(), 2)
        b = Activity.objects.create(
            club=self.civil, creator=self.b, kind="event", title="نادي آخر"
        )
        self.login(self.b)
        self.assertEqual(
            self.client.post(
                f"/requests/{b.pk}/upload/",
                {
                    "file": SimpleUploadedFile("foreign.pdf", b"%PDF-1.4\n"),
                    "supersedes": str(second.pk),
                },
            ).status_code,
            404,
        )
        self.login(self.a)
        self.client.post(f"/files/{second.pk}/delete/")
        second.refresh_from_db()
        self.assertTrue(second.deleted)
        self.assertTrue(Path(second.file.path).exists())
        self.assertEqual(self.client.get(f"/files/{second.pk}/").status_code, 404)

    def test_case_documents_do_not_leak(self):
        case = Case.objects.create(
            subject="قضية سرية",
            category="أكاديمية",
            description="اختبار",
            assigned=self.admin,
        )
        self.login(self.admin)
        self.assertEqual(
            self.client.post(
                f"/cases/{case.pk}/upload/",
                {"file": SimpleUploadedFile("case.pdf", b"%PDF-1.4\n")},
            ).status_code,
            302,
        )
        doc = CaseDocument.objects.get()
        self.assertEqual(self.client.get(f"/case-files/{doc.pk}/").status_code, 200)
        self.login(self.a)
        self.assertEqual(self.client.get(f"/case-files/{doc.pk}/").status_code, 403)
        self.login(self.deputy)
        p = self.deputy.profile
        p.modules = ["cases"]
        p.save()
        self.assertEqual(self.client.get(f"/case-files/{doc.pk}/").status_code, 404)

    def test_monthly_plans_and_club_profile_scope(self):
        self.login(self.a)
        data = {
            "month": "2027-03-12",
            "title": "خطة شهرية",
            "objectives": "التعلم",
            "activities": "دورة علمية",
        }
        response = self.client.post(f"/clubs/{self.computer.pk}/plan/", data)
        self.assertEqual(response.status_code, 302)
        plan = ClubPlan.objects.get()
        self.assertEqual(plan.month.day, 1)
        self.assertEqual(
            self.client.post(f"/clubs/{self.computer.pk}/plan/", data).status_code, 200
        )
        self.assertEqual(ClubPlan.objects.count(), 1)
        self.login(self.b)
        self.assertEqual(
            self.client.get(f"/clubs/{self.computer.pk}/").status_code, 404
        )
        self.assertEqual(
            self.client.get(f"/clubs/{self.computer.pk}/plan/{plan.pk}/").status_code,
            404,
        )

    def test_publication_requires_approval_and_evidence(self):
        url = f"/requests/{self.activity.pk}/publications/"
        data = {
            "title": "إعلان ورشة",
            "scheduled": (timezone.localtime() + timedelta(days=2)).strftime(
                "%Y-%m-%dT%H:%M"
            ),
            "channel": "صفحة النادي",
            "status": "scheduled",
        }
        self.login(self.a)
        self.assertEqual(self.client.post(url, data).status_code, 200)
        self.assertEqual(Publication.objects.count(), 0)
        self.login(self.admin)
        self.client.post(url, data)
        self.assertEqual(Publication.objects.count(), 0)
        a = self.activity
        a.status = "approved"
        a.save()
        self.client.post(url, data)
        self.assertEqual(Publication.objects.count(), 1)
        pub = Publication.objects.get()
        data["status"] = "published"
        self.client.post(url + str(pub.pk) + "/", data)
        pub.refresh_from_db()
        self.assertEqual(pub.status, "scheduled")
        data["evidence"] = "https://example.test/post/123"
        self.client.post(url + str(pub.pk) + "/", data)
        pub.refresh_from_db()
        self.assertEqual(pub.status, "published")

    def test_comments_and_task_assignment_scope(self):
        self.login(self.b)
        self.assertEqual(
            self.client.post(
                f"/requests/{self.activity.pk}/comment/", {"text": "محاولة"}
            ).status_code,
            404,
        )
        self.login(self.a)
        self.client.post(
            f"/requests/{self.activity.pk}/comment/", {"text": "يرجى المراجعة"}
        )
        self.assertEqual(self.activity.comments.count(), 1)
        self.login(self.admin)
        self.assertContains(
            self.client.get(f"/requests/{self.activity.pk}/"), "يرجى المراجعة"
        )

    def test_rate_limits_are_persisted(self):
        from .security import consume_limit
        from .models import RateLimit

        self.assertTrue(consume_limit("sensitive-operation", limit=2))
        self.assertTrue(consume_limit("sensitive-operation", limit=2))
        self.assertFalse(consume_limit("sensitive-operation", limit=2))
        self.assertEqual(RateLimit.objects.get().attempts, 2)

    @override_settings(ETCS_EMAIL_NOTIFICATIONS=True)
    def test_optional_email_queue_and_duplicate_prevention(self):
        n = Notification.objects.create(user=self.a, text="تنبيه اختباري")
        self.assertTrue(EmailDelivery.objects.filter(notification=n).exists())
        call_command("deliver_email")
        call_command("deliver_email")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIsNotNone(EmailDelivery.objects.get(notification=n).sent)

    def test_health_has_no_private_information(self):
        response = self.client.get("/healthz/")
        self.assertEqual(response.json(), {"status": "ok"})

    def test_structured_online_sessions_are_relational(self):
        self.login(self.a)
        tomorrow = timezone.localdate() + timedelta(days=5)
        data = {
            "title": "ورشة اختبار",
            "participants": "10",
            "platform": "Zoom",
            "detail-presenter": "مقدم اختباري",
            "session-TOTAL_FORMS": "1",
            "session-INITIAL_FORMS": "0",
            "session-0-title": "جلسة أولى",
            "session-0-date": str(tomorrow),
            "session-0-start": "10:00",
            "session-0-end": "12:00",
        }
        response = self.client.post("/new/online/", data)
        self.assertEqual(response.status_code, 302)
        session = WorkshopSession.objects.get()
        self.assertEqual(session.activity.club, self.computer)
        self.assertEqual(session.title, "جلسة أولى")

    def test_extra_days_are_validated_and_stored(self):
        self.login(self.a)
        data = {
            "title": "فعالية متعددة الأيام",
            "participants": "0",
            "req-TOTAL_FORMS": "0",
            "req-INITIAL_FORMS": "0",
        }
        for prefix in ["program", "speakers", "partners"]:
            data.update({prefix + "-TOTAL_FORMS": "0", prefix + "-INITIAL_FORMS": "0"})
        data.update(
            {
                "extra_dates-TOTAL_FORMS": "1",
                "extra_dates-INITIAL_FORMS": "0",
                "extra_dates-0-date": "2027-03-15",
                "extra_dates-0-start": "10:00",
                "extra_dates-0-end": "12:00",
                "extra_dates-0-venue": "قاعة إضافية",
            }
        )
        response = self.client.post("/new/event/", data)
        self.assertEqual(response.status_code, 302)
        row = Activity.objects.get(title=data["title"])
        self.assertEqual(row.event_dates.count(), 1)

    def test_signed_autosave_is_idempotent_and_bound_to_user(self):
        self.login(self.a)
        response = self.client.get("/new/event/")
        token = response.context["draft_token"]
        data = {
            "title": "مسودة واحدة",
            "participants": "0",
            "draft_token": token,
            "autosave": "1",
            "req-TOTAL_FORMS": "0",
            "req-INITIAL_FORMS": "0",
        }
        for prefix in ["program", "speakers", "partners", "extra_dates"]:
            data.update({prefix + "-TOTAL_FORMS": "0", prefix + "-INITIAL_FORMS": "0"})
        self.assertTrue(self.client.post("/new/event/", data).json()["saved"])
        self.assertTrue(self.client.post("/new/event/", data).json()["saved"])
        self.assertEqual(Activity.objects.filter(title="مسودة واحدة").count(), 1)
        self.login(self.b)
        self.assertEqual(self.client.post("/new/event/", data).status_code, 403)

    def test_club_meetings_remain_private(self):
        self.login(self.a)
        data = {
            "title": "اجتماع لجنة النادي",
            "date": "2027-03-11T10:00",
            "attendees": "اللجنة",
            "agenda": "الخطة الشهرية",
        }
        response = self.client.post("/club-meetings/", data)
        self.assertEqual(response.status_code, 302)
        from .models import Meeting

        meeting = Meeting.objects.get()
        self.assertEqual(meeting.club, self.computer)
        self.login(self.b)
        self.assertNotContains(self.client.get("/club-meetings/"), "اجتماع لجنة النادي")
        self.assertEqual(
            self.client.get(f"/club-meetings/{meeting.pk}/").status_code, 404
        )

    def test_letters_module_and_audit_are_permission_checked(self):
        letter = Letter.objects.create(
            activity=self.activity,
            subject="كتاب خاص",
            body="اختبار",
            official_number="OFF-TEST-7",
        )
        self.login(self.a)
        self.assertEqual(self.client.get("/letters/").status_code, 403)
        self.assertEqual(self.client.get("/manage/audit/").status_code, 403)
        self.login(self.admin)
        self.assertContains(
            self.client.get("/letters/", {"q": "OFF-TEST-7"}), "كتاب خاص"
        )
        self.assertEqual(self.client.get("/clubs/").status_code, 200)
        self.login(self.deputy)
        p = self.deputy.profile
        p.modules = ["requests", "letters"]
        p.save()
        p.clubs.add(self.civil)
        self.assertNotContains(self.client.get("/letters/"), "كتاب خاص")
        self.assertEqual(self.client.get(f"/letters/{letter.pk}/").status_code, 404)

    def test_failed_invitation_delivery_does_not_claim_success(self):
        from unittest.mock import patch
        from .models import Invitation

        self.login(self.admin)
        with patch(
            "coordination.views.send_mail",
            side_effect=OSError("Synthetic mail failure"),
        ):
            response = self.client.post(
                "/manage/invite/",
                {
                    "email": "not-sent@example.test",
                    "role": "club",
                    "club": self.computer.pk,
                },
            )
        self.assertContains(response, "تعذر إرسال الدعوة")
        self.assertFalse(
            Invitation.objects.filter(email="not-sent@example.test").exists()
        )

    def test_windows_initial_account_is_unique_and_password_hashed(self):
        from unittest.mock import patch
        from io import StringIO
        from .models import Profile

        Profile.objects.filter(role="coordinator").update(role="deputy")
        with (
            patch("builtins.input", return_value="windows-owner@example.test"),
            patch(
                "coordination.management.commands.bootstrap.getpass.getpass",
                return_value="Unique-Windows-owner-482!",
            ),
        ):
            call_command("bootstrap", interactive=True, stdout=StringIO())
        owner = Profile.objects.get(role="coordinator").user
        self.assertTrue(owner.check_password("Unique-Windows-owner-482!"))
        self.assertNotEqual(owner.password, "Unique-Windows-owner-482!")
        with patch(
            "builtins.input",
            side_effect=AssertionError("Must not ask for a replacement account"),
        ):
            call_command("bootstrap", interactive=True, stdout=StringIO())
        self.assertEqual(Profile.objects.filter(role="coordinator").count(), 1)
