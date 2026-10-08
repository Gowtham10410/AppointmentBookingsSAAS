from typing import Any, TypeVar

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import transaction
from django.utils import timezone

T = TypeVar("T", bound=AbstractUser)


class UserManager(BaseUserManager[T]):
    use_in_migrations = True

    def _create_user(self, email: str | None, password: str | None, **extra_fields: Any) -> T:
        if not email:
            raise ValueError("The email field must be set.")
        if not extra_fields.get("organisation"):
            raise ValueError("An organisation is required for every user.")
        email = self.normalize_email(email)
        email = email.lower()
        if not extra_fields.get("full_name"):
            first_name = extra_fields.get("first_name", "")
            last_name = extra_fields.get("last_name", "")
            extra_fields["full_name"] = f"{first_name} {last_name}".strip() or email.split("@", maxsplit=1)[0]
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str | None = None, password: str | None = None, **extra_fields: Any) -> T:
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str | None = None, password: str | None = None, **extra_fields: Any) -> T:
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", "org_admin")
        extra_fields.setdefault("email_verified_at", timezone.now())
        if not extra_fields.get("is_staff"):
            raise ValueError("Superuser must have is_staff=True.")
        if not extra_fields.get("is_superuser"):
            raise ValueError("Superuser must have is_superuser=True.")
        if extra_fields.get("organisation"):
            user = self._create_user(email, password, **extra_fields)
            organisation = extra_fields["organisation"]
            if organisation.owner_id is None:
                organisation.owner = user
                organisation.save(update_fields=["owner"])
            return user

        from accounts.models import Organisation

        with transaction.atomic():
            organisation = Organisation.objects.create(name=f"{email or 'Admin'} Organisation")
            extra_fields["organisation"] = organisation
            user = self._create_user(email, password, **extra_fields)
            organisation.owner = user
            organisation.save(update_fields=["owner"])
            return user
