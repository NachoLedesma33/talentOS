from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Nombres deterministas para PK, FK, UNIQUE, INDEX y CHECK.
# Sin modelos de negocio: las entidades llegan en Fase 2 con su organization_id.
_NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ix": "ix_%(column_0_label)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
}


class Base(DeclarativeBase):
    """Metadata común; esta fase solo define la convención de nombres."""

    metadata = MetaData(naming_convention=_NAMING_CONVENTION)
