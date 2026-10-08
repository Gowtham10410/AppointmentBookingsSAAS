from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from typing import Literal

from django.db import transaction
from django.utils import timezone

from accounts.models import EmailToken, User

EmailTokenPurpose = Literal["verify_email", "reset_password"]
TOKEN_LIFETIMES = {"verify_email": timedelta(hours=24), "reset_password": timedelta(hours=1)}


class InvalidEmailToken(Exception):
    """The token is unknown, already used, or has the wrong purpose."""


class ExpiredEmailToken(Exception):
    """The token exists but has expired."""


def _token_hash(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


@transaction.atomic
def issue_token(user: User, purpose: EmailTokenPurpose) -> str:
    if purpose not in TOKEN_LIFETIMES:
        raise ValueError("Unsupported email token purpose.")

    now = timezone.now()
    EmailToken.objects.filter(user=user, purpose=purpose, used_at__isnull=True).update(used_at=now)
    plaintext = secrets.token_urlsafe(32)
    EmailToken.objects.create(
        user=user,
        purpose=purpose,
        token_hash=_token_hash(plaintext),
        expires_at=now + TOKEN_LIFETIMES[purpose],
    )
    return plaintext


@transaction.atomic
def consume_token(plaintext: str, purpose: EmailTokenPurpose) -> EmailToken:
    if purpose not in TOKEN_LIFETIMES:
        raise ValueError("Unsupported email token purpose.")

    digest = _token_hash(plaintext)
    try:
        token = EmailToken.objects.select_for_update().select_related("user").get(token_hash=digest, purpose=purpose)
    except EmailToken.DoesNotExist as exc:
        raise InvalidEmailToken("Token is invalid or already used.") from exc

    if not secrets.compare_digest(token.token_hash, digest) or token.used_at is not None:
        raise InvalidEmailToken("Token is invalid or already used.")

    now = timezone.now()
    token.used_at = now
    token.save(update_fields=["used_at"])
    if token.expires_at <= now:
        raise ExpiredEmailToken("Token has expired.")
    return token