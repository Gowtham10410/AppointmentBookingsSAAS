from .base import *  # noqa: F401,F403

DEBUG = True
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CORS_ALLOW_ALL_ORIGINS = True
