from datetime import date, time

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from scheduling.models import Booking, Service, Staff, WorkingHours


@pytest.mark.django_db
class TestSchedulingModels:
    def test_reference_format_and_cancel_token_was_removed(self, organisation, client_user, org_admin_user):
        staff = Staff.objects.create(organisation=organisation, name="Dr. Rao", specialization="Dentistry")
        service = Service.objects.create(organisation=organisation, name="Consultation", duration_minutes=60, price=1200)

        booking = Booking.objects.create(
            organisation=organisation,
            client=client_user,
            created_by=org_admin_user,
            staff=staff,
            service=service,
            customer_name="Priya Rao",
            customer_email="priya@example.com",
            customer_phone="9876543210",
            date=date(2027, 1, 10),
            start_time=time(9, 0),
            end_time=time(9, 30),
        )

        assert booking.reference.startswith("SAS-")
        assert not hasattr(booking, "cancel_token")

        booking.customer_name = "Changed after booking"
        with pytest.raises(ValidationError, match="snapshots are immutable"):
            booking.save()

    def test_booking_clean_rejects_cross_tenant_relations(self, organisation, client_user, org_admin_user):
        other = type(organisation).objects.create(name="Other Salon")
        foreign_staff = Staff.objects.create(organisation=other, name="Foreign staff")
        service = Service.objects.create(organisation=organisation, name="Consultation", duration_minutes=60)
        booking = Booking(
            organisation=organisation,
            client=client_user,
            created_by=org_admin_user,
            staff=foreign_staff,
            service=service,
            customer_name=client_user.full_name,
            customer_email=client_user.email,
            customer_phone=client_user.phone,
            date=date(2027, 1, 10),
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        with pytest.raises(ValidationError, match="same organisation"):
            booking.full_clean()

    def test_duplicate_active_slot_is_rejected_by_database(self, organisation, client_user, org_admin_user):
        staff = Staff.objects.create(organisation=organisation, name="Dr. Dental", specialization="Dental")
        service = Service.objects.create(organisation=organisation, name="Checkup", duration_minutes=30, price=900)

        Booking.objects.create(
            organisation=organisation,
            client=client_user,
            created_by=org_admin_user,
            staff=staff,
            service=service,
            customer_name="A",
            customer_email="a@example.com",
            customer_phone="9876543210",
            date=date(2027, 1, 15),
            start_time=time(10, 0),
            end_time=time(10, 30),
            status="confirmed",
        )

        with pytest.raises(IntegrityError):
            Booking.objects.create(
                organisation=organisation,
                client=client_user,
                created_by=org_admin_user,
                staff=staff,
                service=service,
                customer_name="B",
                customer_email="b@example.com",
                customer_phone="9876543211",
                date=date(2027, 1, 15),
                start_time=time(10, 0),
                end_time=time(10, 30),
                status="confirmed",
            )

    def test_active_slot_is_cleared_on_cancel_and_restored_on_rebooking(self, organisation, client_user, org_admin_user):
        staff = Staff.objects.create(organisation=organisation, name="Dr. Cardio", specialization="Cardio")
        service = Service.objects.create(organisation=organisation, name="Follow-up", duration_minutes=45, price=1500)

        booking = Booking.objects.create(
            organisation=organisation,
            client=client_user,
            created_by=org_admin_user,
            staff=staff,
            service=service,
            customer_name="Ramesh",
            customer_email="ramesh@example.com",
            customer_phone="9876543210",
            date=date(2027, 1, 20),
            start_time=time(11, 0),
            end_time=time(11, 45),
            status="confirmed",
        )

        assert booking.active_slot == 1

        booking.set_status("cancelled")
        booking.save()
        booking.refresh_from_db()
        assert booking.active_slot is None
        assert booking.status == "cancelled"

        replacement = Booking.objects.create(
            organisation=organisation,
            client=client_user,
            created_by=org_admin_user,
            staff=staff,
            service=service,
            customer_name="Ramesh",
            customer_email="ramesh@example.com",
            customer_phone="9876543210",
            date=date(2027, 1, 20),
            start_time=time(11, 0),
            end_time=time(11, 45),
            status="confirmed",
        )
        replacement.refresh_from_db()
        assert replacement.active_slot == 1

    def test_working_hours_constraint_and_staff_relationship(self, organisation):
        staff = Staff.objects.create(organisation=organisation, name="Therapist", specialization="Therapy")
        service = Service.objects.create(organisation=organisation, name="Therapy", duration_minutes=60, price=1000)
        staff.services.add(service)

        hours = WorkingHours.objects.create(staff=staff, day_of_week=0, start_time=time(9, 0), end_time=time(17, 0))
        assert hours.staff == staff
        assert hours.day_of_week == 0

        with pytest.raises(IntegrityError):
            WorkingHours.objects.create(staff=staff, day_of_week=0, start_time=time(9, 0), end_time=time(17, 0))

    def test_service_and_booking_constraints(self, organisation):
        with pytest.raises(IntegrityError), transaction.atomic():
            Service.objects.create(organisation=organisation, name="Bad", duration_minutes=0, price=-1)

        invalid_service = Service(organisation=organisation, name="Bad", duration_minutes=0, price=-1)
        with pytest.raises(ValidationError):
            invalid_service.full_clean()
