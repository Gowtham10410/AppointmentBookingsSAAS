import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models.functions import Lower


def backfill_accounts(apps, schema_editor):
    alias = schema_editor.connection.alias
    User = apps.get_model("accounts", "User")
    Organisation = apps.get_model("accounts", "Organisation")
    Service = apps.get_model("scheduling", "Service")
    Staff = apps.get_model("scheduling", "Staff")
    Booking = apps.get_model("scheduling", "Booking")

    users = list(User.objects.using(alias).order_by("pk"))
    normalized_emails = {}
    for user in users:
        normalized = user.email.strip().lower()
        if normalized in normalized_emails:
            raise RuntimeError(
                "Cannot normalize duplicate case-insensitive email addresses for user IDs "
                f"{normalized_emails[normalized]} and {user.pk}. Resolve the collision, then retry."
            )
        normalized_emails[normalized] = user.pk

    has_existing_data = bool(users) or Service.objects.using(alias).exists() or Staff.objects.using(alias).exists() or Booking.objects.using(alias).exists()
    if not has_existing_data:
        return

    owner = next((user for user in users if user.role == "admin"), None)
    if owner is None:
        owner_email = "migration-owner@demo.invalid"
        suffix = 1
        while User.objects.using(alias).filter(email__iexact=owner_email).exists():
            owner_email = f"migration-owner-{suffix}@demo.invalid"
            suffix += 1
        owner = User.objects.using(alias).create(
            email=owner_email,
            password="!",
            first_name="Demo",
            last_name="Owner",
            full_name="Demo Owner",
            role="org_admin",
            is_active=False,
            is_staff=False,
            is_superuser=False,
        )

    code = "DEMO-7K4Q9"
    suffix = 1
    while Organisation.objects.using(alias).filter(org_code=code).exists():
        code = f"DEMO-{suffix:05d}"
        suffix += 1
    organisation = Organisation.objects.using(alias).create(
        name="Demo Organisation",
        business_type="other",
        org_code=code,
        owner_id=owner.pk,
    )

    for user in users:
        original_role = user.role
        user.email = user.email.strip().lower()
        user.full_name = " ".join(part for part in [user.first_name, user.last_name] if part).strip() or user.email.split("@", maxsplit=1)[0]
        user.organisation_id = organisation.pk
        if original_role == "admin":
            user.role = "org_admin"
        else:
            user.role = "client"
            user.is_active = False
            user.email_verified_at = None
        user.save(using=alias, update_fields=["email", "full_name", "organisation", "role", "is_active", "email_verified_at"])

    if owner.pk not in {user.pk for user in users}:
        owner.organisation_id = organisation.pk
        owner.save(using=alias, update_fields=["organisation"])


def reverse_backfill_accounts(apps, schema_editor):
    alias = schema_editor.connection.alias
    User = apps.get_model("accounts", "User")
    Organisation = apps.get_model("accounts", "Organisation")
    organisation = Organisation.objects.using(alias).filter(org_code__startswith="DEMO-").first()
    if organisation is None:
        return

    users = User.objects.using(alias).filter(organisation_id=organisation.pk)
    for user in users:
        user.organisation_id = None
        if user.role == "org_admin":
            user.role = "admin"
        elif user.role == "client" and not user.is_active:
            user.role = "staff"
        user.save(using=alias, update_fields=["organisation", "role"])
    owner_id = organisation.owner_id
    organisation.owner_id = None
    organisation.save(using=alias, update_fields=["owner"])
    if owner_id and User.objects.using(alias).filter(pk=owner_id, email__startswith="migration-owner").exists():
        User.objects.using(alias).filter(pk=owner_id).delete()
    organisation.delete(using=alias)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        ("scheduling", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Organisation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("business_type", models.CharField(choices=[("salon", "Salon"), ("beauty_parlour", "Beauty parlour"), ("spa", "Spa"), ("barbershop", "Barbershop"), ("clinic", "Clinic"), ("other", "Other")], default="salon", max_length=20)),
                ("org_code", models.CharField(blank=True, max_length=16, unique=True)),
                ("phone", models.CharField(blank=True, max_length=15)),
                ("address_line", models.CharField(blank=True, max_length=255)),
                ("city", models.CharField(blank=True, max_length=100)),
                ("state", models.CharField(blank=True, max_length=100)),
                ("postal_code", models.CharField(blank=True, max_length=20)),
                ("country", models.CharField(default="India", max_length=100)),
                ("timezone", models.CharField(default="Asia/Kolkata", max_length=64)),
                ("buffer_minutes", models.PositiveSmallIntegerField(default=10, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(60)])),
                ("min_lead_minutes", models.PositiveSmallIntegerField(default=30, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(1440)])),
                ("booking_window_days", models.PositiveSmallIntegerField(default=30, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(180)])),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("owner", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="owned_organisation", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "constraints": [
                    models.CheckConstraint(condition=models.Q(("buffer_minutes__gte", 0), ("buffer_minutes__lte", 60)), name="org_buffer_range"),
                    models.CheckConstraint(condition=models.Q(("min_lead_minutes__gte", 0), ("min_lead_minutes__lte", 1440)), name="org_lead_range"),
                    models.CheckConstraint(condition=models.Q(("booking_window_days__gte", 1), ("booking_window_days__lte", 180)), name="org_window_range"),
                ],
            },
        ),
        migrations.AddField(
            model_name="user",
            name="full_name",
            field=models.CharField(max_length=150, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="phone",
            field=models.CharField(blank=True, max_length=15, default=""),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="user",
            name="email_verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="organisation",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="members", to="accounts.organisation"),
        ),
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(choices=[("org_admin", "Organisation admin"), ("client", "Client")], default="client", max_length=20),
        ),
        migrations.CreateModel(
            name="EmailToken",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("purpose", models.CharField(choices=[("verify_email", "Verify email"), ("reset_password", "Reset password")], max_length=20)),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("expires_at", models.DateTimeField()),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="email_tokens", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddIndex(
            model_name="emailtoken",
            index=models.Index(fields=["user", "purpose", "used_at"], name="email_token_active_idx"),
        ),
        migrations.RunPython(backfill_accounts, reverse_backfill_accounts),
        migrations.AlterField(
            model_name="user",
            name="full_name",
            field=models.CharField(max_length=150),
        ),
        migrations.AlterField(
            model_name="user",
            name="organisation",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="members", to="accounts.organisation"),
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(Lower("email"), name="user_email_case_insensitive_unique"),
        ),
    ]