from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q

from accounts.tenancy import TenantManager


class Service(models.Model):
    organisation = models.ForeignKey("accounts.Organisation", on_delete=models.PROTECT, related_name="services")
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    duration_minutes = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(5), MaxValueValidator(480)],
    )
    price = models.DecimalField(max_digits=8, decimal_places=2, default=0, validators=[MinValueValidator(Decimal("0.00"))])
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = TenantManager()

    class Meta:
        constraints = [
            models.CheckConstraint(check=Q(duration_minutes__gte=5) & Q(duration_minutes__lte=480), name="service_duration_range"),
            models.CheckConstraint(check=Q(price__gte=0), name="service_price_non_negative"),
        ]

    def __str__(self) -> str:
        return self.name


class Staff(models.Model):
    organisation = models.ForeignKey("accounts.Organisation", on_delete=models.PROTECT, related_name="staff_members")
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="staff_profile",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15, blank=True)
    specialization = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    services = models.ManyToManyField(Service, related_name="staff_members", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = TenantManager()

    class Meta:
        indexes = [models.Index(fields=["is_active"])]

    def __str__(self) -> str:
        return self.name


class WorkingHours(models.Model):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name="working_hours")
    day_of_week = models.PositiveSmallIntegerField(validators=[MinValueValidator(0), MaxValueValidator(6)])
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_off_day = models.BooleanField(default=False)
    objects = TenantManager()

    class Meta:
        unique_together = ("staff", "day_of_week")
        constraints = [
            models.CheckConstraint(check=Q(day_of_week__gte=0) & Q(day_of_week__lte=6), name="working_hours_day_of_week_range"),
            models.CheckConstraint(check=Q(start_time__lt=F("end_time")), name="working_hours_end_after_start"),
        ]

    def __str__(self) -> str:
        return f"{self.staff} - {self.day_of_week}"


BOOKING_STATUS_CHOICES = [
    ("confirmed", "Confirmed"),
    ("cancelled", "Cancelled"),
    ("completed", "Completed"),
    ("no_show", "No Show"),
]


class Booking(models.Model):
    STATUS_CHOICES = BOOKING_STATUS_CHOICES

    organisation = models.ForeignKey("accounts.Organisation", on_delete=models.PROTECT, related_name="bookings")
    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="client_bookings")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_bookings")
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="cancelled_bookings",
        null=True,
        blank=True,
    )
    staff = models.ForeignKey(Staff, on_delete=models.PROTECT, related_name="bookings")
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="bookings")
    customer_name = models.CharField(max_length=100)
    customer_email = models.EmailField()
    customer_phone = models.CharField(max_length=15)
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="confirmed")
    created_at = models.DateTimeField(auto_now_add=True)
    active_slot = models.SmallIntegerField(null=True, blank=True)
    objects = TenantManager()

    class Meta:
        indexes = [
            models.Index(fields=["staff", "date"]),
            models.Index(fields=["date", "status"]),
            models.Index(fields=["organisation", "date"], name="booking_org_date_idx"),
            models.Index(fields=["organisation", "status"], name="booking_org_status_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["staff", "date", "start_time", "active_slot"], name="booking_unique_active_slot"),
            models.CheckConstraint(check=Q(status__in=[choice[0] for choice in BOOKING_STATUS_CHOICES]), name="booking_status_valid"),
        ]
        unique_together = [("staff", "date", "start_time", "active_slot")]

    def clean(self) -> None:
        super().clean()
        if not all([self.organisation_id, self.staff_id, self.service_id, self.client_id]):
            raise ValidationError("A booking requires an organisation, staff member, service and client.")
        resources = [self, self.staff, self.service, self.client]
        if self.created_by_id:
            resources.append(self.created_by)
        try:
            from .tenancy import assert_same_tenant

            assert_same_tenant(*resources)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

    @property
    def reference(self) -> str:
        return f"SAS-{self.pk:05d}" if self.pk else "SAS-00000"

    def set_status(self, status: str) -> None:
        self.status = status
        self.active_slot = None if status == "cancelled" else 1

    def save(self, *args, **kwargs):
        if self.pk:
            snapshot = Booking.objects.filter(pk=self.pk).values_list(
                "customer_name",
                "customer_email",
                "customer_phone",
            ).first()
            if snapshot is not None and snapshot != (self.customer_name, self.customer_email, self.customer_phone):
                raise ValidationError("Booking customer snapshots are immutable.")
        if self.status == "cancelled":
            self.active_slot = None
        else:
            self.active_slot = 1
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.reference} - {self.customer_name}"
