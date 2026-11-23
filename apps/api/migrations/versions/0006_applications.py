"""Recruitment Core: postulaciones, pipeline e historial de etapas por organización."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_applications"
down_revision: str | None = "0005_candidates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "applications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column(
            "stage",
            sa.Enum(
                "applied",
                "screening",
                "interview",
                "offer",
                "hired",
                "rejected",
                name="application_stage",
                native_enum=False,
                validate_strings=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "source",
            sa.Enum(
                "manual",
                "import",
                "referral",
                "careers",
                name="application_source",
                native_enum=False,
                validate_strings=True,
            ),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_applications_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name="fk_applications_job_id_jobs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            name="fk_applications_candidate_id_candidates",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_applications"),
        sa.UniqueConstraint(
            "organization_id",
            "job_id",
            "candidate_id",
            name="uq_applications_organization_id_job_id_candidate_id",
        ),
    )
    op.create_index("ix_applications_organization_id", "applications", ["organization_id"])
    op.create_index("ix_applications_job_id", "applications", ["job_id"])
    op.create_index("ix_applications_candidate_id", "applications", ["candidate_id"])
    op.create_index("ix_applications_stage", "applications", ["stage"])

    op.create_table(
        "stage_changes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column(
            "from_stage",
            sa.Enum(
                "applied",
                "screening",
                "interview",
                "offer",
                "hired",
                "rejected",
                name="application_stage",
                native_enum=False,
                validate_strings=True,
            ),
            nullable=True,
        ),
        sa.Column(
            "to_stage",
            sa.Enum(
                "applied",
                "screening",
                "interview",
                "offer",
                "hired",
                "rejected",
                name="application_stage",
                native_enum=False,
                validate_strings=True,
            ),
            nullable=False,
        ),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name="fk_stage_changes_application_id_applications",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name="fk_stage_changes_actor_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_stage_changes"),
    )
    op.create_index("ix_stage_changes_application_id", "stage_changes", ["application_id"])


def downgrade() -> None:
    op.drop_index("ix_stage_changes_application_id", table_name="stage_changes")
    op.drop_table("stage_changes")

    op.drop_index("ix_applications_stage", table_name="applications")
    op.drop_index("ix_applications_candidate_id", table_name="applications")
    op.drop_index("ix_applications_job_id", table_name="applications")
    op.drop_index("ix_applications_organization_id", table_name="applications")
    op.drop_table("applications")
