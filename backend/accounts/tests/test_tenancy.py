from datetime import timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from freezegun import freeze_time

from accounts.models import EmailToken, Organisation, User
from accounts.services.email_tokens import (
    EmailTokenPurpose,
    ExpiredEmailToken,
    InvalidEmailToken,
    consume_token,
    issue_token,
)
from accounts.services.org_code import (
    ORG_CODE_ALPHABET,
    OrgCodeGenerationError,
    generate_org_code,
    normalize_org_code,
)
from accounts.tenancy import IsClient, IsOrgAdmin, IsVerifiedUser, TenantScopedMixin
from scheduling.models import Booking, Service, Staff, WorkingHours
from scheduling.tenancy import assert_same_tenant


@pytest.mark.django_db
def test_org_code_format_alphabet_and_1000_unique_organisations() -> None:
    codes = [Organisation.objects.create(name=f"Glow Beauty {index}").org_code for index in range(1000)]

    assert len(set(codes)) == 1000
    assert all(code.startswith("GLOW-") for code in codes)
    assert all(len(code.split("-")[1]) == 5 for code in codes)
    assert all(set(code.split("-")[1]) <= set(ORG_CODE_ALPHABET) for code in codes)


@pytest.mark.parametrize(
    ("name", "prefix"),
    [("Glow Beauty", "GLOW"), ("Salon XYZ", "SALO"), ("AB", "ORG"), ("12人", "ORG"), ("Été Spa", "TSPA")],
)
@pytest.mark.django_db
def test_org_code_name_prefix_edge_cases(name: str, prefix: str) -> None:
    assert generate_org_code(name).startswith(f"{prefix}-")


@pytest.mark.django_db
def test_org_code_collision_retries_with_new_suffix() -> None:
    Organisation.objects.create(name="Glow Existing", org_code="GLOW-AAAAA")

    with patch("accounts.services.org_code._random_suffix", side_effect=["AAAAA", "BBBBB"]):
        assert generate_org_code("Glow Beauty") == "GLOW-BBBBB"


@pytest.mark.django_db
def test_org_code_generation_stops_after_ten_collisions() -> None:
    with patch("accounts.services.org_code._random_suffix", return_value="AAAAA"):
        Organisation.objects.create(name="Glow Existing", org_code="GLOW-AAAAA")
        with pytest.raises(OrgCodeGenerationError):
            generate_org_code("Glow Beauty")


def test_org_code_normalizes_spacing_and_unicode_dashes() -> None:
    assert normalize_org_code(" glow — 7k4q9 ") == "GLOW-7K4Q9"


@pytest.mark.django_db
def test_org_code_is_immutable_after_creation() -> None:
    organisation = Organisation.objects.create(name="Glow Beauty")
    organisation.org_code = "OTHER-7K4Q9"

    with pytest.raises(ValidationError, match="immutable"):
        organisation.save()


@pytest.mark.django_db
def test_organisation_validates_timezone_and_booking_settings() -> None:
    organisation = Organisation(name="Invalid timezone", timezone="Not/AZone")
    with pytest.raises(ValidationError, match="IANA"):
        organisation.full_clean()

    organisation = Organisation(name="Invalid lead", min_lead_minutes=1441)
    with pytest.raises(ValidationError):
        organisation.full_clean()


@pytest.mark.django_db
def test_user_email_is_normalized_and_case_insensitively_unique(organisation) -> None:
    user = User.objects.create_user(
        email="CLIENT@Example.com",
        password="secret123",
        full_name="Client One",
        organisation=organisation,
        role="client",
    )
    assert User.objects.get(pk=user.pk).email == "client@example.com"

    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user(
            email="Client@example.com",
            password="secret123",
            full_name="Client Duplicate",
            organisation=organisation,
            role="client",
        )


@pytest.mark.django_db
def test_create_superuser_bootstraps_owned_organisation() -> None:
    user = User.objects.create_superuser(email="root@example.com", password="secret123")

    assert user.organisation.owner == user
    assert user.role == "org_admin"
    assert user.email_verified_at is not None
    assert user.organisation.org_code.startswith("ROOT-")


@pytest.mark.django_db
def test_email_token_stores_hash_and_consumes_once(client_user) -> None:
    plaintext = issue_token(client_user, "verify_email")
    token = EmailToken.objects.get(user=client_user)

    assert token.token_hash != plaintext
    assert len(token.token_hash) == 64
    assert token.expires_at - token.created_at <= timedelta(hours=24, seconds=2)
    assert consume_token(plaintext, "verify_email").pk == token.pk
    token.refresh_from_db()
    assert token.used_at is not None

    with pytest.raises(InvalidEmailToken):
        consume_token(plaintext, "verify_email")


@pytest.mark.django_db
def test_issuing_new_email_token_invalidates_previous_token(client_user) -> None:
    earlier = issue_token(client_user, "verify_email")
    newer = issue_token(client_user, "verify_email")

    assert EmailToken.objects.filter(user=client_user, purpose="verify_email", used_at__isnull=True).count() == 1
    with pytest.raises(InvalidEmailToken):
        consume_token(earlier, "verify_email")
    assert consume_token(newer, "verify_email").user == client_user


@pytest.mark.django_db
def test_email_token_rejects_expired_tampered_and_wrong_purpose(client_user) -> None:
    plaintext = issue_token(client_user, "verify_email")
    with freeze_time(timezone.now() + timedelta(hours=25)):
        with pytest.raises(ExpiredEmailToken):
            consume_token(plaintext, "verify_email")

    with pytest.raises(InvalidEmailToken):
        consume_token(f"{plaintext}tampered", "verify_email")
    with pytest.raises(InvalidEmailToken):
        consume_token(plaintext, "reset_password")


@pytest.mark.django_db
def test_email_token_services_reject_unsupported_purposes(client_user) -> None:
    unsupported = cast(EmailTokenPurpose, "unsupported")
    with pytest.raises(ValueError, match="Unsupported"):
        issue_token(client_user, unsupported)
    with pytest.raises(ValueError, match="Unsupported"):
        consume_token("token", unsupported)


@pytest.mark.django_db
def test_tenant_querysets_scope_direct_and_related_models(organisation):
    other = Organisation.objects.create(name="Other Salon")
    target_service = Service.objects.create(organisation=organisation, name="Target", duration_minutes=30)
    Service.objects.create(organisation=other, name="Other", duration_minutes=30)
    target_staff = Staff.objects.create(organisation=organisation, name="Target Staff")
    Staff.objects.create(organisation=other, name="Other Staff")
    target_hours = WorkingHours.objects.create(staff=target_staff, day_of_week=0, start_time="09:00", end_time="17:00")

    assert list(Service.objects.for_org(organisation)) == [target_service]
    assert list(Staff.objects.for_org(organisation)) == [target_staff]
    assert list(WorkingHours.objects.for_org(organisation)) == [target_hours]
    assert not Service.objects.for_org(None).exists()


@pytest.mark.django_db
def test_tenant_scoped_mixin_filters_by_authenticated_user(organisation, client_user):
    from rest_framework.generics import GenericAPIView

    other = Organisation.objects.create(name="Other Salon")
    target = Service.objects.create(organisation=organisation, name="Target", duration_minutes=30)
    Service.objects.create(organisation=other, name="Other", duration_minutes=30)

    class ServiceView(TenantScopedMixin, GenericAPIView):
        queryset = Service.objects.all()

    view = ServiceView()
    view.request = SimpleNamespace(user=client_user)
    assert list(view.get_queryset()) == [target]


@pytest.mark.django_db
def test_tenant_scoped_mixin_returns_empty_for_anonymous_or_unassigned_user():
    from django.contrib.auth.models import AnonymousUser
    from rest_framework.generics import GenericAPIView

    class ServiceView(TenantScopedMixin, GenericAPIView):
        queryset = Service.objects.all()

    view = ServiceView()
    view.request = SimpleNamespace(user=AnonymousUser())
    assert not view.get_queryset().exists()

    view.request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, organisation_id=None))
    assert not view.get_queryset().exists()


@pytest.mark.django_db
def test_tenant_scoped_mixin_rejects_queryset_without_tenant_manager(client_user):
    class QuerysetBase:
        def get_queryset(self):
            return []

    class UnsafeView(TenantScopedMixin, QuerysetBase):
        request = SimpleNamespace(user=client_user)

    view = UnsafeView()
    with pytest.raises(TypeError, match="TenantManager"):
        view.get_queryset()


@pytest.mark.django_db
def test_role_and_verified_permissions(org_admin_user, client_user):
    client_user.email_verified_at = timezone.now()
    assert IsOrgAdmin().has_permission(SimpleNamespace(user=org_admin_user), None)
    assert IsClient().has_permission(SimpleNamespace(user=client_user), None)
    assert IsVerifiedUser().has_permission(SimpleNamespace(user=client_user), None)
    assert not IsVerifiedUser().has_permission(SimpleNamespace(user=org_admin_user), None)


@pytest.mark.django_db
def test_same_tenant_invariant_rejects_mismatched_resources(organisation, service):
    staff = Staff.objects.create(organisation=organisation, name="Same tenant")
    assert_same_tenant(staff, service)

    other = Organisation.objects.create(name="Other Salon")
    foreign_staff = Staff.objects.create(organisation=other, name="Foreign")
    with pytest.raises(ValueError, match="same organisation"):
        assert_same_tenant(foreign_staff, service)

    with pytest.raises(ValueError, match="belong to an organisation"):
        assert_same_tenant(WorkingHours())


@pytest.mark.django_db
def test_booking_factory_builds_consistent_tenant_graph(booking: Booking) -> None:
    assert_same_tenant(booking, booking.staff, booking.service, booking.client, booking.created_by)
    assert booking.customer_name == booking.client.full_name
    assert booking.customer_email == booking.client.email