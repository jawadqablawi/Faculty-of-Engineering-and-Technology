import json, io
from datetime import timedelta, datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import (
    SetPasswordForm,
    AuthenticationForm,
    PasswordResetForm,
)
from smtplib import SMTPException
import logging
from django.contrib.auth.views import LoginView, PasswordResetView
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.core import signing
from .security import consume_limit
from .documents import validate_document
from django.db import transaction
from django.db.models import Q, Count, Sum
from django.http import FileResponse, HttpResponse, JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.contrib.auth.models import User
from .models import *
from .forms import *
from .access import profile, allowed, require, activities
from .services import transition, audit


class SafePasswordResetForm(PasswordResetForm):
    def send_mail(self, *args, **kwargs):
        try:
            return super().send_mail(*args, **kwargs)
        except (SMTPException, OSError):
            logging.getLogger(__name__).warning(
                "Password reset delivery unavailable; check mail provider configuration"
            )


class LimitedPasswordReset(PasswordResetView):
    form_class = SafePasswordResetForm

    def post(self, request, *args, **kwargs):
        if not consume_limit("reset:" + request.META.get("REMOTE_ADDR", ""), limit=5):
            return HttpResponse("محاولات كثيرة. يرجى المحاولة لاحقاً.", status=429)
        return super().post(request, *args, **kwargs)


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(label="البريد الإلكتروني")

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()


class SecureLogin(LoginView):
    template_name = "coordination/login.html"
    authentication_form = EmailAuthenticationForm

    def post(self, request, *a, **kw):
        identity = "login:" + request.META.get("REMOTE_ADDR", "")
        if not consume_limit(identity):
            return HttpResponse(
                "محاولات كثيرة. يرجى المحاولة بعد 15 دقيقة.", status=429
            )
        return super().post(request, *a, **kw)

    def form_valid(self, form):
        try:
            profile(form.get_user())
        except PermissionDenied:
            form.add_error(None, "الحساب غير مفعل أو لم يتم التحقق منه")
            return self.form_invalid(form)
        return super().form_valid(form)


def context(request):
    if not request.user.is_authenticated:
        return {}
    try:
        p = profile(request.user)
        return {
            "identity": p,
            "admin_mode": p.role != "club",
            "can_requests": allowed(request.user, "requests", True),
            "can_cases": allowed(request.user, "cases"),
            "can_operations": allowed(request.user, "operations"),
            "can_reports": allowed(request.user, "reports"),
            "can_letters": allowed(request.user, "letters"),
            "unread": Notification.objects.filter(
                user=request.user, read=False
            ).count(),
        }
    except PermissionDenied:
        return {}


@login_required
def home(request):
    p = profile(request.user)
    q = activities(request.user)
    return render(
        request,
        "coordination/home.html",
        {
            "recent": q[:8],
            "new_count": q.filter(status="review").count(),
            "pending_count": q.filter(status__in=["council", "approvals"]).count(),
            "upcoming_count": q.filter(
                status="approved", date__gte=timezone.localdate()
            ).count(),
            "case_count": (
                Case.objects.all()
                if p.role == "coordinator"
                else Case.objects.filter(assigned=request.user)
            )
            .exclude(status__in=["تم الحل", "مغلق"])
            .count()
            if allowed(request.user, "cases")
            else 0,
            "changes_waiting": q.filter(status="changes")[:5],
            "late_letters": Letter.objects.filter(
                activity__in=q, follow_up__lt=timezone.localdate()
            ).exclude(status="مغلق")[:5]
            if allowed(request.user, "letters")
            else [],
            "late_tasks": (
                Task.objects.all()
                if p.role == "coordinator"
                else Task.objects.filter(assigned=request.user)
            )
            .filter(due__lt=timezone.localdate())
            .exclude(status="مكتملة")[:5]
            if allowed(request.user, "operations")
            else [],
            "case_followups": (
                Case.objects.all()
                if p.role == "coordinator"
                else Case.objects.filter(assigned=request.user)
            )
            .filter(follow_up__lte=timezone.localdate())
            .exclude(status__in=["تم الحل", "مغلق"])[:5]
            if allowed(request.user, "cases")
            else [],
            "upcoming": q.filter(
                status="approved", date__gte=timezone.localdate()
            ).order_by("date")[:5],
        },
    )


@login_required
def request_list(request):
    q = activities(request.user)
    if request.GET.get("q"):
        q = q.filter(
            Q(title__icontains=request.GET["q"]) | Q(number__icontains=request.GET["q"])
        )
    if request.GET.get("status"):
        q = q.filter(status=request.GET["status"])
    if request.GET.get("kind"):
        q = q.filter(kind=request.GET["kind"])
    if request.GET.get("club"):
        if not request.GET["club"].isdigit():
            return HttpResponse("عامل تصفية غير صالح", status=400)
        q = q.filter(club_id=request.GET["club"])
    return render(
        request,
        "coordination/list.html",
        {"title": "الطلبات ومتابعتها", "rows": q, "states": Activity.STATES},
    )


@login_required
@transaction.atomic
def edit_activity(request, kind="event", pk=None):
    p = profile(request.user)
    if kind not in ["event", "online"]:
        raise PermissionDenied
    if p.role != "club":
        raise PermissionDenied
    if not pk and request.method == "POST" and request.POST.get("draft_token"):
        try:
            token = signing.loads(
                request.POST["draft_token"], salt="etcs-draft", max_age=86400
            )
        except signing.BadSignature:
            raise PermissionDenied
        if (
            token.get("user") != request.user.pk
            or token.get("club") != p.club_id
            or token.get("kind") != kind
        ):
            raise PermissionDenied
        # A stable, signed draft ID makes retry/autosave/manual-submit requests idempotent.
        stored, _ = Activity.objects.get_or_create(
            pk=token["id"],
            defaults={
                "club": p.club,
                "creator": request.user,
                "kind": kind,
                "title": "",
            },
        )
        pk = stored.pk
    a = (
        get_object_or_404(activities(request.user).select_for_update(), pk=pk)
        if pk
        else Activity(club=p.club, creator=request.user, kind=kind)
    )
    if a.status not in ["draft", "changes"]:
        raise PermissionDenied
    kind = a.kind
    form = ActivityForm(request.POST or None, instance=a, kind=kind)
    detail = DetailsForm(
        request.POST or None, initial=a.details, kind=kind, prefix="detail"
    )
    reqs = Requirements(
        request.POST or None, initial=a.details.get("requirements", []), prefix="req"
    )
    sessions = Sessions(
        request.POST or None, initial=a.details.get("sessions", []), prefix="session"
    )
    extras = (
        [
            (
                label,
                key,
                factory(
                    request.POST or None, initial=a.details.get(key, []), prefix=key
                ),
            )
            for label, key, factory in [
                ("برنامج الفعالية", "program", Programs),
                ("المتحدثون والضيوف", "speakers", Speakers),
                ("الشراكات", "partners", Partners),
                ("مواعيد إضافية للفعالية", "extra_dates", ExtraDates),
            ]
        ]
        if kind == "event"
        else []
    )
    valid = form.is_valid() if request.method == "POST" else False
    if request.method == "POST":
        valid = detail.is_valid() and valid
        valid = (reqs.is_valid() if kind == "event" else sessions.is_valid()) and valid
        for _, _, fs in extras:
            valid = fs.is_valid() and valid
        if valid:
            a = form.save(commit=False)
            d = detail.cleaned_data
            if kind == "event":
                d["requirements"] = [
                    {
                        k: str(v) if k in ["quantity", "price"] else v
                        for k, v in x.items()
                        if k != "DELETE"
                    }
                    for x in reqs.cleaned_data
                    if x and not x.get("DELETE")
                ]
                for x in d["requirements"]:
                    if x["available"] or not x["price"] or x["price"] == "None":
                        x["price"] = "0"
            else:
                d["sessions"] = [
                    {k: str(v) for k, v in x.items() if k != "DELETE"}
                    for x in sessions.cleaned_data
                    if x and not x.get("DELETE")
                ]
            for _, key, fs in extras:
                d[key] = [
                    {
                        k: str(v) if not isinstance(v, (bool, int)) else v
                        for k, v in x.items()
                        if k != "DELETE"
                    }
                    for x in fs.cleaned_data
                    if x and not x.get("DELETE")
                ]
            d = json.loads(json.dumps(d, default=str, ensure_ascii=False))
            a.details = d
            a.save()
            if kind == "event":
                a.event_dates.all().delete()
                for row in d.get("extra_dates", []):
                    EventDate.objects.create(activity=a, **row)
            else:
                a.workshop_sessions.all().delete()
                for row in d.get("sessions", []):
                    WorkshopSession.objects.create(activity=a, **row)

            audit(request.user, "save_draft", a.pk)
            if request.POST.get("autosave"):
                return JsonResponse(
                    {
                        "saved": True,
                        "url": reverse("edit_activity", args=[a.pk]),
                        "time": timezone.now().isoformat(),
                    }
                )
            messages.success(request, "تم حفظ البيانات")
            return redirect("activity", a.pk)
    return render(
        request,
        "coordination/activity_form.html",
        {
            "form": form,
            "detail": detail,
            "formset": reqs if kind == "event" else sessions,
            "kind": kind,
            "activity": a if a.pk and not a._state.adding else None,
            "extras": extras,
            "draft_token": signing.dumps(
                {
                    "id": str(a.pk),
                    "user": request.user.pk,
                    "club": p.club_id,
                    "kind": kind,
                },
                salt="etcs-draft",
            ),
        },
    )


@login_required
def activity(request, pk):
    a = get_object_or_404(activities(request.user), pk=pk)
    from .scheduling import has_conflicts

    conflicts = has_conflicts(a)
    # Conflict existence only; never expose another club's private request.
    return render(
        request,
        "coordination/activity.html",
        {
            "a": a,
            "conflicts": conflicts,
            "details": [
                (DETAIL_FIELDS.get(k, k), v)
                for k, v in a.details.items()
                if k
                not in [
                    "requirements",
                    "sessions",
                    "program",
                    "speakers",
                    "partners",
                    "extra_dates",
                ]
                and v
            ],
            "requirements": a.details.get("requirements", []),
            "sessions": a.details.get("sessions", []),
            "structured": [
                (label, a.details.get(key, []))
                for label, key in [
                    ("برنامج الفعالية", "program"),
                    ("المتحدثون والضيوف", "speakers"),
                    ("الشراكات", "partners"),
                    ("المواعيد الإضافية", "extra_dates"),
                ]
            ],
        },
    )


@login_required
@require_POST
def action(request, pk):
    get_object_or_404(activities(request.user), pk=pk)
    try:
        transition(
            request.user,
            pk,
            request.POST.get("action", ""),
            request.POST.get("note", ""),
        )
    except ValidationError as e:
        messages.error(request, "؛ ".join(e.messages))
    else:
        messages.success(request, "تم تسجيل الإجراء")
    return redirect("activity", pk)


@login_required
@require_POST
def upload(request, pk):
    a = get_object_or_404(activities(request.user), pk=pk)
    p = profile(request.user)
    if p.role != "club" or a.status not in ["draft", "changes", "approved"]:
        raise PermissionDenied
    f = request.FILES.get("file")
    try:
        original, checksum = validate_document(f)
    except ValidationError as error:
        messages.error(request, "؛ ".join(error.messages))
        return redirect("activity", pk)
    with transaction.atomic():
        previous = None
        if request.POST.get("supersedes"):
            if a.status == "approved":
                raise PermissionDenied
            try:
                __import__("uuid").UUID(request.POST["supersedes"])
            except ValueError:
                return HttpResponse("مرجع الملف غير صالح", status=400)
            previous = get_object_or_404(
                Attachment.objects.select_for_update(),
                pk=request.POST["supersedes"],
                activity=a,
                deleted=False,
            )
            if Attachment.objects.filter(supersedes=previous).exists():
                messages.error(request, "تم رفع إصدار أحدث بالفعل؛ حدّث الصفحة")
                return redirect("activity", pk)
        Attachment.objects.create(
            activity=a,
            file=f,
            name=original,
            uploader=request.user,
            checksum=checksum,
            purpose=request.POST.get("purpose", "")[:100],
            supersedes=previous,
            version=previous.version + 1 if previous else 1,
        )
    audit(request.user, "upload", a.pk, original)
    return redirect("activity", pk)


@login_required
def download(request, pk):
    f = get_object_or_404(
        Attachment, pk=pk, activity__in=activities(request.user), deleted=False
    )
    audit(request.user, "download", f.pk)
    preview = request.GET.get("preview") == "1" and Path(f.name).suffix.lower() in [
        ".pdf",
        ".png",
        ".jpg",
        ".jpeg",
    ]
    response = FileResponse(
        f.file.open("rb"), as_attachment=not preview, filename=f.name
    )
    if preview:
        response["Content-Security-Policy"] = "sandbox; default-src 'none'"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
@require_POST
def delete_attachment(request, pk):
    f = get_object_or_404(
        Attachment, pk=pk, activity__in=activities(request.user), deleted=False
    )
    if profile(request.user).role != "club" or f.activity.status not in [
        "draft",
        "changes",
    ]:
        raise PermissionDenied
    a = f.activity_id
    audit(request.user, "delete_attachment", f.pk, f.name)
    f.deleted = True
    f.save(update_fields=["deleted"])
    return redirect("activity", a)


@login_required
def report(request, pk):
    a = get_object_or_404(activities(request.user), pk=pk)
    if profile(request.user).role != "club" or a.status != "approved":
        raise PermissionDenied
    instance = Report.objects.filter(activity=a).first()
    form = ReportForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        r = form.save(commit=False)
        r.activity = a
        previous_correction = r.correction_note
        r.correction_note = ""
        r.save()
        audit(request.user, "report", a.pk)
        from .services import notify

        notify(
            a,
            "تم تقديم التقرير الختامي: " + a.title,
            True,
            actor=request.user,
            event_key="report:"
            + str(a.pk)
            + ":"
            + __import__("hashlib")
            .sha256(
                (
                    json.dumps(form.cleaned_data, default=str, sort_keys=True)
                    + previous_correction
                ).encode()
            )
            .hexdigest(),
        )
        return redirect("activity", a.pk)
    return render(
        request, "coordination/form.html", {"form": form, "title": "التقرير الختامي"}
    )


@login_required
def letter_edit(request, pk=None, activity_pk=None):
    require(request.user, "letters", True)
    obj = (
        get_object_or_404(Letter, pk=pk, activity__in=activities(request.user))
        if pk
        else None
    )
    a = (
        obj.activity
        if obj
        else get_object_or_404(activities(request.user), pk=activity_pk)
    )
    if a.status in ["draft", "review", "changes", "rejected", "cancelled"]:
        raise PermissionDenied
    initial = {
        "subject": "طلب اعتماد: " + a.title,
        "body": f"تحية طيبة وبعد،\nيرجى التكرم بدراسة طلب {a.club.name} لإقامة {a.title} بتاريخ {a.date}.\n{a.description}\nمع الاحترام.",
    }
    form = LetterForm(request.POST or None, instance=obj, initial=initial)
    if request.method == "POST" and form.is_valid():
        letter = form.save(commit=False)
        if (
            letter.status in ["تم الإرسال", "بانتظار الرد", "تمت الموافقة", "مرفوض"]
            and not letter.evidence.strip()
        ):
            form.add_error("evidence", "مرجع دليل الإرسال أو القرار مطلوب")
        else:
            letter.activity = a
            letter.save()
            LetterHistory.objects.create(
                letter=letter,
                actor=request.user,
                snapshot=json.loads(
                    json.dumps(form.cleaned_data, default=str, ensure_ascii=False)
                ),
            )
            audit(
                request.user,
                "letter",
                letter.pk,
                json.dumps(form.cleaned_data, default=str, ensure_ascii=False),
            )
            return redirect("letter", letter.pk)
    return render(
        request,
        "coordination/form.html",
        {"form": form, "title": "إعداد الكتاب الرسمي"},
    )


@login_required
def letter(request, pk):
    require(request.user, "letters")
    obj = get_object_or_404(Letter, pk=pk, activity__in=activities(request.user))
    if request.GET.get("pdf"):
        from django.template.loader import render_to_string
        from weasyprint import HTML

        html = render_to_string("coordination/letter_print.html", {"letter": obj})
        data = HTML(string=html).write_pdf()
        return HttpResponse(
            data,
            content_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{obj.number}.pdf"'},
        )
    return render(request, "coordination/letter.html", {"letter": obj})


@login_required
def records(request, module, pk=None):
    modules = {
        "cases": (Case, CaseForm, "شؤون الطلبة"),
        "tasks": (Task, TaskForm, "المهام"),
        "meetings": (Meeting, MeetingForm, "الاجتماعات"),
        "clubs": (Club, ClubForm, "النوادي"),
        "ideas": (Idea, IdeaForm, "الأفكار الأولية"),
    }
    if module not in modules:
        raise PermissionDenied
    model, klass, title = modules[module]
    p = profile(request.user)
    permission = "cases" if module == "cases" else "operations"
    if module == "clubs":
        if p.role != "coordinator":
            raise PermissionDenied
    elif module != "ideas":
        require(request.user, permission, request.method == "POST")
    elif p.role != "club":
        require(request.user, "requests", request.method == "POST")
    q = model.objects.all()
    if module == "ideas":
        q = (
            q.filter(club=p.club)
            if p.role == "club"
            else q.filter(
                club__in=Club.objects.all()
                if p.role == "coordinator"
                else p.clubs.all()
            )
        )
    if module == "cases" and p.role != "coordinator":
        q = q.filter(assigned=request.user)
    if module == "tasks" and p.role != "coordinator":
        q = q.filter(assigned=request.user)
    if module == "meetings" and p.role != "coordinator":
        q = q.filter(
            Q(creator=request.user)
            | Q(club__in=p.clubs.all())
            | Q(participants=request.user)
        ).distinct()
    search = request.GET.get("q", "").strip()
    if search and module == "cases":
        q = q.filter(Q(subject__icontains=search) | Q(category__icontains=search))
    if module == "cases" and request.GET.get("status"):
        q = q.filter(status=request.GET["status"])
    obj = get_object_or_404(q, pk=pk) if pk else None
    previous_status = getattr(obj, "status", getattr(obj, "outcome", "")) if obj else ""
    if module == "ideas" and p.role != "club":
        klass = model_form(Idea, ("club",))
    form = klass(request.POST or None, request.FILES or None, instance=obj)
    if module == "tasks" and p.role != "coordinator":
        form.fields["assigned"].queryset = User.objects.filter(pk=request.user.pk)
        form.fields["club"].queryset = p.clubs.filter(active=True)
    if module == "cases":
        form.fields["assigned"].queryset = (
            User.objects.filter(
                is_active=True, profile__role__in=["coordinator", "deputy"]
            )
            if p.role == "coordinator"
            else User.objects.filter(pk=request.user.pk)
        )
        form.fields["assigned"].initial = request.user.pk
    if module == "meetings":
        form.fields["club"].queryset = (
            Club.objects.filter(active=True)
            if p.role == "coordinator"
            else p.clubs.filter(active=True)
        )
        if p.role != "coordinator":
            form.fields["club"].required = True
        form.fields["participants"].queryset = (
            User.objects.filter(is_active=True)
            if p.role == "coordinator"
            else User.objects.filter(
                Q(pk=request.user.pk) | Q(profile__club__in=p.clubs.all())
            ).distinct()
        )
    if module == "ideas" and p.role == "club" and obj and obj.outcome != "بحاجة لنقاش":
        raise PermissionDenied
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        if module == "cases" and p.role != "coordinator":
            item.assigned = request.user
        if module == "ideas" and not item.pk:
            if p.role != "club":
                raise PermissionDenied
            item.club = p.club
        if module == "tasks":
            assignee = getattr(item.assigned, "profile", None)
            if assignee and assignee.role == "club":
                if item.club_id and item.club_id != assignee.club_id:
                    form.add_error("assigned", "المستخدم لا ينتمي للنادي المحدد")
                    return render(
                        request,
                        "coordination/records.html",
                        {"title": title, "form": form, "records": q, "module": module},
                    )
                item.club_id = assignee.club_id
        if module == "meetings" and not item.pk:
            item.creator = request.user
        item.save()
        form.save_m2m()
        audit(
            request.user,
            "save_" + module,
            item.pk,
            previous_status
            + " → "
            + str(getattr(item, "status", getattr(item, "outcome", ""))),
        )
        if module == "tasks":
            Notification.objects.create(
                user=item.assigned, text="مهمة: " + item.title, sender=request.user
            )
        messages.success(request, "تم الحفظ")
        return redirect("records", module=module)
    return render(
        request,
        "coordination/records.html",
        {
            "title": title,
            "form": form,
            "records": q,
            "module": module,
            "record_history": Audit.objects.filter(
                action="save_" + module, record=str(pk)
            ).order_by("-created")
            if pk
            else [],
            "case_states": Case._meta.get_field("status").choices,
            "case_documents": obj.documents.all() if module == "cases" and obj else [],
        },
    )


@login_required
def calendar(request):
    profile(request.user)
    # Other clubs' calendar entries contain only explicitly approved public-safe fields.
    from .scheduling import public_calendar

    q = public_calendar()
    own = (
        activities(request.user)
        .exclude(status__in=["approved", "rejected", "cancelled", "completed", "draft"])
        .values("title", "date", "start", "end", "club__name", "kind")
    )
    return render(
        request, "coordination/calendar.html", {"events": list(q), "pending": list(own)}
    )


@login_required
def calendar_export(request):
    profile(request.user)

    def escape(x):
        return (
            str(x)
            .replace("\\", "\\\\")
            .replace("\n", "\\n")
            .replace(";", "\\;")
            .replace(",", "\\,")
        )

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//ETCS//AR",
        "CALSCALE:GREGORIAN",
    ]
    from .scheduling import public_calendar

    zone = ZoneInfo("Asia/Hebron")
    for event in public_calendar():
        if not event["date"]:
            continue
        lines += [
            "BEGIN:VEVENT",
            f"UID:{escape(event['uid'])}@etcs",
            f"DTSTAMP:{timezone.now():%Y%m%dT%H%M%SZ}",
        ]
        if event["start"] and event["end"]:
            begin = datetime.combine(
                event["date"], event["start"], tzinfo=zone
            ).astimezone(ZoneInfo("UTC"))
            finish = datetime.combine(
                event["date"], event["end"], tzinfo=zone
            ).astimezone(ZoneInfo("UTC"))
            lines += [
                f"DTSTART:{begin:%Y%m%dT%H%M%SZ}",
                f"DTEND:{finish:%Y%m%dT%H%M%SZ}",
            ]
        else:
            lines += [
                f"DTSTART;VALUE=DATE:{event['date']:%Y%m%d}",
                f"DTEND;VALUE=DATE:{event['date'] + timedelta(days=1):%Y%m%d}",
            ]
        lines += ["SUMMARY:" + escape(event["title"]), "END:VEVENT"]
    lines += ["END:VCALENDAR"]
    return HttpResponse(
        "\r\n".join(lines) + "\r\n",
        content_type="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="etcs.ics"'},
    )


@login_required
def notifications(request):
    profile(request.user)
    q = Notification.objects.filter(user=request.user)
    if request.method == "POST":
        q.update(read=True)
        return redirect("notifications")
    return render(
        request,
        "coordination/notifications.html",
        {"notifications": q.order_by("-created")[:100]},
    )


@login_required
def reports(request):
    require(request.user, "reports")
    q = activities(request.user)
    today = timezone.localdate()
    period = request.GET.get("period", "")
    if period == "week":
        q = q.filter(date__gte=today - timedelta(days=6), date__lte=today)
    elif period == "month":
        q = q.filter(date__year=today.year, date__month=today.month)
    elif period == "year":
        q = q.filter(date__year=today.year)
    mode = request.GET.get("mode", "")
    if mode == "completed":
        q = q.filter(status="completed")
    elif mode == "online":
        q = q.filter(kind="online")
    elif mode == "archive":
        q = q.filter(status="completed").order_by("-date")
    elif mode == "pending":
        q = q.filter(
            status__in=["review", "changes", "preliminary", "council", "approvals"]
        )
    for field, param in [
        ("date__gte", "from"),
        ("date__lte", "to"),
        ("club_id", "club"),
        ("kind", "kind"),
    ]:
        if request.GET.get(param):
            try:
                q = q.filter(**{field: request.GET[param]})
            except (ValueError, ValidationError):
                return HttpResponse("عامل تصفية غير صالح", status=400)
    if request.GET.get("export") == "xlsx":
        from openpyxl import Workbook

        book = Workbook()
        sheet = book.active
        sheet.title = "الأنشطة"
        sheet.sheet_view.rightToLeft = True
        sheet.append(
            [
                "رقم الطلب",
                "النادي",
                "العنوان",
                "النوع",
                "التاريخ",
                "الحالة",
                "الحضور المتوقع",
                "الميزانية",
            ]
        )
        for a in q:
            vals = [
                a.number or "",
                a.club.name,
                a.title,
                a.get_kind_display(),
                str(a.date or ""),
                a.get_status_display(),
                a.participants,
                float(a.budget),
            ]
            sheet.append(
                [
                    (
                        "'" + v
                        if isinstance(v, str) and v.startswith(("=", "+", "-", "@"))
                        else v
                    )
                    for v in vals
                ]
            )
        out = io.BytesIO()
        book.save(out)
        out.seek(0)
        return FileResponse(out, as_attachment=True, filename="etcs-report.xlsx")
    if request.GET.get("export") == "pdf":
        from weasyprint import HTML
        from django.template.loader import render_to_string

        return HttpResponse(
            HTML(
                string=render_to_string("coordination/report_print.html", {"rows": q})
            ).write_pdf(),
            content_type="application/pdf",
        )
    submitted = dict(q.exclude(submitted__isnull=True).values_list("pk", "submitted"))
    durations = [
        (created - submitted[pk]).total_seconds() / 86400
        for pk, created in History.objects.filter(
            activity__in=q, status="approved"
        ).values_list("activity_id", "created")
        if pk in submitted
    ]
    average_days = sum(durations) / len(durations) if durations else None
    return render(
        request,
        "coordination/reports.html",
        {
            "rows": q,
            "archive": mode == "archive",
            "average_days": average_days,
            "attendance": Report.objects.filter(activity__in=q).aggregate(
                total=Sum("attendees")
            )["total"]
            or 0,
            "club_totals": q.order_by()
            .values("club__name")
            .annotate(total=Count("id"))
            .order_by("club__name"),
            "total": q.count(),
            "completed": q.filter(status="completed").count(),
            "clubs": Club.objects.all()
            if profile(request.user).role == "coordinator"
            else profile(request.user).clubs.all(),
        },
    )


@login_required
def invite(request):
    if profile(request.user).role != "coordinator":
        raise PermissionDenied

    class InviteForm(forms.ModelForm):
        class Meta:
            model = Invitation
            fields = ["email", "role", "club"]
            labels = {"email": "البريد الإلكتروني", "role": "الدور", "club": "النادي"}

        def clean_email(self):
            email = self.cleaned_data["email"].strip().lower()
            if User.objects.filter(email__iexact=email).exists():
                raise forms.ValidationError(
                    "يوجد حساب لهذا البريد؛ حدّث حسابه من صفحة المستخدمين"
                )
            return email

        def clean(self):
            d = super().clean()
            if d.get("role") == "club" and not d.get("club"):
                self.add_error("club", "اختر النادي")
            if d.get("club") and not d["club"].active:
                self.add_error("club", "النادي غير نشط")
            return d

    form = InviteForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        inv = form.save(commit=False)
        inv.email = inv.email.lower()
        inv.expires = timezone.now() + timedelta(days=2)
        inv.save()
        link = request.build_absolute_uri(reverse("accept", args=[inv.token]))
        try:
            send_mail(
                "دعوة نظام تنسيق الكلية",
                "للتحقق من بريدك وتعيين كلمة مرور الحساب: " + link,
                None,
                [inv.email],
            )
        except (SMTPException, OSError):
            inv.delete()
            form.add_error(
                None,
                "تعذر إرسال الدعوة. تحقق من إعدادات مزود البريد قبل المحاولة مجدداً.",
            )
            return render(
                request,
                "coordination/form.html",
                {"title": "دعوة مستخدم", "form": form},
            )
        audit(request.user, "invite", inv.pk)
        from django.conf import settings

        if settings.EMAIL_BACKEND.endswith("console.EmailBackend"):
            messages.warning(
                request,
                "تم إنشاء الدعوة. البريد في وضع التطوير ولم يرسل إلى المستلم؛ رابط التفعيل في مخرجات الخادم المحلية.",
            )
        else:
            messages.success(request, "تم إرسال الدعوة عبر مزود البريد المهيأ")
        return redirect("invite")
    return render(
        request, "coordination/form.html", {"title": "دعوة مستخدم", "form": form}
    )


@transaction.atomic
def accept(request, token):
    inv = get_object_or_404(
        Invitation.objects.select_for_update(),
        token=token,
        used=False,
        expires__gt=timezone.now(),
    )
    user = User(username=inv.email, email=inv.email)

    class ActivationForm(SetPasswordForm):
        first_name = forms.CharField(
            label="الاسم الأول", required=False, max_length=150
        )
        last_name = forms.CharField(label="اسم العائلة", required=False, max_length=150)

    form = ActivationForm(user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        if User.objects.filter(username__iexact=inv.email).exists():
            form.add_error(None, "الحساب موجود بالفعل، يرجى التواصل مع المنسق")
        else:
            user = form.save()
            user.first_name = form.cleaned_data.get("first_name", "")
            user.last_name = form.cleaned_data.get("last_name", "")
            user.save(update_fields=["first_name", "last_name"])
            Profile.objects.create(
                user=user, role=inv.role, club=inv.club, verified=True
            )
            inv.used = True
            inv.save()
            from django.conf import settings

            if settings.ETCS_RLS:
                from django.db import connection

                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT set_config('etcs.user_id',%s,true)", [str(user.pk)]
                    )
            audit(user, "accept_invitation", inv.pk)
            messages.success(request, "تم التحقق من البريد وتفعيل الحساب")
            return redirect("login")
    return render(
        request,
        "coordination/form.html",
        {"title": "تفعيل الحساب والتحقق من البريد", "form": form},
    )


@login_required
def accounts(request):
    if profile(request.user).role != "coordinator":
        raise PermissionDenied
    if request.method == "POST":
        target = get_object_or_404(User, pk=request.POST.get("user"))
        if target == request.user:
            messages.error(request, "لا يمكنك تعطيل حسابك من هذه الصفحة")
        else:
            target.is_active = not target.is_active
            target.save(update_fields=["is_active"])
            audit(request.user, "account_activation", target.pk, str(target.is_active))
        return redirect("accounts")
    return render(
        request,
        "coordination/accounts.html",
        {
            "users": User.objects.select_related("profile").all(),
            "invitations": Invitation.objects.filter(
                used=False, expires__gt=timezone.now()
            ).order_by("-pk"),
        },
    )


@login_required
def permissions(request, pk):
    if profile(request.user).role != "coordinator":
        raise PermissionDenied
    target = get_object_or_404(Profile, user_id=pk)

    class PermissionForm(forms.ModelForm):
        modules = forms.MultipleChoiceField(
            label="الوحدات المسموحة",
            required=False,
            choices=[
                ("requests", "الطلبات والمراجعة"),
                ("letters", "الكتب الرسمية"),
                ("cases", "شؤون الطلبة"),
                ("operations", "المهام"),
                ("reports", "التقارير"),
            ],
            widget=forms.CheckboxSelectMultiple,
        )

        class Meta:
            model = Profile
            fields = ["role", "club", "clubs", "modules", "authorized_activities"]
            labels = {
                "role": "الدور",
                "club": "النادي لحساب رئيس النادي",
                "clubs": "نطاق النوادي للنائب أو المراجع",
                "authorized_activities": "السجلات المصرح بها للمدقق فقط",
            }
            widgets = {"clubs": forms.CheckboxSelectMultiple}

        def clean(self):
            d = super().clean()
            if d.get("role") == "club" and not d.get("club"):
                self.add_error("club", "يجب تحديد النادي")
            if target.user_id == request.user.pk and d.get("role") != "coordinator":
                self.add_error("role", "لا يمكنك إزالة صلاحياتك هنا")
            return d

    old = {
        "role": target.role,
        "club": target.club_id,
        "modules": list(target.modules),
        "clubs": list(target.clubs.values_list("pk", flat=True)),
    }
    form = PermissionForm(request.POST or None, instance=target)
    if request.method == "POST" and form.is_valid():
        form.save()
        if target.role != "coordinator" and (
            target.user.is_staff or target.user.is_superuser
        ):
            target.user.is_staff = False
            target.user.is_superuser = False
            target.user.save(update_fields=["is_staff", "is_superuser"])
        audit(
            request.user,
            "permissions",
            target.pk,
            json.dumps(
                {"previous": old, "new": form.cleaned_data},
                default=str,
                ensure_ascii=False,
            ),
        )
        messages.success(request, "تم تحديث الدور ونطاق الوصول")
        return redirect("accounts")
    return render(
        request,
        "coordination/form.html",
        {"form": form, "title": "صلاحيات " + target.user.email},
    )


@login_required
@require_POST
@transaction.atomic
def report_corrections(request, pk):
    require(request.user, "requests", True)
    a = get_object_or_404(
        activities(request.user).select_for_update(), pk=pk, status="approved"
    )
    report = get_object_or_404(Report, activity=a)
    note = request.POST.get("note", "").strip()
    if not note:
        messages.error(request, "اذكر التصحيحات المطلوبة")
    else:
        report.correction_note = note
        report.save(update_fields=["correction_note"])
        audit(request.user, "report_corrections", a.pk, note)
        from .services import notify

        notify(a, "مطلوب تصحيح التقرير الختامي: " + a.title, actor=request.user)
        messages.success(request, "تم طلب تصحيح التقرير")
    return redirect("activity", a.pk)


@login_required
def system_settings(request):
    if profile(request.user).role != "coordinator":
        raise PermissionDenied
    obj, _ = Setting.objects.get_or_create(
        key="idea_required", defaults={"value": False}
    )

    class SettingsForm(forms.Form):
        idea_required = forms.BooleanField(
            label="اشتراط مناقشة الفكرة واعتمادها قبل إرسال الطلب", required=False
        )

    form = SettingsForm(
        request.POST or None, initial={"idea_required": obj.value is True}
    )
    if request.method == "POST" and form.is_valid():
        obj.value = form.cleaned_data["idea_required"]
        obj.save()
        audit(request.user, "settings", obj.key, str(obj.value))
        messages.success(request, "تم حفظ الإعدادات")
        return redirect("settings")
    return render(
        request, "coordination/form.html", {"form": form, "title": "إعدادات التنسيق"}
    )


@login_required
@require_POST
def anonymize_case(request, pk):
    if profile(request.user).role != "coordinator":
        raise PermissionDenied
    case = get_object_or_404(Case, pk=pk, status="مغلق")
    from django.conf import settings

    cutoff = timezone.now() - timedelta(days=settings.ETCS_CASE_RETENTION_DAYS)
    if case.created > cutoff:
        messages.error(
            request, "تتاح إزالة البيانات الشخصية للقضايا المغلقة بعد سنة من إنشائها"
        )
    else:
        case.subject = "قضية مؤرشفة — أزيلت البيانات الشخصية"
        case.description = "أزيلت البيانات وفق سياسة الاحتفاظ"
        case.notes = ""
        case.contact = ""
        case.department = ""
        for doc in case.documents.all():
            doc.file.delete(save=False)
            doc.delete()
        case.resolution = ""
        case.save()
        audit(request.user, "anonymize_case", case.pk)
        messages.success(
            request, "أزيلت بيانات القضية الشخصية مع الاحتفاظ بالسجل الإحصائي"
        )
    return redirect("record_edit", module="cases", pk=pk)


@login_required
def operations_report(request, kind):
    require(request.user, "reports")
    p = profile(request.user)
    if kind == "cases":
        require(request.user, "cases")
        q = (
            Case.objects.all()
            if p.role == "coordinator"
            else Case.objects.filter(assigned=request.user)
        )
        headers = [
            "رقم القضية",
            "التصنيف",
            "الموضوع",
            "الحالة",
            "التاريخ",
            "موعد المتابعة",
        ]
        rows = [
            [
                c.number,
                c.category,
                c.subject,
                c.status,
                c.created.date(),
                c.follow_up or "",
            ]
            for c in q
        ]
        title = "تقرير شؤون الطلبة — سري"
    elif kind == "letters":
        require(request.user, "letters")
        q = Letter.objects.filter(activity__in=activities(request.user)).select_related(
            "activity"
        )
        headers = [
            "مرجع التتبع الداخلي",
            "الرقم الرسمي",
            "الموضوع",
            "المستلم",
            "الحالة",
            "المتابعة",
        ]
        rows = [
            [
                l.number,
                l.official_number,
                l.subject,
                l.recipient,
                l.status,
                l.follow_up or "",
            ]
            for l in q
        ]
        title = "تقرير الكتب الرسمية"
    elif kind == "tasks":
        require(request.user, "operations")
        q = (
            Task.objects.all()
            if p.role == "coordinator"
            else Task.objects.filter(assigned=request.user)
        )
        headers = ["المهمة", "المكلف", "الموعد", "الحالة", "الأولوية"]
        rows = [[t.title, t.assigned.email, t.due, t.status, t.priority] for t in q]
        title = "تقرير المهام"
    else:
        raise PermissionDenied
    if request.GET.get("export") == "xlsx":
        from openpyxl import Workbook

        book = Workbook()
        sheet = book.active
        sheet.sheet_view.rightToLeft = True
        sheet.append(headers)
        for row in rows:
            sheet.append(
                [
                    (
                        "'" + v
                        if isinstance(v, str) and v.startswith(("=", "+", "-", "@"))
                        else v
                    )
                    for v in row
                ]
            )
        stream = io.BytesIO()
        book.save(stream)
        stream.seek(0)
        return FileResponse(stream, as_attachment=True, filename=f"etcs-{kind}.xlsx")
    if request.GET.get("export") == "pdf":
        from weasyprint import HTML
        from django.template.loader import render_to_string

        return HttpResponse(
            HTML(
                string=render_to_string(
                    "coordination/generic_print.html",
                    {"headers": headers, "rows": rows, "title": title},
                )
            ).write_pdf(),
            content_type="application/pdf",
        )
    return render(
        request,
        "coordination/operations_report.html",
        {"headers": headers, "rows": rows, "title": title},
    )


def health(request):
    from django.db import connection

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})
