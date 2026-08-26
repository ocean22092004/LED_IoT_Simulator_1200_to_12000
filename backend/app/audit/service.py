from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.audit_log import AuditLog
from backend.app.db.models.user import User


async def record_audit(
    session: AsyncSession,
    *,
    user: User | None,
    action: str,
    entity_type: str,
    entity_id: UUID | None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    audit = AuditLog(
        user_id=user.id if user is not None else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata_json=dict(metadata or {}),
    )
    session.add(audit)
    await session.flush()
    return audit
