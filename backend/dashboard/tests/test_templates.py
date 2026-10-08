from datetime import time, timedelta

import pytest
from django.utils import timezone

from scheduling.models import Service, Staff, WorkingHours


@pytest.mark.django_db
class TestPublicTemplates:
    def test_homepage_renders(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "Smart Appointment Scheduler" in response.content.decode("utf-8")

    def test_booking_page_renders_slots(self, client, organisation):
        staff = Staff.objects.create(organisation=organisation, name="Anita Rao", specialization="General", is_active=True)
        service = Service.objects.create(organisation=organisation, name="Consultation", duration_minutes=30, price=500, is_active=True)
        staff.services.add(service)

        booking_date = timezone.localdate() + timedelta(days=1)
        weekday = booking_date.weekday()
        WorkingHours.objects.create(staff=staff, day_of_week=weekday, start_time=time(9, 0), end_time=time(17, 0), is_off_day=False)

        response = client.get(f"/book/?service={service.pk}&staff={staff.pk}&date={booking_date.isoformat()}")
        assert response.status_code == 200
        assert "09:00" in response.content.decode("utf-8")
