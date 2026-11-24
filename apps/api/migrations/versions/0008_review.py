"""Revisión humana: señal de inyección y obligatoriedad de revisión por extracción."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_review"
down_revision: str | None = "0007_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "document_extractions",
        sa.Column(
            "injection_detected",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "document_extractions",
        sa.Column(
            "review_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("document_extractions", "review_required")
    op.drop_column("document_extractions", "injection_detected")
