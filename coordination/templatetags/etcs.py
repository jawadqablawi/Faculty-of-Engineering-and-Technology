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
