"""Integraciones: configuración cifrada por organización y proveedor."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Alembic carga los scripts de versión antes de comparar metadata. Registrar aquí
# los modelos evita tocar `migrations/env.py` y mantiene `alembic check` sincero.
import app.integrations.models  # noqa: F401

revision: str = "0013_integrations"
down_revision: str | None = "0012_automation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, validate_strings=True)


def upgrade() -> None:
    op.create_table(
        "integrations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column(
            "provider",
            _enum("integration_provider", "email_sandbox", "webhook_outbound", "webhook_inbound"),
            nullable=False,
        ),
        sa.Column("encrypted_config_ref", sa.String(512), nullable=False),
        sa.Column("key_id", sa.String(12), nullable=False),
        sa.Column("config_version", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            _enum("integration_status", "active", "disabled"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_integrations_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_integrations"),
        sa.UniqueConstraint(
            "organization_id", "provider", name="uq_integrations_organization_id_provider"
        ),
        sa.CheckConstraint(
            "config_version >= 1", name="ck_integrations_config_version_positive"
        ),
        sa.CheckConstraint("length(key_id) = 12", name="ck_integrations_key_id_length"),
        sa.CheckConstraint(
            "length(encrypted_config_ref) > 0", name="ck_integrations_encrypted_ref_length"
        ),
    )
    op.create_index(
        "ix_integrations_organization_id_status",
        "integrations",
        ["organization_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_integrations_organization_id_status", table_name="integrations")
    op.drop_table("integrations")
