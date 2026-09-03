"""Model primitives every feature module builds on."""

import uuid

from django.db import models
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


class BaseModel(UUIDPrimaryKeyModel, TimeStampedModel):
    """Default base class for feature-module models."""

    class Meta:
        abstract = True
