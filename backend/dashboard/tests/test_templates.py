import re
from datetime import time, timedelta

import pytest
from django.utils import timezone

from scheduling.models import Service, Staff, WorkingHours


@pytest.mark.django_db
class TestPublicTemplates:
    def test_homepage_renders(self, client):
        response = client.get("/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Appointments, without the back-and-forth." in content
        assert "Register as Organisation" in content
        assert "Share your Org Code" in content
        assert "4.9/5" not in content
        assert "API health" not in content

        navigation = re.search(r'<nav class="nav-links"[^>]*>(.*?)</nav>', content, re.DOTALL)
        assert navigation is not None
        labels = re.findall(r">([^<>]+)</a>", navigation.group(1))
        assert labels == ["Home", "Book Now", "Register as Client", "Log in", "Register as Organisation"]

    def test_booking_page_gates_anonymous_visitors(self, client):
        response = client.get("/book/")
        content = response.content.decode("utf-8")

        assert response.status_code == 200
        assert "Log in to book with your salon" in content
        assert "Register as Client" in content
        assert "name=\"customer_email\"" not in content
        assert "Confirm booking" not in content

    def test_booking_page_renders_slots_for_verified_client(self, client, organisation, client_user):
        staff = Staff.objects.create(organisation=organisation, name="Anita Rao", specialization="General", is_active=True)
        service = Service.objects.create(organisation=organisation, name="Consultation", duration_minutes=30, price=500, is_active=True)
        staff.services.add(service)

        booking_date = timezone.localdate() + timedelta(days=1)
        weekday = booking_date.weekday()
        WorkingHours.objects.create(staff=staff, day_of_week=weekday, start_time=time(9, 0), end_time=time(17, 0), is_off_day=False)

        client.force_login(client_user)
        response = client.get(f"/book/?service={service.pk}&staff={staff.pk}&date={booking_date.isoformat()}")
        assert response.status_code == 200
        assert "09:00" in response.content.decode("utf-8")
        assert "Anita Rao" in response.content.decode("utf-8")
