from django import template
from coordination.forms import DETAIL_FIELDS
from coordination.models import Activity

register = template.Library()
LABELS = {
    "number": "رقم الطلب",
    "kind": "نوع الطلب",
    "title": "العنوان",
    "description": "الوصف",
    "objectives": "الأهداف",
    "audience": "الفئة المستهدفة",
    "participants": "العدد المتوقع",
    "organizer": "المسؤول",
    "contact": "التواصل",
    "date": "التاريخ",
    "start": "البداية",
    "end": "النهاية",
    "venue": "الموقع",
    "platform": "المنصة",
    "meeting_url": "رابط اللقاء",
    "status": "الحالة",
    "council_approved": "موافقة المجلس",
    "university_approved": "موافقة الجامعة",
    "submitted": "تاريخ التقديم",
    "details": "التفاصيل",
    "requirements": "الاحتياجات",
    "sessions": "الجلسات",
    "category": "الفئة",
    "item": "الصنف",
    "quantity": "الكمية",
    "unit": "الوحدة",
    "price": "سعر الوحدة",
    "provider": "الجهة الموفرة",
    "available": "متوفر",
    "notes": "ملاحظات",
    "person": "المسؤول",
    "equipment": "المعدات",
    "name": "الاسم",
    "position": "الصفة",
    "organization": "المؤسسة",
    "external": "خارجي",
    "role": "الدور",
    "invitation": "دعوة رسمية",
    "coordination": "التنسيق",
}


@register.filter
def label(value):
    return LABELS.get(value, DETAIL_FIELDS.get(value, "بيانات إضافية"))


@register.filter
def state(value):
    return dict(Activity.STATES).get(value, value)


@register.filter
def action_label(value):
    return {
        "submit": "إرسال الطلب",
        "save_draft": "حفظ مسودة",
        "preliminary": "موافقة أولية",
        "changes": "طلب تعديل",
        "reject": "رفض الطلب",
        "forward": "رفع للمجلس",
        "council_ok": "موافقة المجلس",
        "university_ok": "موافقة الجامعة",
        "complete": "إكمال النشاط",
        "permissions": "تعديل الصلاحيات",
        "upload": "رفع ملف",
        "download": "تنزيل ملف",
        "delete_attachment": "حذف مرفق",
        "comment": "تعليق",
        "publication": "خطة نشر",
        "approval_requirement": "متطلبات الموافقة",
        "invite": "دعوة مستخدم",
        "accept_invitation": "تفعيل مستخدم",
        "account_activation": "تفعيل أو تعطيل حساب",
        "letter": "تعديل كتاب رسمي",
        "case_upload": "مرفق قضية",
        "case_download": "تنزيل مرفق قضية",
        "monthly_plan": "خطة شهرية",
        "save_cases": "متابعة قضية",
        "save_tasks": "تعديل مهمة",
        "save_meetings": "تعديل اجتماع",
        "save_clubs": "تعديل نادي",
        "save_ideas": "متابعة فكرة",
        "report": "تقرير ختامي",
        "report_corrections": "تصحيح تقرير",
        "anonymize_case": "إزالة بيانات شخصية",
        "settings": "إعدادات",
    }.get(value, "إجراء إداري")
