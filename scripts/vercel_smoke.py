"""Test Vercel mode with a non-superuser database OWNER, as on managed PostgreSQL.

Creates/removes only a temporary database and role on ETCS_TEST_DATABASE_URL.
No external service credentials are printed or modified.
"""

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


def checks():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.test import Client
    from django.utils import timezone
    from django.db import connection, transaction
    from django.core.files.uploadedfile import SimpleUploadedFile
    from coordination.models import (
        User,
        Profile,
        Club,
        Activity,
        Attachment,
        StoredDocument,
        Letter,
        Task,
    )

    admin = User.objects.get(email="vercel-owner@example.test")
    clubs = list(Club.objects.order_by("pk")[:2])
    users = []
    for i, club in enumerate(clubs):
        user = User.objects.create_user(
            f"vercel-club-{i}@example.test", email=f"vercel-club-{i}@example.test"
        )
        Profile.objects.create(user=user, role="club", club=club, verified=True)
        users.append(user)
    client = Client(HTTP_X_FORWARDED_PROTO="https")
    client.force_login(users[0])
    page = client.get("/new/event/")
    assert page.status_code == 200
    from datetime import timedelta

    data = {
        "title": "Vercel persistent request",
        "description": "وصف خاص لا يظهر للنادي الآخر",
        "objectives": "الاختبار",
        "organizer": "منظم",
        "contact": "synthetic@example.test",
        "participants": "12",
        "date": str(timezone.localdate() + timedelta(days=5)),
        "start": "10:00",
        "end": "12:00",
        "venue": "قاعة مشتركة",
        "draft_token": page.context_data["draft_token"]
        if hasattr(page, "context_data")
        else "",
    }
    for prefix in ["req", "program", "speakers", "partners", "extra_dates"]:
        data.update({prefix + "-TOTAL_FORMS": "0", prefix + "-INITIAL_FORMS": "0"})
    response = client.post("/new/event/", data)
    assert response.status_code == 302
    activity_id = response.url.strip("/").split("/")[1]
    client.post(
        f"/requests/{activity_id}/upload/",
        {
            "file": SimpleUploadedFile(
                "persistent.pdf", b"%PDF-1.4\nStored safely in Postgres"
            )
        },
    )
    with transaction.atomic():
        with connection.cursor() as c:
            c.execute("SELECT set_config('etcs.user_id',%s,true)", [str(users[0].pk)])
        attachment = Attachment.objects.get(activity_id=activity_id)
        assert bytes(
            StoredDocument.objects.get(name=attachment.file.name).data
        ).startswith(b"%PDF")
    assert client.get(f"/files/{attachment.pk}/").status_code == 200
    client.force_login(users[1])
    assert client.get(f"/files/{attachment.pk}/").status_code == 404
    with transaction.atomic():
        with connection.cursor() as c:
            c.execute("SELECT set_config('etcs.user_id',%s,true)", [str(users[1].pk)])
        assert StoredDocument.objects.count() == 0
        assert Activity.objects.count() == 0
    client.force_login(users[0])
    client.post(f"/requests/{activity_id}/action/", {"action": "submit"})
    client.force_login(admin)
    client.post(f"/requests/{activity_id}/action/", {"action": "preliminary"})
    client.post(
        f"/requests/{activity_id}/letter/",
        {
            "subject": "كتاب عربي من Vercel",
            "body": "نص فعلي عربي",
            "recipient": "المجلس",
            "status": "مسودة",
        },
    )
    for action in ["forward", "council_ok", "university_ok"]:
        client.post(
            f"/requests/{activity_id}/action/",
            {"action": action, "note": "Synthetic recorded decision"},
        )
    with transaction.atomic():
        with connection.cursor() as c:
            c.execute("SELECT set_config('etcs.user_id',%s,true)", [str(admin.pk)])
        assert Activity.objects.get(pk=activity_id).status == "approved"
        letter = Letter.objects.get(activity_id=activity_id)
        Task.objects.create(
            title="Vercel due reminder",
            assigned=users[0],
            club=clubs[0],
            due=timezone.localdate(),
        )
    assert client.get(f"/letters/{letter.pk}/?pdf=1").content.startswith(b"%PDF")
    assert client.get("/reports/?export=pdf").content.startswith(b"%PDF")
    client.force_login(users[1])
    calendar = client.get("/calendar/").content.decode()
    assert "Vercel persistent request" in calendar
    assert "وصف خاص" not in calendar
    client.logout()
    assert client.get("/cron/reminders/").status_code == 401
    assert (
        client.get(
            "/cron/reminders/", HTTP_AUTHORIZATION="Bearer " + os.environ["CRON_SECRET"]
        ).status_code
        == 200
    )
    print(
        "PASS: Vercel mode with a non-superuser database owner; private database files; cross-club denial; full approval; Arabic PDFs; safe cross-club calendar; authenticated scheduled job"
    )


if "--check" in sys.argv:
    checks()
    sys.exit()
url = os.environ.get("ETCS_TEST_DATABASE_URL")
if not url:
    raise SystemExit(
        "Use a dedicated local test PostgreSQL server via ETCS_TEST_DATABASE_URL"
    )
parsed = urlparse(url)
name = "etcs_vercel_" + uuid.uuid4().hex[:10]
role = name + "_owner"
password = secrets.token_urlsafe(32)
netloc = quote(role) + ":" + quote(password) + "@" + parsed.netloc.split("@")[-1]
target = urlunparse(parsed._replace(netloc=netloc, path="/" + name))
with psycopg.connect(url, autocommit=True) as admin:
    admin.execute(
        sql.SQL("CREATE ROLE {} LOGIN CREATEROLE PASSWORD {}").format(
            sql.Identifier(role), sql.Literal(password)
        )
    )
    admin.execute(
        sql.SQL("CREATE DATABASE {} OWNER {}").format(
            sql.Identifier(name), sql.Identifier(role)
        )
    )
    try:
        env = os.environ.copy()
        env.update(
            DATABASE_URL=target,
            VERCEL="1",
            VERCEL_ENV="production",
            VERCEL_PROJECT_PRODUCTION_URL="etcs-test.vercel.app",
            ETCS_ALLOWED_HOSTS="etcs-test.vercel.app,testserver",
            ETCS_DEBUG="0",
            ETCS_SECRET_KEY=secrets.token_urlsafe(64),
            ETCS_RLS="1",
            ETCS_OWNER_EMAIL="vercel-owner@example.test",
            ETCS_OWNER_PASSWORD=secrets.token_urlsafe(24),
            CRON_SECRET=secrets.token_urlsafe(32),
            ETCS_EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
            ETCS_EMAIL_NOTIFICATIONS="1",
        )
        env["ETCS_RUNTIME_ROLE"] = name + "_runtime"
        build_env = env.copy()
        build_env["ETCS_DEPLOY_PREPARE"] = "1"
        subprocess.run(
            [sys.executable, "manage.py", "vercel_prepare"],
            cwd=ROOT,
            env=build_env,
            check=True,
        )
        subprocess.run(
            [sys.executable, "manage.py", "collectstatic", "--noinput"],
            cwd=ROOT,
            env=env,
            check=True,
        )
        subprocess.run(
            [sys.executable, "scripts/vercel_smoke.py", "--check"],
            cwd=ROOT,
            env=env,
            check=True,
        )
    finally:
        admin.execute(
            sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
        )
        admin.execute(
            sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(name + "_runtime"))
        )
        admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
