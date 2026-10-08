from __future__ import annotations

from django.db import models
from rest_framework.permissions import BasePermission


class TenantQuerySet(models.QuerySet):
    def for_org(self, organisation):
        if organisation is None:
            return self.none()
        field_names = {field.name for field in self.model._meta.get_fields()}
        lookup = "organisation" if "organisation" in field_names else "staff__organisation"
        return self.filter(**{lookup: organisation})


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    """Queryset manager requiring tenant-aware reads for tenant-owned records."""


class TenantScopedMixin:
    def get_queryset(self):
        queryset = super().get_queryset()
        request = getattr(self, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated or user.organisation_id is None:
            return queryset.none()
        if not hasattr(queryset, "for_org"):
            raise TypeError("Tenant-scoped views must use TenantManager querysets.")
        return queryset.for_org(user.organisation)


class IsVerifiedUser(BasePermission):
    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.email_verified_at is not None)


class IsOrgAdmin(BasePermission):
    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.role == "org_admin")


class IsClient(BasePermission):
    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.role == "client")