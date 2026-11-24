from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum, StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IntegrationDomainError(ValueError):
    """Error determinista de integraciones; nunca incluye config ni secretos."""

    code = "integration_error"

    def __init__(self, code: str | None = None) -> None:
        self.code = code if code is not None else type(self).code
        super().__init__(self.code)


class IntegrationKeyMissingError(IntegrationDomainError):
    """La clave de cifrado no está configurada o no es una clave Fernet válida."""

    code = "integration_key_missing"


class IntegrationConfigUnreadableError(IntegrationDomainError):
    """El token cifrado es inválido o corresponde a otra clave."""

    code = "integration_config_unreadable"


class IntegrationTenantMismatchError(IntegrationDomainError):
    """El recurso no pertenece a la organización autenticada."""

    code = "integration_not_found"


class IntegrationProvider(StrEnum):
    EMAIL_SANDBOX = "email_sandbox"
    WEBHOOK_OUTBOUND = "webhook_outbound"
    WEBHOOK_INBOUND = "webhook_inbound"


class IntegrationStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


def _utcnow() -> datetime:
    """Timestamp UTC aplicado por Python; la BD no define reloj local."""
    return datetime.now(UTC)


def _enum_values(enum_type: type[Enum]) -> list[str]:
    return [str(member.value) for member in enum_type]


class Integration(Base):
    """Configuración cifrada de un proveedor; sin relaciones bidireccionales."""

    __tablename__ = "integrations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[IntegrationProvider] = mapped_column(
        SAEnum(
            IntegrationProvider,
            name="integration_provider",
            native_enum=False,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
    )
    # Token Fernet: nunca configuración en claro.
    encrypted_config_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    # sha256(clave Fernet decodificada).hexdigest()[:12]; sin secreto en claro.
    key_id: Mapped[str] = mapped_column(String(12), nullable=False)
    config_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[IntegrationStatus] = mapped_column(
        SAEnum(
            IntegrationStatus,
            name="integration_status",
            native_enum=False,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
        default=IntegrationStatus.ACTIVE,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        UniqueConstraint(
            "organization_id", "provider", name="uq_integrations_organization_id_provider"
        ),
        CheckConstraint(
            "config_version >= 1", name="ck_integrations_config_version_positive"
        ),
        CheckConstraint("length(key_id) = 12", name="ck_integrations_key_id_length"),
        CheckConstraint(
            "length(encrypted_config_ref) > 0", name="ck_integrations_encrypted_ref_length"
        ),
        Index(
            "ix_integrations_organization_id_status", "organization_id", "status"
        ),
    )
