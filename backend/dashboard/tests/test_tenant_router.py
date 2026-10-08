from collections.abc import Iterator

import pytest
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.permissions import AllowAny

from accounts.tenancy import TenantScopedMixin

TENANT_SCOPE_EXCEPTIONS = {
    "bookings-create": "The booking service validates staff, service, client and creator tenant identity before persistence.",
    "services": "The function view builds its queryset with TenantManager.for_org(request.user.organisation).",
    "staff-list": "The function view builds staff/service querysets with TenantManager.for_org(request.user.organisation).",
    "staff-slots": "Both staff and service lookups use TenantManager.for_org(request.user.organisation).",
    "auth-me": "Returns only request.user's own account profile; it does not query tenant-owned collections.",
    "me": "Returns only request.user's own account profile; it does not query tenant-owned collections.",
}


def _api_views(patterns, prefix: str = "") -> Iterator[tuple[str, object]]:
    for pattern in patterns:
        route = f"{prefix}{pattern.pattern}"
        if isinstance(pattern, URLResolver):
            yield from _api_views(pattern.url_patterns, route)
        elif isinstance(pattern, URLPattern) and route.startswith("api/"):
            yield pattern.name or route, pattern.callback


@pytest.mark.django_db
def test_authenticated_api_views_are_tenant_scoped_or_explicitly_exempt() -> None:
    for route_name, callback in _api_views(get_resolver().url_patterns):
        view_class = getattr(callback, "cls", None)
        if view_class is None:
            continue
        permission_classes = getattr(view_class, "permission_classes", ())
        if not permission_classes or any(permission is AllowAny for permission in permission_classes):
            continue
        if issubclass(view_class, TenantScopedMixin):
            continue
        assert route_name in TENANT_SCOPE_EXCEPTIONS, (
            f"Authenticated API route {route_name!r} must use TenantScopedMixin or have a justified exception."
        )
        assert TENANT_SCOPE_EXCEPTIONS[route_name]