from django.db import migrations


def change_policies(apps, schema_editor, enabled):
    if schema_editor.connection.vendor != "postgresql":
        return
    request = "NULLIF(current_setting('etcs.delete_request', true), '')"
    audit = "NULLIF(current_setting('etcs.delete_audit', true), '')"
    coordinator = "public.etcs_coordinator()"
    activity = f"activity_id::text = {request}"
    file_scope = (
        "EXISTS (SELECT 1 FROM public.coordination_attachment a "
        f"WHERE a.file = coordination_storeddocument.name AND a.{activity})"
    )
    policies = [
        (
            "audit",
            "etcs_delete",
            "DELETE",
            f"{coordinator} AND id::text = {audit} AND action NOT IN ('delete_audit_entry','delete_request')",
        ),
        (
            "activity",
            "etcs_delete",
            "DELETE",
            f"{coordinator} AND id::text = {request}",
        ),
        ("history", "etcs_delete", "DELETE", f"{coordinator} AND {activity}"),
        (
            "letterhistory",
            "etcs_delete",
            "DELETE",
            f"{coordinator} AND EXISTS (SELECT 1 FROM public.coordination_letter l WHERE l.id = letter_id AND l.{activity})",
        ),
        (
            "notification",
            "etcs_delete_request",
            "DELETE",
            f"{coordinator} AND {activity}",
        ),
        (
            "emaildelivery",
            "etcs_delete_request",
            "DELETE",
            f"{coordinator} AND EXISTS (SELECT 1 FROM public.coordination_notification n WHERE n.id = notification_id AND n.{activity})",
        ),
        (
            "storeddocument",
            "etcs_read_request_delete",
            "SELECT",
            f"{coordinator} AND {file_scope}",
        ),
    ]
    originals = {
        "audit": "public.etcs_user_id() IS NOT NULL",
        "activity": "public.etcs_club_write(club_id,'requests')",
        "history": "EXISTS (SELECT 1 FROM public.coordination_activity a WHERE a.id=activity_id AND public.etcs_club_write(a.club_id,'requests'))",
        "letterhistory": "public.etcs_module('letters') AND EXISTS (SELECT 1 FROM public.coordination_letter l WHERE l.id=letter_id)",
    }
    with schema_editor.connection.cursor() as cursor:
        for table, policy, action, condition in policies:
            name = f"public.coordination_{table}"
            cursor.execute(f"DROP POLICY IF EXISTS {policy} ON {name}")
            if enabled or table in originals:
                condition = condition if enabled else originals[table]
                cursor.execute(
                    f"CREATE POLICY {policy} ON {name} FOR {action} USING ({condition})"
                )


def install(apps, schema_editor):
    change_policies(apps, schema_editor, True)


def uninstall(apps, schema_editor):
    change_policies(apps, schema_editor, False)


class Migration(migrations.Migration):
    dependencies = [("coordination", "0020_audit_audit_action_record_date_and_more")]
    operations = [migrations.RunPython(install, uninstall)]
