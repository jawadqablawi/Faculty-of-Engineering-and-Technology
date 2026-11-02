import json
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from .access import activities, allowed, profile, require
from .documents import validate_document
from .forms import PublicationForm, PlanForm
from .models import (
    Activity,
    ApprovalRequirement,
    ActivityComment,
    Case,
    CaseDocument,
    Club,
    ClubPlan,
    Audit,
    Task,
)
from .services import audit, notify


def scoped_clubs(user):
    p = profile(user)
    if p.role == "coordinator":
        return Club.objects.all()
    if p.role == "club":
        return Club.objects.filter(pk=p.club_id)
    if p.role == "deputy" and "operations" in p.modules:
        return p.clubs.all()
    return Club.objects.none()


@login_required
@require_POST
def comment(request, pk):
    activity = get_object_or_404(activities(request.user), pk=pk)
    p = profile(request.user)
    if p.role != "club":
        require(request.user, "requests", True)
    if activity.status in ["cancelled", "completed", "rejected"]:
        raise PermissionDenied
    text = request.POST.get("text", "").strip()
    if not text or len(text) > 4000:
        messages.error(request, "أدخل تعليقاً لا يتجاوز 4000 حرف")
    else:
        ActivityComment.objects.create(activity=activity, actor=request.user, text=text)
        audit(request.user, "comment", activity.pk)
        notify(
            activity,
            "تعليق جديد: " + activity.title,
            admins=p.role == "club",
            actor=request.user,
        )
    return redirect("activity", pk)


@login_required
def publications(request, pk, item=None):
    activity = get_object_or_404(activities(request.user), pk=pk)
    p = profile(request.user)
    if p.role != "club":
        require(request.user, "requests", request.method == "POST")
    obj = get_object_or_404(activity.publications, pk=item) if item else None
    form = PublicationForm(request.POST or None, instance=obj)
    if p.role == "club":
        form.fields["status"].choices = [
            (k, v)
            for k, v in form.fields["status"].choices
            if k in ["draft", "review"] or obj and k == obj.status
        ]
    if request.method == "POST" and form.is_valid():
        record = form.save(commit=False)
        if record.status in ["scheduled", "published"] and activity.status not in [
            "approved",
            "completed",
        ]:
            form.add_error("status", "لا يمكن اعتماد النشر قبل الاعتماد النهائي للنشاط")
        elif record.status == "published" and not record.evidence:
            form.add_error("evidence", "أرفق رابط المنشور لإثبات النشر الفعلي")
        elif p.role == "club" and obj and obj.status not in ["draft", "review"]:
            raise PermissionDenied
        else:
            record.activity = activity
            record.save()
            audit(request.user, "publication", activity.pk, record.get_status_display())
            messages.success(
                request,
                "تم حفظ خطة النشر. لا ينشر النظام تلقائياً على المنصات الخارجية.",
            )
            return redirect("publications", pk)
    return render(
        request,
        "coordination/publications.html",
        {
            "a": activity,
            "form": form,
            "publications": activity.publications.order_by("scheduled"),
        },
    )


@login_required
@transaction.atomic
def approval(request, pk, item=None):
    require(request.user, "requests", True)
    activity = get_object_or_404(activities(request.user).select_for_update(), pk=pk)
    if activity.status not in ["review", "preliminary", "council", "approvals"]:
        raise PermissionDenied
    obj = get_object_or_404(activity.approval_requirements, pk=item) if item else None

    class DecisionForm(forms.ModelForm):
        class Meta:
            model = ApprovalRequirement
            fields = ["office", "required", "decision", "evidence"]
            labels = {
                "office": "الجهة صاحبة الموافقة",
                "required": "موافقة إلزامية",
                "decision": "القرار",
                "evidence": "مرجع الموافقة أو دليل القرار",
            }

        def clean(self):
            d = super().clean()
            if d.get("office") in ["مجلس الطلبة", "الجامعة"] and not d.get("required"):
                self.add_error("required", "هذه موافقة أساسية إلزامية")
            if d.get("decision") != "pending" and not d.get("evidence", "").strip():
                self.add_error("evidence", "مرجع القرار مطلوب")
            if (
                obj
                and obj.office in ["مجلس الطلبة", "الجامعة"]
                and d.get("office") != obj.office
            ):
                self.add_error("office", "لا يمكن تغيير جهة الموافقة الأساسية")
            if (
                d.get("office") in ["مجلس الطلبة", "الجامعة"]
                and d.get("decision") != "pending"
            ):
                self.add_error(
                    "decision",
                    "سجل هذا القرار عبر إجراءات الطلب الرسمية للحفاظ على ترتيب الموافقات",
                )
            if (
                activity.approval_requirements.filter(office=d.get("office", ""))
                .exclude(pk=obj.pk if obj else None)
                .exists()
            ):
                self.add_error("office", "هذه الجهة مسجلة بالفعل")
            return d

    form = DecisionForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        decision = form.save(commit=False)
        decision.activity = activity
        decision.actor = request.user
        decision.decided = timezone.now() if decision.decision != "pending" else None
        decision.save()
        audit(
            request.user,
            "approval_requirement",
            activity.pk,
            json.dumps(form.cleaned_data, default=str, ensure_ascii=False),
        )
        messages.success(request, "تم حفظ متطلبات الموافقة")
        return redirect("activity", pk)
    return render(
        request,
        "coordination/form.html",
        {"form": form, "title": "تسجيل جهة موافقة مطلوبة"},
    )


@login_required
def club_profile(request, pk):
    club = get_object_or_404(scoped_clubs(request.user), pk=pk)
    records = activities(request.user).filter(club=club)
    return render(
        request,
        "coordination/club.html",
        {
            "club": club,
            "members": User.objects.filter(profile__club=club, is_active=True),
            "rows": records[:10],
            "submitted": records.exclude(status="draft").count(),
            "approved": records.filter(status="approved").count(),
            "completed": records.filter(status="completed").count(),
            "plans": club.plans.order_by("-month"),
        },
    )


@login_required
def plan(request, pk, item=None):
    club = get_object_or_404(scoped_clubs(request.user), pk=pk)
    p = profile(request.user)
    if p.role != "club":
        require(request.user, "operations", True)
    obj = get_object_or_404(ClubPlan, pk=item, club=club) if item else None
    form = PlanForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        row = form.save(commit=False)
        row.club = club
        row.month = row.month.replace(day=1)
        if (
            ClubPlan.objects.filter(club=club, month=row.month)
            .exclude(pk=obj.pk if obj else None)
            .exists()
        ):
            form.add_error("month", "توجد خطة لهذا الشهر؛ عدّل الخطة الحالية")
        else:
            row.save()
            audit(request.user, "monthly_plan", row.pk)
            return redirect("club_profile", pk)
    return render(
        request,
        "coordination/form.html",
        {"form": form, "title": "الخطة الشهرية — " + club.name},
    )


@login_required
def logo(request, pk):
    club = get_object_or_404(scoped_clubs(request.user), pk=pk)
    if not club.logo:
        return HttpResponse(status=404)
    return FileResponse(club.logo.open("rb"))


def case_scope(user):
    require(user, "cases")
    return (
        Case.objects.all()
        if profile(user).role == "coordinator"
        else Case.objects.filter(assigned=user)
    )


@login_required
@require_POST
def case_upload(request, pk):
    require(request.user, "cases", True)
    case = get_object_or_404(case_scope(request.user), pk=pk)
    file = request.FILES.get("file")
    try:
        name, _ = validate_document(file)
    except ValidationError as error:
        messages.error(request, "؛ ".join(error.messages))
    else:
        CaseDocument.objects.create(
            case=case, file=file, name=name, uploader=request.user
        )
        audit(request.user, "case_upload", case.pk)
    return redirect("record_edit", module="cases", pk=pk)


@login_required
def case_download(request, pk):
    record = get_object_or_404(CaseDocument, pk=pk, case__in=case_scope(request.user))
    audit(request.user, "case_download", record.case_id)
    return FileResponse(
        record.file.open("rb"), as_attachment=True, filename=record.name
    )


@login_required
@require_POST
def task_status(request, pk):
    p = profile(request.user)
    task = get_object_or_404(Task, pk=pk, assigned=request.user)
    if p.role == "club" and task.club_id != p.club_id:
        raise PermissionDenied
    status = request.POST.get("status")
    if status not in dict(Task._meta.get_field("status").choices):
        return HttpResponse(status=400)
    task.status = status
    task.save(update_fields=["status"])
    audit(request.user, "task_status", task.pk, status)
    return redirect("my_tasks")


@login_required
def my_tasks(request):
    p = profile(request.user)
    rows = Task.objects.filter(assigned=request.user)
    if p.role == "club":
        rows = rows.filter(club=p.club)
    return render(
        request, "coordination/my_tasks.html", {"tasks": rows.order_by("due")}
    )


@login_required
def audit_log(request):
    if profile(request.user).role != "coordinator":
        raise PermissionDenied
    rows = Audit.objects.select_related("actor").order_by("-created")
    if request.GET.get("q"):
        rows = rows.filter(action__icontains=request.GET["q"])
    from django.core.paginator import Paginator

    return render(
        request,
        "coordination/audit.html",
        {"page": Paginator(rows, 50).get_page(request.GET.get("page"))},
    )


@login_required
@require_POST
def revoke_invitation(request, pk):
    if profile(request.user).role != "coordinator":
        raise PermissionDenied
    from .models import Invitation

    row = get_object_or_404(Invitation, pk=pk, used=False)
    row.used = True
    row.save(update_fields=["used"])
    audit(request.user, "revoke_invitation", row.pk)
    messages.success(request, "تم إلغاء الدعوة؛ الرابط السابق لم يعد صالحاً")
    return redirect("accounts")


@login_required
def club_meetings(request, pk=None):
    p = profile(request.user)
    if p.role != "club":
        raise PermissionDenied
    from .models import Meeting
    from .forms import model_form

    q = Meeting.objects.filter(club=p.club)
    obj = get_object_or_404(q, pk=pk, creator=request.user) if pk else None
    klass = model_form(Meeting, ("club", "creator"))
    form = klass(request.POST or None, instance=obj)
    form.fields["participants"].queryset = User.objects.filter(
        is_active=True, profile__club=p.club
    )
    if request.method == "POST" and form.is_valid():
        meeting = form.save(commit=False)
        meeting.club = p.club
        meeting.creator = request.user
        meeting.save()
        form.save_m2m()
        audit(request.user, "save_meetings", meeting.pk)
        messages.success(request, "تم حفظ الاجتماع")
        return redirect("club_meetings")
    return render(
        request,
        "coordination/club_meetings.html",
        {"form": form, "meetings": q.order_by("-date")},
    )


@login_required
def letter_list(request):
    require(request.user, "letters")
    from .models import Letter
    from django.db.models import Q
    from django.core.paginator import Paginator

    rows = (
        Letter.objects.filter(activity__in=activities(request.user))
        .select_related("activity__club")
        .order_by("-created")
    )
    search = request.GET.get("q", "").strip()
    if search:
        match = (
            Q(subject__icontains=search)
            | Q(official_number__icontains=search)
            | Q(recipient__icontains=search)
        )
        if search.startswith("LET-") and search.rsplit("-", 1)[-1].isdigit():
            match |= Q(pk=int(search.rsplit("-", 1)[-1]))
        rows = rows.filter(match)
    if request.GET.get("status"):
        rows = rows.filter(status=request.GET["status"])
    return render(
        request,
        "coordination/letters.html",
        {
            "page": Paginator(rows, 30).get_page(request.GET.get("page")),
            "states": Letter._meta.get_field("status").choices,
        },
    )


@login_required
def clubs_overview(request):
    return render(
        request, "coordination/clubs.html", {"clubs": scoped_clubs(request.user)}
    )
