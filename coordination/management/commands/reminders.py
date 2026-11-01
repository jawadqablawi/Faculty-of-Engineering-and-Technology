from django.core.management.base import BaseCommand
from django.utils import timezone
from coordination.models import Task, Notification, Activity, Profile, Letter, Case


class Command(BaseCommand):
    help = "Idempotent daily reminders; schedule with cron."

    def handle(self, *args, **kwargs):
        today = timezone.localdate()

        def add(user, text, key, activity=None):
            Notification.objects.get_or_create(
                key=f"{key}:{today}:{user.pk}",
                defaults={"user": user, "text": text, "activity": activity},
            )

        for task in Task.objects.filter(due__lte=today).exclude(status="مكتملة"):
            add(task.assigned, "متابعة مهمة: " + task.title, f"task:{task.pk}")
        for c in Case.objects.filter(follow_up__lte=today).exclude(
            status__in=["تم الحل", "مغلق"]
        ):
            add(c.assigned, "متابعة قضية: " + c.subject, f"case:{c.pk}")
        for a in Activity.objects.filter(status="approved"):
            due = str(a.details.get("publication_date", "")) == str(today)
            overdue = a.date and a.date < today and not hasattr(a, "report")
            if due or overdue:
                for p in Profile.objects.filter(
                    club=a.club, role="club", verified=True, user__is_active=True
                ):
                    add(
                        p.user,
                        ("موعد إعلان الورشة: " if due else "التقرير الختامي مستحق: ")
                        + a.title,
                        f"activity:{a.pk}",
                        a,
                    )
        for l in Letter.objects.filter(follow_up__lte=today).exclude(status="مغلق"):
            for p in Profile.objects.filter(
                role="coordinator", verified=True, user__is_active=True
            ):
                add(p.user, "متابعة كتاب: " + l.subject, f"letter:{l.pk}", l.activity)
        self.stdout.write("Reminders processed")
