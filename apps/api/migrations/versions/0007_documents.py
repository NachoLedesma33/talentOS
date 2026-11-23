"""Document Intelligence: archivos privados, extracciones y campos con evidencia."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_documents"
down_revision: str | None = "0006_applications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, validate_strings=True)


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("internal_name", sa.String(128), nullable=False),
        sa.Column("content_type", sa.String(255), nullable=False),
        sa.Column("extension", sa.String(10), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column(
            "status",
            _enum("document_status", "uploaded", "processing", "processed", "failed"),
            nullable=False,
        ),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_documents_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            name="fk_documents_candidate_id_candidates",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
            name="fk_documents_uploaded_by_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
        sa.UniqueConstraint("internal_name", name="uq_documents_internal_name"),
    )
    op.create_index("ix_documents_organization_id", "documents", ["organization_id"])
    op.create_index("ix_documents_candidate_id", "documents", ["candidate_id"])
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_index("ix_documents_checksum_sha256", "documents", ["checksum_sha256"])

    op.create_table(
        "document_extractions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(50), nullable=False),
        sa.Column(
            "status",
            _enum("extraction_status", "pending", "completed", "failed"),
            nullable=False,
        ),
        sa.Column("pages", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_document_extractions_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_extractions"),
        sa.UniqueConstraint(
            "document_id",
            "provider",
            "prompt_version",
            name="uq_document_extractions_document_id_provider_prompt_version",
        ),
    )
    op.create_index(
        "ix_document_extractions_document_id", "document_extractions", ["document_id"]
    )

    op.create_table(
        "extracted_fields",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("extraction_id", sa.Uuid(), nullable=False),
        sa.Column(
            "field_name",
            _enum(
                "extracted_field_name",
                "name",
                "email",
                "location",
                "experience",
                "education",
                "skills",
                "projects",
                "languages",
            ),
            nullable=False,
        ),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            _enum(
                "extracted_field_status",
                "extracted",
                "needs_review",
                "missing",
                "confirmed",
                "corrected",
            ),
            nullable=False,
        ),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("confirmed_by", sa.Uuid(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["extraction_id"],
            ["document_extractions.id"],
            name="fk_extracted_fields_extraction_id_document_extractions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by"],
            ["users.id"],
            name="fk_extracted_fields_confirmed_by_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_extracted_fields"),
    )
    op.create_index("ix_extracted_fields_extraction_id", "extracted_fields", ["extraction_id"])


def downgrade() -> None:
    op.drop_index("ix_extracted_fields_extraction_id", table_name="extracted_fields")
    op.drop_table("extracted_fields")

    op.drop_index("ix_document_extractions_document_id", table_name="document_extractions")
    op.drop_table("document_extractions")

    op.drop_index("ix_documents_checksum_sha256", table_name="documents")
    op.drop_index("ix_documents_status", table_name="documents")
    op.drop_index("ix_documents_candidate_id", table_name="documents")
    op.drop_index("ix_documents_organization_id", table_name="documents")
    op.drop_table("documents")
