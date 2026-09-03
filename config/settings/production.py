"""Production settings. Fails loudly when a required secret is missing."""

from .base import *  # noqa: F403
from .base import env

DEBUG = False

# No default: the process refuses to boot without an explicit host list.
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")


# ---------------------------------------------------------------------------
# HTTPS / transport security
# ---------------------------------------------------------------------------

SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 365)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = env.bool(
    "DJANGO_SESSION_EXPIRE_AT_BROWSER_CLOSE", default=False
)
SESSION_COOKIE_AGE = env.int("DJANGO_SESSION_COOKIE_AGE", default=60 * 60 * 12)


# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------
# Hashed, long-cacheable names. Served by nginx (see README), not by Django.

STORAGES["staticfiles"] = {  # noqa: F405
    "BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"
}


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

DATABASES["default"]["CONN_MAX_AGE"] = env.int(  # noqa: F405
    "DATABASE_CONN_MAX_AGE", default=600
)


# ---------------------------------------------------------------------------
# Error reporting
# ---------------------------------------------------------------------------

ADMINS = [
    tuple(entry.split(":", 1))
    for entry in env.list("DJANGO_ADMINS", default=[])
    if ":" in entry
]
MANAGERS = ADMINS

LOGGING["handlers"]["mail_admins"] = {  # noqa: F405
    "level": "ERROR",
    "class": "django.utils.log.AdminEmailHandler",
}
LOGGING["loggers"]["django.request"] = {  # noqa: F405
    "handlers": ["console", "mail_admins"],
    "level": "ERROR",
    "propagate": False,
}
