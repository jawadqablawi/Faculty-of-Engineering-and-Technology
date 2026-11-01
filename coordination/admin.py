from django.contrib import admin
from .models import Profile, Club, Setting, Audit
from .services import audit


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "role", "club", "verified"]
    filter_horizontal = ["clubs", "authorized_activities"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        audit(request.user, "permission_change", obj.pk, ",".join(form.changed_data))


admin.site.register(Club)
admin.site.register(Setting)


@admin.register(Audit)
class AuditAdmin(admin.ModelAdmin):
    list_display = ["created", "actor", "action", "record"]
    readonly_fields = ["created", "actor", "action", "record", "note"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.site_header = "إدارة نظام تنسيق الكلية"
