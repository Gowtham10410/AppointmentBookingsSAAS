from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    EmailTokenObtainPairView,
    create_booking,
    healthz,
    list_services,
    list_staff,
    logout,
    lookup_org,
    me,
    staff_slots,
)

urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    path("orgs/lookup/", lookup_org, name="orgs-lookup"),
    path("services/", list_services, name="services"),
    path("staff/", list_staff, name="staff-list"),
    path("staff/<int:pk>/slots/", staff_slots, name="staff-slots"),
    path("bookings/", create_booking, name="bookings-create"),
    path("auth/login/", EmailTokenObtainPairView.as_view(), name="auth-login"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="auth-refresh"),
    path("auth/logout/", logout, name="auth-logout"),
    path("auth/me/", me, name="auth-me"),
    path("me/", me, name="me"),
]
