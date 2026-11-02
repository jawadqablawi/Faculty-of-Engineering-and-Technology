from django.db import migrations

SQL = r"""
CREATE OR REPLACE FUNCTION public.etcs_authenticated() RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
 SELECT EXISTS(SELECT 1 FROM public.auth_user u JOIN public.coordination_profile p ON p.user_id=u.id WHERE u.id=public.etcs_user_id() AND u.is_active AND p.verified AND (p.role<>'club' OR EXISTS(SELECT 1 FROM public.coordination_club c WHERE c.id=p.club_id AND c.active)))
$$;
ALTER TABLE public.coordination_calendarentry ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.coordination_calendarentry FORCE ROW LEVEL SECURITY;
CREATE POLICY etcs_read ON public.coordination_calendarentry FOR SELECT USING (public.etcs_authenticated());
CREATE POLICY etcs_insert ON public.coordination_calendarentry FOR INSERT WITH CHECK (public.etcs_module('requests') AND EXISTS(SELECT 1 FROM public.coordination_activity a WHERE a.id=activity_id AND a.status='approved' AND public.etcs_club_write(a.club_id,'requests')));
CREATE POLICY etcs_update ON public.coordination_calendarentry FOR UPDATE USING (public.etcs_module('requests') AND EXISTS(SELECT 1 FROM public.coordination_activity a WHERE a.id=activity_id AND public.etcs_club_write(a.club_id,'requests'))) WITH CHECK (public.etcs_module('requests') AND EXISTS(SELECT 1 FROM public.coordination_activity a WHERE a.id=activity_id AND a.status='approved' AND public.etcs_club_write(a.club_id,'requests')));
CREATE POLICY etcs_delete ON public.coordination_calendarentry FOR DELETE USING (public.etcs_module('requests') AND EXISTS(SELECT 1 FROM public.coordination_activity a WHERE a.id=activity_id AND public.etcs_club_write(a.club_id,'requests')));
ALTER TABLE public.coordination_storeddocument ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.coordination_storeddocument FORCE ROW LEVEL SECURITY;
CREATE POLICY etcs_insert ON public.coordination_storeddocument FOR INSERT WITH CHECK (public.etcs_authenticated() AND uploader_id=public.etcs_user_id());
CREATE POLICY etcs_read ON public.coordination_storeddocument FOR SELECT USING (public.etcs_authenticated() AND (uploader_id=public.etcs_user_id() OR EXISTS(SELECT 1 FROM public.coordination_attachment a WHERE a.file=coordination_storeddocument.name AND NOT a.deleted) OR EXISTS(SELECT 1 FROM public.coordination_casedocument c WHERE c.file=coordination_storeddocument.name) OR EXISTS(SELECT 1 FROM public.coordination_club c WHERE c.logo=coordination_storeddocument.name AND public.etcs_club_write(c.id,'operations'))));
CREATE POLICY etcs_delete ON public.coordination_storeddocument FOR DELETE USING (public.etcs_authenticated() AND (uploader_id=public.etcs_user_id() OR EXISTS(SELECT 1 FROM public.coordination_casedocument c WHERE c.file=coordination_storeddocument.name) OR public.etcs_module('operations')));
CREATE POLICY etcs_delivery_update ON public.coordination_emaildelivery FOR UPDATE USING (public.etcs_module('operations')) WITH CHECK (public.etcs_module('operations'));
DROP VIEW public.etcs_calendar_public;
CREATE VIEW public.etcs_calendar_public WITH (security_barrier=true) AS SELECT uid,title,date,start,"end",club_name,kind FROM public.coordination_calendarentry;
CREATE OR REPLACE FUNCTION public.etcs_conflict(aid uuid,day date,beginning time,ending time,place text) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
 SELECT EXISTS(SELECT 1 FROM public.coordination_calendarentry c WHERE c.activity_id<>aid AND c.kind='event' AND c.date=day AND c.start<ending AND c."end">beginning AND c.venue_key=place)
$$;
"""


def install(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(SQL)


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP VIEW public.etcs_calendar_public")
        cursor.execute(
            "CREATE VIEW public.etcs_calendar_public WITH (security_barrier=true) AS SELECT a.id::text AS uid,a.title,a.date,a.start,a.\"end\",c.name AS club_name,a.kind FROM public.coordination_activity a JOIN public.coordination_club c ON c.id=a.club_id WHERE a.status='approved'"
        )
        cursor.execute(
            "DROP POLICY etcs_delivery_update ON public.coordination_emaildelivery"
        )
        for table, names in [
            (
                "coordination_calendarentry",
                ["etcs_read", "etcs_insert", "etcs_update", "etcs_delete"],
            ),
            (
                "coordination_storeddocument",
                ["etcs_read", "etcs_insert", "etcs_delete"],
            ),
        ]:
            for name in names:
                cursor.execute(f"DROP POLICY {name} ON public.{table}")
            cursor.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY")
        cursor.execute("DROP FUNCTION public.etcs_authenticated()")


class Migration(migrations.Migration):
    dependencies = [("coordination", "0013_calendarentry_storeddocument")]
    operations = [migrations.RunPython(install, uninstall)]
