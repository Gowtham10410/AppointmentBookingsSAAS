from datetime import time, timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Organisation
from scheduling.models import Booking, Service, Staff, WorkingHours


@pytest.mark.django_db
class TestPublicApi:
    def test_services_and_staff_endpoints(self, organisation, client_user):
        staff = Staff.objects.create(organisation=organisation, name="Dr. Mira", specialization="General", is_active=True)
        service = Service.objects.create(organisation=organisation, name="Consultation", duration_minutes=30, price=500, is_active=True)
        staff.services.add(service)

        client = APIClient()
        client.force_authenticate(user=client_user)

        services_response = client.get("/api/services/")
        assert services_response.status_code == 200
        assert services_response.json()[0]["name"] == "Consultation"

        staff_response = client.get(f"/api/staff/?service={service.pk}")
        assert staff_response.status_code == 200
        assert staff_response.json()[0]["id"] == staff.pk
        assert staff_response.json()[0]["name"] == "Dr. Mira"

    def test_catalogue_slots_and_booking_ids_do_not_cross_tenants(self, organisation, client_user):
        other = Organisation.objects.create(name="Other Salon")
        own_service = Service.objects.create(organisation=organisation, name="Own", duration_minutes=30)
        foreign_service = Service.objects.create(organisation=other, name="Foreign", duration_minutes=30)
        own_staff = Staff.objects.create(organisation=organisation, name="Own Staff")
        foreign_staff = Staff.objects.create(organisation=other, name="Foreign Staff")
        booking_date = timezone.localdate() + timedelta(days=1)

        client = APIClient()
        client.force_authenticate(user=client_user)

        services_response = client.get("/api/services/")
        assert [item["name"] for item in services_response.json()] == ["Own"]

        staff_response = client.get("/api/staff/")
        assert [item["name"] for item in staff_response.json()] == ["Own Staff"]

        foreign_staff_slots = client.get(
            f"/api/staff/{foreign_staff.pk}/slots/?date={booking_date.isoformat()}&service={own_service.pk}"
        )
        assert foreign_staff_slots.status_code == 404

        foreign_service_slots = client.get(
            f"/api/staff/{own_staff.pk}/slots/?date={booking_date.isoformat()}&service={foreign_service.pk}"
        )
        assert foreign_service_slots.status_code == 404

        booking_response = client.post(
            "/api/bookings/",
            {
                "staff": foreign_staff.pk,
                "service": foreign_service.pk,
                "date": booking_date.isoformat(),
                "start_time": "09:00",
                "customer_name": "Test Client",
                "customer_email": client_user.email,
                "customer_phone": client_user.phone,
            },
            format="json",
        )
        assert booking_response.status_code == 404

    def test_booking_creation_requires_client_identity(self, organisation, client_user, org_admin_user):
        staff = Staff.objects.create(organisation=organisation, name="Dr. Asha", specialization="Dermatology", is_active=True)
        service = Service.objects.create(organisation=organisation, name="Skin consult", duration_minutes=30, price=800, is_active=True)
        staff.services.add(service)

        booking_date = timezone.localdate() + timedelta(days=1)
        weekday = booking_date.weekday()
        WorkingHours.objects.create(staff=staff, day_of_week=weekday, start_time=time(9, 0), end_time=time(17, 0), is_off_day=False)

        client = APIClient()
        client.force_authenticate(user=client_user)
        response = client.post(
            "/api/bookings/",
            {
                "staff": staff.pk,
                "service": service.pk,
                "date": booking_date.isoformat(),
                "start_time": "09:00",
                "customer_name": "Priya Rao",
                "customer_email": "priya@example.com",
                "customer_phone": "9876543210",
            },
            format="json",
        )

        assert response.status_code == 201
        assert response.json()["reference"].startswith("SAS-")
        assert Booking.objects.count() == 1
        booking = Booking.objects.get()
        assert booking.organisation == organisation
        assert booking.client == client_user
        assert booking.created_by == client_user
        assert booking.customer_name == client_user.full_name
        assert booking.customer_email == client_user.email
        assert booking.customer_phone == client_user.phone

    def test_booking_creation_requires_authentication(self):
        response = APIClient().post("/api/bookings/", {}, format="json")
        assert response.status_code == 401

    def test_login_returns_tokens(self, client_user):
        client = APIClient()
        response = client.post("/api/auth/login/", {"email": client_user.email, "password": "secret123"}, format="json")

        assert response.status_code == 200
        assert "access" in response.json()
        assert "refresh" in response.json()
