import uuid
from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator


class Club(models.Model):
    name = models.CharField(max_length=180, unique=True)
    active = models.BooleanField(default=True)
    email = models.EmailField(blank=True)
    president = models.CharField(max_length=150, blank=True)
    vice_president = models.CharField(max_length=150, blank=True)
    committee = models.TextField(blank=True)
    logo = models.ImageField(upload_to="club-logos/", blank=True)

    def __str__(self):
        return self.name


class Profile(models.Model):
    ROLES = [
        ("coordinator", "منسق الكلية"),
        ("deputy", "نائب المنسق"),
        ("club", "إدارة النادي"),
        ("reviewer", "مراجع المجلس"),
        ("auditor", "مدقق"),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLES, default="club")
    club = models.ForeignKey(Club, on_delete=models.PROTECT, null=True, blank=True)
    clubs = models.ManyToManyField(Club, related_name="delegates", blank=True)
    modules = models.JSONField(default=list, blank=True)
    authorized_activities = models.ManyToManyField(
        "Activity", related_name="authorized_readers", blank=True
    )
    verified = models.BooleanField(default=False)

    def __str__(self):
        return str(self.user)


class Activity(models.Model):
    STATES = [
        ("draft", "مسودة"),
        ("review", "بانتظار المراجعة"),
        ("changes", "مطلوب تعديل"),
        ("preliminary", "موافقة أولية"),
        ("council", "مرفوع للمجلس"),
        ("approvals", "بانتظار الموافقات"),
        ("approved", "معتمد"),
        ("rejected", "مرفوض"),
        ("completed", "مكتمل"),
        ("cancelled", "ملغي"),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    number = models.CharField(max_length=30, unique=True, blank=True, null=True)
    club = models.ForeignKey(Club, on_delete=models.PROTECT)
    creator = models.ForeignKey(User, on_delete=models.PROTECT)
    kind = models.CharField(
        max_length=10,
        choices=[("event", "فعالية وجاهية"), ("online", "ورشة إلكترونية")],
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    objectives = models.TextField(blank=True)
    audience = models.CharField(max_length=200, blank=True)
    participants = models.PositiveIntegerField(default=0)
    organizer = models.CharField(max_length=150, blank=True)
    contact = models.CharField(max_length=200, blank=True)
    date = models.DateField(null=True, blank=True)
    start = models.TimeField(null=True, blank=True)
    end = models.TimeField(null=True, blank=True)
    venue = models.CharField(max_length=180, blank=True)
    platform = models.CharField(max_length=50, blank=True)
    meeting_url = models.URLField(blank=True)
    details = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATES, default="draft")
    council_approved = models.BooleanField(default=False)
    university_approved = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    submitted = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-updated"]
        indexes = [
            models.Index(fields=["club", "status"]),
            models.Index(fields=["date", "status"]),
        ]

    def __str__(self):
        return self.title

    @property
    def academic_year(self):
        if not self.date:
            return "غير محدد"
        year = self.date.year if self.date.month >= 9 else self.date.year - 1
        return f"{year} / {year + 1}"

    @property
    def semester(self):
        if not self.date:
            return "غير محدد"
        if self.date.month >= 9 or self.date.month == 1:
            return "الفصل الأول"
        return "الفصل الثاني" if self.date.month <= 6 else "الفصل الصيفي"

    @property
    def budget(self):
        return sum(
            Decimal(str(x.get("quantity", 0))) * Decimal(str(x.get("price", 0)))
            for x in self.details.get("requirements", [])
        )


class History(models.Model):
    activity = models.ForeignKey(
        Activity, on_delete=models.PROTECT, related_name="history"
    )
    actor = models.ForeignKey(User, on_delete=models.PROTECT)
    previous = models.CharField(max_length=30, blank=True)
    status = models.CharField(max_length=30)
    note = models.TextField(blank=True)
    snapshot = models.JSONField(default=dict)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created"]


class Attachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    activity = models.ForeignKey(
        Activity, on_delete=models.PROTECT, related_name="attachments"
    )
    file = models.FileField(upload_to="documents/%Y/%m/")
    name = models.CharField(max_length=200)
    uploader = models.ForeignKey(User, on_delete=models.PROTECT)
    supersedes = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="next_version",
    )
    version = models.PositiveIntegerField(default=1)
    checksum = models.CharField(max_length=64, blank=True)
    purpose = models.CharField(max_length=100, blank=True)
    deleted = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)


class Letter(models.Model):
    activity = models.ForeignKey(
        Activity, on_delete=models.PROTECT, related_name="letters"
    )
    subject = models.CharField(max_length=200)
    recipient = models.CharField(max_length=200, default="مجلس الطلبة")
    body = models.TextField()
    official_number = models.CharField(max_length=100, blank=True)
    status = models.CharField(
        max_length=30,
        choices=[
            (x, x)
            for x in [
                "مسودة",
                "جاهز للمراجعة",
                "جاهز للتوقيع",
                "تم الإرسال",
                "بانتظار الرد",
                "تمت الموافقة",
                "مرفوض",
                "بحاجة لتعديل",
                "مغلق",
            ]
        ],
        default="مسودة",
    )
    evidence = models.TextField(blank=True)
    follow_up = models.DateField(null=True, blank=True)
    submitted_date = models.DateField(null=True, blank=True)
    response_date = models.DateField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    @property
    def number(self):
        return f"LET-{self.created.year}-{self.pk:04d}"


class Case(models.Model):
    contact = models.CharField(max_length=200, blank=True)
    department = models.CharField(max_length=150, blank=True)
    subject = models.CharField(max_length=200)
    category = models.CharField(
        max_length=100,
        choices=[
            (x, x)
            for x in [
                "أكاديمية",
                "تعارض امتحانات",
                "تسجيل مساقات",
                "مختبرات",
                "مرافق الجامعة",
                "شكاوى",
                "اقتراحات",
                "عامة",
            ]
        ],
    )
    description = models.TextField()
    priority = models.CharField(
        max_length=20,
        choices=[("normal", "عادية"), ("high", "عاجلة")],
        default="normal",
    )
    status = models.CharField(
        max_length=50,
        choices=[
            (x, x)
            for x in [
                "جديد",
                "قيد المتابعة",
                "محوّل للجهة المختصة",
                "بانتظار الرد",
                "تم الحل",
                "مغلق",
            ]
        ],
        default="جديد",
    )
    notes = models.TextField(blank=True)
    resolution = models.TextField(blank=True)
    follow_up = models.DateField(null=True, blank=True)
    assigned = models.ForeignKey(User, on_delete=models.PROTECT)
    created = models.DateTimeField(auto_now_add=True)

    @property
    def number(self):
        return f"STD-{self.created.year}-{self.pk:04d}"


class Task(models.Model):
    title = models.CharField(max_length=200)
    club = models.ForeignKey(Club, on_delete=models.PROTECT, null=True, blank=True)
    assigned = models.ForeignKey(User, on_delete=models.PROTECT)
    due = models.DateField()
    priority = models.CharField(max_length=20, default="عادية")
    status = models.CharField(
        max_length=30,
        choices=[(x, x) for x in ["جديدة", "قيد التنفيذ", "مكتملة"]],
        default="جديدة",
    )
    notes = models.TextField(blank=True)

    @property
    def display_status(self):
        from django.utils import timezone

        return (
            "متأخرة"
            if self.status != "مكتملة" and self.due < timezone.localdate()
            else self.status
        )


class Meeting(models.Model):
    club = models.ForeignKey(Club, on_delete=models.PROTECT, null=True, blank=True)
    creator = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="organized_meetings",
    )
    participants = models.ManyToManyField(
        User, blank=True, related_name="coordination_meetings"
    )
    title = models.CharField(max_length=200)
    date = models.DateTimeField()
    attendees = models.TextField()
    agenda = models.TextField()
    notes = models.TextField(blank=True)
    decisions = models.TextField(blank=True)


class Idea(models.Model):
    club = models.ForeignKey(Club, on_delete=models.PROTECT)
    title = models.CharField(max_length=200)
    description = models.TextField()
    objective = models.TextField()
    date = models.DateField()
    outcome = models.CharField(
        max_length=60,
        choices=[
            (x, x)
            for x in [
                "بحاجة لنقاش",
                "جاهز للتقديم الرسمي",
                "بحاجة لتعديل",
                "غير موصى به",
            ]
        ],
        default="بحاجة لنقاش",
    )
    notes = models.TextField(blank=True)


class Report(models.Model):
    activity = models.OneToOneField(
        Activity, on_delete=models.PROTECT, related_name="report"
    )
    actual_date = models.DateField()
    location = models.CharField(max_length=200)
    attendees = models.PositiveIntegerField()
    summary = models.TextField()
    outcomes = models.TextField()
    challenges = models.TextField(blank=True)
    recommendations = models.TextField(blank=True)
    costs = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)]
    )
    accepted = models.BooleanField(default=False)
    correction_note = models.TextField(blank=True)


class Notification(models.Model):
    sender = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_coordination_notifications",
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.CharField(max_length=250)
    activity = models.ForeignKey(
        Activity, on_delete=models.CASCADE, null=True, blank=True
    )
    key = models.CharField(max_length=200, unique=True, null=True, blank=True)
    read = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)


class Audit(models.Model):
    actor = models.ForeignKey(User, on_delete=models.PROTECT, null=True)
    action = models.CharField(max_length=100)
    record = models.CharField(max_length=100)
    note = models.TextField(blank=True)
    created = models.DateTimeField(auto_now_add=True)


class Invitation(models.Model):
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    email = models.EmailField()
    role = models.CharField(max_length=20, choices=Profile.ROLES)
    club = models.ForeignKey(Club, on_delete=models.PROTECT, null=True, blank=True)
    expires = models.DateTimeField()
    used = models.BooleanField(default=False)


class Setting(models.Model):
    key = models.CharField(max_length=80, unique=True)
    value = models.JSONField(default=dict)


class EventDate(models.Model):
    activity = models.ForeignKey(
        Activity, on_delete=models.CASCADE, related_name="event_dates"
    )
    date = models.DateField()
    start = models.TimeField()
    end = models.TimeField()
    venue = models.CharField(max_length=180)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end__gt=models.F("start")),
                name="event_date_end_after_start",
            )
        ]


class WorkshopSession(models.Model):
    activity = models.ForeignKey(
        Activity, on_delete=models.CASCADE, related_name="workshop_sessions"
    )
    title = models.CharField(max_length=150)
    date = models.DateField()
    start = models.TimeField()
    end = models.TimeField()
    presenter = models.CharField(max_length=150, blank=True)
    topic = models.CharField(max_length=300, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end__gt=models.F("start")),
                name="workshop_session_end_after_start",
            )
        ]


class Publication(models.Model):
    activity = models.ForeignKey(
        Activity, on_delete=models.PROTECT, related_name="publications"
    )
    title = models.CharField(max_length=180)
    scheduled = models.DateTimeField()
    channel = models.CharField(max_length=100)
    responsible = models.CharField(max_length=150, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ("draft", "مسودة"),
            ("review", "بانتظار المراجعة"),
            ("scheduled", "مجدول"),
            ("published", "تم النشر"),
            ("cancelled", "ملغي"),
        ],
        default="draft",
    )
    evidence = models.URLField(blank=True)
    notes = models.TextField(blank=True)


class ApprovalRequirement(models.Model):
    activity = models.ForeignKey(
        Activity, on_delete=models.PROTECT, related_name="approval_requirements"
    )
    office = models.CharField(max_length=150)
    required = models.BooleanField(default=True)
    decision = models.CharField(
        max_length=20,
        choices=[
            ("pending", "بانتظار القرار"),
            ("approved", "موافق"),
            ("rejected", "مرفوض"),
        ],
        default="pending",
    )
    evidence = models.TextField(blank=True)
    actor = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True)
    decided = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["activity", "office"], name="unique_activity_approval_office"
            )
        ]


class LetterHistory(models.Model):
    letter = models.ForeignKey(Letter, on_delete=models.PROTECT, related_name="history")
    actor = models.ForeignKey(User, on_delete=models.PROTECT)
    snapshot = models.JSONField(default=dict)
    created = models.DateTimeField(auto_now_add=True)


class ActivityComment(models.Model):
    activity = models.ForeignKey(
        Activity, on_delete=models.PROTECT, related_name="comments"
    )
    actor = models.ForeignKey(User, on_delete=models.PROTECT)
    text = models.TextField(max_length=4000)
    created = models.DateTimeField(auto_now_add=True)


class CaseDocument(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(Case, on_delete=models.PROTECT, related_name="documents")
    file = models.FileField(upload_to="case-documents/%Y/%m/")
    name = models.CharField(max_length=200)
    uploader = models.ForeignKey(User, on_delete=models.PROTECT)
    created = models.DateTimeField(auto_now_add=True)


class ClubPlan(models.Model):
    club = models.ForeignKey(Club, on_delete=models.PROTECT, related_name="plans")
    month = models.DateField()
    title = models.CharField(max_length=200)
    objectives = models.TextField()
    activities = models.TextField()
    notes = models.TextField(blank=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["club", "month"], name="club_monthly_plan")
        ]


class RateLimit(models.Model):
    key = models.CharField(max_length=64, unique=True)
    attempts = models.PositiveIntegerField(default=0)
    expires = models.DateTimeField()


class NumberSequence(models.Model):
    prefix = models.CharField(max_length=5)
    year = models.PositiveIntegerField()
    value = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["prefix", "year"], name="unique_document_sequence"
            )
        ]


class EmailDelivery(models.Model):
    notification = models.OneToOneField(
        Notification, on_delete=models.CASCADE, related_name="email_delivery"
    )
    attempts = models.PositiveIntegerField(default=0)
    last_attempt = models.DateTimeField(null=True, blank=True)
    sent = models.DateTimeField(null=True, blank=True)
