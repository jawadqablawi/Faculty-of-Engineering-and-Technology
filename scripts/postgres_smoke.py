"""Isolated PostgreSQL RLS validation. Requires ETCS_TEST_DATABASE_URL with CREATEDB/CREATEROLE privileges."""

import os
from pathlib import Path
import secrets
import subprocess
import sys
from urllib.parse import urlparse, urlunparse, quote
import uuid
import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def web_checks():
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()
    from django.test import Client
    from django.db import connection, transaction
    from coordination.models import Activity, User, ApprovalRequirement
    from coordination.access import activities

    admin = User.objects.get(email="rls-coordinator@example.test")
    club = User.objects.get(email="rls-computer@example.test")
    other = User.objects.get(email="rls-civil@example.test")
    own_id = os.environ["ETCS_SMOKE_ACTIVITY"]
    # Without request identity no private activity is visible.
    assert Activity.objects.count() == 0
    with transaction.atomic():
        with connection.cursor() as c:
            c.execute("SELECT set_config('etcs.user_id',%s,true)", [str(other.pk)])
        assert not Activity.objects.filter(pk=own_id).exists()
        assert Activity.objects.count() == 0
    assert Activity.objects.count() == 0, "Identity leaked across transactions"
    client = Client()
    client.force_login(other)
    assert client.get(f"/requests/{own_id}/").status_code == 404
    response = client.get("/calendar/")
    assert response.status_code == 200
    import re, json

    public = json.loads(
        re.search(
            r'<script id="events" type="application/json">(.*?)</script>',
            response.content.decode(),
            re.S,
        ).group(1)
    )
    assert any(event["title"] == "Public approved calendar event" for event in public)
    assert "RLS-PRIVATE-DESCRIPTION" not in response.content.decode()
    client.force_login(club)
    assert client.get(f"/requests/{own_id}/").status_code == 200
    from django.core.files.uploadedfile import SimpleUploadedFile

    assert (
        client.post(
            f"/requests/{own_id}/upload/",
            {"file": SimpleUploadedFile("private.pdf", b"%PDF-1.4\n")},
        ).status_code
        == 302
    )
    response = client.post(f"/requests/{own_id}/action/", {"action": "submit"})
    assert response.status_code == 302
    client.force_login(admin)
    assert client.get("/").status_code == 200
    assert (
        client.post(
            f"/requests/{own_id}/action/", {"action": "preliminary"}
        ).status_code
        == 302
    )
    with transaction.atomic():
        with connection.cursor() as c:
            c.execute("SELECT set_config('etcs.user_id',%s,true)", [str(admin.pk)])
        assert Activity.objects.get(pk=own_id).status == "preliminary"
        assert ApprovalRequirement.objects.filter(activity_id=own_id).count() == 2
    assert (
        client.post(
            f"/requests/{own_id}/letter/",
            {
                "subject": "Test letter",
                "recipient": "Council",
                "body": "Synthetic approval request",
                "status": "مسودة",
            },
        ).status_code
        == 302
    )
    for action in ["forward", "council_ok", "university_ok"]:
        assert (
            client.post(
                f"/requests/{own_id}/action/",
                {"action": action, "note": "Synthetic recorded evidence"},
            ).status_code
            == 302
        )
    with transaction.atomic():
        with connection.cursor() as c:
            c.execute("SELECT set_config('etcs.user_id',%s,true)", [str(admin.pk)])
        assert Activity.objects.get(pk=own_id).status == "approved"
        from coordination.models import Attachment, Invitation

        attachment = Attachment.objects.get(activity_id=own_id)
        invitation = Invitation.objects.create(
            email="rls-invite@example.test",
            role="club",
            club=club.profile.club,
            expires=__import__("django").utils.timezone.now()
            + __import__("datetime").timedelta(days=1),
        )
    client.force_login(other)
    assert client.get(f"/files/{attachment.pk}/").status_code == 404
    client.logout()
    assert (
        client.post(
            f"/accept/{invitation.token}/",
            {
                "new_password1": "Synthetic-pass-7b2377!",
                "new_password2": "Synthetic-pass-7b2377!",
            },
        ).status_code
        == 302
    )
    print(
        "PASS: PostgreSQL row isolation, anonymous default deny, transaction identity reset, calendar safe projection, HTTP cross-club denial, club submission and coordinator review under restricted web role"
    )


if "--web" in sys.argv:
    web_checks()
    sys.exit()

admin_url = os.environ.get("ETCS_TEST_DATABASE_URL")
if not admin_url:
    raise SystemExit(
        "Set ETCS_TEST_DATABASE_URL to a dedicated test PostgreSQL server (not production)."
    )
name = "etcs_test_" + uuid.uuid4().hex[:12]
role = name + "_web"
password = secrets.token_urlsafe(32)
parsed = urlparse(admin_url)
maintenance_url = urlunparse(parsed._replace(path="/" + name))
netloc = quote(role) + ":" + quote(password) + "@" + parsed.netloc.split("@")[-1]
web_url = urlunparse(parsed._replace(netloc=netloc, path="/" + name))
with psycopg.connect(admin_url, autocommit=True) as admin_connection:
    admin_connection.execute(
        sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
            sql.Identifier(role), sql.Literal(password)
        )
    )
    admin_connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        env = os.environ.copy()
        env.update(DATABASE_URL=maintenance_url, ETCS_DEBUG="1", ETCS_RLS="0")

        def run(*args, **kwargs):
            return subprocess.run(
                [sys.executable, *args],
                cwd=ROOT,
                env=kwargs.get("env", env),
                check=True,
            )

        run("manage.py", "migrate", "--noinput")
        run("manage.py", "bootstrap")
        run("manage.py", "grant_web_role", role)
        fixture = """
from coordination.models import *
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta,time
from pathlib import Path
for email,role,club in [('rls-coordinator@example.test','coordinator',None),('rls-computer@example.test','club',Club.objects.get(name='نادي هندسة الحاسوب')),('rls-civil@example.test','club',Club.objects.get(name='نادي البناء والمدني والمعماري'))]:
 u=User.objects.create_user(email,email=email);Profile.objects.create(user=u,role=role,club=club,verified=True)
u=User.objects.get(email='rls-computer@example.test')
a=Activity.objects.create(club=u.profile.club,creator=u,kind='event',title='اختبار PostgreSQL',description='بيانات اصطناعية',objectives='التحقق',organizer='فريق اختبار',contact='test@example.test',date=timezone.localdate()+timedelta(days=20),start=time(10),end=time(12),participants=10,venue='قاعة اختبار')
Activity.objects.create(club=u.profile.club,creator=u,kind='event',title='Public approved calendar event',description='RLS-PRIVATE-DESCRIPTION',status='approved',date=timezone.localdate()+timedelta(days=20),start=time(8),end=time(9),venue='Other venue')
Path(__import__('os').environ['ETCS_SMOKE_ID_FILE']).write_text(str(a.pk))
"""
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            env["ETCS_SMOKE_ID_FILE"] = temporary + "/activity"
            env["ETCS_PRIVATE_MEDIA"] = temporary + "/media"
            run("manage.py", "shell", "-c", fixture)
            web_env = env.copy()
            web_env.update(
                DATABASE_URL=web_url,
                ETCS_RLS="1",
                ETCS_SMOKE_ACTIVITY=Path(env["ETCS_SMOKE_ID_FILE"]).read_text(),
            )
            run("scripts/postgres_smoke.py", "--web", env=web_env)
        with psycopg.connect(web_url) as connection:
            with connection.transaction():
                try:
                    connection.execute("DELETE FROM public.coordination_audit")
                except psycopg.errors.InsufficientPrivilege:
                    pass
                else:
                    raise AssertionError("Web role may delete audit history")
        print("PASS: restricted web role cannot delete audit history")
    finally:
        admin_connection.execute(
            sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
        )
        admin_connection.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
