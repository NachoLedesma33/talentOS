"""Recruitment Core: vacantes, requisitos y versiones inmutables."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_jobs"
down_revision: str | None = "0003_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "open",
                "paused",
                "closed",
                "archived",
                name="job_status",
                native_enum=False,
                validate_strings=True,
            ),
            nullable=False,
        ),
        sa.Column("modality", sa.String(length=50), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("seniority", sa.String(length=50), nullable=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_jobs_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_jobs_owner_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_jobs"),
    )
    op.create_index("ix_jobs_organization_id", "jobs", ["organization_id"])
    op.create_index("ix_jobs_owner_id", "jobs", ["owner_id"])
    op.create_index("ix_jobs_status", "jobs", ["status"])

    op.create_table(
        "job_requirements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column(
            "category",
            sa.Enum(
                "skill",
                "experience",
                "education",
                "language",
                "certification",
                "other",
                name="requirement_category",
                native_enum=False,
                validate_strings=True,
            ),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "importance",
            sa.Enum(
                "required",
                "desirable",
                name="requirement_importance",
                native_enum=False,
                validate_strings=True,
            ),
            nullable=False,
        ),
        sa.Column("expected_level", sa.String(length=100), nullable=True),
        sa.Column("acceptable_evidence", sa.JSON(), nullable=False),
        sa.Column("weight", sa.Double(), nullable=False),
        sa.Column("weight_justification", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "weight >= 0 AND weight <= 1 "
            "AND (weight = 0 OR length(trim(weight_justification)) > 0)",
            name="ck_job_requirements_weight",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name="fk_job_requirements_job_id_jobs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_job_requirements"),
    )
    op.create_index("ix_job_requirements_job_id", "job_requirements", ["job_id"])

    op.create_table(
        "job_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name="fk_job_versions_job_id_jobs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_job_versions"),
        sa.UniqueConstraint("job_id", "version", name="uq_job_versions_job_id_version"),
    )
    op.create_index("ix_job_versions_job_id", "job_versions", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_job_versions_job_id", table_name="job_versions")
    op.drop_table("job_versions")

    op.drop_index("ix_job_requirements_job_id", table_name="job_requirements")
    op.drop_table("job_requirements")

    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_index("ix_jobs_owner_id", table_name="jobs")
    op.drop_index("ix_jobs_organization_id", table_name="jobs")
    op.drop_table("jobs")
