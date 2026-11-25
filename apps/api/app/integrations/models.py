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


class WebhookDeliveryStatus(StrEnum):
    """Estados de una entrega saliente; transiciones deterministas."""

    PENDING = "pending"
    SENDING = "sending"
    DELIVERED = "delivered"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class WebhookDeliveryExistsError(IntegrationDomainError):
    """Ya existe la entrega para esa integración y event_id."""

    code = "webhook_delivery_exists"


class WebhookDeliveryNotFoundError(IntegrationDomainError):
    """La entrega no existe o no pertenece al tenant autenticado."""

    code = "webhook_delivery_not_found"


class WebhookDeliveryInvalidStatusError(IntegrationDomainError):
    """La transición solicitada no es válida para el estado actual."""

    code = "webhook_delivery_invalid_status"


class ProviderTimeoutError(IntegrationDomainError):
    """El proveedor agotó el timeout o falló la red."""

    code = "provider_timeout"


class ProviderRejectedError(IntegrationDomainError):
    """El proveedor rechazó la entrega con un código no transitorio."""

    code = "provider_rejected"


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


class WebhookDelivery(Base):
    """Outbox de webhooks salientes: metadatos y hash, nunca cuerpo ni payload."""

    __tablename__ = "webhook_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    integration_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("integrations.id", ondelete="CASCADE"), nullable=False
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
    # URL sin userinfo, query ni fragmento: nunca credenciales en la evidencia.
    endpoint_snapshot: Mapped[str] = mapped_column(String(2048), nullable=False)
    # sha256 del payload saneado canónico; sin CV, correos ni secretos.
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[WebhookDeliveryStatus] = mapped_column(
        SAEnum(
            WebhookDeliveryStatus,
            name="webhook_delivery_status",
            native_enum=False,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
        default=WebhookDeliveryStatus.PENDING,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "integration_id",
            "event_id",
            name="uq_webhook_deliveries_organization_id_integration_id_event_id",
        ),
        CheckConstraint("attempts >= 0", name="ck_webhook_deliveries_attempts_nonnegative"),
        CheckConstraint(
            "length(payload_hash) = 64", name="ck_webhook_deliveries_payload_hash_length"
        ),
        CheckConstraint(
            "length(endpoint_snapshot) > 0",
            name="ck_webhook_deliveries_endpoint_snapshot_length",
        ),
        CheckConstraint(
            "last_status_code IS NULL OR last_status_code BETWEEN 100 AND 599",
            name="ck_webhook_deliveries_last_status_code_range",
        ),
        Index(
            "ix_webhook_deliveries_organization_id_status_next_attempt_at",
            "organization_id",
            "status",
            "next_attempt_at",
        ),
    )


class EmailTemplate(StrEnum):
    """Plantillas cerradas; el servidor controla todo el texto renderizado."""

    INITIAL_CONTACT = "initial_contact"
    INTERVIEW_INVITE = "interview_invite"
    FOLLOW_UP = "follow_up"


class EmailLanguage(StrEnum):
    ES = "es"
    EN = "en"


class EmailApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class EmailDeliveryStatus(StrEnum):
    NOT_SENT = "not_sent"
    SENT = "sent"
    FAILED = "failed"


EMAIL_APPROVAL_TRANSITIONS: dict[
    EmailApprovalStatus, frozenset[EmailApprovalStatus]
] = {
    EmailApprovalStatus.PENDING: frozenset(
        {EmailApprovalStatus.APPROVED, EmailApprovalStatus.REJECTED}
    ),
    EmailApprovalStatus.APPROVED: frozenset(),
    EmailApprovalStatus.REJECTED: frozenset(),
}


class InvalidEmailApprovalTransitionError(IntegrationDomainError):
    """El borrador no permite la transición de aprobación pedida."""

    code = "email_invalid_state"


class EmailDraftNotFoundError(IntegrationDomainError):
    """El borrador no existe o no pertenece al tenant autenticado."""

    code = "email_not_found"


class EmailDraftExistsError(IntegrationDomainError):
    """Ya existe el borrador para esa clave natural del tenant."""

    code = "email_draft_exists"


def ensure_email_approval_transition(
    current: EmailApprovalStatus, target: EmailApprovalStatus
) -> None:
    """Única fuente de transiciones permitidas de aprobación de correo."""
    if target not in EMAIL_APPROVAL_TRANSITIONS.get(current, frozenset()):
        raise InvalidEmailApprovalTransitionError()


class EmailDraft(Base):
    """Borrador de correo sandbox: metadatos y hash, nunca destinatario ni cuerpo."""

    __tablename__ = "email_drafts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    integration_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("integrations.id", ondelete="CASCADE"), nullable=False
    )
    # Referencia opaca al candidato: sin FK y sin nombre, correo ni CV.
    candidate_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    template: Mapped[EmailTemplate] = mapped_column(
        SAEnum(
            EmailTemplate,
            name="email_template",
            native_enum=False,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
    )
    topic: Mapped[str] = mapped_column(String(120), nullable=False)
    language: Mapped[EmailLanguage] = mapped_column(
        SAEnum(
            EmailLanguage,
            name="email_language",
            native_enum=False,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
    )
    call_to_action: Mapped[str] = mapped_column(String(120), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    body_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    approval_status: Mapped[EmailApprovalStatus] = mapped_column(
        SAEnum(
            EmailApprovalStatus,
            name="email_approval_status",
            native_enum=False,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
        default=EmailApprovalStatus.PENDING,
    )
    # UUID opacos de actores: decidido por el servicio, nunca por el cliente.
    requested_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivery_status: Mapped[EmailDeliveryStatus] = mapped_column(
        SAEnum(
            EmailDeliveryStatus,
            name="email_delivery_status",
            native_enum=False,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
        default=EmailDeliveryStatus.NOT_SENT,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "integration_id",
            "candidate_id",
            "template",
            "topic",
            "language",
            "call_to_action",
            name="uq_email_drafts_natural_key",
        ),
        CheckConstraint("length(topic) BETWEEN 1 AND 120", name="ck_email_drafts_topic_length"),
        CheckConstraint(
            "length(call_to_action) BETWEEN 1 AND 120",
            name="ck_email_drafts_call_to_action_length",
        ),
        CheckConstraint("length(subject) BETWEEN 1 AND 200", name="ck_email_drafts_subject_length"),
        CheckConstraint("length(body_hash) = 64", name="ck_email_drafts_body_hash_length"),
        CheckConstraint("attempts >= 0", name="ck_email_drafts_attempts_nonnegative"),
        Index(
            "ix_email_drafts_organization_id_approval_status_delivery_status",
            "organization_id",
            "approval_status",
            "delivery_status",
        ),
    )

    def decide(
        self,
        target: EmailApprovalStatus,
        decided_by: uuid.UUID,
        decided_at: datetime,
    ) -> EmailDraft:
        """Aplica una transición válida; la separación de duties la valida el servicio."""
        ensure_email_approval_transition(self.approval_status, target)
        self.approval_status = target
        self.decided_by = decided_by
        self.decided_at = decided_at
        return self
