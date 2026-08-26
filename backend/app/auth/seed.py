import asyncio
from uuid import UUID, uuid5

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.service import hash_password, verify_password
from backend.app.common.enums import UserRole
from backend.app.config import Settings
from backend.app.db.models.user import User

USER_NAMESPACE = UUID("4ad38e3e-d970-5a18-8894-143fd69d8c13")


async def seed_default_users(session: AsyncSession, settings: Settings) -> int:
    configured_users = {
        "admin": (settings.admin_password.get_secret_value(), UserRole.ADMIN),
        "staff": (settings.staff_password.get_secret_value(), UserRole.STAFF),
        "tech": (settings.tech_password.get_secret_value(), UserRole.TECHNICIAN),
    }
    result = await session.execute(
        select(User).where(User.username.in_(list(configured_users)))
    )
    existing = {user.username: user for user in result.scalars()}

    for username, (password, role) in configured_users.items():
        user = existing.get(username)
        if user is None:
            session.add(
                User(
                    id=uuid5(USER_NAMESPACE, username),
                    username=username,
                    password_hash=await asyncio.to_thread(hash_password, password),
                    role=role,
                    is_active=True,
                )
            )
            continue

        if not await asyncio.to_thread(verify_password, password, user.password_hash):
            user.password_hash = await asyncio.to_thread(hash_password, password)
        user.role = role
        user.is_active = True

    await session.flush()
    count = await session.scalar(
        select(func.count())
        .select_from(User)
        .where(User.username.in_(list(configured_users)))
    )
    return int(count or 0)
