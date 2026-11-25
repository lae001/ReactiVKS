"""Ограниченная очистка служебных данных auth-service."""

from datetime import datetime, timedelta

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.models import OUTBOX, RefreshTokenRow
from auth_service.models.password_reset import PasswordResetRow, ResetRateRow


async def purge_auth(session: AsyncSession, now: datetime) -> None:
    tokens = (
        select(RefreshTokenRow.id)
        .where(
            or_(
                RefreshTokenRow.expires_at < now - timedelta(days=7),
                RefreshTokenRow.revoked_at < now - timedelta(days=7),
            )
        )
        .limit(5000)
    )
    await session.execute(delete(RefreshTokenRow).where(RefreshTokenRow.id.in_(tokens)))
    resets = (
        select(PasswordResetRow.token_hash)
        .where(or_(PasswordResetRow.expires_at < now, PasswordResetRow.used_at.is_not(None)))
        .limit(5000)
    )
    await session.execute(delete(PasswordResetRow).where(PasswordResetRow.token_hash.in_(resets)))
    limits = select(ResetRateRow.key).where(ResetRateRow.requested_at < now - timedelta(days=1)).limit(5000)
    await session.execute(delete(ResetRateRow).where(ResetRateRow.key.in_(limits)))
    old = select(OUTBOX.c.id).where(OUTBOX.c.published_at < now - timedelta(days=7)).limit(5000)
    await session.execute(delete(OUTBOX).where(OUTBOX.c.id.in_(old)))
