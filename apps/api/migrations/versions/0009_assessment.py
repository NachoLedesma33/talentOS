"""Evidence-Based Matching: evaluaciones por versión y criterios con evidencia verificable."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_assessment"
down_revision: str | None = "0008_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, validate_strings=True)


def upgrade() -> None:
    op.create_table(
        "assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("job_version_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            _enum("assessment_status", "pending", "completed", "failed", "needs_review"),
            nullable=False,
        ),
        sa.Column("model_version", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(50), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("limitations", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_assessments_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name="fk_assessments_application_id_applications",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_version_id"],
            ["job_versions.id"],
            name="fk_assessments_job_version_id_job_versions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            name="fk_assessments_candidate_id_candidates",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_assessments_created_by_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_assessments"),
        sa.UniqueConstraint(
            "organization_id",
            "application_id",
            "job_version_id",
            "prompt_version",
            name="uq_assessments_org_app_version_prompt",
        ),
    )
    op.create_index("ix_assessments_organization_id", "assessments", ["organization_id"])
    op.create_index("ix_assessments_application_id", "assessments", ["application_id"])
    op.create_index("ix_assessments_candidate_id", "assessments", ["candidate_id"])
    op.create_index("ix_assessments_status", "assessments", ["status"])

    op.create_table(
        "requirement_evaluations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("assessment_id", sa.Uuid(), nullable=False),
        sa.Column("requirement_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            _enum(
                "requirement_evaluation_status",
                "supported",
                "partial",
                "not_found",
                "needs_review",
            ),
            nullable=False,
        ),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("limitations", sa.JSON(), nullable=False),
        sa.Column(
            "review_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["assessments.id"],
            name="fk_requirement_evaluations_assessment_id_assessments",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["users.id"],
            name="fk_requirement_evaluations_reviewed_by_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_requirement_evaluations"),
    )
    op.create_index(
        "ix_requirement_evaluations_assessment_id", "requirement_evaluations", ["assessment_id"]
    )
    op.create_index(
        "ix_requirement_evaluations_requirement_id", "requirement_evaluations", ["requirement_id"]
    )
    op.create_index(
        "ix_requirement_evaluations_status", "requirement_evaluations", ["status"]
    )


def downgrade() -> None:
    op.drop_index("ix_requirement_evaluations_status", table_name="requirement_evaluations")
    op.drop_index("ix_requirement_evaluations_requirement_id", table_name="requirement_evaluations")
    op.drop_index("ix_requirement_evaluations_assessment_id", table_name="requirement_evaluations")
    op.drop_table("requirement_evaluations")

    op.drop_index("ix_assessments_status", table_name="assessments")
    op.drop_index("ix_assessments_candidate_id", table_name="assessments")
    op.drop_index("ix_assessments_application_id", table_name="assessments")
    op.drop_index("ix_assessments_organization_id", table_name="assessments")
    op.drop_table("assessments")
