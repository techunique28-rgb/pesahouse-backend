from contextlib import contextmanager
from contextvars import ContextVar
from uuid import UUID

from django.core.exceptions import ImproperlyConfigured


class TenantContextMissing(ImproperlyConfigured):
    pass


_landlord_id: ContextVar[UUID | str | None] = ContextVar(
    "current_landlord_id",
    default=None,
)


def set_current_landlord(landlord_id) -> UUID | str:
    if landlord_id is None:
        raise TenantContextMissing("A landlord context is required")
    if isinstance(landlord_id, UUID):
        value = landlord_id
    else:
        value = str(landlord_id)
    _landlord_id.set(value)
    return value


def get_current_landlord():
    return _landlord_id.get()


def clear_current_landlord() -> None:
    _landlord_id.set(None)


@contextmanager
def use_landlord(landlord_id):
    previous = get_current_landlord()
    set_current_landlord(landlord_id)
    try:
        yield landlord_id
    finally:
        if previous is None:
            clear_current_landlord()
        else:
            set_current_landlord(previous)
