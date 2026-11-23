from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.audit.models import AuditLog


def record_audit(
    db: DBSession,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID,
) -> AuditLog:
    """Escribe metadatos de auditoría; el llamador es dueño del commit."""
    entry = AuditLog(
        organization_id=organization_id,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    db.add(entry)
    db.flush()
    return entry


def list_resource_events(
    db: DBSession,
    organization_id: uuid.UUID,
    resource_type: str,
    resource_id: uuid.UUID,
) -> list[AuditLog]:
    """Lee eventos de un recurso del tenant; nunca escribe ni expone payload."""
    stmt = (
        select(AuditLog)
        .where(
            AuditLog.organization_id == organization_id,
            AuditLog.resource_type == resource_type,
            AuditLog.resource_id == resource_id,
        )
        .order_by(AuditLog.timestamp, AuditLog.id)
    )
    return list(db.execute(stmt).scalars().all())
