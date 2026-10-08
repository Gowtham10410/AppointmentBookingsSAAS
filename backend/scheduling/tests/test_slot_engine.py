from datetime import time, timedelta

import pytest
from django.utils import timezone

from scheduling.models import Booking, Service, Staff, WorkingHours
from scheduling.services import book_slot, generate_slots


@pytest.mark.django_db
class TestSlotEngine:
    def test_generate_slots_ignores_overlap_and_respects_working_hours(self, organisation, client_user, org_admin_user):
        staff = Staff.objects.create(organisation=organisation, name="Dr. Skin", specialization="Dermatology", is_active=True)
        service = Service.objects.create(organisation=organisation, name="Skin check", duration_minutes=30, price=800, is_active=True)
        staff.services.add(service)

        booking_date = timezone.localdate() + timedelta(days=1)
        weekday = booking_date.weekday()
        WorkingHours.objects.create(staff=staff, day_of_week=weekday, start_time=time(9, 0), end_time=time(17, 0), is_off_day=False)

        Booking.objects.create(
            organisation=organisation,
            client=client_user,
            created_by=org_admin_user,
            staff=staff,
            service=service,
            customer_name="Ravi",
            customer_email="ravi@example.com",
            customer_phone="9876543210",
            date=booking_date,
            start_time=time(10, 0),
            end_time=time(10, 30),
            status="confirmed",
        )

        slots = generate_slots(staff, booking_date, service)
        times = [slot["start_time"] for slot in slots]

        assert "09:00" in times
        assert "09:40" not in times
        assert "10:20" not in times
        assert "11:00" in times

    def test_book_slot_rejects_duplicate_active_slot(self, organisation, client_user, org_admin_user):
        staff = Staff.objects.create(organisation=organisation, name="Dr. Cardio", specialization="Cardio", is_active=True)
        service = Service.objects.create(organisation=organisation, name="Echo scan", duration_minutes=30, price=1500, is_active=True)
        staff.services.add(service)

        slot_date = timezone.localdate() + timedelta(days=2)
        weekday = slot_date.weekday()
        WorkingHours.objects.create(staff=staff, day_of_week=weekday, start_time=time(9, 0), end_time=time(17, 0), is_off_day=False)

        booking = book_slot(
            staff=staff,
            service=service,
            client=client_user,
            created_by=org_admin_user,
            date=slot_date,
            start_time="11:00",
            customer_name="Asha",
            customer_email="asha@example.com",
            customer_phone="9876543210",
        )

        assert booking.active_slot == 1

        with pytest.raises(ValueError, match="slot unavailable"):
            book_slot(
                staff=staff,
                service=service,
                client=client_user,
                created_by=org_admin_user,
                date=slot_date,
                start_time="11:00",
                customer_name="Nisha",
                customer_email="nisha@example.com",
                customer_phone="9876543211",
            )

    def test_cancelled_booking_reopens_slot(self, organisation, client_user, org_admin_user):
        staff = Staff.objects.create(organisation=organisation, name="Dr. General", specialization="General", is_active=True)
        service = Service.objects.create(organisation=organisation, name="Consultation", duration_minutes=30, price=900, is_active=True)
        staff.services.add(service)

        slot_date = timezone.localdate() + timedelta(days=3)
        weekday = slot_date.weekday()
        WorkingHours.objects.create(staff=staff, day_of_week=weekday, start_time=time(9, 0), end_time=time(17, 0), is_off_day=False)

        booking = Booking.objects.create(
            organisation=organisation,
            client=client_user,
            created_by=org_admin_user,
            staff=staff,
            service=service,
            customer_name="Chetan",
            customer_email="chetan@example.com",
            customer_phone="9876543210",
            date=slot_date,
            start_time=time(11, 0),
            end_time=time(11, 30),
            status="confirmed",
        )

        booking.set_status("cancelled")
        booking.save()

        slots = generate_slots(staff, slot_date, service)
        assert "11:00" in [slot["start_time"] for slot in slots]
