"""Webhooks salientes: outbox tenant-scoped con hash, intentos y dead-letter."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Alembic carga las versiones antes de comparar metadata: registrar el modelo
# mantiene `alembic check` sincero sin tocar `migrations/env.py`.
import app.integrations.models  # noqa: F401

revision: str = "0015_webhook_deliveries"
down_revision: str | None = "0014_webhook_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, validate_strings=True)


def upgrade() -> None:
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("integration_id", sa.Uuid(), nullable=False),
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
        sa.Column("endpoint_snapshot", sa.String(2048), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column(
            "status",
            _enum(
                "webhook_delivery_status",
                "pending",
                "sending",
                "delivered",
                "failed",
                "dead_letter",
            ),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        sa.Column("last_status_code", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["integration_id"],
            ["integrations.id"],
            name="fk_webhook_deliveries_integration_id_integrations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_webhook_deliveries_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_webhook_deliveries"),
        sa.UniqueConstraint(
            "organization_id",
            "integration_id",
            "event_id",
            name="uq_webhook_deliveries_organization_id_integration_id_event_id",
        ),
        sa.CheckConstraint(
            "attempts >= 0", name="ck_webhook_deliveries_attempts_nonnegative"
        ),
        sa.CheckConstraint(
            "length(payload_hash) = 64", name="ck_webhook_deliveries_payload_hash_length"
        ),
        sa.CheckConstraint(
            "length(endpoint_snapshot) > 0",
            name="ck_webhook_deliveries_endpoint_snapshot_length",
        ),
        sa.CheckConstraint(
            "last_status_code IS NULL OR last_status_code BETWEEN 100 AND 599",
            name="ck_webhook_deliveries_last_status_code_range",
        ),
    )
    op.create_index(
        "ix_webhook_deliveries_organization_id_status_next_attempt_at",
        "webhook_deliveries",
        ["organization_id", "status", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_webhook_deliveries_organization_id_status_next_attempt_at",
        table_name="webhook_deliveries",
    )
    op.drop_table("webhook_deliveries")
