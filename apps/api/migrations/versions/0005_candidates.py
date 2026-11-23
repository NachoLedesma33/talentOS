"""Recruitment Core: candidatos y notas internas con aislamiento por organización."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_candidates"
down_revision: str | None = "0004_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column(
            "profile_status",
            sa.Enum(
                "draft",
                "review",
                "confirmed",
                "archived",
                name="profile_status",
                native_enum=False,
                validate_strings=True,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_candidates_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_candidates"),
    )
    op.create_index("ix_candidates_organization_id", "candidates", ["organization_id"])
    op.create_index("ix_candidates_profile_status", "candidates", ["profile_status"])
    op.create_index("ix_candidates_email", "candidates", ["email"])

    op.create_table(
        "candidate_notes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            name="fk_candidate_notes_candidate_id_candidates",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name="fk_candidate_notes_author_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_candidate_notes"),
    )
    op.create_index("ix_candidate_notes_candidate_id", "candidate_notes", ["candidate_id"])


def downgrade() -> None:
    op.drop_index("ix_candidate_notes_candidate_id", table_name="candidate_notes")
    op.drop_table("candidate_notes")

    op.drop_index("ix_candidates_email", table_name="candidates")
    op.drop_index("ix_candidates_profile_status", table_name="candidates")
    op.drop_index("ix_candidates_organization_id", table_name="candidates")
    op.drop_table("candidates")
