import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from smtplib import SMTPException
from uuid import UUID
from zoneinfo import ZoneInfo

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordResetForm,
    SetPasswordForm,
)
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView, PasswordResetView
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, F, Q, Sum
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST

from .access import activities, allowed, profile, require
from .documents import optimize_image, validate_document
from .forms import (
    DETAIL_FIELDS,
    CaseForm,
    ClubAccountForm,
    ClubForm,
    ClubNeeds,
    ClubRequestForm,
    IdeaForm,
    LetterForm,
    MeetingForm,
    ReportForm,
    TaskForm,
    model_form,
)
from .models import (
    Activity,
    Attachment,
    Audit,
    Case,
    Club,
    EventDate,
    History,
    Idea,
    Invitation,
    Letter,
    LetterHistory,
    Meeting,
    Notification,
    Profile,
    Report,
    Setting,
    Task,
)
from .security import consume_limit
from .services import audit, transition
from .table_views import REQUEST_SORT, page_context


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
    username = forms.EmailField(
        label="البريد الإلكتروني",
        widget=forms.EmailInput(attrs={"autocomplete": "username", "dir": "ltr"}),
    )

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
            "unread_count": Notification.objects.filter(
                user=request.user, read=False
            ).count(),
            "upload_limit_mb": settings.ETCS_MAX_UPLOAD_BYTES // (1024 * 1024),
            "admin_mode": p.role != "club",
            "can_requests": allowed(request.user, "requests", True),
            "can_cases": allowed(request.user, "cases"),
            "can_operations": allowed(request.user, "operations"),
            "can_reports": allowed(request.user, "reports"),
            "can_letters": allowed(request.user, "letters"),
        }
    except PermissionDenied:
        return {}


WAITING_REQUEST_STATES = [
    "review",
    "changes",
    "preliminary",
    "council",
    "approvals",
    "student_approved",
]


@login_required
def home(request):
    p = profile(request.user)
    requests = activities(request.user)
    if p.role != "club":
        requests = requests.exclude(status="draft")
    counts = {
        row["status"]: row["total"]
        for row in requests.order_by().values("status").annotate(total=Count("pk"))
    }
    tasks = Task.objects.filter(assigned=request.user).exclude(status="مكتملة")
    if p.role == "club":
        tasks = tasks.filter(club_id=p.club_id)
    stats = []
    if p.role != "club":
        stats = [
            ("review", "الطلبات الجديدة", counts.get("review", 0)),
            ("council", "قيد الموافقة من المجلس", counts.get("council", 0)),
            (
                "student_approved",
                "الموافق عليها من شؤون الطلبة",
                counts.get("student_approved", 0),
            ),
            (
                "approved",
                "المعتمدة رسميًا",
                counts.get("approved", 0) + counts.get("completed", 0),
            ),
        ]
    chart = [
        (label, counts.get(status, 0))
        for status, label in Activity.STATES
        if counts.get(status)
    ]
    today = timezone.localdate()
    week_starts = [today + timedelta(weeks=index) for index in range(4)]
    upcoming = requests.filter(status="approved", date__gte=today).aggregate(
        total=Count("pk"),
        **{
            f"week_{index}": Count(
                "pk", filter=Q(date__gte=start, date__lt=start + timedelta(weeks=1))
            )
            for index, start in enumerate(week_starts)
        },
    )
    upcoming_chart = [
        (start, upcoming[f"week_{index}"]) for index, start in enumerate(week_starts)
    ]
    upcoming_chart_max = max(1, *(total for _, total in upcoming_chart))
    return render(
        request,
        "coordination/home.html",
        {
            "recent": (
                requests if p.role == "club" else requests.filter(status="review")
            )[:8],
            "stats": stats,
            "chart": chart,
            "chart_max": max(counts.values(), default=1),
            "pending_count": sum(
                counts.get(status, 0) for status in WAITING_REQUEST_STATES
            ),
            "upcoming_count": upcoming["total"],
            "upcoming_chart": upcoming_chart,
            "upcoming_chart_max": upcoming_chart_max,
            "task_count": tasks.count(),
            "notification_count": Notification.objects.filter(
                user=request.user, read=False
            ).count(),
        },
    )


@login_required
def request_list(request):
    p = profile(request.user)
    q = activities(request.user)
    if p.role != "club":
        q = q.exclude(status="draft")
    clubs = (
        q.order_by("club__name", "club_id")
        .values_list("club_id", "club__name")
        .distinct()
    )
    if request.GET.get("q"):
        q = q.filter(
            Q(title__icontains=request.GET["q"]) | Q(number__icontains=request.GET["q"])
        )
    if request.GET.get("status") == "pending":
        q = q.filter(status__in=WAITING_REQUEST_STATES)
    elif request.GET.get("status"):
        status = request.GET["status"]
        q = q.filter(
            status__in=["approved", "completed"] if status == "approved" else [status]
        )
    if request.GET.get("kind"):
        q = q.filter(kind=request.GET["kind"])
    if request.GET.get("club"):
        if not request.GET["club"].isdecimal():
            return HttpResponse("عامل تصفية غير صالح", status=400)
        q = q.filter(club_id=request.GET["club"])
    return render(
        request,
        "coordination/list.html",
        {
            "title": "طلباتي ومتابعتها" if p.role == "club" else "الطلبات الواردة",
            **page_context(request, q, REQUEST_SORT, "-updated", 20),
            "clubs": clubs,
            "states": Activity.STATES,
        },
    )


@login_required
@transaction.atomic
def edit_activity(request, kind="event", pk=None):
    p = profile(request.user)
    if p.role != "club" or kind not in {"event", "online"}:
        raise PermissionDenied
    a = (
        get_object_or_404(
            activities(request.user).select_for_update(of=("self",)), pk=pk
        )
        if pk
        else Activity(club=p.club, creator=request.user, kind=kind)
    )
    if a.status not in {"draft", "changes"}:
        raise PermissionDenied

    data = request.POST if request.method == "POST" else None
    if not pk and data is not None and data.get("draft_token"):
        try:
            token = signing.loads(
                data["draft_token"], salt="club-request", max_age=86400
            )
        except signing.BadSignature:
            raise PermissionDenied
        if (token["user"], token["club"], token["kind"]) != (
            request.user.pk,
            p.club_id,
            kind,
        ):
            raise PermissionDenied
        a.pk = token["id"]
        if activities(request.user).filter(pk=a.pk).exists():
            return redirect("activity", a.pk)
    form = ClubRequestForm(data, instance=a)
    previous_needs = a.details.get("requirements", [])
    needs = ClubNeeds(
        data,
        initial=[
            {"item": row.get("item"), "quantity": row.get("quantity")}
            for row in previous_needs
        ],
        prefix="needs",
    )
    if request.method == "POST":
        valid = form.is_valid()
        if needs.is_valid() and valid:
            a = form.save(commit=False)
            a.details = {
                **a.details,
                "simple_request": True,
                "requirements": [
                    {
                        **(
                            previous_needs[index] if index < len(previous_needs) else {}
                        ),
                        "item": row["item"],
                        "quantity": str(row["quantity"]),
                    }
                    for index, row in enumerate(needs.cleaned_data)
                    if row and not row.get("DELETE")
                ],
            }
            try:
                with transaction.atomic():
                    a.save(force_insert=not pk)
            except IntegrityError:
                if pk or not activities(request.user).filter(pk=a.pk).exists():
                    raise
                return redirect("activity", a.pk)
            audit(request.user, "save_draft", a.pk)
            return redirect("activity", a.pk)
    return render(
        request,
        "coordination/club_request_form.html",
        {
            "form": form,
            "needs": needs,
            "a": a,
            "draft_token": signing.dumps(
                {
                    "id": str(a.pk),
                    "user": request.user.pk,
                    "club": p.club_id,
                    "kind": kind,
                },
                salt="club-request",
            )
            if not pk
            else "",
        },
    )


@login_required
def activity(request, pk):
    from .request_tracking import tracking
    from .scheduling import has_conflicts

    if request.method == "GET" and request.GET.get("live") == "1":
        revision = get_object_or_404(
            activities(request.user).values_list("updated", flat=True), pk=pk
        )
        response = JsonResponse({"revision": revision.isoformat()})
        response["Cache-Control"] = "private, no-store"
        return response

    a = get_object_or_404(
        activities(request.user).prefetch_related("approval_requirements"), pk=pk
    )
    p = profile(request.user)
    conflicts = has_conflicts(a)
    can_review = allowed(request.user, "requests", True)
    tracker = tracking(a, show_reason=p.role == "club" or can_review)
    if p.role == "club" or a.details.get("simple_request"):
        steps = {
            "review": [("forward", "إحالة إلى المجلس")],
            "preliminary": [("forward", "إحالة إلى المجلس")],
            "council": [("council_ok", "تسجيل موافقة المجلس")],
            "approvals": [("student_ok", "تسجيل موافقة شؤون الطلبة")],
            "student_approved": [("university_ok", "اعتماد رسمي")],
        }
        return render(
            request,
            "coordination/club_request.html",
            {
                "a": a,
                "conflicts": conflicts,
                "tracking": tracker,
                "editable": p.role == "club" and a.status in {"draft", "changes"},
                "requirements": a.details.get("requirements", []),
                "attachments": a.attachments.filter(deleted=False).order_by("created"),
                "next_steps": steps.get(a.status, []) if can_review else [],
                "report_note": a.report.correction_note
                if not a.details.get("simple_request") and hasattr(a, "report")
                else "",
            },
        )
    display_history = a.history.select_related("actor").order_by("created", "pk")
    if not can_review or request.GET.get("details") != "1":
        display_history = display_history.defer("snapshot")
    if not can_review:
        display_history = display_history.defer("note")
    # Conflict existence only; never expose another club's private request.
    return render(
        request,
        "coordination/activity.html",
        {
            "a": a,
            "conflicts": conflicts,
            "tracking": tracker,
            "display_history": display_history,
            "activity_comments": a.comments.select_related("actor"),
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
@transaction.atomic
def upload(request, pk):
    a = get_object_or_404(
        activities(request.user).select_for_update(of=("self",)), pk=pk
    )
    p = profile(request.user)
    if p.role != "club" or a.status not in ["draft", "changes", "approved"]:
        raise PermissionDenied
    printing = a.details.get("simple_request") or request.POST.get("printing") == "1"
    description = request.POST.get("description", "").strip()
    if printing and (
        a.status not in {"draft", "changes"} or not 1 <= len(description) <= 500
    ):
        messages.error(request, "اكتب وصفًا للملف من حرف إلى 500 حرف قبل الإرسال.")
        return redirect("activity", pk)
    if a.attachments.count() >= settings.ETCS_MAX_REQUEST_ATTACHMENTS:
        messages.error(
            request, "بلغ الطلب الحد الأقصى للمرفقات، بما فيها الإصدارات السابقة."
        )
        return redirect("activity", pk)
    f = request.FILES.get("file")
    try:
        original, checksum = validate_document(f)
        existing_file = (
            a.attachments.filter(checksum=checksum, deleted=False)
            .values_list("file", flat=True)
            .first()
        )
        stored_file = existing_file or optimize_image(f)
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
            file=stored_file,
            name=original,
            uploader=request.user,
            checksum=checksum,
            purpose=request.POST.get("purpose", "")[:100],
            print_description=description if printing else "",
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
@transaction.atomic
def delete_attachment(request, pk):
    f = get_object_or_404(
        Attachment, pk=pk, activity__in=activities(request.user), deleted=False
    )
    a = get_object_or_404(
        activities(request.user).select_for_update(of=("self",)), pk=f.activity_id
    )
    if profile(request.user).role != "club" or a.status not in [
        "draft",
        "changes",
    ]:
        raise PermissionDenied
    audit(request.user, "delete_attachment", f.pk, f.name)
    f.deleted = True
    f.save(update_fields=["deleted"])
    return redirect("activity", a.pk)


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
            push_event="report",
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
            created = not letter.pk
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
            if created:
                from .services import notify

                notify(
                    a,
                    "تم تسجيل كتاب رسمي: " + a.title,
                    actor=request.user,
                    push_event="letter",
                    event_key=f"letter-created:{letter.pk}",
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
        from .pdf import render_pdf

        data = render_pdf("coordination/letter_print.html", {"letter": obj})
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
                user=item.assigned,
                text="مهمة: " + item.title,
                sender=request.user,
                push_event="task",
            )
        messages.success(request, "تم الحفظ")
        return redirect("records", module=module)
    records_page = Paginator(q.order_by("pk"), 40).get_page(request.GET.get("page"))
    return render(
        request,
        "coordination/records.html",
        {
            "title": title,
            "form": form,
            "records": records_page,
            "page": records_page,
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
    from .scheduling import has_conflicts, public_calendar

    if event_id := request.GET.get("event_conflict"):
        scoped = activities(request.user).filter(status="approved", kind="event")
        activity = None
        try:
            if event_id.startswith("day-"):
                day_id = int(event_id.removeprefix("day-"))
                event_day = (
                    EventDate.objects.select_related("activity")
                    .filter(pk=day_id, activity__in=scoped)
                    .first()
                )
                activity = event_day.activity if event_day else None
            else:
                activity = scoped.filter(pk=UUID(event_id)).first()
        except (ValueError, OverflowError):
            pass
        result = None
        if activity and all(
            (activity.date, activity.start, activity.end, activity.venue)
        ):
            result = has_conflicts(activity)
        response = JsonResponse({"conflict": result})
        response["Cache-Control"] = "private, no-store"
        return response

    q = public_calendar()
    return render(request, "coordination/calendar.html", {"events": q})


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
@never_cache
def notifications(request):
    profile(request.user)
    notifications = Notification.objects.filter(user=request.user)
    if request.method == "POST":
        notification_id = request.POST.get("notification")
        if notification_id is not None:
            try:
                notification_id = int(notification_id)
            except ValueError:
                return HttpResponse(status=400)
            target = get_object_or_404(notifications, pk=notification_id)
            notifications.filter(pk=target.pk, read=False).update(read=True)
        else:
            notifications.filter(read=False).update(read=True)
        if request.headers.get("Accept") == "application/json":
            return JsonResponse({"unread": notifications.filter(read=False).count()})
        return redirect("notifications")
    if request.GET.get("panel") == "1":
        return render(
            request,
            "coordination/notification_list.html",
            {
                "notifications": notifications.order_by("-created", "-pk")[:6],
                "compact": True,
            },
        )
    return render(
        request,
        "coordination/notifications.html",
        {
            "notifications": notifications.order_by("-created", "-pk")[:100],
        },
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
        from .report_exports import activity_workbook

        return activity_workbook(q)
    if request.GET.get("export") == "pdf":
        from .pdf import render_pdf

        return HttpResponse(
            render_pdf("coordination/report_print.html", {"rows": q}),
            content_type="application/pdf",
        )
    average_duration = History.objects.filter(
        activity__in=q,
        status="approved",
        activity__submitted__isnull=False,
    ).aggregate(average=Avg(F("created") - F("activity__submitted")))["average"]
    average_days = (
        average_duration.total_seconds() / 86400
        if average_duration is not None
        else None
    )
    page = Paginator(
        q.order_by("-date" if mode == "archive" else "-updated", "pk"), 40
    ).get_page(request.GET.get("page"))
    return render(
        request,
        "coordination/reports.html",
        {
            "rows": page,
            "page": page,
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


@sensitive_post_parameters("temporary_password")
@never_cache
@login_required
def create_club_account(request):
    if profile(request.user).role != "coordinator":
        raise PermissionDenied

    form = ClubAccountForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=email,
                    email=email,
                    password=form.cleaned_data["temporary_password"],
                    first_name=form.cleaned_data["first_name"],
                )
                club = form.cleaned_data["club"]
                Profile.objects.create(
                    user=user,
                    role="club",
                    club=club,
                    verified=True,
                )
                audit(request.user, "create_club_account", user.pk, str(club.pk))
        except IntegrityError:
            if not User.objects.filter(username=email).exists():
                raise
            form.add_error("email", "يوجد حساب لهذا البريد بالفعل.")
        else:
            messages.success(
                request,
                "تم إنشاء حساب النادي. سلّم بيانات الدخول لمسؤول النادي بطريقة آمنة.",
            )
            return redirect("accounts")

    return render(
        request,
        "coordination/account_form.html",
        {
            "form": form,
            "title": "إنشاء حساب نادي",
            "description": "سلّم البريد وكلمة المرور لمسؤول النادي مباشرةً.",
            "submit_label": "إنشاء الحساب",
            "back_to_accounts": True,
        },
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
    users_page = Paginator(
        User.objects.select_related("profile__club").order_by("email", "pk"), 40
    ).get_page(request.GET.get("page"))
    return render(
        request,
        "coordination/accounts.html",
        {
            "users": users_page,
            "page": users_page,
            "invitations": Invitation.objects.filter(
                used=False, expires__gt=timezone.now()
            ).order_by("-pk"),
        },
    )


@login_required
@transaction.atomic
def permissions(request, pk):
    if profile(request.user).role != "coordinator":
        raise PermissionDenied
    target = get_object_or_404(Profile, user_id=pk)

    class PermissionForm(forms.ModelForm):
        first_name = forms.CharField(
            label="الاسم المعروض", max_length=150, required=False
        )
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
    form = PermissionForm(
        request.POST or None,
        instance=target,
        initial={"first_name": target.user.first_name},
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        if (
            "first_name" in request.POST
            and target.user.first_name != form.cleaned_data["first_name"]
        ):
            target.user.first_name = form.cleaned_data["first_name"]
            target.user.save(update_fields=["first_name"])
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

        notify(
            a,
            "مطلوب تصحيح التقرير الختامي: " + a.title,
            actor=request.user,
            push_event="report_corrections",
        )
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

        def format_row(case):
            return [
                case.number,
                case.category,
                case.subject,
                case.status,
                case.created.date(),
                case.follow_up or "",
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

        def format_row(letter):
            return [
                letter.number,
                letter.official_number,
                letter.subject,
                letter.recipient,
                letter.status,
                letter.follow_up or "",
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
        q = q.select_related("assigned")

        def format_row(task):
            return [
                task.title,
                task.assigned.email,
                task.due,
                task.status,
                task.priority,
            ]

        title = "تقرير المهام"
    else:
        raise PermissionDenied
    if request.GET.get("export") == "xlsx":
        from .report_exports import workbook_response

        return workbook_response(
            headers, map(format_row, q.iterator(chunk_size=250)), f"etcs-{kind}.xlsx"
        )
    if request.GET.get("export") == "pdf":
        from .pdf import render_pdf

        return HttpResponse(
            render_pdf(
                "coordination/generic_print.html",
                {
                    "headers": headers,
                    "rows": list(map(format_row, q.iterator(chunk_size=250))),
                    "title": title,
                },
            ),
            content_type="application/pdf",
        )
    page = Paginator(q.order_by("pk"), 40).get_page(request.GET.get("page"))
    return render(
        request,
        "coordination/operations_report.html",
        {
            "headers": headers,
            "rows": map(format_row, page),
            "title": title,
            "page": page,
        },
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
