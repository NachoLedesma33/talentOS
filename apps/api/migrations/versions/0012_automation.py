"""Automation Engine: reglas versionadas, ejecuciones, trazas y aprobaciones."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Alembic carga los scripts de versión antes de comparar metadata. Registrar aquí
# los modelos evita tocar `migrations/env.py` y mantiene `alembic check` sincero.
import app.automation.models  # noqa: F401

revision: str = "0012_automation"
down_revision: str | None = "0011_interviews"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, validate_strings=True)


def upgrade() -> None:
    op.create_table(
        "automations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "status",
            _enum("automation_status", "draft", "active", "inactive", "archived"),
            nullable=False,
        ),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_automations_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_automations_created_by_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_automations"),
        sa.UniqueConstraint(
            "organization_id", "name", name="uq_automations_organization_id_name"
        ),
        sa.CheckConstraint(
            "current_version >= 1", name="ck_automations_current_version_positive"
        ),
        sa.CheckConstraint("length(name) <= 200", name="ck_automations_name_length"),
    )
    op.create_index("ix_automations_organization_id", "automations", ["organization_id"])
    op.create_index("ix_automations_status", "automations", ["status"])

    op.create_table(
        "automation_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("automation_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("trigger", sa.JSON(), nullable=False),
        sa.Column("conditions", sa.JSON(), nullable=False),
        sa.Column("actions", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_automation_versions_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["automation_id"],
            ["automations.id"],
            name="fk_automation_versions_automation_id_automations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_automation_versions_created_by_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_automation_versions"),
        sa.UniqueConstraint(
            "automation_id", "version", name="uq_automation_versions_automation_version"
        ),
        sa.CheckConstraint("version >= 1", name="ck_automation_versions_version_positive"),
    )
    op.create_index(
        "ix_automation_versions_organization_id", "automation_versions", ["organization_id"]
    )
    op.create_index(
        "ix_automation_versions_automation_id", "automation_versions", ["automation_id"]
    )

    op.create_table(
        "automation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("automation_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "mode", _enum("automation_run_mode", "test", "live"), nullable=False
        ),
        sa.Column(
            "status",
            _enum(
                "automation_run_status",
                "pending",
                "running",
                "waiting_approval",
                "completed",
                "failed",
                "cancelled",
                "timed_out",
            ),
            nullable=False,
        ),
        sa.Column("trigger_event_type", sa.String(100), nullable=False),
        sa.Column("trigger_event_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_automation_runs_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["automation_id"],
            ["automations.id"],
            name="fk_automation_runs_automation_id_automations",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name="fk_automation_runs_actor_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_automation_runs"),
        sa.UniqueConstraint(
            "automation_id", "idempotency_key", name="uq_automation_runs_automation_idem"
        ),
        sa.CheckConstraint("version >= 1", name="ck_automation_runs_version_positive"),
        sa.CheckConstraint(
            "length(idempotency_key) <= 100", name="ck_automation_runs_idem_length"
        ),
        sa.CheckConstraint(
            "length(trigger_event_type) <= 100", name="ck_automation_runs_event_type_length"
        ),
    )
    op.create_index(
        "ix_automation_runs_organization_id", "automation_runs", ["organization_id"]
    )
    op.create_index(
        "ix_automation_runs_automation_id", "automation_runs", ["automation_id"]
    )
    op.create_index("ix_automation_runs_status", "automation_runs", ["status"])
    op.create_index(
        "ix_automation_runs_correlation_id", "automation_runs", ["correlation_id"]
    )

    op.create_table(
        "automation_run_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column(
            "event_type",
            _enum(
                "automation_run_event_type",
                "trigger_matched",
                "condition_evaluated",
                "action_planned",
                "action_executed",
                "approval_requested",
                "approval_resolved",
                "retry_scheduled",
                "completed",
                "failed",
                "cancelled",
                "dry_run",
            ),
            nullable=False,
        ),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_automation_run_events_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["automation_runs.id"],
            name="fk_automation_run_events_run_id_automation_runs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_automation_run_events"),
    )
    op.create_index(
        "ix_automation_run_events_organization_id",
        "automation_run_events",
        ["organization_id"],
    )
    op.create_index("ix_automation_run_events_run_id", "automation_run_events", ["run_id"])
    op.create_index(
        "ix_automation_run_events_event_type", "automation_run_events", ["event_type"]
    )
    op.create_index(
        "ix_automation_run_events_created_at", "automation_run_events", ["created_at"]
    )

    op.create_table(
        "automation_approvals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column(
            "action_type",
            _enum(
                "automation_action_type",
                "create_task",
                "create_message_draft",
                "request_approval",
                "record_note",
                "propose_stage_change",
                "run_authorized_analysis",
            ),
            nullable=False,
        ),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            _enum("automation_approval_status", "pending", "approved", "rejected"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_automation_approvals_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["automation_runs.id"],
            name="fk_automation_approvals_run_id_automation_runs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_automation_approvals_created_by_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"],
            ["users.id"],
            name="fk_automation_approvals_decided_by_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_automation_approvals"),
        sa.UniqueConstraint(
            "run_id", "action_type", name="uq_automation_approvals_run_action"
        ),
        sa.CheckConstraint(
            "length(payload_hash) = 64", name="ck_automation_approvals_hash_length"
        ),
    )
    op.create_index(
        "ix_automation_approvals_organization_id", "automation_approvals", ["organization_id"]
    )
    op.create_index("ix_automation_approvals_run_id", "automation_approvals", ["run_id"])
    op.create_index("ix_automation_approvals_status", "automation_approvals", ["status"])


def downgrade() -> None:
    op.drop_index("ix_automation_approvals_status", table_name="automation_approvals")
    op.drop_index("ix_automation_approvals_run_id", table_name="automation_approvals")
    op.drop_index(
        "ix_automation_approvals_organization_id", table_name="automation_approvals"
    )
    op.drop_table("automation_approvals")

    op.drop_index("ix_automation_run_events_created_at", table_name="automation_run_events")
    op.drop_index("ix_automation_run_events_event_type", table_name="automation_run_events")
    op.drop_index("ix_automation_run_events_run_id", table_name="automation_run_events")
    op.drop_index(
        "ix_automation_run_events_organization_id", table_name="automation_run_events"
    )
    op.drop_table("automation_run_events")

    op.drop_index("ix_automation_runs_correlation_id", table_name="automation_runs")
    op.drop_index("ix_automation_runs_status", table_name="automation_runs")
    op.drop_index("ix_automation_runs_automation_id", table_name="automation_runs")
    op.drop_index("ix_automation_runs_organization_id", table_name="automation_runs")
    op.drop_table("automation_runs")

    op.drop_index("ix_automation_versions_automation_id", table_name="automation_versions")
    op.drop_index(
        "ix_automation_versions_organization_id", table_name="automation_versions"
    )
    op.drop_table("automation_versions")

    op.drop_index("ix_automations_status", table_name="automations")
    op.drop_index("ix_automations_organization_id", table_name="automations")
    op.drop_table("automations")
