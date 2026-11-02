from django.db import migrations


def install(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP POLICY etcs_read ON public.coordination_notification")
        cursor.execute(
            "CREATE POLICY etcs_read ON public.coordination_notification FOR SELECT USING (user_id=public.etcs_user_id() OR sender_id=public.etcs_user_id())"
        )


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP POLICY etcs_read ON public.coordination_notification")
        cursor.execute(
            "CREATE POLICY etcs_read ON public.coordination_notification FOR SELECT USING (user_id=public.etcs_user_id())"
        )


class Migration(migrations.Migration):
    dependencies = [("coordination", "0011_notification_sender")]
    operations = [migrations.RunPython(install, uninstall)]
