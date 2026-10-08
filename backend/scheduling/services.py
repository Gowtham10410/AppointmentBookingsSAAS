from __future__ import annotations

from datetime import date as date_type
from datetime import datetime, timedelta
from datetime import time as time_type
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from accounts.models import User

from .models import Booking, Service, Staff
from .tenancy import assert_same_tenant


def _business_tz() -> ZoneInfo:
    return ZoneInfo(getattr(settings, "BUSINESS_TZ", "Asia/Kolkata"))


def _business_day() -> date_type:
    tz = _business_tz()
    return timezone.localtime(timezone.now(), timezone=tz).date()


def _candidate_overlap_filter(start_time: time_type, end_time: time_type):
    return Q(start_time__lt=end_time) & Q(end_time__gt=start_time)


def _parse_slot_time(value: str | time_type) -> time_type:
    if isinstance(value, time_type):
        return value
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"Invalid time value: {value}")


def generate_slots(staff: Staff, date_value: date_type, service: Service) -> list[dict[str, str]]:
    assert_same_tenant(staff, service)
    if not staff.is_active or not service.is_active:
        return []

    if staff.services.exists() and not staff.services.filter(pk=service.pk).exists():
        return []

    today = _business_day()
    if date_value < today or date_value > today + timedelta(days=settings.BOOKING_WINDOW_DAYS):
        return []

    working_hours = staff.working_hours.filter(day_of_week=date_value.weekday()).first()
    if working_hours is None or working_hours.is_off_day:
        return []

    business_tz = _business_tz()
    start_dt = datetime.combine(date_value, working_hours.start_time, tzinfo=business_tz)
    end_dt = datetime.combine(date_value, working_hours.end_time, tzinfo=business_tz)
    slot_duration = timedelta(minutes=service.duration_minutes)
    step = slot_duration + timedelta(minutes=settings.BUFFER_MINUTES)

    generated: list[dict[str, str]] = []
    current = start_dt

    while current + slot_duration <= end_dt:
        candidate_end = current + slot_duration
        if date_value == today:
            lead_cutoff = timezone.localtime(timezone.now(), timezone=business_tz) + timedelta(minutes=settings.MIN_LEAD_MINUTES)
            if current < lead_cutoff:
                current += step
                continue

        overlap_qs = Booking.objects.filter(staff=staff, date=date_value).exclude(status="cancelled").filter(
            _candidate_overlap_filter(current.timetz().replace(tzinfo=None), candidate_end.timetz().replace(tzinfo=None))
        )
        if overlap_qs.exists():
            current += step
            continue

        generated.append({
            "start_time": current.strftime("%H:%M"),
            "end_time": candidate_end.strftime("%H:%M"),
        })
        current += step

    return generated


def book_slot(
    staff: Staff,
    service: Service,
    client: User | None = None,
    created_by: User | None = None,
    date: date_type | str | None = None,
    start_time: str | time_type | None = None,
    customer_name: str | None = None,
    customer_email: str | None = None,
    customer_phone: str | None = None,
    **kwargs: object,
) -> Booking:
    if date is None:
        date = kwargs.get("date_value")
    if start_time is None:
        start_time = kwargs.get("start_time_value")

    if (
        client is None
        or created_by is None
        or date is None
        or start_time is None
        or customer_name is None
        or customer_email is None
        or customer_phone is None
    ):
        raise ValueError("slot unavailable")

    assert_same_tenant(staff, service, client, created_by)
    normalized_date = date if isinstance(date, date_type) else datetime.strptime(str(date), "%Y-%m-%d").date()
    normalized_time = _parse_slot_time(str(start_time))
    slots = generate_slots(staff, normalized_date, service)
    slot_map = {slot["start_time"]: slot["end_time"] for slot in slots}

    if normalized_time.strftime("%H:%M") not in slot_map:
        raise ValueError("slot unavailable")

    for attempt in range(3):
        try:
            with transaction.atomic():
                locked_staff = Staff.objects.select_for_update().get(pk=staff.pk)
                assert_same_tenant(locked_staff, service, client, created_by)
                fresh_slots = generate_slots(locked_staff, normalized_date, service)
                fresh_map = {slot["start_time"]: slot["end_time"] for slot in fresh_slots}
                if normalized_time.strftime("%H:%M") not in fresh_map:
                    raise ValueError("slot unavailable")

                booking = Booking(
                    organisation=locked_staff.organisation,
                    client=client,
                    created_by=created_by,
                    staff=locked_staff,
                    service=service,
                    customer_name=client.full_name.strip(),
                    customer_email=client.email,
                    customer_phone=client.phone,
                    date=normalized_date,
                    start_time=normalized_time,
                    end_time=_parse_slot_time(fresh_map[normalized_time.strftime("%H:%M")]),
                    status="confirmed",
                )
                booking.save()
                return booking
        except IntegrityError as exc:
            if attempt >= 2:
                raise ValueError("slot unavailable") from exc
            continue
        except ValueError:
            raise

    raise ValueError("slot unavailable")
