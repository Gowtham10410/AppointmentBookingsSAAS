from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Model


def assert_same_tenant(*objects: Model) -> None:
    organisation_ids: list[int | None] = []
    for obj in objects:
        try:
            organisation_field = "organisation_id"
            organisation_id = getattr(obj, organisation_field)
        except (AttributeError, ObjectDoesNotExist) as exc:
            raise ValueError("Every booking resource must belong to an organisation.") from exc
        organisation_ids.append(organisation_id)

    if not organisation_ids or any(value is None for value in organisation_ids) or len(set(organisation_ids)) != 1:
        raise ValueError("Booking resources must belong to the same organisation.")