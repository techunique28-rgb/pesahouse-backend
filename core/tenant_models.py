import logging
from contextlib import contextmanager

from django.db import models
from django.db.models import QuerySet

from .tenant_context import TenantContextMissing, get_current_landlord

logger = logging.getLogger(__name__)


@contextmanager
def unscoped(reason: str):
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("unscoped() requires a reason")
    logger.warning(
        "Tenant scope bypassed",
        extra={"reason": reason.strip(), "landlord_id": None},
    )
    from .tenant_context import clear_current_landlord, set_current_landlord
    previous = get_current_landlord()
    clear_current_landlord()
    try:
        yield
    finally:
        if previous is not None:
            set_current_landlord(previous)


class TenantQuerySet(QuerySet):
    def _ensure_scope(self):
        landlord_id = get_current_landlord()
        if landlord_id is None:
            raise TenantContextMissing(
                "Tenant query requires an active landlord context"
            )
        return landlord_id

    def filter(self, *args, **kwargs):
        if getattr(self, "_bypass_tenant_scope", False):
            return super().filter(*args, **kwargs)
        return super().filter(*args, **kwargs).filter(
            landlord_id=self._ensure_scope()
        )

    def exclude(self, *args, **kwargs):
        if getattr(self, "_bypass_tenant_scope", False):
            return super().exclude(*args, **kwargs)
        self._ensure_scope()
        return super().exclude(*args, **kwargs)

    def get(self, *args, **kwargs):
        if getattr(self, "_bypass_tenant_scope", False):
            return super().get(*args, **kwargs)
        return super().get(*args, **kwargs)

    def all(self):
        if getattr(self, "_bypass_tenant_scope", False):
            return super().all()
        self._ensure_scope()
        return super().all()

    def count(self):
        self._ensure_scope()
        return super().count()

    def exists(self):
        self._ensure_scope()
        return super().exists()

    def update(self, **kwargs):
        landlord_id = self._ensure_scope()
        if "landlord" in kwargs or "landlord_id" in kwargs:
            raise ValueError("Tenant queryset cannot change landlord_id")
        return super().filter(landlord_id=landlord_id).update(**kwargs)

    def delete(self):
        landlord_id = self._ensure_scope()
        return super().filter(landlord_id=landlord_id).delete()


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    def get_queryset(self):
        landlord_id = get_current_landlord()
        if landlord_id is None:
            raise TenantContextMissing(
                "Tenant query requires an active landlord context"
            )
        return super().get_queryset().filter(landlord_id=landlord_id)

    def unscoped(self, reason: str):
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("unscoped() requires a reason")
        logger.warning(
            "Tenant scope bypassed",
            extra={"reason": reason.strip(), "landlord_id": None},
        )
        queryset = super().get_queryset()
        queryset._bypass_tenant_scope = True
        return queryset


class TenantModel(models.Model):
    landlord = models.ForeignKey(
        "landlords.Landlord",
        on_delete=models.PROTECT,
        related_name="+",
    )
    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def save(
        self,
        *args,
        force_insert=False,
        force_update=False,
        using=None,
        update_fields=None,
        **kwargs,
    ):
        landlord_id = get_current_landlord()
        if landlord_id is None:
            raise TenantContextMissing(
                "Tenant save requires an active landlord context"
            )
        row_landlord_id = getattr(self, "landlord_id", None)
        if str(row_landlord_id) != str(landlord_id):
            raise TenantContextMissing(
                "Tenant row landlord differs from active landlord context"
            )
        return super().save(
            *args,
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
            **kwargs,
        )

    @classmethod
    def bulk_create(cls, objs, *args, **kwargs):
        cls._guard_bulk_rows(objs)
        return super().bulk_create(objs, *args, **kwargs)

    @classmethod
    def bulk_update(cls, objs, fields, *args, **kwargs):
        cls._guard_bulk_rows(objs)
        return super().bulk_update(objs, fields, *args, **kwargs)

    @classmethod
    def _guard_bulk_rows(cls, objs):
        landlord_id = get_current_landlord()
        if landlord_id is None:
            raise TenantContextMissing(
                "Tenant bulk operation requires a landlord context"
            )
        for obj in objs:
            if str(obj.landlord_id) != str(landlord_id):
                raise TenantContextMissing(
                    "Tenant bulk row differs from active landlord context"
                )
