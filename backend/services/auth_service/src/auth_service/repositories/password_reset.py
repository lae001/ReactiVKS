"""Блокировка и однократное погашение восстановления в транзакции."""

from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.domain.identifiers import UserId
from auth_service.models.password_reset import PasswordResetRow, ResetRateRow


class ResetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def allow(self, key: str, now: datetime) -> bool:
        statement = insert(ResetRateRow).values(key=key, requested_at=now)
        return (
            await self.session.scalar(
                statement.on_conflict_do_update(
                    index_elements=[ResetRateRow.key],
                    set_={"requested_at": now},
                    where=ResetRateRow.requested_at <= now - timedelta(seconds=60),
                ).returning(ResetRateRow.key)
            )
            is not None
        )

    async def add(self, token_hash: bytes, user_id: UserId, now: datetime) -> None:
        self.session.add(
            PasswordResetRow(token_hash=token_hash, user_id=user_id, expires_at=now + timedelta(minutes=30))
        )

    async def user_for_token(self, token_hash: bytes, now: datetime) -> UserId | None:
        identity = await self.session.scalar(
            select(PasswordResetRow.user_id).where(PasswordResetRow.token_hash == token_hash)
        )
        if identity is None:
            return None
        await self.session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(str(identity), 1))))
        row = (
            await self.session.execute(
                select(PasswordResetRow)
                .where(
                    PasswordResetRow.token_hash == token_hash,
                    PasswordResetRow.used_at.is_(None),
                    PasswordResetRow.expires_at > now,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        return UserId(row.user_id) if row else None

    async def consume_all(self, user_id: UserId, now: datetime) -> None:
        await self.session.execute(
            update(PasswordResetRow)
            .where(PasswordResetRow.user_id == user_id, PasswordResetRow.used_at.is_(None))
            .values(used_at=now)
        )
