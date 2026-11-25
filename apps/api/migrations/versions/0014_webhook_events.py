"""Webhooks entrantes: evidencia tenant-scoped, dedupe y estado de entrega."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Alembic carga las versiones antes de comparar metadata: registrar el modelo
# mantiene `alembic check` sincero sin tocar `migrations/env.py`.
import app.integrations.models  # noqa: F401

revision: str = "0014_webhook_events"
down_revision: str | None = "0013_integrations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, validate_strings=True)


def upgrade() -> None:
    op.create_table(
        "webhook_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("integration_id", sa.Uuid(), nullable=False),
        sa.Column(
            "provider",
            _enum("integration_provider", "email_sandbox", "webhook_outbound", "webhook_inbound"),
            nullable=False,
        ),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column(
            "event_type",
            _enum(
                "webhook_event_type",
                "candidate.created",
                "document.uploaded",
                "document.extraction.completed",
                "application.stage_changed",
                "assessment.completed",
                "approval.requested",
                "approval.resolved",
            ),
            nullable=False,
        ),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("payload_version", sa.String(4), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            _enum(
                "webhook_event_status",
                "enqueue_failed",
                "queued",
                "processing",
                "processed",
                "failed",
                "dead_letter",
            ),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["integration_id"],
            ["integrations.id"],
            name="fk_webhook_events_integration_id_integrations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_webhook_events_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_webhook_events"),
        sa.UniqueConstraint(
            "organization_id",
            "provider",
            "event_id",
            name="uq_webhook_events_organization_id_provider_event_id",
        ),
        sa.CheckConstraint(
            "attempts >= 0", name="ck_webhook_events_attempts_nonnegative"
        ),
        sa.CheckConstraint(
            "length(payload_hash) = 64", name="ck_webhook_events_payload_hash_length"
        ),
    )
    op.create_index(
        "ix_webhook_events_organization_id_status_received_at",
        "webhook_events",
        ["organization_id", "status", "received_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_webhook_events_organization_id_status_received_at",
        table_name="webhook_events",
    )
    op.drop_table("webhook_events")
