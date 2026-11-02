from datetime import date, time, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from coordination.models import (
    Task,
    Notification,
    Activity,
    Profile,
    Letter,
    Case,
    Publication,
    RateLimit,
    Meeting,
)


class Command(BaseCommand):
    help = "Generate due/approaching reminders idempotently; run every five minutes."

    def handle(self, *args, **kwargs):
        now = timezone.localtime()
        today = now.date()

        def add(user, text, key, activity=None):
            if not user.is_active:
                return
            Notification.objects.get_or_create(
                key=f"{key}:{today}:{user.pk}",
                defaults={"user": user, "text": text, "activity": activity},
            )

        for task in (
            Task.objects.filter(due__lte=today + timedelta(days=1))
            .exclude(status="مكتملة")
            .select_related("assigned")
        ):
            add(task.assigned, "تذكير بمهمة: " + task.title, f"task:{task.pk}")
        for case in (
            Case.objects.filter(follow_up__lte=today + timedelta(days=1))
            .exclude(status__in=["تم الحل", "مغلق"])
            .select_related("assigned")
        ):
            add(case.assigned, "متابعة قضية: " + case.subject, f"case:{case.pk}")
        for activity in Activity.objects.filter(status="approved").select_related(
            "club"
        ):
            dates = []
            value = activity.details.get("publication_date")
            if value:
                try:
                    due_date = date.fromisoformat(value)
                    due_time = time.fromisoformat(
                        activity.details.get("publication_time") or "00:00"
                    )
                    if due_date <= today and (
                        due_date < today or due_time <= now.time().replace(tzinfo=None)
                    ):
                        dates.append(("announcement", "موعد إعلان النشاط: "))
                except (ValueError, TypeError):
                    pass
            reminders = activity.details.get("reminders", "")
            if isinstance(reminders, str):
                reminders = reminders.replace(",", " ").split()
            if str(today) in reminders:
                dates.append(("workshop-reminder", "تذكير بالورشة: "))
            for key, label in [
                ("registration_open", "بدء التسجيل: "),
                ("registration_deadline", "نهاية التسجيل: "),
                ("post_publication", "موعد النشر بعد الورشة: "),
            ]:
                if activity.details.get(key) == str(today):
                    dates.append((key, label))
            if activity.date and today <= activity.date <= today + timedelta(days=1):
                dates.append(("upcoming", "نشاط قادم: "))
            if (
                activity.date
                and activity.date < today
                and not hasattr(activity, "report")
            ):
                dates.append(("final-report", "التقرير الختامي مستحق: "))
            if dates:
                for p in Profile.objects.filter(
                    club=activity.club, role="club", verified=True, user__is_active=True
                ).select_related("user"):
                    for key, label in dates:
                        add(
                            p.user,
                            label + activity.title,
                            f"{key}:{activity.pk}",
                            activity,
                        )
        for publication in Publication.objects.filter(
            scheduled__lte=now, status="scheduled", activity__status="approved"
        ).select_related("activity"):
            for p in Profile.objects.filter(
                club=publication.activity.club,
                role="club",
                verified=True,
                user__is_active=True,
            ).select_related("user"):
                add(
                    p.user,
                    "موعد نشر: " + publication.title,
                    f"publication:{publication.pk}",
                    publication.activity,
                )
        for letter in (
            Letter.objects.filter(follow_up__lte=today + timedelta(days=1))
            .exclude(status="مغلق")
            .select_related("activity")
        ):
            for p in Profile.objects.filter(
                role__in=["coordinator", "deputy"], verified=True, user__is_active=True
            ).select_related("user"):
                if (
                    p.role == "coordinator"
                    or "letters" in p.modules
                    and p.clubs.filter(pk=letter.activity.club_id).exists()
                ):
                    add(
                        p.user,
                        "متابعة كتاب: " + letter.subject,
                        f"letter:{letter.pk}",
                        letter.activity,
                    )
        for meeting in Meeting.objects.filter(
            date__gte=now, date__lte=now + timedelta(days=1)
        ).prefetch_related("participants"):
            for user in meeting.participants.all():
                add(user, "اجتماع قادم: " + meeting.title, f"meeting:{meeting.pk}")
        RateLimit.objects.filter(expires__lt=now - timedelta(days=1)).delete()
        self.stdout.write("Reminders processed")
