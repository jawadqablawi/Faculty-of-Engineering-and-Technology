from django.contrib import admin
from django.contrib.auth import views as auth
from django.urls import path
from coordination import views as v, extra_views as x

urlpatterns = [
    path("letters/", x.letter_list, name="letters"),
    path("clubs/", x.clubs_overview, name="clubs"),
    path("club-meetings/", x.club_meetings, name="club_meetings"),
    path("club-meetings/<int:pk>/", x.club_meetings, name="club_meeting_edit"),
    path(
        "manage/invitations/<int:pk>/revoke/",
        x.revoke_invitation,
        name="revoke_invitation",
    ),
    path("healthz/", v.health, name="health"),
    path("requests/<uuid:pk>/comment/", x.comment, name="comment"),
    path("requests/<uuid:pk>/publications/", x.publications, name="publications"),
    path(
        "requests/<uuid:pk>/publications/<int:item>/",
        x.publications,
        name="publication_edit",
    ),
    path("requests/<uuid:pk>/approvals/new/", x.approval, name="approval_new"),
    path("requests/<uuid:pk>/approvals/<int:item>/", x.approval, name="approval_edit"),
    path("clubs/<int:pk>/", x.club_profile, name="club_profile"),
    path("clubs/<int:pk>/plan/", x.plan, name="plan"),
    path("clubs/<int:pk>/plan/<int:item>/", x.plan, name="plan_edit"),
    path("clubs/<int:pk>/logo/", x.logo, name="logo"),
    path("cases/<int:pk>/upload/", x.case_upload, name="case_upload"),
    path("case-files/<uuid:pk>/", x.case_download, name="case_download"),
    path("tasks/mine/", x.my_tasks, name="my_tasks"),
    path("tasks/<int:pk>/status/", x.task_status, name="task_status"),
    path("manage/audit/", x.audit_log, name="audit_log"),
    path(
        "reports/operations/<str:kind>/", v.operations_report, name="operations_report"
    ),
    path("", v.home, name="home"),
    path("login/", v.SecureLogin.as_view(), name="login"),
    path("logout/", auth.LogoutView.as_view(), name="logout"),
    path(
        "password-reset/",
        v.LimitedPasswordReset.as_view(
            template_name="coordination/form.html",
            email_template_name="coordination/reset_email.txt",
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth.PasswordResetDoneView.as_view(
            template_name="coordination/reset_done.html"
        ),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth.PasswordResetConfirmView.as_view(template_name="coordination/form.html"),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth.PasswordResetCompleteView.as_view(
            template_name="coordination/reset_done.html"
        ),
        name="password_reset_complete",
    ),
    path("requests/", v.request_list, name="requests"),
    path("new/<str:kind>/", v.edit_activity, name="new_activity"),
    path("requests/<uuid:pk>/", v.activity, name="activity"),
    path("requests/<uuid:pk>/edit/", v.edit_activity, name="edit_activity"),
    path("requests/<uuid:pk>/action/", v.action, name="action"),
    path("requests/<uuid:pk>/upload/", v.upload, name="upload"),
    path("requests/<uuid:pk>/report/", v.report, name="report"),
    path("files/<uuid:pk>/", v.download, name="download"),
    path("files/<uuid:pk>/delete/", v.delete_attachment, name="delete_attachment"),
    path("requests/<uuid:activity_pk>/letter/", v.letter_edit, name="new_letter"),
    path("letters/<int:pk>/", v.letter, name="letter"),
    path("letters/<int:pk>/edit/", v.letter_edit, name="edit_letter"),
    path("calendar/", v.calendar, name="calendar"),
    path("calendar/export/", v.calendar_export, name="calendar_export"),
    path("notifications/", v.notifications, name="notifications"),
    path("reports/", v.reports, name="reports"),
    path("manage/invite/", v.invite, name="invite"),
    path("manage/accounts/", v.accounts, name="accounts"),
    path("accept/<uuid:token>/", v.accept, name="accept"),
    path("operations/<str:module>/", v.records, name="records"),
    path("operations/<str:module>/<int:pk>/", v.records, name="record_edit"),
    path("manage/permissions/<int:pk>/", v.permissions, name="permissions"),
    path("manage/settings/", v.system_settings, name="settings"),
    path(
        "requests/<uuid:pk>/report/corrections/",
        v.report_corrections,
        name="report_corrections",
    ),
    path("cases/<int:pk>/anonymize/", v.anonymize_case, name="anonymize_case"),
    path("admin/", admin.site.urls),
]
