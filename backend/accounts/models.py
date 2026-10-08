from typing import ClassVar
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.functions import Lower

from .managers import UserManager


class Organisation(models.Model):
    BUSINESS_TYPE_CHOICES = [
        ("salon", "Salon"),
        ("beauty_parlour", "Beauty parlour"),
        ("spa", "Spa"),
        ("barbershop", "Barbershop"),
        ("clinic", "Clinic"),
        ("other", "Other"),
    ]

    name = models.CharField(max_length=120)
    business_type = models.CharField(max_length=20, choices=BUSINESS_TYPE_CHOICES, default="salon")
    org_code = models.CharField(max_length=16, unique=True, blank=True)
    phone = models.CharField(max_length=15, blank=True)
    address_line = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100, default="India")
    timezone = models.CharField(max_length=64, default="Asia/Kolkata")
    buffer_minutes = models.PositiveSmallIntegerField(
        default=10,
        validators=[MinValueValidator(0), MaxValueValidator(60)],
    )
    min_lead_minutes = models.PositiveSmallIntegerField(
        default=30,
        validators=[MinValueValidator(0), MaxValueValidator(1440)],
    )
    booking_window_days = models.PositiveSmallIntegerField(
        default=30,
        validators=[MinValueValidator(1), MaxValueValidator(180)],
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    owner = models.OneToOneField(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="owned_organisation",
        null=True,
        blank=True,
    )

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(buffer_minutes__gte=0, buffer_minutes__lte=60), name="org_buffer_range"),
            models.CheckConstraint(condition=models.Q(min_lead_minutes__gte=0, min_lead_minutes__lte=1440), name="org_lead_range"),
            models.CheckConstraint(condition=models.Q(booking_window_days__gte=1, booking_window_days__lte=180), name="org_window_range"),
        ]

    def clean(self) -> None:
        super().clean()
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValidationError({"timezone": "Enter a valid IANA time zone."}) from exc

    def save(self, *args, **kwargs) -> None:
        from .services.org_code import generate_org_code

        if not self.org_code:
            self.org_code = generate_org_code(self.name)
        if self.pk:
            current_code = Organisation.objects.filter(pk=self.pk).values_list("org_code", flat=True).first()
            if current_code is not None and current_code != self.org_code:
                raise ValidationError({"org_code": "Organisation codes are immutable."})
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name


class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=15, blank=True)
    role = models.CharField(max_length=20, choices=[("org_admin", "Organisation admin"), ("client", "Client")], default="client")
    organisation = models.ForeignKey("accounts.Organisation", on_delete=models.PROTECT, related_name="members")
    email_verified_at = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD: ClassVar[str] = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    objects: UserManager["User"] = UserManager()

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        constraints = [models.UniqueConstraint(Lower("email"), name="user_email_case_insensitive_unique")]

    def save(self, *args, **kwargs) -> None:
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    @property
    def name(self) -> str:
        return self.full_name.strip() or self.get_full_name() or self.email


class EmailToken(models.Model):
    PURPOSE_CHOICES = [("verify_email", "Verify email"), ("reset_password", "Reset password")]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="email_tokens")
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES)
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["user", "purpose", "used_at"], name="email_token_active_idx")]

    def __str__(self) -> str:
        return f"{self.purpose} token for user {self.user_id}"
