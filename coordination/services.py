from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.utils import timezone
from django.forms.models import model_to_dict
from .models import Activity, History, Audit, Notification, Profile, Setting
from .access import profile, require
import json


def snapshot(a):
    d = model_to_dict(a, exclude=["id", "creator", "club"])
    return json.loads(json.dumps(d, default=str))


def audit(user, action, record, note=""):
    Audit.objects.create(actor=user, action=action, record=str(record), note=note)


def notify(a, text, admins=False):
    p = Profile.objects.filter(user__is_active=True, verified=True)
    if admins:
        p = p.filter(role__in=["coordinator", "deputy"])
        p = [
            x
            for x in p
            if x.role == "coordinator"
            or ("requests" in x.modules and x.clubs.filter(pk=a.club_id).exists())
        ]
    else:
        p = p.filter(role="club", club=a.club)
    for x in p:
        Notification.objects.create(user=x.user, text=text, activity=a)


@transaction.atomic
def transition(user, activity_id, action, note=""):
    a = Activity.objects.select_for_update().get(pk=activity_id)
    p = profile(user)
    previous = a.status
    if p.role == "club":
        if p.club_id != a.club_id:
            raise PermissionDenied
        rules = {
            "submit": ({"draft", "changes"}, "review"),
            "withdraw": ({"draft", "review", "changes"}, "cancelled"),
        }
    else:
        require(user, "requests", True)
        if p.role != "coordinator" and not p.clubs.filter(pk=a.club_id).exists():
            raise PermissionDenied
        rules = {
            "preliminary": ({"review"}, "preliminary"),
            "changes": ({"review", "preliminary"}, "changes"),
            "reject": ({"review", "preliminary", "council", "approvals"}, "rejected"),
            "forward": ({"preliminary"}, "council"),
            "council_ok": ({"council"}, "approvals"),
            "university_ok": ({"approvals"}, "approved"),
            "complete": ({"approved"}, "completed"),
            "cancel": ({"approved", "council", "approvals"}, "cancelled"),
        }
    if action not in rules or previous not in rules[action][0]:
        raise ValidationError("الإجراء غير متاح في حالة الطلب الحالية")
    if (
        action
        in {"changes", "reject", "forward", "council_ok", "university_ok", "cancel"}
        and not note.strip()
    ):
        raise ValidationError("يرجى تسجيل السبب أو مرجع دليل القرار")
    if action == "submit":
        if not all(
            [
                a.title,
                a.description,
                a.objectives,
                a.organizer,
                a.contact,
                a.date,
                a.start,
                a.end,
                a.participants,
            ]
        ):
            raise ValidationError(
                "أكمل الوصف والأهداف والمسؤول والتواصل والعدد والتاريخ والأوقات أولاً"
            )
        if a.date < timezone.localdate() or a.end <= a.start:
            raise ValidationError("التاريخ أو الوقت غير صالح")
        if a.kind == "event" and not a.venue:
            raise ValidationError("أدخل مكان الفعالية")
        if a.kind == "online" and (
            not a.platform
            or not a.details.get("presenter")
            or not a.details.get("sessions")
        ):
            raise ValidationError("أدخل المنصة والمقدم وجلسة واحدة على الأقل")
        setting = Setting.objects.filter(key="idea_required").first()
        if setting and setting.value is True:
            from .models import Idea

            if not Idea.objects.filter(
                pk=a.details.get("idea_reference") or None,
                club=a.club,
                outcome="جاهز للتقديم الرسمي",
            ).exists():
                raise ValidationError("يلزم اعتماد الفكرة للتقديم الرسمي")
        if not a.number:
            # UUID-derived suffix avoids races without a mutable shared counter.
            a.number = f"{'EVT' if a.kind == 'event' else 'ONL'}-{timezone.localdate().year}-{a.pk.hex[:12].upper()}"
        a.submitted = timezone.now()
    if action == "forward" and not a.letters.exists():
        raise ValidationError("أعد الكتاب الرسمي أولاً")
    if action == "council_ok":
        a.council_approved = True
    if action == "university_ok":
        if not a.council_approved:
            raise ValidationError("موافقة المجلس مطلوبة")
        a.university_approved = True
    if action == "complete":
        if not hasattr(a, "report"):
            raise ValidationError("يلزم تقديم التقرير الختامي أولاً")
        if a.report.correction_note:
            raise ValidationError("يجب تصحيح التقرير وإعادة تقديمه أولاً")
        a.report.accepted = True
        a.report.save(update_fields=["accepted"])
    a.status = rules[action][1]
    a.save()
    History.objects.create(
        activity=a,
        actor=user,
        previous=previous,
        status=a.status,
        note=note,
        snapshot=snapshot(a),
    )
    audit(user, action, a.pk, note)
    notify(a, f"{a.title}: {a.get_status_display()}", admins=p.role == "club")
    return a
