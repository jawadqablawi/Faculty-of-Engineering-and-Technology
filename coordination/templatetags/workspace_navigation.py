from django import template
from django.urls import reverse

register = template.Library()

REQUEST_PAGES = {
    "activity": "تفاصيل الطلب",
    "edit_activity": "تعديل الطلب",
    "publications": "النشر",
    "publication_edit": "تعديل النشر",
    "approval_new": "تسجيل موافقة",
    "approval_edit": "تعديل الموافقة",
    "report": "التقرير الختامي",
    "new_letter": "إنشاء كتاب رسمي",
}
ACCOUNT_PAGES = {
    "invite": "دعوة مستخدم",
    "create_club_account": "إنشاء حساب نادي",
    "permissions": "صلاحيات المستخدم",
}
CLUB_PAGES = {
    "club_profile": "ملف النادي",
    "plan": "خطة النادي",
    "plan_edit": "تعديل الخطة",
}
OTHER_PAGES = {
    "notifications": "الإشعارات",
    "calendar": "تقويم الأنشطة",
    "letters": "الكتب الرسمية",
    "letter": "عرض الكتاب",
    "edit_letter": "تعديل الكتاب",
    "reports": "التقارير",
    "operations_report": "تقرير العمليات",
    "records": "السجلات",
    "record_edit": "تعديل السجل",
    "club_meetings": "اجتماعات النادي",
    "club_meeting_edit": "تعديل الاجتماع",
    "my_tasks": "المهام المسندة إليّ",
}


def navigation(identity):
    requests_label = (
        "طلباتي ومتابعتها" if identity.role == "club" else "الطلبات الواردة"
    )
    links = [
        ("home", "الرئيسية", "home", ()),
        ("requests", requests_label, "inbox", ()),
    ]
    if identity.role == "club":
        links.extend(
            [
                ("new_activity", "فعالية وجاهية جديدة", "add", ("event",)),
                ("new_activity", "ورشة إلكترونية جديدة", "video", ("online",)),
                ("calendar", "تقويم الأنشطة", "calendar", ()),
            ]
        )
    if identity.role == "coordinator":
        links.extend(
            [
                ("accounts", "المستخدمون والدعوات", "users", ()),
                ("settings", "الإعدادات", "settings", ()),
                ("audit_log", "سجل الإجراءات", "history", ()),
                ("clubs", "التقويم", "calendar", ()),
            ]
        )
    return links


def section_for(name):
    if name in REQUEST_PAGES:
        return "requests"
    if name in ACCOUNT_PAGES:
        return "accounts"
    if name in CLUB_PAGES or name == "calendar":
        return "clubs"
    return None


@register.simple_tag(takes_context=True)
def workspace_links(context, identity):
    match = context["request"].resolver_match
    name = match.url_name if match else None
    section = section_for(name)
    links = []
    for route, label, icon, args in navigation(identity):
        active = route == name and (not args or args == (match.kwargs.get("kind"),))
        links.append(
            {
                "href": reverse(route, args=args),
                "label": label,
                "icon": icon,
                "active": "page" if active else "location" if route == section else "",
            }
        )
    return links


@register.simple_tag(takes_context=True)
def workspace_breadcrumbs(context, identity):
    match = context["request"].resolver_match
    name = match.url_name if match else None
    if not name or name == "home":
        return []

    links = workspace_links(context, identity)
    current = next((link["label"] for link in links if link["active"] == "page"), None)
    crumbs = [("الرئيسية", reverse("home"))]
    if not current:
        current = (
            REQUEST_PAGES.get(name)
            or ACCOUNT_PAGES.get(name)
            or CLUB_PAGES.get(name)
            or OTHER_PAGES.get(name)
        )
        section = next((link for link in links if link["active"] == "location"), None)
        if section:
            crumbs.append((section["label"], section["href"]))
    if not current:
        return []
    return [*crumbs, (current, "")]
