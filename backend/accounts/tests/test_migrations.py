from datetime import date, time

import pytest
from django.core.exceptions import FieldDoesNotExist
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

INITIAL_MIGRATIONS = [("accounts", "0001_initial"), ("scheduling", "0001_initial")]
TENANT_MIGRATIONS = [("accounts", "0002_organisation_and_verified_users"), ("scheduling", "0002_tenant_owned_records")]


@pytest.mark.django_db(transaction=True)
def test_fresh_migration_does_not_create_demo_data() -> None:
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate(INITIAL_MIGRATIONS)
        executor = MigrationExecutor(connection)
        executor.migrate(TENANT_MIGRATIONS)
        apps = executor.loader.project_state(TENANT_MIGRATIONS).apps
        Organisation = apps.get_model("accounts", "Organisation")
        assert Organisation.objects.count() == 0
    finally:
        MigrationExecutor(connection).migrate(latest)


@pytest.mark.django_db(transaction=True)
def test_existing_rows_backfill_to_demo_organisation_without_losing_snapshots() -> None:
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate(INITIAL_MIGRATIONS)
        old_apps = MigrationExecutor(connection).loader.project_state(INITIAL_MIGRATIONS).apps
        User = old_apps.get_model("accounts", "User")
        Service = old_apps.get_model("scheduling", "Service")
        Staff = old_apps.get_model("scheduling", "Staff")
        WorkingHours = old_apps.get_model("scheduling", "WorkingHours")
        Booking = old_apps.get_model("scheduling", "Booking")

        owner = User.objects.create(
            email="OWNER@EXAMPLE.COM",
            password="!",
            first_name="Priya",
            last_name="Owner",
            role="admin",
            is_active=True,
        )
        legacy_staff_user = User.objects.create(
            email="staff@example.com",
            password="!",
            first_name="Mira",
            last_name="Shah",
            role="staff",
            is_active=True,
        )
        service = Service.objects.create(name="Haircut", duration_minutes=30, price="500.00")
        staff = Staff.objects.create(user=legacy_staff_user, specialization="Stylist")
        WorkingHours.objects.create(staff=staff, day_of_week=0, start_time=time(9), end_time=time(17))
        booking = Booking.objects.create(
            staff=staff,
            service=service,
            customer_name="Existing Client",
            customer_email="client@example.com",
            customer_phone="9876543210",
            date=date(2027, 1, 4),
            start_time=time(10),
            end_time=time(10, 30),
            status="confirmed",
            active_slot=1,
        )

        MigrationExecutor(connection).migrate(TENANT_MIGRATIONS)
        new_apps = MigrationExecutor(connection).loader.project_state(TENANT_MIGRATIONS).apps
        NewUser = new_apps.get_model("accounts", "User")
        Organisation = new_apps.get_model("accounts", "Organisation")
        NewStaff = new_apps.get_model("scheduling", "Staff")
        NewService = new_apps.get_model("scheduling", "Service")
        NewBooking = new_apps.get_model("scheduling", "Booking")

        migrated_owner = NewUser.objects.get(pk=owner.pk)
        migrated_staff_user = NewUser.objects.get(pk=legacy_staff_user.pk)
        migrated_staff = NewStaff.objects.get(pk=staff.pk)
        migrated_service = NewService.objects.get(pk=service.pk)
        migrated_booking = NewBooking.objects.get(pk=booking.pk)
        organisation = Organisation.objects.get(pk=migrated_owner.organisation_id)

        assert organisation.name == "Demo Organisation"
        assert organisation.owner_id == migrated_owner.pk
        assert migrated_owner.email == "owner@example.com"
        assert migrated_owner.role == "org_admin"
        assert migrated_staff_user.role == "client"
        assert not migrated_staff_user.is_active
        assert migrated_staff.user_id is None
        assert migrated_staff.name == "Mira Shah"
        assert migrated_staff.organisation_id == organisation.pk
        assert migrated_service.organisation_id == organisation.pk
        assert migrated_booking.organisation_id == organisation.pk
        assert migrated_booking.client.is_active is False
        assert migrated_booking.client.role == "client"
        assert migrated_booking.created_by_id == migrated_owner.pk
        assert migrated_booking.customer_name == "Existing Client"
        assert migrated_booking.customer_email == "client@example.com"
        assert migrated_booking.customer_phone == "9876543210"
        with pytest.raises(FieldDoesNotExist):
            NewBooking._meta.get_field("cancel_token")
    finally:
        MigrationExecutor(connection).migrate(latest)