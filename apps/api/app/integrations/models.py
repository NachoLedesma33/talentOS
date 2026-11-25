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


class WebhookEventType(StrEnum):
    """Tipos de evento cerrados del envelope (SDD 11.1)."""

    CANDIDATE_CREATED = "candidate.created"
    DOCUMENT_UPLOADED = "document.uploaded"
    DOCUMENT_EXTRACTION_COMPLETED = "document.extraction.completed"
    APPLICATION_STAGE_CHANGED = "application.stage_changed"
    ASSESSMENT_COMPLETED = "assessment.completed"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_RESOLVED = "approval.resolved"


class WebhookEventStatus(StrEnum):
    """Estados observables de un evento entrante; transiciones deterministas."""

    ENQUEUE_FAILED = "enqueue_failed"
    QUEUED = "queued"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


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


class WebhookEvent(Base):
    """Evidencia de un webhook entrante; nunca cuerpo crudo ni payload con texto."""

    __tablename__ = "webhook_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    integration_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("integrations.id", ondelete="CASCADE"), nullable=False
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
    event_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    event_type: Mapped[WebhookEventType] = mapped_column(
        SAEnum(
            WebhookEventType,
            name="webhook_event_type",
            native_enum=False,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    correlation_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    payload_version: Mapped[str] = mapped_column(String(4), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    status: Mapped[WebhookEventStatus] = mapped_column(
        SAEnum(
            WebhookEventStatus,
            name="webhook_event_status",
            native_enum=False,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
        default=WebhookEventStatus.QUEUED,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # sha256 del payload saneado canónico; sin texto de CV, secreto ni firma.
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "provider",
            "event_id",
            name="uq_webhook_events_organization_id_provider_event_id",
        ),
        CheckConstraint("attempts >= 0", name="ck_webhook_events_attempts_nonnegative"),
        CheckConstraint(
            "length(payload_hash) = 64", name="ck_webhook_events_payload_hash_length"
        ),
        Index(
            "ix_webhook_events_organization_id_status_received_at",
            "organization_id",
            "status",
            "received_at",
        ),
    )
