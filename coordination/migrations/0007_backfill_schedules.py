from datetime import date, time
from django.db import migrations


def backfill(apps, schema_editor):
    Activity = apps.get_model("coordination", "Activity")
    Session = apps.get_model("coordination", "WorkshopSession")
    Approval = apps.get_model("coordination", "ApprovalRequirement")
    History = apps.get_model("coordination", "History")
    for activity in Activity.objects.all().iterator():
        if (
            activity.kind == "online"
            and not Session.objects.filter(activity=activity).exists()
        ):
            for row in activity.details.get("sessions", []):
                try:
                    start = time.fromisoformat(row["start"])
                    end = time.fromisoformat(row["end"])
                    day = date.fromisoformat(row["date"])
                    if end <= start:
                        continue
                    Session.objects.create(
                        activity=activity,
                        title=row.get("title", "جلسة"),
                        date=day,
                        start=start,
                        end=end,
                        presenter=row.get("presenter", ""),
                        topic=row.get("topic", ""),
                    )
                except (KeyError, TypeError, ValueError):
                    continue
        if activity.status in [
            "preliminary",
            "council",
            "approvals",
            "approved",
            "completed",
        ]:
            for office, state, flag in [
                ("مجلس الطلبة", "approvals", activity.council_approved),
                ("الجامعة", "approved", activity.university_approved),
            ]:
                entry = (
                    History.objects.filter(activity=activity, status=state)
                    .exclude(note="")
                    .order_by("-created")
                    .first()
                )
                defaults = {"required": True}
                if flag and entry:
                    defaults.update(
                        decision="approved",
                        evidence=entry.note,
                        actor_id=entry.actor_id,
                        decided=entry.created,
                    )
                Approval.objects.get_or_create(
                    activity=activity, office=office, defaults=defaults
                )


class Migration(migrations.Migration):
    dependencies = [("coordination", "0006_postgresql_rls")]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
