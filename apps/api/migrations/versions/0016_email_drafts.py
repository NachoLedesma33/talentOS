"""Borradores de correo sandbox: aprobación humana separada y solo metadatos."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Alembic carga las versiones antes de comparar metadata: registrar el modelo
# mantiene `alembic check` sincero sin tocar `migrations/env.py`.
import app.integrations.models  # noqa: F401

revision: str = "0016_email_drafts"
down_revision: str | None = "0015_webhook_deliveries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, validate_strings=True)


def upgrade() -> None:
    op.create_table(
        "email_drafts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("integration_id", sa.Uuid(), nullable=False),
        # Referencia opaca al candidato: sin FK a candidates ni datos personales.
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column(
            "template",
            _enum("email_template", "initial_contact", "interview_invite", "follow_up"),
            nullable=False,
        ),
        sa.Column("topic", sa.String(120), nullable=False),
        sa.Column("language", _enum("email_language", "es", "en"), nullable=False),
        sa.Column("call_to_action", sa.String(120), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("body_hash", sa.String(64), nullable=False),
        sa.Column(
            "approval_status",
            _enum("email_approval_status", "pending", "approved", "rejected"),
            nullable=False,
        ),
        sa.Column("requested_by", sa.Uuid(), nullable=True),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "delivery_status",
            _enum("email_delivery_status", "not_sent", "sent", "failed"),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["integration_id"],
            ["integrations.id"],
            name="fk_email_drafts_integration_id_integrations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_email_drafts_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_email_drafts"),
        sa.UniqueConstraint(
            "organization_id",
            "integration_id",
            "candidate_id",
            "template",
            "topic",
            "language",
            "call_to_action",
            name="uq_email_drafts_natural_key",
        ),
        sa.CheckConstraint(
            "length(topic) BETWEEN 1 AND 120", name="ck_email_drafts_topic_length"
        ),
        sa.CheckConstraint(
            "length(call_to_action) BETWEEN 1 AND 120",
            name="ck_email_drafts_call_to_action_length",
        ),
        sa.CheckConstraint(
            "length(subject) BETWEEN 1 AND 200", name="ck_email_drafts_subject_length"
        ),
        sa.CheckConstraint(
            "length(body_hash) = 64", name="ck_email_drafts_body_hash_length"
        ),
        sa.CheckConstraint(
            "attempts >= 0", name="ck_email_drafts_attempts_nonnegative"
        ),
    )
    op.create_index(
        "ix_email_drafts_organization_id_approval_status_delivery_status",
        "email_drafts",
        ["organization_id", "approval_status", "delivery_status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_email_drafts_organization_id_approval_status_delivery_status",
        table_name="email_drafts",
    )
    op.drop_table("email_drafts")
