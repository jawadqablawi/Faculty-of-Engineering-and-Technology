from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import connection, transaction
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from .access import activities, profile
from .models import Attachment, Audit, CaseDocument, Club, LetterHistory
from .services import audit
from .storage import DatabaseStorage

PROTECTED_AUDIT_ACTIONS = ("delete_audit_entry", "delete_request")


def coordinator_only(request):
    if profile(request.user).role != "coordinator":
        raise PermissionDenied


def deletion_scope(setting, identifier):
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config(%s, %s, true)", [setting, str(identifier)]
            )


@login_required
@require_POST
@transaction.atomic
def delete_audit_entry(request, pk):
    coordinator_only(request)
    entry = get_object_or_404(
        Audit.objects.exclude(action__in=PROTECTED_AUDIT_ACTIONS),
        pk=pk,
    )
    deletion_scope("etcs.delete_audit", entry.pk)
    deleted, _ = entry.delete()
    if deleted:
        audit(request.user, "delete_audit_entry", pk)
        messages.success(request, "تم حذف قيد سجل الإجراءات.")
    return redirect("audit_log")


@login_required
@require_POST
@transaction.atomic
def delete_request(request, pk):
    coordinator_only(request)
    activity = get_object_or_404(
        activities(request.user).select_for_update(of=("self",)),
        pk=pk,
    )
    deletion_scope("etcs.delete_request", pk)
    attachments = activity.attachments.all()
    storage = Attachment._meta.get_field("file").storage
    for name in set(attachments.exclude(file="").values_list("file", flat=True)):
        if (
            Attachment.objects.filter(file=name).exclude(activity=activity).exists()
            or CaseDocument.objects.filter(file=name).exists()
            or Club.objects.filter(logo=name).exists()
        ):
            continue
        if isinstance(storage, DatabaseStorage):
            storage.delete(name)
        else:
            transaction.on_commit(lambda path=name: storage.delete(path), robust=True)
    attachments.update(supersedes=None)
    attachments.delete()
    activity.history.all().delete()
    LetterHistory.objects.filter(letter__activity=activity).delete()
    activity.letters.all().delete()
    activity.approval_requirements.all().delete()
    activity.publications.all().delete()
    activity.comments.all().delete()
    if hasattr(activity, "report"):
        activity.report.delete()
    activity.delete()
    audit(request.user, "delete_request", pk)
    messages.success(request, "تم حذف الطلب ومرفقاته غير المشتركة.")
    return redirect("requests")
