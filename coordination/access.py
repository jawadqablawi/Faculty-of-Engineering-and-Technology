from django.core.exceptions import PermissionDenied
from .models import Activity, Profile


def profile(user):
    if not user.is_authenticated or not user.is_active:
        raise PermissionDenied
    try:
        p = user.profile
    except Profile.DoesNotExist:
        raise PermissionDenied
    if not p.verified:
        raise PermissionDenied("يجب تفعيل الحساب والتحقق من البريد")
    if p.role == "club" and (not p.club_id or not p.club.active):
        raise PermissionDenied
    return p


def allowed(user, module, write=False):
    p = profile(user)
    if p.role == "coordinator":
        return True
    if p.role == "deputy":
        return module in p.modules
    if p.role == "auditor":
        return not write and module == "reports" and module in p.modules
    if p.role == "reviewer":
        return not write and module == "requests" and module in p.modules
    return False


def require(user, module, write=False):
    if not allowed(user, module, write):
        raise PermissionDenied


def activities(user):
    p = profile(user)
    q = Activity.objects.select_related("club", "creator")
    if p.role == "club":
        return q.filter(club=p.club)
    if (
        not allowed(user, "requests")
        and not allowed(user, "reports")
        and not allowed(user, "letters")
    ):
        return q.none()
    if p.role == "coordinator":
        return q
    if p.role == "auditor":
        return q.filter(pk__in=p.authorized_activities.values("pk"))
    return q.filter(club__in=p.clubs.all())
