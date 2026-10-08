from __future__ import annotations

import re
import secrets
import string

ORG_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
ORG_CODE_SUFFIX_LENGTH = 5
ORG_CODE_MAX_ATTEMPTS = 10
_DASH_TRANSLATION = str.maketrans({"–": "-", "—": "-", "−": "-", "‐": "-", "‑": "-"})


class OrgCodeGenerationError(RuntimeError):
    """Raised when no unique organisation code is generated within the retry limit."""


def normalize_org_code(value: str) -> str:
    normalized = value.translate(_DASH_TRANSLATION).strip().upper()
    return re.sub(r"\s+", "", normalized)


def _prefix_for_name(name: str) -> str:
    letters = "".join(character for character in name.upper() if character in string.ascii_uppercase)
    return letters[:4] if len(letters) >= 3 else "ORG"


def _random_suffix() -> str:
    return "".join(secrets.choice(ORG_CODE_ALPHABET) for _ in range(ORG_CODE_SUFFIX_LENGTH))


def generate_org_code(name: str) -> str:
    from accounts.models import Organisation

    prefix = _prefix_for_name(name)
    for _ in range(ORG_CODE_MAX_ATTEMPTS):
        candidate = f"{prefix}-{_random_suffix()}"
        if not Organisation.objects.filter(org_code__iexact=candidate).exists():
            return candidate
    raise OrgCodeGenerationError("Could not generate a unique organisation code after 10 attempts.")