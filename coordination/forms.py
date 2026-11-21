from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password

from .models import (
    Activity,
    Case,
    Club,
    ClubPlan,
    Idea,
    Letter,
    Meeting,
    Publication,
    Report,
    Task,
)


class ClubAccountForm(forms.Form):
    first_name = forms.CharField(label="اسم مسؤول النادي", max_length=150)
    email = forms.EmailField(
        label="البريد الإلكتروني",
        max_length=User._meta.get_field("username").max_length,
        widget=forms.EmailInput(attrs={"autocomplete": "off", "dir": "ltr"}),
    )
    club = forms.ModelChoiceField(
        label="النادي",
        queryset=Club.objects.filter(active=True).order_by("name"),
        empty_label="اختر النادي",
    )
    temporary_password = forms.CharField(
        label="كلمة المرور",
        strip=False,
        max_length=4096,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if (
            User.objects.filter(email__iexact=email).exists()
            or User.objects.filter(username__iexact=email).exists()
        ):
            raise forms.ValidationError("يوجد حساب لهذا البريد بالفعل.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get("email")
        password = cleaned_data.get("temporary_password")
        if email and password:
            try:
                validate_password(password, User(username=email, email=email))
            except forms.ValidationError as error:
                self.add_error("temporary_password", error)
        return cleaned_data


class ClubRequestForm(forms.ModelForm):
    class Meta:
        model = Activity
        fields = ["title", "description", "date", "venue"]
        labels = {
            "title": "العنوان",
            "description": "الوصف",
            "date": "التاريخ",
            "venue": "المكان",
        }
        widgets = {
            "date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("description", "date", "venue"):
            self.fields[name].required = True

    def clean_date(self):
        from django.utils import timezone

        day = self.cleaned_data["date"]
        if day < timezone.localdate():
            raise forms.ValidationError("اختر تاريخًا من اليوم فما بعد.")
        return day


class ClubNeedForm(forms.Form):
    item = forms.CharField(label="الصنف", max_length=180)
    quantity = forms.IntegerField(label="العدد", min_value=1, max_value=1_000_000)


ClubNeeds = forms.formset_factory(
    ClubNeedForm, extra=1, can_delete=True, max_num=100, validate_max=True
)


DETAIL_FIELDS = {
    "activity_type": "نوع النشاط",
    "expected_outcomes": "النتائج المتوقعة",
    "team": "فريق التنظيم",
    "scope": "داخل الجامعة / خارجها",
    "discussed": "ملخص النقاش المسبق",
    "idea_reference": "مرجع الفكرة",
    "alternative_date": "موعد بديل",
    "setup": "وقت التجهيز",
    "cleanup": "وقت التنظيف",
    "additional_dates": "الأيام الإضافية",
    "indoor": "داخلي / خارجي",
    "capacity": "سعة المكان",
    "venue_needs": "متطلبات المكان وإمكانية الوصول",
    "program": "البرنامج: الفقرة، البداية، النهاية، المسؤول والمعدات",
    "speakers": "المتحدثون: الاسم، المؤسسة، التواصل، الدور والدعوة",
    "partners": "الشراكات: الجهة، النوع، التفاصيل ومسؤول التواصل",
    "media": "خطة الإعلام والترويج وفريق النشر",
    "registration_url": "رابط التسجيل",
    "registration_deadline": "نهاية التسجيل",
    "presenter": "مقدم الورشة ومؤهلاته ووسائل التواصل",
    "topic": "الموضوع ومحاور المحتوى",
    "prerequisites": "المتطلبات السابقة",
    "certificates": "الشهادات المطلوبة",
    "publication_date": "موعد الإعلان",
    "publication_time": "وقت الإعلان",
    "publication_channel": "قناة النشر",
    "publication_status": "حالة النشر",
    "registration_open": "بدء التسجيل",
    "reminders": "مواعيد التذكير",
    "post_publication": "موعد النشر بعد الورشة",
    "registration_required": "التسجيل مطلوب؟",
    "announcement_required": "إعلان مطلوب؟",
    "media_team": "فريق الإعلام المسؤول",
    "promotional_text": "النص الترويجي",
    "presenter_qualifications": "مؤهلات مقدم الورشة ومؤسسته",
    "presenter_contact": "التواصل مع مقدم الورشة",
    "content_outline": "محاور المحتوى",
    "accessibility": "احتياجات إمكانية الوصول",
    "notes": "ملاحظات إضافية",
}


def model_form(model, exclude=()):
    widgets = {
        f.name: forms.DateInput(attrs={"type": "date"})
        for f in model._meta.fields
        if f.get_internal_type() == "DateField"
    }
    widgets.update(
        {
            f.name: forms.DateTimeInput(attrs={"type": "datetime-local"})
            for f in model._meta.fields
            if f.get_internal_type() == "DateTimeField"
        }
    )
    labels = {
        "subject": "الموضوع",
        "recipient": "الجهة المستقبلة",
        "body": "نص الكتاب",
        "official_number": "الرقم الرسمي إن وجد",
        "status": "الحالة",
        "evidence": "دليل الإرسال أو الرد",
        "follow_up": "موعد المتابعة",
        "category": "التصنيف",
        "description": "الوصف",
        "priority": "الأولوية",
        "notes": "ملاحظات داخلية",
        "resolution": "ملخص الحل",
        "assigned": "المكلف",
        "title": "العنوان",
        "club": "النادي",
        "due": "الموعد النهائي",
        "date": "التاريخ",
        "attendees": "الحضور",
        "agenda": "جدول الأعمال",
        "decisions": "القرارات",
        "objective": "الهدف",
        "outcome": "نتيجة النقاش",
        "actual_date": "التاريخ الفعلي",
        "location": "الموقع / المنصة",
        "summary": "الملخص",
        "outcomes": "النتائج والأهداف المحققة",
        "challenges": "التحديات",
        "recommendations": "التوصيات",
        "costs": "التكلفة الفعلية ₪",
        "name": "الاسم",
        "month": "الشهر (اختر أي يوم فيه)",
        "activities": "الأنشطة المخطط لها",
        "scheduled": "تاريخ ووقت النشر",
        "channel": "قناة النشر",
        "responsible": "المسؤول عن النشر",
        "contact": "التواصل (عند الحاجة)",
        "department": "القسم المعني",
        "logo": "شعار النادي",
        "participants": "المشاركون",
        "submitted_date": "تاريخ الإرسال",
        "response_date": "تاريخ الرد",
        "active": "نشط",
        "email": "البريد الإلكتروني",
        "president": "رئيس النادي",
        "vice_president": "نائب الرئيس",
        "committee": "اللجنة",
    }
    return forms.modelform_factory(
        model, exclude=["created", *exclude], widgets=widgets, labels=labels
    )


LetterForm = model_form(Letter, ("activity",))
CaseForm = model_form(Case)
TaskForm = model_form(Task)
MeetingForm = model_form(Meeting, ("creator",))
IdeaForm = model_form(Idea, ("club", "outcome", "notes"))
ReportForm = model_form(Report, ("activity", "accepted", "correction_note"))
ClubForm = model_form(Club)


PublicationForm = model_form(Publication, ("activity",))
PlanForm = model_form(ClubPlan, ("club",))
