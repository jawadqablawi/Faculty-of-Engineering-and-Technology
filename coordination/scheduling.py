from django.conf import settings
from django.db import connection
from .models import Activity, EventDate, WorkshopSession, Meeting, Publication
from .access import profile, activities


def public_calendar():
    if settings.ETCS_RLS:
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT uid,title,date,start,"end",club_name,kind FROM public.etcs_calendar_public'
            )
            return [
                dict(
                    zip(
                        ["uid", "title", "date", "start", "end", "club__name", "kind"],
                        row,
                    )
                )
                for row in cursor.fetchall()
            ]
    result = []
    for a in Activity.objects.filter(status="approved").select_related("club"):
        if a.kind == "online" and a.workshop_sessions.exists():
            continue
        result.append(
            {
                "uid": str(a.pk),
                "title": a.title,
                "date": a.date,
                "start": a.start,
                "end": a.end,
                "club__name": a.club.name,
                "kind": a.kind,
            }
        )
    for d in EventDate.objects.filter(activity__status="approved").select_related(
        "activity__club"
    ):
        result.append(
            {
                "uid": f"day-{d.pk}",
                "title": d.activity.title,
                "date": d.date,
                "start": d.start,
                "end": d.end,
                "club__name": d.activity.club.name,
                "kind": "event",
            }
        )
    for s in WorkshopSession.objects.filter(activity__status="approved").select_related(
        "activity__club"
    ):
        result.append(
            {
                "uid": f"session-{s.pk}",
                "title": s.title,
                "date": s.date,
                "start": s.start,
                "end": s.end,
                "club__name": s.activity.club.name,
                "kind": "online",
            }
        )
    return result


def has_conflicts(activity):
    if activity.kind != "event" or not all(
        [activity.date, activity.start, activity.end, activity.venue]
    ):
        return False
    candidates = [
        (str(activity.date), str(activity.start), str(activity.end), activity.venue)
    ] + [
        (str(r["date"]), str(r["start"]), str(r["end"]), r["venue"])
        for r in activity.details.get("extra_dates", [])
    ]
    # RLS calendar projection intentionally excludes venues. The parameterized
    # definer function returns only conflict existence, never another club's data.
    if settings.ETCS_RLS:
        with connection.cursor() as cursor:
            for day, start, end, venue in candidates:
                cursor.execute(
                    "SELECT public.etcs_conflict(%s,%s,%s,%s,%s)",
                    [str(activity.pk), day, start, end, venue],
                )
                if cursor.fetchone()[0]:
                    return True
        return False
    for day, start, end, venue in candidates:
        if (
            Activity.objects.filter(
                kind="event",
                status="approved",
                date=day,
                start__lt=end,
                end__gt=start,
                venue=venue,
            )
            .exclude(pk=activity.pk)
            .exists()
        ):
            return True
        if (
            EventDate.objects.filter(
                activity__status="approved",
                date=day,
                start__lt=end,
                end__gt=start,
                venue=venue,
            )
            .exclude(activity=activity)
            .exists()
        ):
            return True
    return False
