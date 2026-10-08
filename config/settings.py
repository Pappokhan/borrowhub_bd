"""Django settings for BorrowHub BD — configured entirely through environment variables.

Local development works with zero configuration (DEBUG on, SQLite).
For production set DJANGO_DEBUG=0 and the variables listed in .env.example.
"""
import logging
import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from django.contrib.messages import constants as message_constants
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    return os.environ.get(name, str(int(default))).strip().lower() in ("1", "true", "yes", "on")


def env_list(name, default=""):
    return [x.strip() for x in os.environ.get(name, default).split(",") if x.strip()]


def env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


# --------------------------------------------------------------------------- core
_DEV_KEY = "django-insecure-dev-key-change-me-in-production"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", _DEV_KEY)
DEBUG = env_bool("DJANGO_DEBUG", True)
if not DEBUG:
    if SECRET_KEY == _DEV_KEY or len(SECRET_KEY) < 40:
        raise ImproperlyConfigured("Set DJANGO_SECRET_KEY (50+ random characters) when DJANGO_DEBUG=0.")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]")
if not DEBUG and env_bool("DJANGO_HEALTHCHECK_LOCALHOST", True):
    ALLOWED_HOSTS += ["127.0.0.1", "localhost"]  # lets container health checks call /healthz/
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")
SITE_URL = os.environ.get("SITE_URL", "http://localhost:8000").rstrip("/")  # used in emails / sitemap links

# Change the admin URL in production to avoid bots probing /admin/
ADMIN_URL = os.environ.get("DJANGO_ADMIN_URL", "admin/").strip("/") + "/"

INSTALLED_APPS = [
    "core.admin_config.BorrowAdminConfig",  # admin with BorrowHub dashboard stats
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.contrib.sitemaps",
    "accounts",
    "listings",
    "bookings",
    "core",
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
    "core.middleware.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.site",
            ],
        },
    },
]
if not DEBUG:  # cache compiled templates
    TEMPLATES[0]["APP_DIRS"] = False
    TEMPLATES[0]["OPTIONS"]["loaders"] = [
        ("django.template.loaders.cached.Loader", [
            "django.template.loaders.filesystem.Loader",
            "django.template.loaders.app_directories.Loader",
        ]),
    ]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


# --------------------------------------------------------------------------- database
def _database_from_url(url):
    p = urlparse(url)
    engines = {"postgres": "django.db.backends.postgresql", "postgresql": "django.db.backends.postgresql",
               "sqlite": "django.db.backends.sqlite3"}
    if p.scheme not in engines:
        raise ImproperlyConfigured(f"Unsupported DATABASE_URL scheme: {p.scheme}")
    if p.scheme == "sqlite":
        return {"ENGINE": engines[p.scheme], "NAME": unquote(p.path[1:]) or BASE_DIR / "db.sqlite3"}  # sqlite:///rel.db  or  sqlite:////abs/path.db
    return {"ENGINE": engines[p.scheme], "NAME": p.path.lstrip("/"), "USER": unquote(p.username or ""),
            "PASSWORD": unquote(p.password or ""), "HOST": p.hostname or "localhost", "PORT": str(p.port or 5432)}


if os.environ.get("DATABASE_URL"):
    DATABASES = {"default": _database_from_url(os.environ["DATABASE_URL"])}
elif os.environ.get("DB_NAME"):
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql", "NAME": os.environ["DB_NAME"],
        "USER": os.environ.get("DB_USER", ""), "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", "localhost"), "PORT": os.environ.get("DB_PORT", "5432")}}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
if DATABASES["default"]["ENGINE"].endswith("postgresql"):
    DATABASES["default"]["CONN_MAX_AGE"] = env_int("DB_CONN_MAX_AGE", 60)
    DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

# --------------------------------------------------------------------------- cache / sessions
# Set REDIS_URL (e.g. redis://redis:6379/1) so login throttling & caches are shared across workers.
if os.environ.get("REDIS_URL"):
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache",
                          "LOCATION": os.environ["REDIS_URL"]}}
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "borrowhub"}}

# --------------------------------------------------------------------------- auth
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["accounts.backends.EmailOrUsernameBackend"]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:dashboard"
LOGOUT_REDIRECT_URL = "core:home"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14  # 14 days
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# Login / form throttling (see core/security.py)
LOGIN_MAX_ATTEMPTS = env_int("LOGIN_MAX_ATTEMPTS", 5)
LOGIN_LOCKOUT_SECONDS = env_int("LOGIN_LOCKOUT_SECONDS", 15 * 60)
TRUST_PROXY_HEADERS = env_bool("TRUST_PROXY_HEADERS", False)  # True when behind nginx / a load balancer

# --------------------------------------------------------------------------- i18n
LANGUAGE_CODE = "en"
TIME_ZONE = "Asia/Dhaka"
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------------- static & media
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(os.environ.get("DJANGO_MEDIA_ROOT", BASE_DIR / "media"))
# Sensitive uploads (NID photos) live OUTSIDE the public media folder and are served only to staff.
PRIVATE_MEDIA_ROOT = Path(os.environ.get("DJANGO_PRIVATE_MEDIA_ROOT", BASE_DIR / "private_media"))
# Serve /media/ from Django itself (OK for demos / small sites). In production let nginx serve it
# (docker-compose does) or move to S3 and set DJANGO_SERVE_MEDIA=0.
SERVE_MEDIA = env_bool("DJANGO_SERVE_MEDIA", DEBUG)

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": (
        "whitenoise.storage.CompressedStaticFilesStorage" if DEBUG
        else "whitenoise.storage.CompressedManifestStaticFilesStorage")},
}
WHITENOISE_MAX_AGE = 0 if DEBUG else 60 * 60 * 24 * 365  # hashed filenames → cache forever

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
MESSAGE_TAGS = {message_constants.ERROR: "danger"}
DATA_UPLOAD_MAX_MEMORY_SIZE = 30 * 1024 * 1024  # multiple listing photos
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 2000

# --------------------------------------------------------------------------- email
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "BorrowHub BD <no-reply@borrowhub.bd>")
SERVER_EMAIL = DEFAULT_FROM_EMAIL
# Email members when something happens on their bookings (in addition to in-app notifications).
EMAIL_NOTIFICATIONS = env_bool("EMAIL_NOTIFICATIONS", False)
ADMINS = [("Admin", e) for e in env_list("DJANGO_ADMIN_EMAILS")]  # receive 500-error emails

# --------------------------------------------------------------------------- security (production)
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SSL_REDIRECT", True)
    SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]  # so container health checks work over plain HTTP
    SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", True)
    SECURE_HSTS_SECONDS = env_int("DJANGO_HSTS_SECONDS", 60 * 60 * 24 * 365)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("DJANGO_HSTS_SUBDOMAINS", True)
    SECURE_HSTS_PRELOAD = env_bool("DJANGO_HSTS_PRELOAD", False)
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"
    if not SECURE_HSTS_PRELOAD:
        SILENCED_SYSTEM_CHECKS = ["security.W021"]  # preload list is an opt-in, irreversible decision

# --------------------------------------------------------------------------- logging
LOG_LEVEL = os.environ.get("DJANGO_LOG_LEVEL", "INFO" if not DEBUG else "DEBUG")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"std": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "std"},
        "mail_admins": {"class": "django.utils.log.AdminEmailHandler", "level": "ERROR",
                        "filters": ["require_debug_false"]},
    },
    "filters": {"require_debug_false": {"()": "django.utils.log.RequireDebugFalse"}},
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.request": {"handlers": ["console", "mail_admins"], "level": "WARNING", "propagate": False},
        "django.security": {"handlers": ["console", "mail_admins"], "level": "WARNING", "propagate": False},
        "borrowhub": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}

# Optional error tracking: pip install sentry-sdk and set SENTRY_DSN
if os.environ.get("SENTRY_DSN"):
    try:
        import sentry_sdk
        sentry_sdk.init(dsn=os.environ["SENTRY_DSN"], send_default_pii=False,
                        traces_sample_rate=float(os.environ.get("SENTRY_TRACES", "0.0")))
    except ImportError:
        logging.getLogger("borrowhub").warning("SENTRY_DSN is set but sentry-sdk is not installed.")
