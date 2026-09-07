"""Model primitives every feature module builds on."""

import uuid

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class TimeStampedModel(models.Model):
    """Adds created/updated bookkeeping."""

    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        abstract = True


class UUIDPrimaryKeyModel(models.Model):
    """Opaque, globally unique identifiers.

    Sequential integer ids leak row counts and stop being unique the moment a
    module is split onto its own database - a UUID keeps identifiers valid
    across service boundaries.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    """QuerySet that soft-deletes by default, preventing permanent data deletion."""

    def delete(self, *, deleted_by_id=None):
        return self.update(
            is_deleted=True,
            deleted_at=timezone.now(),
            deleted_by_id=deleted_by_id,
        )

    def hard_delete(self):
        return super().delete()

    def alive(self):
        return self.filter(is_deleted=False)

    def dead(self):
        return self.filter(is_deleted=True)


class SoftDeleteManager(models.Manager.from_queryset(SoftDeleteQuerySet)):
    """Default manager filtering out soft-deleted records."""

    def get_queryset(self):
        qs = super().get_queryset()
        if any(f.name == "is_deleted" for f in self.model._meta.get_fields()):
            return qs.filter(is_deleted=False)
        return qs


class BaseModel(UUIDPrimaryKeyModel, TimeStampedModel):
    """Default base class for feature-module models.

    Provides UUID primary key, timestamp bookkeeping, audit tracking (who created/updated),
    and soft-delete semantics (no permanent data deletion via the system).
    """

    created_by_id = models.UUIDField(
        _("created by id"), null=True, blank=True, editable=False, db_index=True
    )
    updated_by_id = models.UUIDField(
        _("updated by id"), null=True, blank=True, editable=False
    )
    is_deleted = models.BooleanField(
        _("is deleted"), default=False, db_index=True, editable=False
    )
    deleted_at = models.DateTimeField(
        _("deleted at"), null=True, blank=True, editable=False
    )
    deleted_by_id = models.UUIDField(
        _("deleted by id"), null=True, blank=True, editable=False
    )

    objects = SoftDeleteManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False, *, deleted_by_id=None):
        """Soft-delete this record instead of permanently deleting it."""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        if deleted_by_id is not None:
            self.deleted_by_id = deleted_by_id
        update_fields = ["is_deleted", "deleted_at", "deleted_by_id"]
        if hasattr(self, "updated_at"):
            self.updated_at = timezone.now()
            update_fields.append("updated_at")
        self.save(update_fields=update_fields)

    def hard_delete(self, using=None, keep_parents=False):
        """Physical deletion, restricted from normal operations."""
        return super().delete(using=using, keep_parents=keep_parents)
