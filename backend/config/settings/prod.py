# ruff: noqa: F401,F403,F405
from django.core.exceptions import ImproperlyConfigured

from .base import *

if not SECRET_KEY or SECRET_KEY == "dev-secret-key":
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set in production settings.")

DEBUG = False
SESSION_COOKIE_SECURE = COOKIE_SECURE
CSRF_COOKIE_SECURE = COOKIE_SECURE
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=False)
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
