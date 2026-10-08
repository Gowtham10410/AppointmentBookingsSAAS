from django.contrib import admin
from django.urls import include, path

from dashboard.views import (
    book_page,
    booking_success,
    check_email,
    home_page,
    login_portal,
    logout_portal,
    org_dashboard,
    register_client,
    register_organisation,
    resend_verification_email,
    verify_email,
)

urlpatterns = [
    path("", home_page, name="home"),
    path("book/", book_page, name="book"),
    path("register/client/", register_client, name="register_client"),
    path("register/organisation/", register_organisation, name="register_organisation"),
    path("login/", login_portal, name="login"),
    path("logout/", logout_portal, name="logout"),
    path("check-email/", check_email, name="check_email"),
    path("resend-verification/", resend_verification_email, name="resend_verification"),
    path("verify-email/", verify_email, name="verify_email"),
    path("dashboard/", org_dashboard, name="org_dashboard"),
    path("booking/<int:pk>/confirmation/", booking_success, name="booking_success"),
    path("admin/", admin.site.urls),
    path("api/", include("dashboard.urls")),
]
