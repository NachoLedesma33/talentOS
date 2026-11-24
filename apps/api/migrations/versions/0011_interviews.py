"""Interview Assistant: guías versionadas, preguntas por requisito y feedback humano."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Alembic carga los scripts de versión antes de comparar metadata. Registrar aquí
# los modelos evita tocar `migrations/env.py` y mantiene `alembic check` sincero.
import app.interviews.models  # noqa: F401

revision: str = "0011_interviews"
down_revision: str | None = "0010_agent_runtime"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, validate_strings=True)


def upgrade() -> None:
    op.create_table(
        "interview_guides",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            _enum("interview_guide_status", "draft", "published", "archived"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_interview_guides_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name="fk_interview_guides_application_id_applications",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_interview_guides_created_by_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_interview_guides"),
        sa.UniqueConstraint(
            "organization_id",
            "application_id",
            "version",
            name="uq_interview_guides_org_app_version",
        ),
        sa.CheckConstraint("version >= 1", name="ck_interview_guides_version_positive"),
    )
    op.create_index("ix_interview_guides_organization_id", "interview_guides", ["organization_id"])
    op.create_index("ix_interview_guides_application_id", "interview_guides", ["application_id"])
    op.create_index("ix_interview_guides_status", "interview_guides", ["status"])

    op.create_table(
        "interview_guide_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("guide_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_interview_guide_revisions_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["guide_id"],
            ["interview_guides.id"],
            name="fk_interview_guide_revisions_guide_id_interview_guides",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_interview_guide_revisions_created_by_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_interview_guide_revisions"),
        sa.UniqueConstraint(
            "guide_id", "version", name="uq_interview_guide_revisions_guide_version"
        ),
        sa.CheckConstraint(
            "version >= 1", name="ck_interview_guide_revisions_version_positive"
        ),
    )
    op.create_index(
        "ix_interview_guide_revisions_organization_id",
        "interview_guide_revisions",
        ["organization_id"],
    )
    op.create_index(
        "ix_interview_guide_revisions_guide_id", "interview_guide_revisions", ["guide_id"]
    )

    op.create_table(
        "interview_questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("guide_id", sa.Uuid(), nullable=False),
        sa.Column("requirement_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "category",
            _enum("interview_question_category", "technical", "deep_dive"),
            nullable=False,
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("evidence_focus", sa.String(1000), nullable=False),
        sa.Column("competency", sa.String(100), nullable=False),
        sa.Column(
            "status",
            _enum("interview_question_status", "draft", "approved", "rejected", "archived"),
            nullable=False,
        ),
        sa.Column(
            "review_required", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("model_version", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(50), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_interview_questions_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["guide_id"],
            ["interview_guides.id"],
            name="fk_interview_questions_guide_id_interview_guides",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_interview_questions_created_by_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_interview_questions"),
        sa.UniqueConstraint("guide_id", "position", name="uq_interview_questions_guide_position"),
        sa.UniqueConstraint(
            "guide_id",
            "requirement_id",
            "category",
            name="uq_interview_questions_guide_requirement_category",
        ),
        sa.CheckConstraint("position > 0", name="ck_interview_questions_position_positive"),
        sa.CheckConstraint(
            "length(question) <= 2000", name="ck_interview_questions_question_length"
        ),
    )
    op.create_index(
        "ix_interview_questions_organization_id", "interview_questions", ["organization_id"]
    )
    op.create_index("ix_interview_questions_guide_id", "interview_questions", ["guide_id"])
    op.create_index(
        "ix_interview_questions_requirement_id", "interview_questions", ["requirement_id"]
    )
    op.create_index("ix_interview_questions_status", "interview_questions", ["status"])

    op.create_table(
        "interview_feedbacks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("guide_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("interviewer_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            _enum("interview_feedback_status", "pending", "submitted", "needs_review"),
            nullable=False,
        ),
        sa.Column("observed_evidence", sa.JSON(), nullable=False),
        sa.Column("gaps", sa.JSON(), nullable=False),
        sa.Column(
            "follow_up_needed", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_interview_feedbacks_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["interview_questions.id"],
            name="fk_interview_feedbacks_question_id_interview_questions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["guide_id"],
            ["interview_guides.id"],
            name="fk_interview_feedbacks_guide_id_interview_guides",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name="fk_interview_feedbacks_application_id_applications",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["interviewer_id"],
            ["users.id"],
            name="fk_interview_feedbacks_interviewer_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_interview_feedbacks"),
        sa.CheckConstraint("length(notes) <= 1000", name="ck_interview_feedbacks_notes_length"),
    )
    op.create_index(
        "ix_interview_feedbacks_organization_id", "interview_feedbacks", ["organization_id"]
    )
    op.create_index("ix_interview_feedbacks_question_id", "interview_feedbacks", ["question_id"])
    op.create_index("ix_interview_feedbacks_guide_id", "interview_feedbacks", ["guide_id"])
    op.create_index(
        "ix_interview_feedbacks_application_id", "interview_feedbacks", ["application_id"]
    )
    op.create_index("ix_interview_feedbacks_status", "interview_feedbacks", ["status"])


def downgrade() -> None:
    op.drop_index("ix_interview_feedbacks_status", table_name="interview_feedbacks")
    op.drop_index("ix_interview_feedbacks_application_id", table_name="interview_feedbacks")
    op.drop_index("ix_interview_feedbacks_guide_id", table_name="interview_feedbacks")
    op.drop_index("ix_interview_feedbacks_question_id", table_name="interview_feedbacks")
    op.drop_index("ix_interview_feedbacks_organization_id", table_name="interview_feedbacks")
    op.drop_table("interview_feedbacks")

    op.drop_index("ix_interview_questions_status", table_name="interview_questions")
    op.drop_index("ix_interview_questions_requirement_id", table_name="interview_questions")
    op.drop_index("ix_interview_questions_guide_id", table_name="interview_questions")
    op.drop_index("ix_interview_questions_organization_id", table_name="interview_questions")
    op.drop_table("interview_questions")

    op.drop_index("ix_interview_guide_revisions_guide_id", table_name="interview_guide_revisions")
    op.drop_index(
        "ix_interview_guide_revisions_organization_id", table_name="interview_guide_revisions"
    )
    op.drop_table("interview_guide_revisions")

    op.drop_index("ix_interview_guides_status", table_name="interview_guides")
    op.drop_index("ix_interview_guides_application_id", table_name="interview_guides")
    op.drop_index("ix_interview_guides_organization_id", table_name="interview_guides")
    op.drop_table("interview_guides")
