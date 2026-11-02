from django.db import migrations


def install(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "CREATE OR REPLACE FUNCTION public.etcs_coordinator() RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$ SELECT EXISTS(SELECT 1 FROM public.auth_user u JOIN public.coordination_profile p ON p.user_id=u.id WHERE u.id=public.etcs_user_id() AND u.is_active AND p.verified AND p.role='coordinator') $$"
        )
        cursor.execute("DROP POLICY etcs_read ON public.coordination_notification")
        cursor.execute(
            "CREATE POLICY etcs_read ON public.coordination_notification FOR SELECT USING (user_id=public.etcs_user_id() OR sender_id=public.etcs_user_id() OR public.etcs_coordinator())"
        )


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP POLICY etcs_read ON public.coordination_notification")
        cursor.execute(
            "CREATE POLICY etcs_read ON public.coordination_notification FOR SELECT USING (user_id=public.etcs_user_id() OR sender_id=public.etcs_user_id())"
        )
        cursor.execute("DROP FUNCTION public.etcs_coordinator()")


class Migration(migrations.Migration):
    dependencies = [("coordination", "0014_serverless_storage_and_calendar_rls")]
    operations = [migrations.RunPython(install, uninstall)]
