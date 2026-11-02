from django.db import migrations


def install(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "ALTER TABLE public.coordination_notification ENABLE ROW LEVEL SECURITY"
        )
        cursor.execute(
            "ALTER TABLE public.coordination_notification FORCE ROW LEVEL SECURITY"
        )
        cursor.execute(
            "CREATE POLICY etcs_read ON public.coordination_notification FOR SELECT USING (user_id=public.etcs_user_id())"
        )
        # A scoped server action can enqueue another recipient's notification;
        # maintenance workers deliver it with a separate credential.
        cursor.execute(
            "CREATE POLICY etcs_insert ON public.coordination_notification FOR INSERT WITH CHECK (public.etcs_user_id() IS NOT NULL)"
        )
        cursor.execute(
            "CREATE POLICY etcs_update ON public.coordination_notification FOR UPDATE USING (user_id=public.etcs_user_id()) WITH CHECK (user_id=public.etcs_user_id())"
        )
        cursor.execute(
            "CREATE POLICY etcs_delete ON public.coordination_notification FOR DELETE USING (user_id=public.etcs_user_id())"
        )
        cursor.execute(
            "ALTER TABLE public.coordination_emaildelivery ENABLE ROW LEVEL SECURITY"
        )
        cursor.execute(
            "ALTER TABLE public.coordination_emaildelivery FORCE ROW LEVEL SECURITY"
        )
        cursor.execute(
            "CREATE POLICY etcs_insert ON public.coordination_emaildelivery FOR INSERT WITH CHECK (public.etcs_user_id() IS NOT NULL)"
        )
        cursor.execute(
            "CREATE POLICY etcs_read ON public.coordination_emaildelivery FOR SELECT USING (EXISTS(SELECT 1 FROM public.coordination_notification n WHERE n.id=notification_id))"
        )


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table, policies in [
            (
                "coordination_notification",
                ["etcs_read", "etcs_insert", "etcs_update", "etcs_delete"],
            ),
            ("coordination_emaildelivery", ["etcs_insert", "etcs_read"]),
        ]:
            for policy in policies:
                cursor.execute(f"DROP POLICY {policy} ON public.{table}")
            cursor.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY")


class Migration(migrations.Migration):
    dependencies = [("coordination", "0008_emaildelivery")]
    operations = [migrations.RunPython(install, uninstall)]
