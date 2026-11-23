from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum, StrEnum

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, Uuid
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _utcnow() -> datetime:
    """Timestamp UTC aplicado por Python; la BD no define reloj local."""
    return datetime.now(UTC)


def _enum_values(enum_type: type[Enum]) -> list[str]:
    return [str(member.value) for member in enum_type]


class DocumentStatus(StrEnum):
    """Estado grueso de recepción; las fases finas viven en DocumentExtraction."""

    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class ExtractionStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class ExtractedFieldName(StrEnum):
    NAME = "name"
    EMAIL = "email"
    LOCATION = "location"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    SKILLS = "skills"
    PROJECTS = "projects"
    LANGUAGES = "languages"


class ExtractedFieldStatus(StrEnum):
    EXTRACTED = "extracted"
    NEEDS_REVIEW = "needs_review"
    MISSING = "missing"
    CONFIRMED = "confirmed"
    CORRECTED = "corrected"


class Document(Base):
    """Metadatos del archivo privado: nunca el CV, rutas absolutas ni atributos protegidos."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    internal_name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    extension: Mapped[str] = mapped_column(String(10), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        SAEnum(
            DocumentStatus,
            name="document_status",
            native_enum=False,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
        default=DocumentStatus.UPLOADED,
    )
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Código estable, nunca mensaje con fragmentos del documento ni PII.
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        Index("ix_documents_organization_id", "organization_id"),
        Index("ix_documents_candidate_id", "candidate_id"),
        Index("ix_documents_status", "status"),
        Index("ix_documents_checksum_sha256", "checksum_sha256"),
    )


class DocumentExtraction(Base):
    """Resultado crudo por proveedor y prompt; páginas con offsets verificables."""

    __tablename__ = "document_extractions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[ExtractionStatus] = mapped_column(
        SAEnum(
            ExtractionStatus,
            name="extraction_status",
            native_enum=False,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
        default=ExtractionStatus.PENDING,
    )
    pages: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        Index("ix_document_extractions_document_id", "document_id"),
        UniqueConstraint(
            "document_id",
            "provider",
            "prompt_version",
            name="uq_document_extractions_document_id_provider_prompt_version",
        ),
    )


class ExtractedField(Base):
    """Campo profesional con evidencia; la confirmación queda ligada a un usuario."""

    __tablename__ = "extracted_fields"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    extraction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("document_extractions.id", ondelete="CASCADE"),
        nullable=False,
    )
    field_name: Mapped[ExtractedFieldName] = mapped_column(
        SAEnum(
            ExtractedFieldName,
            name="extracted_field_name",
            native_enum=False,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
    )
    value: Mapped[object] = mapped_column(JSON, nullable=False)
    status: Mapped[ExtractedFieldStatus] = mapped_column(
        SAEnum(
            ExtractedFieldStatus,
            name="extracted_field_status",
            native_enum=False,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
        default=ExtractedFieldStatus.EXTRACTED,
    )
    evidence: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (Index("ix_extracted_fields_extraction_id", "extraction_id"),)
