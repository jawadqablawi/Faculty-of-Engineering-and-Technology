import os
from urllib.parse import urlparse, parse_qs
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get("ETCS_SECRET_KEY")
DEBUG = os.environ.get("ETCS_DEBUG", "0") == "1"
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError(
            "Set ETCS_SECRET_KEY; use ETCS_DEBUG=1 only for local development"
        )
    SECRET_KEY = "local-development-only-do-not-deploy"
if os.environ.get("VERCEL") == "1":
    platform_hosts = [
        os.environ.get(key, "").strip()
        for key in ["VERCEL_PROJECT_PRODUCTION_URL", "VERCEL_URL"]
        if os.environ.get(key, "").strip()
    ]
    if not os.environ.get("ETCS_ALLOWED_HOSTS") and platform_hosts:
        os.environ["ETCS_ALLOWED_HOSTS"] = ",".join(platform_hosts)
    if not os.environ.get("ETCS_TRUSTED_ORIGINS") and platform_hosts:
        os.environ["ETCS_TRUSTED_ORIGINS"] = ",".join(
            "https://" + host for host in platform_hosts
        )
if not DEBUG:
    if len(SECRET_KEY) < 50:
        raise RuntimeError(
            "Production ETCS_SECRET_KEY must contain at least 50 characters"
        )
    if not os.environ.get("ETCS_ALLOWED_HOSTS"):
        raise RuntimeError("Set explicit ETCS_ALLOWED_HOSTS for production")
ALLOWED_HOSTS = os.environ.get(
    "ETCS_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver"
).split(",")
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "coordination.apps.CoordinationConfig",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "coordination.views.context",
            ]
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("ETCS_DB", BASE_DIR / "db.sqlite3"),
        "OPTIONS": {"timeout": 30},
    }
}
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "ar"
TIME_ZONE = "Asia/Hebron"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = Path(os.environ.get("ETCS_PRIVATE_MEDIA", BASE_DIR / "private_media"))
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 28800
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_SSL_REDIRECT = not DEBUG
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
X_FRAME_OPTIONS = "DENY"
EMAIL_BACKEND = os.environ.get(
    "ETCS_EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend"
    if DEBUG
    else "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = os.environ.get("ETCS_EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("ETCS_EMAIL_PORT", "587"))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get("ETCS_EMAIL_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("ETCS_EMAIL_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get("ETCS_FROM_EMAIL", "etcs@localhost")
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
DATA_UPLOAD_MAX_MEMORY_SIZE = 12582912

SECURE_HSTS_SECONDS = int(os.environ.get("ETCS_HSTS_SECONDS", "0" if DEBUG else "3600"))

# PostgreSQL is selected explicitly; SQLite remains supported for local development.
if os.environ.get("DATABASE_URL"):
    database_connection = os.environ["DATABASE_URL"]
    if os.environ.get("VERCEL") == "1" and os.environ.get("ETCS_DEPLOY_PREPARE") != "1":
        import hashlib, hmac
        from urllib.parse import quote, urlunparse

        runtime_role = os.environ.get("ETCS_RUNTIME_ROLE", "etcs_vercel_web")
        runtime_password = hmac.new(
            SECRET_KEY.encode(),
            ("etcs-runtime:" + runtime_role).encode(),
            hashlib.sha256,
        ).hexdigest()
        original = urlparse(database_connection)
        database_connection = urlunparse(
            original._replace(
                netloc=quote(runtime_role)
                + ":"
                + runtime_password
                + "@"
                + original.netloc.split("@")[-1]
            )
        )
    db = urlparse(database_connection)
    if db.scheme not in ["postgres", "postgresql"]:
        raise RuntimeError("DATABASE_URL must use PostgreSQL")
    from urllib.parse import unquote

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": unquote(db.path.lstrip("/")),
            "USER": unquote(db.username or ""),
            "PASSWORD": unquote(db.password or ""),
            "HOST": db.hostname,
            "PORT": db.port or 5432,
            "CONN_MAX_AGE": 60,
            "OPTIONS": {"sslmode": parse_qs(db.query).get("sslmode", ["require"])[0]},
        }
    }
    if parse_qs(db.query).get("channel_binding"):
        DATABASES["default"]["OPTIONS"]["channel_binding"] = parse_qs(db.query)[
            "channel_binding"
        ][0]
CSRF_TRUSTED_ORIGINS = [
    x for x in os.environ.get("ETCS_TRUSTED_ORIGINS", "").split(",") if x
]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}
ETCS_RLS = os.environ.get("ETCS_RLS", "0") == "1"
if ETCS_RLS:
    if DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
        raise RuntimeError("ETCS_RLS requires PostgreSQL")
    MIDDLEWARE.insert(
        MIDDLEWARE.index("django.contrib.auth.middleware.AuthenticationMiddleware") + 1,
        "coordination.middleware.DatabaseIdentityMiddleware",
    )
EMAIL_TIMEOUT = 15
EMAIL_USE_TLS = os.environ.get("ETCS_EMAIL_TLS", "1") == "1"
EMAIL_USE_SSL = os.environ.get("ETCS_EMAIL_SSL", "0") == "1"
if EMAIL_USE_SSL:
    EMAIL_USE_TLS = False
SECURE_HSTS_INCLUDE_SUBDOMAINS = os.environ.get("ETCS_HSTS_SUBDOMAINS", "0") == "1"
SECURE_HSTS_PRELOAD = os.environ.get("ETCS_HSTS_PRELOAD", "0") == "1"
FILE_UPLOAD_PERMISSIONS = 0o600
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o700

SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]

ETCS_EMAIL_NOTIFICATIONS = os.environ.get("ETCS_EMAIL_NOTIFICATIONS", "0") == "1"

ETCS_CASE_RETENTION_DAYS = max(
    1, int(os.environ.get("ETCS_CASE_RETENTION_DAYS", "365"))
)

ETCS_MAX_UPLOAD_BYTES = int(
    os.environ.get("ETCS_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))
)
ETCS_PDF_BACKEND = os.environ.get("ETCS_PDF_BACKEND", "weasyprint")
ETCS_SERVERLESS = os.environ.get("VERCEL", "") == "1"
ETCS_CRON_SECRET = os.environ.get("CRON_SECRET", "")
if ETCS_SERVERLESS:
    if not os.environ.get("DATABASE_URL"):
        raise RuntimeError(
            "Vercel requires external PostgreSQL; SQLite data would be lost"
        )
    if not ETCS_RLS:
        raise RuntimeError("Set ETCS_RLS=1 on Vercel to enforce database isolation")
    DATABASES["default"]["CONN_MAX_AGE"] = 0
    DATABASES["default"]["OPTIONS"]["prepare_threshold"] = None
    STORAGES["default"] = {"BACKEND": "coordination.storage.DatabaseStorage"}
    ETCS_MAX_UPLOAD_BYTES = 3 * 1024 * 1024
    DATA_UPLOAD_MAX_MEMORY_SIZE = 4 * 1024 * 1024
    ETCS_PDF_BACKEND = "fpdf"
    MEDIA_ROOT = Path("/tmp/etcs-unused-media")
