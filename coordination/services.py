from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.forms.models import model_to_dict
from .models import (
    Activity,
    History,
    Audit,
    Notification,
    Profile,
    Setting,
    ApprovalRequirement,
    LetterHistory,
    NumberSequence,
)
from .access import profile, require
import json


def snapshot(a):
    d = model_to_dict(a, exclude=["id", "creator", "club"])
    d["attachments"] = [
        {"name": f.name, "id": str(f.pk), "version": f.version, "checksum": f.checksum}
        for f in a.attachments.filter(deleted=False)
    ]
    return json.loads(json.dumps(d, default=str))


def audit(user, action, record, note=""):
    Audit.objects.create(actor=user, action=action, record=str(record), note=note)


def notify(a, text, admins=False, actor=None, event_key=None):
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
        if event_key:
            Notification.objects.get_or_create(
                key=f"{event_key}:{x.user_id}",
                defaults={"user": x.user, "text": text, "activity": a, "sender": actor},
            )
        else:
            Notification.objects.create(
                user=x.user, text=text, activity=a, sender=actor
            )


@transaction.atomic
def next_number(prefix):
    year = timezone.localdate().year
    try:
        with transaction.atomic():
            row, _ = NumberSequence.objects.select_for_update().get_or_create(
                prefix=prefix, year=year
            )
    except IntegrityError:
        row = NumberSequence.objects.select_for_update().get(prefix=prefix, year=year)
    row.value += 1
    row.save(update_fields=["value"])
    return f"{prefix}-{year}-{row.value:04d}"


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
        if setting and setting.value is True and a.kind == "event":
            from .models import Idea

            ref = a.details.get("idea_reference")
            if ref and not str(ref).isdigit():
                raise ValidationError("مرجع الفكرة يجب أن يكون رقماً صحيحاً")
            if not Idea.objects.filter(
                pk=ref or None,
                club=a.club,
                outcome="جاهز للتقديم الرسمي",
            ).exists():
                raise ValidationError("يلزم اعتماد الفكرة للتقديم الرسمي")
        if not a.number:
            a.number = next_number("EVT" if a.kind == "event" else "ONL")
        a.submitted = timezone.now()
    if action == "submit":
        from datetime import date, time

        for row in a.details.get("extra_dates", []) + a.details.get("sessions", []):
            try:
                day = date.fromisoformat(row["date"])
                start = time.fromisoformat(row["start"])
                end = time.fromisoformat(row["end"])
            except (ValueError, KeyError, TypeError):
                raise ValidationError("أحد المواعيد الإضافية غير صالح")
            if day < timezone.localdate() or end <= start:
                raise ValidationError("راجع تاريخ ووقت كل جلسة أو يوم إضافي")
    if action == "preliminary":
        for office in ["مجلس الطلبة", "الجامعة"]:
            ApprovalRequirement.objects.get_or_create(
                activity=a, office=office, defaults={"required": True}
            )
    if action == "forward" and not a.letters.exists():
        raise ValidationError("أعد الكتاب الرسمي أولاً")
    if action == "council_ok":
        a.council_approved = True
        ApprovalRequirement.objects.update_or_create(
            activity=a,
            office="مجلس الطلبة",
            defaults={
                "required": True,
                "decision": "approved",
                "evidence": note,
                "actor": user,
                "decided": timezone.now(),
            },
        )
    if action == "university_ok":
        if not a.council_approved:
            raise ValidationError("موافقة المجلس مطلوبة")
        ApprovalRequirement.objects.update_or_create(
            activity=a,
            office="الجامعة",
            defaults={
                "required": True,
                "decision": "approved",
                "evidence": note,
                "actor": user,
                "decided": timezone.now(),
            },
        )
        if (
            a.approval_requirements.filter(required=True)
            .exclude(decision="approved")
            .exists()
        ):
            raise ValidationError("ما زالت هناك موافقات إلزامية ناقصة أو مرفوضة")
        a.university_approved = True
    if action == "complete":
        if not hasattr(a, "report"):
            raise ValidationError("يلزم تقديم التقرير الختامي أولاً")
        if a.report.correction_note:
            raise ValidationError("يجب تصحيح التقرير وإعادة تقديمه أولاً")
        a.report.accepted = True
        a.report.save(update_fields=["accepted"])
    if action in ["forward", "council_ok"]:
        letter = a.letters.order_by("-created").first()
        if letter:
            letter.status = "تم الإرسال" if action == "forward" else "تمت الموافقة"
            letter.evidence = note
            if action == "forward":
                letter.submitted_date = timezone.localdate()
            else:
                letter.response_date = timezone.localdate()
            letter.save()
            LetterHistory.objects.create(
                letter=letter,
                actor=user,
                snapshot=json.loads(
                    json.dumps(model_to_dict(letter), default=str, ensure_ascii=False)
                ),
            )
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
    notify(
        a, f"{a.title}: {a.get_status_display()}", admins=p.role == "club", actor=user
    )
    return a
