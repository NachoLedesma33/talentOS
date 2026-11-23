"""Línea base de esquema: sin DDL de negocio en Fase 1.

Las entidades (con organization_id) se introducen en Fase 2 mediante revisiones nuevas.
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Revise 0001 no crea objetos: es el punto de partida del historial."""
    pass


def downgrade() -> None:
    """No hay esquema creado por esta revisión; la reversión no ejecuta DDL."""
    pass
