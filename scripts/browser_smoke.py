"""Run real-browser checks against an isolated temporary database (never user data)."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request

root = Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix="etcs-smoke-") as scratch:
    env = os.environ.copy()
    env.update(
        ETCS_DEBUG="1",
        ETCS_DB=scratch + "/db.sqlite3",
        ETCS_SMOKE_SESSION=scratch + "/session",
        ETCS_SMOKE_BASE_URL="http://127.0.0.1:8017",
        ETCS_SMOKE_ARTIFACTS=os.environ.get(
            "ETCS_SMOKE_ARTIFACTS", "/tmp/etcs-browser-artifacts"
        ),
    )
    Path(env["ETCS_SMOKE_ARTIFACTS"]).mkdir(parents=True, exist_ok=True)

    def manage(*args):
        subprocess.run(
            [sys.executable, "manage.py", *args], cwd=root, env=env, check=True
        )

    manage("migrate", "--noinput")
    manage(
        "shell",
        "-c",
        """
from datetime import time
from pathlib import Path
import os
from coordination.models import Activity, Club, Notification, Profile
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client
from django.utils import timezone

call_command("bootstrap")
club = Club.objects.get(name="نادي هندسة الحاسوب")
other = Club.objects.exclude(pk=club.pk).first()
member = User.objects.create_user("browser@example.test", email="browser@example.test")
Profile.objects.create(user=member, role="club", club=club, verified=True)
for event_club, title in [(club, "فعالية معتمدة للاختبار"), (other, "حجز متزامن للاختبار")]:
    Activity.objects.create(
        club=event_club, creator=member, title=title, kind="event", status="approved",
        venue="قاعة اختبار", date=timezone.localdate(), start=time(10), end=time(12),
    )
Notification.objects.create(user=member, text="إشعار اختباري أول")
Notification.objects.create(user=member, text="إشعار اختباري ثانٍ")
client = Client()
client.force_login(member)
Path(os.environ["ETCS_SMOKE_SESSION"]).write_text(client.cookies["sessionid"].value)
""",
    )
    with open(scratch + "/server.log", "w+") as log:
        process = subprocess.Popen(
            [sys.executable, "manage.py", "runserver", "127.0.0.1:8017", "--noreload"],
            cwd=root,
            env=env,
            stdout=log,
            stderr=log,
        )
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError("Smoke server failed to start")
                try:
                    opener.open(
                        env["ETCS_SMOKE_BASE_URL"] + "/login/", timeout=1
                    ).close()
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("Smoke server did not become ready")
            subprocess.run(
                ["node", "scripts/browser_smoke.cjs"], cwd=root, env=env, check=True
            )
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
