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
        "from coordination.models import Club,Profile; from django.contrib.auth.models import User; from django.test import Client; from pathlib import Path; from django.core.management import call_command; import os; call_command('bootstrap'); u=User.objects.create_user('browser@example.test',email='browser@example.test'); Profile.objects.create(user=u,role='club',club=Club.objects.get(name='نادي هندسة الحاسوب'),verified=True); c=Client(); c.force_login(u); Path(os.environ['ETCS_SMOKE_SESSION']).write_text(c.cookies['sessionid'].value)",
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
