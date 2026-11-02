from django.db import migrations

FUNCTIONS = r"""
CREATE OR REPLACE FUNCTION public.etcs_user_id() RETURNS bigint LANGUAGE sql STABLE AS $$
 SELECT NULLIF(current_setting('etcs.user_id',true),'')::bigint
$$;
CREATE OR REPLACE FUNCTION public.etcs_module(mod text) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
 SELECT EXISTS(SELECT 1 FROM public.coordination_profile p JOIN public.auth_user u ON u.id=p.user_id WHERE u.id=public.etcs_user_id() AND u.is_active AND p.verified AND (p.role='coordinator' OR p.role='deputy' AND p.modules ? mod))
$$;
CREATE OR REPLACE FUNCTION public.etcs_club_write(cid bigint,mod text) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
 SELECT EXISTS(SELECT 1 FROM public.coordination_profile p JOIN public.auth_user u ON u.id=p.user_id WHERE u.id=public.etcs_user_id() AND u.is_active AND p.verified AND
 (p.role='coordinator' OR p.role='deputy' AND p.modules ? mod AND EXISTS(SELECT 1 FROM public.coordination_profile_clubs pc WHERE pc.profile_id=p.id AND pc.club_id=cid) OR p.role='club' AND mod IN ('requests','plans') AND p.club_id=cid AND EXISTS(SELECT 1 FROM public.coordination_club c WHERE c.id=cid AND c.active)))
$$;
CREATE OR REPLACE FUNCTION public.etcs_activity_read(cid bigint,aid uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
 SELECT EXISTS(SELECT 1 FROM public.coordination_profile p JOIN public.auth_user u ON u.id=p.user_id WHERE u.id=public.etcs_user_id() AND u.is_active AND p.verified AND
 (p.role='coordinator' OR p.role='club' AND p.club_id=cid AND EXISTS(SELECT 1 FROM public.coordination_club c WHERE c.id=cid AND c.active) OR p.role IN ('deputy','reviewer') AND (p.modules ? 'requests' OR p.role='deputy' AND (p.modules ? 'reports' OR p.modules ? 'letters')) AND EXISTS(SELECT 1 FROM public.coordination_profile_clubs pc WHERE pc.profile_id=p.id AND pc.club_id=cid) OR p.role='auditor' AND p.modules ? 'reports' AND EXISTS(SELECT 1 FROM public.coordination_profile_authorized_activities pa WHERE pa.profile_id=p.id AND pa.activity_id=aid)))
$$;
CREATE OR REPLACE FUNCTION public.etcs_conflict(aid uuid,day date,beginning time,ending time,place text) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
 SELECT EXISTS(SELECT 1 FROM public.coordination_activity a WHERE a.id<>aid AND a.status='approved' AND a.kind='event' AND a.date=day AND a.start<ending AND a."end">beginning AND a.venue=place) OR EXISTS(SELECT 1 FROM public.coordination_eventdate d JOIN public.coordination_activity a ON a.id=d.activity_id WHERE a.id<>aid AND a.status='approved' AND d.date=day AND d.start<ending AND d."end">beginning AND d.venue=place)
$$;
CREATE OR REPLACE VIEW public.etcs_calendar_public WITH (security_barrier=true) AS
 SELECT a.id::text AS uid,a.title,a.date,a.start,a."end",c.name AS club_name,a.kind FROM public.coordination_activity a JOIN public.coordination_club c ON c.id=a.club_id WHERE a.status='approved' AND (a.kind='event' OR NOT EXISTS(SELECT 1 FROM public.coordination_workshopsession s WHERE s.activity_id=a.id))
 UNION ALL
 SELECT 'day-'||d.id::text,a.title,d.date,d.start,d."end",c.name,a.kind FROM public.coordination_eventdate d JOIN public.coordination_activity a ON a.id=d.activity_id JOIN public.coordination_club c ON c.id=a.club_id WHERE a.status='approved'
 UNION ALL
 SELECT 'session-'||s.id::text,s.title,s.date,s.start,s."end",c.name,a.kind FROM public.coordination_workshopsession s JOIN public.coordination_activity a ON a.id=s.activity_id JOIN public.coordination_club c ON c.id=a.club_id WHERE a.status='approved';
"""

ACTIVITY_CHILDREN = [
    "history",
    "attachment",
    "report",
    "eventdate",
    "workshopsession",
    "activitycomment",
    "publication",
]


def install(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as c:
        c.execute(FUNCTIONS)

        def policy(table, read, write):
            name = "coordination_" + table
            c.execute(f"ALTER TABLE public.{name} ENABLE ROW LEVEL SECURITY")
            c.execute(f"ALTER TABLE public.{name} FORCE ROW LEVEL SECURITY")
            c.execute(
                f"CREATE POLICY etcs_read ON public.{name} FOR SELECT USING ({read})"
            )
            c.execute(
                f"CREATE POLICY etcs_insert ON public.{name} FOR INSERT WITH CHECK ({write})"
            )
            c.execute(
                f"CREATE POLICY etcs_update ON public.{name} FOR UPDATE USING ({write}) WITH CHECK ({write})"
            )
            c.execute(
                f"CREATE POLICY etcs_delete ON public.{name} FOR DELETE USING ({write})"
            )

        policy(
            "activity",
            "public.etcs_activity_read(club_id,id)",
            "public.etcs_club_write(club_id,'requests')",
        )
        for table in ACTIVITY_CHILDREN:
            read = f"EXISTS(SELECT 1 FROM public.coordination_activity a WHERE a.id=activity_id)"
            write = f"EXISTS(SELECT 1 FROM public.coordination_activity a WHERE a.id=activity_id AND public.etcs_club_write(a.club_id,'requests'))"
            policy(table, read, write)
        for table in ["letter", "approvalrequirement"]:
            module = "letters" if table == "letter" else "requests"
            expression = f"public.etcs_module('{module}') AND EXISTS(SELECT 1 FROM public.coordination_activity a WHERE a.id=activity_id)"
            policy(
                table,
                "EXISTS(SELECT 1 FROM public.coordination_activity a WHERE a.id=activity_id)"
                if table == "approvalrequirement"
                else expression,
                expression,
            )
        policy(
            "letterhistory",
            "EXISTS(SELECT 1 FROM public.coordination_letter l WHERE l.id=letter_id)",
            "public.etcs_module('letters') AND EXISTS(SELECT 1 FROM public.coordination_letter l WHERE l.id=letter_id)",
        )
        for table in ["idea", "clubplan"]:
            mod = "requests" if table == "idea" else "plans"
            expression = f"public.etcs_club_write(club_id,'{mod}') OR public.etcs_club_write(club_id,'operations')"
            policy(table, expression, expression)
        case = "public.etcs_module('cases') AND (assigned_id=public.etcs_user_id() OR EXISTS(SELECT 1 FROM public.coordination_profile p WHERE p.user_id=public.etcs_user_id() AND p.role='coordinator'))"
        policy("case", case, case)
        policy(
            "casedocument",
            "EXISTS(SELECT 1 FROM public.coordination_case c WHERE c.id=case_id)",
            "EXISTS(SELECT 1 FROM public.coordination_case c WHERE c.id=case_id)",
        )
        task = "assigned_id=public.etcs_user_id() OR EXISTS(SELECT 1 FROM public.coordination_profile p WHERE p.user_id=public.etcs_user_id() AND p.role='coordinator')"
        policy("task", task, task)
        meeting = "creator_id=public.etcs_user_id() OR public.etcs_club_write(club_id,'operations') OR EXISTS(SELECT 1 FROM public.coordination_profile p WHERE p.user_id=public.etcs_user_id() AND p.role='coordinator') OR EXISTS(SELECT 1 FROM public.coordination_meeting_participants mp WHERE mp.meeting_id=coordination_meeting.id AND mp.user_id=public.etcs_user_id())"
        policy("meeting", meeting, meeting)
        # Audit rows are append-only to the restricted role. Read scope never crosses clubs.
        audit_read = "actor_id=public.etcs_user_id() OR EXISTS(SELECT 1 FROM public.coordination_profile p WHERE p.user_id=public.etcs_user_id() AND p.role='coordinator')"
        policy("audit", audit_read, "public.etcs_user_id() IS NOT NULL")


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    tables = ACTIVITY_CHILDREN + [
        "activity",
        "letter",
        "approvalrequirement",
        "letterhistory",
        "idea",
        "clubplan",
        "case",
        "casedocument",
        "task",
        "meeting",
        "audit",
    ]
    with schema_editor.connection.cursor() as c:
        c.execute("DROP VIEW IF EXISTS public.etcs_calendar_public")
        for table in tables:
            for policy in ["etcs_read", "etcs_insert", "etcs_update", "etcs_delete"]:
                c.execute(
                    f"DROP POLICY IF EXISTS {policy} ON public.coordination_{table}"
                )
            c.execute(
                f"ALTER TABLE public.coordination_{table} DISABLE ROW LEVEL SECURITY"
            )
        for function in [
            "etcs_conflict(uuid,date,time,time,text)",
            "etcs_activity_read(bigint,uuid)",
            "etcs_club_write(bigint,text)",
            "etcs_module(text)",
            "etcs_user_id()",
        ]:
            c.execute(f"DROP FUNCTION IF EXISTS public.{function}")


class Migration(migrations.Migration):
    dependencies = [("coordination", "0005_numbersequence")]
    operations = [migrations.RunPython(install, uninstall)]
