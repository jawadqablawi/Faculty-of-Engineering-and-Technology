from django.contrib import admin
from django.contrib.auth import views as auth
from django.urls import path
from coordination import views as v

urlpatterns = [
    path(
        "reports/operations/<str:kind>/", v.operations_report, name="operations_report"
    ),
    path("", v.home, name="home"),
    path("login/", v.SecureLogin.as_view(), name="login"),
    path("logout/", auth.LogoutView.as_view(), name="logout"),
    path(
        "password-reset/",
        auth.PasswordResetView.as_view(
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
