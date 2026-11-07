"""
Django settings for config project.
"""

import os
import sys
from pathlib import Path

from config.deployment_safety import (
    check_secret_key,
    mail_backend_for,
    parse_flag,
    parse_trusted_proxies,
    resolve_https,
    telegram_alert_settings,
)

BASE_DIR = Path(__file__).resolve().parent.parent


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-wxswn1r_u^eaz20hc89%^_so7#ho40g8i4jd+&l%jd@qnbu44a",
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get("DJANGO_DEBUG", "False") == "True"

# True only under `manage.py test`. Tests run on plain HTTP with fast hashers.
TESTING = len(sys.argv) > 1 and sys.argv[1] == "test"

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "accounts.middleware.AccountSecurityMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.roles",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases
#
# PostgreSQL is the approved production database (docs/ARCHITECTURE.md).
# Configuration comes entirely from environment variables so no credentials
# are hardcoded. If DB_NAME is not set, fall back to SQLite for local
# bootstrap/dev convenience only -- SQLite is not the intended production
# database.

if os.environ.get("DB_NAME"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["DB_NAME"],
            "USER": os.environ.get("DB_USER", ""),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "localhost"),
            "PORT": os.environ.get("DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# Custom user model (docs/adr/0004-phase-1-authorization-foundation.md)
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["accounts.backends.NormalizedUsernameBackend"]

# Phase 1 administrative authorization (docs/adr/0004-phase-1-authorization-foundation.md)
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"


# Phase 6 Gate 7 (ADR 0013): sessions, cookies, network source.
# 30 minutes of inactivity or 8 hours since sign-in, whichever comes first
# (OD-5); enforced server-side by accounts.middleware on every request.
SESSION_IDLE_SECONDS = 30 * 60
SESSION_ABSOLUTE_SECONDS = 8 * 60 * 60
SESSION_COOKIE_AGE = SESSION_IDLE_SECONDS
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
# A stale form shows a plain-words "page has expired" page, not Django's technical one.
CSRF_FAILURE_VIEW = "accounts.views.csrf_failure"

# Production HTTPS: Secure cookies, HTTPS redirect and HSTS. On by default outside debug
# and test runs; an explicit DJANGO_HTTPS=False is refused there, so HTTPS cannot be lost
# silently. Local development and tests use plain HTTP by default; an explicit
# DJANGO_HTTPS=True enables HTTPS behavior.
HTTPS = resolve_https(os.environ.get("DJANGO_HTTPS"), debug=DEBUG, testing=TESTING)
SESSION_COOKIE_SECURE = HTTPS
CSRF_COOKIE_SECURE = HTTPS
SECURE_SSL_REDIRECT = HTTPS
SECURE_HSTS_SECONDS = 31536000 if HTTPS else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = HTTPS
SECURE_HSTS_PRELOAD = parse_flag("DJANGO_HSTS_PRELOAD", os.environ.get("DJANGO_HSTS_PRELOAD"))
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# OD-3: forwarded headers are trusted only from these proxy addresses/CIDRs
# (comma-separated). Empty: X-Forwarded-For is ignored. A malformed entry stops startup
# instead of being skipped, which would silently drop the proxy's trust.
TRUSTED_PROXIES = parse_trusted_proxies(os.environ.get("DJANGO_TRUSTED_PROXIES", ""))
if TRUSTED_PROXIES and HTTPS:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# Dedicated key for hashing network sources; defaults to a value derived from
# SECRET_KEY so raw addresses are never stored.
SOURCE_HASH_KEY = os.environ.get("DJANGO_SOURCE_HASH_KEY", "source-hash:" + SECRET_KEY)

# Phase 7: full web address of this site (e.g. https://erp.school.in), used in
# links inside WhatsApp messages. Required before the school can choose ASSIST.
PORTAL_BASE_URL = os.environ.get("PORTAL_BASE_URL", "").strip().rstrip("/")

# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = "en-us"

# House date style ("15 Oct 2026"); see config/formats/en/formats.py.
FORMAT_MODULE_PATH = ["config.formats"]

# The school's local timezone. Business dates (e.g. "is this date in the
# future?") come from timezone.localdate(), so this must be the school's
# timezone, not UTC. USE_TZ stays on: stored timestamps remain timezone-aware.
TIME_ZONE = "Asia/Kolkata"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# The manifest storage needs `collectstatic` first; tests and local DEBUG use plain storage
# so `{% static %}` works without it. Production (DEBUG off, not testing) is unchanged.
# Security Gate 2: production refuses to start with a missing, blank or development-default
# secret key. Debug and test runs are unchanged.
check_secret_key(SECRET_KEY, debug=DEBUG, testing=TESTING)

if DEBUG or TESTING:
    STORAGES["staticfiles"]["BACKEND"] = "django.contrib.staticfiles.storage.StaticFilesStorage"

# Tests create many users; the default PBKDF2 hasher is deliberately slow. A fast,
# insecure hasher is used only under `manage.py test`. Real passwords are unaffected.
if TESTING:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Crash reporting: errors are written to the console (Railway logs) and every
# unhandled 500 is emailed to DJANGO_ADMINS (comma-separated addresses). Each
# installation sets ERP_INSTANCE_NAME (e.g. "st-marys") so the email subject
# says which school it came from. The email is an allow-list report built by
# config.error_reporting (exception types, route pattern and traceback locations only;
# no query strings, client details, usernames, messages or variables). Nothing is sent
# until both DJANGO_ADMINS and an SMTP host (EMAIL_HOST) are set.
ERP_INSTANCE_NAME = os.environ.get("ERP_INSTANCE_NAME", "local").strip() or "local"
ADMINS = [
    (address.strip(), address.strip())
    for address in os.environ.get("DJANGO_ADMINS", "").split(",")
    if address.strip()
]
EMAIL_SUBJECT_PREFIX = f"[school-erp {ERP_INSTANCE_NAME}] "
DEFAULT_EXCEPTION_REPORTER_FILTER = "config.error_reporting.PrivacyExceptionReporterFilter"

# Optional Telegram crash alert to the operator (config.telegram_alerts), built from the
# same allow-list as the email. Set both variables to turn it on; one without the other
# stops startup. Debug and test runs always get blanks, so they never contact Telegram.
TELEGRAM_ERROR_BOT_TOKEN, TELEGRAM_ERROR_CHAT_ID = telegram_alert_settings(
    os.environ.get("TELEGRAM_ERROR_BOT_TOKEN"),
    os.environ.get("TELEGRAM_ERROR_CHAT_ID"),
    debug=DEBUG,
    testing=TESTING,
)

# Outgoing mail over SMTP, only when EMAIL_HOST is set. Without it, production discards
# mail and local development (DJANGO_DEBUG=True) prints it to the console.
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_BACKEND = mail_backend_for(EMAIL_HOST, debug=DEBUG)
if EMAIL_HOST:
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = parse_flag("EMAIL_USE_TLS", os.environ.get("EMAIL_USE_TLS"), default=True)
    EMAIL_TIMEOUT = 10
SERVER_EMAIL = os.environ.get("SERVER_EMAIL", EMAIL_HOST_USER if EMAIL_HOST else "root@localhost")
DEFAULT_FROM_EMAIL = SERVER_EMAIL

# Railway shows anything written to stdout/stderr. Tests stay quiet unless
# DJANGO_LOG_LEVEL is set explicitly.
LOG_LEVEL = os.environ.get("DJANGO_LOG_LEVEL", "CRITICAL" if TESTING else "INFO").upper()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "{asctime} {levelname} {name} {message}", "style": "{"},
    },
    "filters": {
        "require_debug_false": {"()": "django.utils.log.RequireDebugFalse"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain", "level": LOG_LEVEL},
        "mail_admins": {
            "class": "config.error_reporting.PrivacyAdminEmailHandler",
            "level": "ERROR",
            "filters": ["require_debug_false"],
            "include_html": False,
        },
        "telegram_alerts": {
            "class": "config.telegram_alerts.TelegramAlertHandler",
            "level": "ERROR",
            "filters": ["require_debug_false"],
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        # Replaces Django's defaults (console only under DEBUG, mail_admins
        # for everything) so records just propagate to the root console.
        "django": {"handlers": [], "level": "INFO", "propagate": True},
        # Unhandled exceptions (500s); propagates to the console as well.
        # Telegram first: its 3 s timeout must not wait behind SMTP's 10 s EMAIL_TIMEOUT.
        "django.request": {
            "handlers": ["telegram_alerts", "mail_admins"],
            "level": "INFO",
            "propagate": True,
        },
    },
}
