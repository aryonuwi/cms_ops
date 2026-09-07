"""
Base settings shared by every environment.

Environment-specific overrides live in `local.py` and `production.py`.
Nothing secret belongs in this file - read it from the environment instead.
"""

from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured
from django.templatetags.static import static

# ops_views/config/settings/base.py -> ops_views/
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

SECRET_KEY = env("DJANGO_SECRET_KEY")

TWO_FACTOR_ENCRYPTION_KEY = env(
    "DJANGO_TWO_FACTOR_ENCRYPTION_KEY",
    default="dGhpcy1pcy1hLXNhbXBsZS0zMi1ieXRlLWtleS0xMjM0NTY=",
)

DEBUG = env.bool("DJANGO_DEBUG", default=False)

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])

ROOT_URLCONF = "config.urls"

# Configurable so production can move the admin off the guessable default and
# cut the volume of automated login attempts.
ADMIN_URL = env("DJANGO_ADMIN_URL", default="admin/")

WSGI_APPLICATION = "config.wsgi.application"

ASGI_APPLICATION = "config.asgi.application"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
# `unfold` must be declared before `django.contrib.admin` so its templates and
# admin site override the stock ones.

DJANGO_APPS = [
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "unfold.contrib.inlines",
    "unfold.contrib.import_export",
    "unfold.contrib.guardian",
    "unfold.contrib.simple_history",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS: list[str] = []

# One entry per feature module. Each is self-contained and can be lifted out
# into its own service later - see docs in README ("Arsitektur modular").
LOCAL_APPS = [
    "apps.common",
    "apps.accounts",
    "apps.access",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware.TwoFactorVerificationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


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
            ],
        },
    },
]


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
# PostgreSQL everywhere - local, staging and production run the same engine so
# behaviour that differs between backends (JSON operators, constraint timing,
# collation ordering) never surprises anyone at deploy time.
#
#   postgres://USER:PASSWORD@HOST:5432/DBNAME
#
# No default on purpose: a missing DATABASE_URL must stop the process, not
# silently fall back to a throwaway sqlite file.

DATABASES = {"default": env.db_url("DATABASE_URL")}

if DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
    raise ImproperlyConfigured(
        "This project targets PostgreSQL. DATABASE_URL resolved to "
        f"{DATABASES['default']['ENGINE']!r}."
    )

# Reuse connections instead of opening one per request.
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DATABASE_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

DATABASES["default"].setdefault("OPTIONS", {})
DATABASES["default"]["OPTIONS"].update(
    {
        # `require` or stricter whenever the database is not on this host.
        "sslmode": env("DATABASE_SSLMODE", default="require"),
        # Fail fast instead of hanging a worker on an unreachable host.
        "connect_timeout": env.int("DATABASE_CONNECT_TIMEOUT", default=10),
        # Shows up in pg_stat_activity - makes it obvious which process holds
        # a lock or a long-running query.
        "application_name": env("DATABASE_APPLICATION_NAME", default="ops_views"),
    }
)

DATABASES["default"]["TEST"] = {"NAME": env("DATABASE_TEST_NAME", default=None)}


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
# Redis kalau REDIS_URL diisi - container `redis` bersama di mesin lokal,
# managed Redis di production. Lihat README bagian "Cache" dan
# ADR-015. Fallback locmem (in-process, per-worker) kalau REDIS_URL kosong,
# supaya `manage.py check`/`test` tetap jalan di mesin tanpa Redis - caching
# itu sendiri tetap opsional, bukan prasyarat boot seperti DATABASE_URL.

CACHES = {"default": env.cache_url("REDIS_URL", default="locmemcache://")}

# Diset eksplisit, bukan lewat query string `?key_prefix=` di REDIS_URL:
# django-environ 0.14.0 menulis key itu sebagai `key_prefix` huruf kecil di
# dict CACHES, tapi Django hanya membaca `KEY_PREFIX` huruf besar - jadi lewat
# URL, prefix itu diam-diam tidak pernah terpakai. Prefix ini yang menjaga
# key project ini tidak bentrok dengan project lain di container Redis
# bersama (ADR-015).
CACHES["default"]["KEY_PREFIX"] = env("CACHE_KEY_PREFIX", default="ops_views")


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
# A project-owned user model from day one; swapping it after the first
# migration is painful.

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "admin:login"
LOGIN_REDIRECT_URL = "admin:index"

# Akun admin pertama, dipakai `manage.py seed_admin` saat setup awal. Sengaja
# tanpa default: kredensial tidak pernah tinggal di dalam kode (R2), dan
# perintahnya berhenti dengan pesan jelas kalau keduanya kosong.
SEED_ADMIN_EMAIL = env("DJANGO_SEED_ADMIN_EMAIL", default="")
SEED_ADMIN_PASSWORD = env("DJANGO_SEED_ADMIN_PASSWORD", default="")

# Akun staff non-superuser, dipakai `manage.py seed_dummy` untuk menguji hak
# akses menu (apps.access) secara manual - superuser di atas selalu bypass
# FeatureGrant (ADR-012), jadi tidak bisa dipakai memverifikasi pembatasan.
SEED_DUMMY_EMAIL = env("DJANGO_SEED_DUMMY_EMAIL", default="")
SEED_DUMMY_PASSWORD = env("DJANGO_SEED_DUMMY_PASSWORD", default="")


# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------

LANGUAGE_CODE = env("DJANGO_LANGUAGE_CODE", default="en-us")
TIME_ZONE = env("DJANGO_TIME_ZONE", default="Asia/Jakarta")
USE_I18N = True
USE_TZ = True


# ---------------------------------------------------------------------------
# Static & media
# ---------------------------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

MAILERS = {
    "default": env.email_url(
        "EMAIL_URL", default="consolemail://"
    ),
}
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="ops-views@localhost")
SERVER_EMAIL = env("SERVER_EMAIL", default=DEFAULT_FROM_EMAIL)


# ---------------------------------------------------------------------------
# Security defaults
# ---------------------------------------------------------------------------
# Hardened here, relaxed in local.py - so a forgotten override fails closed.

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # 5 MB


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {process:d} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL", default="INFO")},
    "loggers": {
        "django.db.backends": {"level": "WARNING", "propagate": True},
    },
}


# ---------------------------------------------------------------------------
# Unfold admin
# ---------------------------------------------------------------------------
# Navigation is assembled from each feature module's own contribution, so
# adding a module does not mean editing a central list.

# Public name of the panel. The project is aliased as `cms_ops` (ADR-014);
# the human-readable form is configurable per environment without a code change.
SITE_TITLE = env("DJANGO_SITE_TITLE", default="CMS Ops")

UNFOLD = {
    # Menyelaraskan admin dengan landing page. STYLES adalah hook resmi Unfold;
    # file-nya dimuat sebelum styles.css milik Unfold, jadi aturannya menang
    # lewat spesifisitas - lihat catatan di admin.css.
    "STYLES": [lambda request: static("common/admin.css")],
    "SITE_TITLE": SITE_TITLE,
    "SITE_HEADER": SITE_TITLE,
    "SITE_SUBHEADER": "Operations control panel",
    "SITE_SYMBOL": "monitoring",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "SHOW_BACK_BUTTON": True,
    "THEME": None,  # let the operator toggle light/dark
    "BORDER_RADIUS": "10px",  # sejalan dengan kartu di landing page
    "COLORS": {
        "primary": {
            "50": "240 249 255",
            "100": "224 242 254",
            "200": "186 230 253",
            "300": "125 211 252",
            "400": "56 189 248",
            "500": "14 165 233",
            "600": "2 132 199",
            "700": "3 105 161",
            "800": "7 89 133",
            "900": "12 74 110",
            "950": "8 47 73",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
        # Resolved per request, so each feature module contributes its own
        # entries without this file having to know about them.
        "navigation": "apps.common.navigation.build_sidebar_navigation",
    },
}
