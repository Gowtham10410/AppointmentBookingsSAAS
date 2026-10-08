import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def backfill_scheduling(apps, schema_editor):
    alias = schema_editor.connection.alias
    Organisation = apps.get_model("accounts", "Organisation")
    User = apps.get_model("accounts", "User")
    Service = apps.get_model("scheduling", "Service")
    Staff = apps.get_model("scheduling", "Staff")
    Booking = apps.get_model("scheduling", "Booking")

    organisation = Organisation.objects.using(alias).filter(org_code__startswith="DEMO-").first()
    if organisation is None:
        if Service.objects.using(alias).exists() or Staff.objects.using(alias).exists() or Booking.objects.using(alias).exists():
            raise RuntimeError("Scheduling rows exist without the Demo Organisation account backfill.")
        return

    owner = organisation.owner
    if owner is None:
        raise RuntimeError("The Demo Organisation must have an owner before booking records are migrated.")

    for service in Service.objects.using(alias).all().iterator():
        service.organisation_id = organisation.pk
        service.save(using=alias, update_fields=["organisation"])

    for staff in Staff.objects.using(alias).select_related("user").all().iterator():
        user = staff.user
        staff.name = (user.full_name or "").strip() or f"{user.first_name} {user.last_name}".strip() or user.email
        staff.organisation_id = organisation.pk
        staff.user_id = None
        staff.save(using=alias, update_fields=["name", "organisation", "user"])

    for booking in Booking.objects.using(alias).all().iterator():
        if booking.client_id:
            continue
        email = f"legacy-booking-{booking.pk}@migration.invalid"
        suffix = 1
        while User.objects.using(alias).filter(email__iexact=email).exists():
            email = f"legacy-booking-{booking.pk}-{suffix}@migration.invalid"
            suffix += 1
        client = User.objects.using(alias).create(
            email=email,
            password="!",
            full_name=booking.customer_name,
            phone=booking.customer_phone,
            role="client",
            organisation_id=organisation.pk,
            is_active=False,
            is_staff=False,
            is_superuser=False,
        )
        booking.organisation_id = organisation.pk
        booking.client_id = client.pk
        booking.created_by_id = owner.pk
        booking.save(using=alias, update_fields=["organisation", "client", "created_by"])


def reverse_backfill_scheduling(apps, schema_editor):
    alias = schema_editor.connection.alias
    User = apps.get_model("accounts", "User")
    Service = apps.get_model("scheduling", "Service")
    Staff = apps.get_model("scheduling", "Staff")
    Booking = apps.get_model("scheduling", "Booking")

    legacy_client_ids = []
    for booking in Booking.objects.using(alias).all().iterator():
        if booking.client_id:
            legacy_client_ids.append(booking.client_id)
        booking.organisation_id = None
        booking.client_id = None
        booking.created_by_id = None
        booking.save(using=alias, update_fields=["organisation", "client", "created_by"])
    Service.objects.using(alias).update(organisation=None)
    Staff.objects.using(alias).update(organisation=None)
    User.objects.using(alias).filter(pk__in=legacy_client_ids, email__contains="@migration.invalid").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_organisation_and_verified_users"),
        ("scheduling", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="service",
            name="organisation",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="services", to="accounts.organisation"),
        ),
        migrations.AddField(
            model_name="staff",
            name="organisation",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="staff_members", to="accounts.organisation"),
        ),
        migrations.AddField(
            model_name="staff",
            name="name",
            field=models.CharField(max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="staff",
            name="phone",
            field=models.CharField(blank=True, max_length=15, default=""),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="staff",
            name="user",
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="staff_profile", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="booking",
            name="organisation",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="bookings", to="accounts.organisation"),
        ),
        migrations.AddField(
            model_name="booking",
            name="client",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="client_bookings", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="booking",
            name="created_by",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="created_bookings", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="booking",
            name="cancelled_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="booking",
            name="cancelled_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="cancelled_bookings", to=settings.AUTH_USER_MODEL),
        ),
        migrations.RunPython(backfill_scheduling, reverse_backfill_scheduling),
        migrations.AlterField(
            model_name="service",
            name="organisation",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="services", to="accounts.organisation"),
        ),
        migrations.AlterField(
            model_name="staff",
            name="organisation",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="staff_members", to="accounts.organisation"),
        ),
        migrations.AlterField(
            model_name="staff",
            name="name",
            field=models.CharField(max_length=100),
        ),
        migrations.AlterField(
            model_name="booking",
            name="organisation",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="bookings", to="accounts.organisation"),
        ),
        migrations.AlterField(
            model_name="booking",
            name="client",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="client_bookings", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name="booking",
            name="created_by",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="created_bookings", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddIndex(
            model_name="booking",
            index=models.Index(fields=["organisation", "date"], name="booking_org_date_idx"),
        ),
        migrations.AddIndex(
            model_name="booking",
            index=models.Index(fields=["organisation", "status"], name="booking_org_status_idx"),
        ),
        migrations.RemoveField(
            model_name="booking",
            name="cancel_token",
        ),
    ]