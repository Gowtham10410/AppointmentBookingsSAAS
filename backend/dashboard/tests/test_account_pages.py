import re

import pytest
from django.core import mail
from django.utils import timezone

from accounts.models import User

OWNER_DATA = {
    "full_name": "Maya Owner",
    "email": "maya.owner@example.com",
    "phone": "9876543210",
    "password": "Violet-Trail-2026!",
    "terms": "on",
    "organisation_name": "Glow Beauty Parlour",
    "business_type": "beauty_parlour",
    "organisation_phone": "9123456780",
    "address_line": "14 Market Road",
    "city": "Chennai",
    "state": "Tamil Nadu",
    "postal_code": "600001",
}


CLIENT_DATA = {
    "full_name": "Asha Client",
    "email": "asha.client@example.com",
    "phone": "9876543211",
    "password": "Violet-Trail-2026!",
}


def verification_token_from_last_email() -> str:
    match = re.search(r"[?&]token=([^\s]+)", str(mail.outbox[-1].body))
    assert match is not None
    return match.group(1)


@pytest.mark.django_db
def test_owner_registration_verification_portal_login_and_welcome(client, django_capture_on_commit_callbacks):
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post("/register/organisation/", OWNER_DATA)

    assert response.status_code == 302
    assert response["Location"].startswith("/check-email/")
    user = User.objects.get(email=OWNER_DATA["email"])
    organisation = user.organisation
    assert organisation.owner == user
    assert user.role == "org_admin"
    assert user.email_verified_at is None
    assert mail.outbox and "verify-email" in mail.outbox[-1].body

    verify_response = client.get(f"/verify-email/?token={verification_token_from_last_email()}")
    assert verify_response.status_code == 200
    assert "Your email is verified" in verify_response.content.decode()
    user.refresh_from_db()
    assert user.email_verified_at is not None

    login_response = client.post(
        "/login/",
        {"portal": "organisation", "email": user.email, "password": OWNER_DATA["password"]},
    )
    assert login_response.status_code == 302
    assert login_response["Location"] == "/dashboard/"

    welcome = client.get("/dashboard/")
    assert welcome.status_code == 200
    assert organisation.org_code in welcome.content.decode()
    assert "Set working hours" in welcome.content.decode()


@pytest.mark.django_db
def test_client_registration_live_org_preview_verification_and_portal_login(
    client,
    organisation,
    django_capture_on_commit_callbacks,
):
    mail.outbox.clear()
    owner = organisation.owner
    owner.email_verified_at = timezone.now()
    owner.save(update_fields=["email_verified_at"])

    register_page = client.get(f"/register/client/?org={organisation.org_code.lower()}")
    assert register_page.status_code == 200
    assert organisation.name.encode() in register_page.content

    lookup = client.get(f"/api/orgs/lookup/?code={organisation.org_code.lower()}")
    assert lookup.status_code == 200
    assert lookup.json() == {
        "name": organisation.name,
        "city": organisation.city,
        "state": organisation.state,
        "business_type": organisation.business_type,
    }
    assert "org_code" not in lookup.json()

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            "/register/client/",
            {**CLIENT_DATA, "org_code": f" {organisation.org_code.lower()} "},
        )
    assert response.status_code == 302
    user = User.objects.get(email=CLIENT_DATA["email"])
    assert user.organisation == organisation
    assert user.role == "client"
    assert user.email_verified_at is None

    wrong_portal = client.post(
        "/login/",
        {"portal": "client", "email": user.email, "password": CLIENT_DATA["password"]},
    )
    assert wrong_portal.status_code == 200
    assert b"verify your email" in wrong_portal.content

    token = verification_token_from_last_email()
    assert client.get(f"/verify-email/?token={token}").status_code == 200
    user.refresh_from_db()
    assert user.email_verified_at is not None

    login_response = client.post(
        "/login/",
        {"portal": "client", "email": user.email, "password": CLIENT_DATA["password"]},
    )
    assert login_response.status_code == 302
    assert login_response["Location"] == "/book/"
    booking_page = client.get("/book/")
    assert "Log in to book with your salon" not in booking_page.content.decode()
    assert organisation.name.encode() in booking_page.content


@pytest.mark.django_db
def test_wrong_portal_and_unverified_owner_login_are_friendly(client):
    owner_response = client.post("/register/organisation/", OWNER_DATA)
    assert owner_response.status_code == 302
    owner = User.objects.get(email=OWNER_DATA["email"])

    unverified = client.post(
        "/login/",
        {"portal": "organisation", "email": owner.email, "password": OWNER_DATA["password"]},
    )
    assert b"verify your email" in unverified.content

    owner.email_verified_at = timezone.now()
    owner.save(update_fields=["email_verified_at"])
    wrong_portal = client.post(
        "/login/",
        {"portal": "client", "email": owner.email, "password": OWNER_DATA["password"]},
    )
    assert b"This is an organisation account" in wrong_portal.content


@pytest.mark.django_db
def test_org_lookup_is_generic_for_unknown_and_unverified_organisations(client, organisation):
    owner = organisation.owner
    owner.email_verified_at = None
    owner.save(update_fields=["email_verified_at"])
    unverified = client.get(f"/api/orgs/lookup/?code={organisation.org_code}")
    unknown = client.get("/api/orgs/lookup/?code=OTHER-7K4Q9")

    assert unverified.status_code == 404
    assert unknown.status_code == 404
    assert unverified.json() == unknown.json()
    assert unverified.json()["code"] == "org_not_found"


@pytest.mark.django_db
def test_resend_verification_has_generic_response_for_unknown_and_unverified_emails(
    client,
    organisation,
    django_capture_on_commit_callbacks,
):
    mail.outbox.clear()
    known_email = organisation.owner.email
    with django_capture_on_commit_callbacks(execute=True):
        known = client.post("/resend-verification/", {"email": known_email})
    unknown = client.post("/resend-verification/", {"email": "unknown@example.com"})

    assert known.status_code == 200
    assert unknown.status_code == 200
    assert b"If the address is registered" in known.content
    assert b"If the address is registered" in unknown.content
    assert len(mail.outbox) == 1
