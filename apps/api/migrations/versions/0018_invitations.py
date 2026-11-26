"""Invitaciones por token con organización, rol y expiración."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_invitations"
down_revision: str | None = "0017_password_reset"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "owner",
                "admin",
                "recruiter",
                "reviewer",
                "viewer",
                name="membership_role",
                native_enum=False,
                validate_strings=True,
            ),
            nullable=False,
        ),
        # SHA-256 hex: 64 caracteres. El token en claro nunca se persiste.
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("invited_by", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["invited_by"],
            ["users.id"],
            name="fk_invitations_invited_by_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_invitations_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_invitations"),
        sa.UniqueConstraint("token_hash", name="uq_invitations_token_hash"),
        sa.CheckConstraint("email = lower(email)", name="email_lowercase"),
        sa.CheckConstraint("length(token_hash) = 64", name="token_hash_length"),
    )
    op.create_index(
        "ix_invitations_organization_id", "invitations", ["organization_id"]
    )
    op.create_index("ix_invitations_token_hash", "invitations", ["token_hash"])
    op.create_index(
        "ix_invitations_organization_id_email",
        "invitations",
        ["organization_id", "email"],
    )


def downgrade() -> None:
    op.drop_index("ix_invitations_organization_id_email", table_name="invitations")
    op.drop_index("ix_invitations_token_hash", table_name="invitations")
    op.drop_index("ix_invitations_organization_id", table_name="invitations")
    op.drop_table("invitations")
