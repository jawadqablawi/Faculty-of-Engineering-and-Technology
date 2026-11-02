"""Create a local production .env without printing secrets or replacing existing files."""

import argparse
from pathlib import Path
import re
import secrets

parser = argparse.ArgumentParser()
parser.add_argument(
    "--domain", required=True, help="Public DNS hostname, without scheme or path"
)
args = parser.parse_args()
if not re.fullmatch(
    r"(?=.{1,253}$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}",
    args.domain,
):
    parser.error("Enter a valid public DNS hostname")
path = Path(__file__).resolve().parent.parent / ".env"
values = {
    "ETCS_DOMAIN": args.domain,
    "ETCS_DEBUG": "0",
    "ETCS_SECRET_KEY": secrets.token_urlsafe(64),
    "ETCS_DB_PASSWORD": secrets.token_hex(32),
    "ETCS_WEB_DB_PASSWORD": secrets.token_hex(32),
    "ETCS_ALLOWED_HOSTS": args.domain + ",localhost,127.0.0.1",
    "ETCS_TRUSTED_ORIGINS": "https://" + args.domain,
    "ETCS_PRIVATE_MEDIA": "/data/private_media",
    "ETCS_EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
    "ETCS_EMAIL_HOST": "",
    "ETCS_EMAIL_PORT": "587",
    "ETCS_EMAIL_USER": "",
    "ETCS_EMAIL_PASSWORD": "",
    "ETCS_FROM_EMAIL": "",
    "ETCS_EMAIL_NOTIFICATIONS": "0",
}
try:
    with open(
        path, "x", opener=lambda p, flags: __import__("os").open(p, flags, 0o600)
    ) as f:
        for key, value in values.items():
            f.write(key + "=" + value + "\n")
except FileExistsError:
    raise SystemExit(
        "Existing .env preserved. Edit it securely rather than regenerating credentials."
    )
print(
    "Created private .env. Configure SMTP securely, then follow docs/DEPLOYMENT.md. No secret values printed."
)
