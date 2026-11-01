from django import forms
from .models import Activity, Letter, Case, Task, Meeting, Idea, Report, Club


class ActivityForm(forms.ModelForm):
    class Meta:
        model = Activity
        fields = [
            "title",
            "description",
            "objectives",
            "organizer",
            "contact",
            "audience",
            "participants",
            "date",
            "start",
            "end",
            "venue",
            "platform",
            "meeting_url",
        ]
        labels = dict(
            zip(
                fields,
                [
                    "عنوان النشاط",
                    "وصف النشاط",
                    "الأهداف",
                    "المنظم المسؤول",
                    "هاتف أو بريد التواصل",
                    "الفئة المستهدفة",
                    "العدد المتوقع",
                    "التاريخ المقترح",
                    "وقت البداية",
                    "وقت النهاية",
                    "المبنى والقاعة",
                    "المنصة",
                    "رابط اللقاء",
                ],
            )
        )
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "start": forms.TimeInput(attrs={"type": "time"}),
            "end": forms.TimeInput(attrs={"type": "time"}),
            "description": forms.Textarea(attrs={"rows": 3}),
            "objectives": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *a, kind="event", **kw):
        super().__init__(*a, **kw)
        self.kind = kind
        if kind == "event":
            self.fields.pop("platform")
            self.fields.pop("meeting_url")
        else:
            self.fields.pop("venue")
            self.fields["platform"] = forms.ChoiceField(
                label="منصة الورشة",
                choices=[
                    (x, x)
                    for x in [
                        "Google Meet",
                        "Zoom",
                        "Microsoft Teams",
                        "Discord",
                        "أخرى",
                    ]
                ],
            )

    def clean(self):
        d = super().clean()
        if d.get("start") and d.get("end") and d["end"] <= d["start"]:
            self.add_error("end", "وقت النهاية يجب أن يلي البداية")
        return d


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
    "notes": "ملاحظات إضافية",
}


class DetailsForm(forms.Form):
    def __init__(self, *a, kind="event", **kw):
        super().__init__(*a, **kw)
        online = {
            "presenter",
            "topic",
            "prerequisites",
            "certificates",
            "registration_open",
            "reminders",
            "post_publication",
        }
        physical = {
            "activity_type",
            "scope",
            "setup",
            "cleanup",
            "additional_dates",
            "indoor",
            "capacity",
            "venue_needs",
            "program",
            "speakers",
            "partners",
        }
        for k, v in DETAIL_FIELDS.items():
            if k in {"program", "speakers", "partners"}:
                continue
            if (kind == "event" and k in online) or (
                kind == "online" and k in physical
            ):
                continue
            widget = (
                forms.Textarea(attrs={"rows": 2})
                if k
                in {
                    "program",
                    "speakers",
                    "partners",
                    "media",
                    "notes",
                    "presenter",
                    "topic",
                }
                else forms.TextInput()
            )
            if k in {
                "publication_date",
                "registration_deadline",
                "registration_open",
                "post_publication",
                "alternative_date",
            }:
                widget = forms.DateInput(attrs={"type": "date"})
            self.fields[k] = forms.CharField(
                label=v, required=False, widget=widget, max_length=4000
            )


class RequirementForm(forms.Form):
    category = forms.ChoiceField(
        label="الفئة",
        choices=[("", "اختر الفئة")]
        + [
            (x, x)
            for x in [
                "قاعات وغرف",
                "أجهزة عرض وشاشات",
                "حواسيب",
                "صوتيات",
                "إنترنت",
                "معدات كهربائية",
                "معدات مختبرات",
                "طاولات وكراسٍ",
                "مطبوعات",
                "شهادات وجوائز",
                "ديكور",
                "ضيافة",
                "مواصلات",
                "تغطية إعلامية",
                "خدمات خارجية",
                "أخرى",
            ]
        ],
    )
    item = forms.CharField(label="الصنف", max_length=150)
    description = forms.CharField(label="الوصف", required=False, max_length=500)
    quantity = forms.DecimalField(label="الكمية", min_value=0, decimal_places=2)
    unit = forms.CharField(label="الوحدة", required=False, max_length=50)
    price = forms.DecimalField(
        label="سعر الوحدة ₪", min_value=0, decimal_places=2, required=False, initial=0
    )
    provider = forms.CharField(label="الجهة الموفرة", required=False, max_length=150)
    available = forms.BooleanField(label="متوفر مجاناً", required=False)
    notes = forms.CharField(label="ملاحظات", required=False, max_length=500)


class SessionForm(forms.Form):
    title = forms.CharField(label="عنوان الجلسة", max_length=150)
    date = forms.DateField(
        label="التاريخ", widget=forms.DateInput(attrs={"type": "date"})
    )
    start = forms.TimeField(
        label="البداية", widget=forms.TimeInput(attrs={"type": "time"})
    )
    end = forms.TimeField(
        label="النهاية", widget=forms.TimeInput(attrs={"type": "time"})
    )
    presenter = forms.CharField(label="مقدم الجلسة", required=False, max_length=150)
    topic = forms.CharField(label="الموضوع", required=False, max_length=300)

    def clean(self):
        d = super().clean()
        if d.get("start") and d.get("end") and d["end"] <= d["start"]:
            raise forms.ValidationError("نهاية الجلسة يجب أن تلي بدايتها")
        return d


Requirements = forms.formset_factory(
    RequirementForm, extra=1, can_delete=True, max_num=50, validate_max=True
)
Sessions = forms.formset_factory(
    SessionForm, extra=1, can_delete=True, max_num=50, validate_max=True
)


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
CaseForm = model_form(Case, ("assigned",))
TaskForm = model_form(Task)
MeetingForm = model_form(Meeting)
IdeaForm = model_form(Idea, ("club", "outcome", "notes"))
ReportForm = model_form(Report, ("activity", "accepted", "correction_note"))
ClubForm = model_form(Club)


class ProgramForm(forms.Form):
    title = forms.CharField(label="عنوان الفقرة", max_length=150)
    start = forms.TimeField(
        label="البداية", widget=forms.TimeInput(attrs={"type": "time"})
    )
    end = forms.TimeField(
        label="النهاية", widget=forms.TimeInput(attrs={"type": "time"})
    )
    person = forms.CharField(label="المسؤول", max_length=150)
    description = forms.CharField(label="الوصف", required=False, max_length=1000)
    equipment = forms.CharField(
        label="المعدات المطلوبة", required=False, max_length=1000
    )

    def clean(self):
        d = super().clean()
        if d.get("start") and d.get("end") and d["end"] <= d["start"]:
            raise forms.ValidationError("نهاية الفقرة يجب أن تلي بدايتها")
        return d


class SpeakerForm(forms.Form):
    name = forms.CharField(label="اسم المتحدث", max_length=150)
    position = forms.CharField(label="الصفة", required=False, max_length=150)
    organization = forms.CharField(label="المؤسسة", required=False, max_length=150)
    contact = forms.CharField(label="التواصل", required=False, max_length=150)
    external = forms.BooleanField(label="من خارج الجامعة", required=False)
    role = forms.CharField(label="الدور في النشاط", required=False, max_length=150)
    invitation = forms.BooleanField(label="يحتاج دعوة رسمية", required=False)
    requirements = forms.CharField(
        label="متطلبات خاصة", required=False, max_length=1000
    )


class PartnerForm(forms.Form):
    name = forms.CharField(label="اسم الجهة", max_length=150)
    kind = forms.CharField(label="نوع الشريك", required=False, max_length=150)
    details = forms.CharField(label="تفاصيل التعاون", required=False, max_length=1000)
    coordination = forms.CharField(
        label="التنسيق المطلوب", required=False, max_length=1000
    )
    contact = forms.CharField(label="مسؤول التواصل", required=False, max_length=150)


Programs = forms.formset_factory(
    ProgramForm, extra=1, can_delete=True, max_num=50, validate_max=True
)
Speakers = forms.formset_factory(
    SpeakerForm, extra=1, can_delete=True, max_num=50, validate_max=True
)
Partners = forms.formset_factory(
    PartnerForm, extra=1, can_delete=True, max_num=50, validate_max=True
)
