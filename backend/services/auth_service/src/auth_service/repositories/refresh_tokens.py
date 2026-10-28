"""Refresh-токены: ``auth.refresh_tokens``.

Все операции – по хешу токена. Сам токен существует один раз, в ответе, который его выдал; он не хранится, не
журналируется и не сравнивается в открытом виде.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.domain.identifiers import RefreshTokenId, SessionFamilyId, UserId
from auth_service.domain.sessions import RefreshToken
from auth_service.models import RefreshTokenRow

__all__ = ["RefreshTokenRepository"]


class RefreshTokenRepository:
    """Работает в транзакции вызывающего сценария; сам не коммитит."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, token: RefreshToken, *, user_agent: str | None, created_at: datetime) -> None:
        self._session.add(
            RefreshTokenRow(
                id=token.id,
                user_id=token.user_id,
                family_id=token.family_id,
                token_hash=token.token_hash,
                expires_at=token.expires_at,
                revoked_at=token.revoked_at,
                replaced_by=token.replaced_by,
                user_agent=user_agent,
                created_at=created_at,
            )
        )
        await self._session.flush()

    async def lock_by_hash(self, token_hash: bytes) -> RefreshToken | None:
        """Найти токен и заблокировать строку до конца транзакции.

        ``FOR UPDATE`` упорядочивает одновременные обмены одного токена: второй запрос дождется первого и увидит
        токен уже обмененным – это и есть повторное использование. Строка возвращается в любом состоянии; годен ли
        токен, решает домен.
        """
        statement = select(RefreshTokenRow).where(RefreshTokenRow.token_hash == token_hash).with_for_update()
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def get_by_hash(self, token_hash: bytes) -> RefreshToken | None:
        """Без блокировки – для выхода, который отзывает в любом случае."""
        statement = select(RefreshTokenRow).where(RefreshTokenRow.token_hash == token_hash)
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def save_rotation(self, token: RefreshToken) -> None:
        """Записать, что токен обменян: строка остается, чтобы повторное предъявление распознавалось."""
        await self._session.execute(
            update(RefreshTokenRow)
            .where(RefreshTokenRow.id == token.id)
            .values(revoked_at=token.revoked_at, replaced_by=token.replaced_by)
        )

    async def revoke_family(self, family_id: SessionFamilyId, *, at: datetime) -> int:
        """Отозвать все живые токены семьи. Возвращает, сколько отозвано.

        Одним запросом, а не циклом: строки находятся и отзываются в одном месте, и токен, вставленный только что
        закоммиченным запросом, не проскочит между чтением и записью.
        """
        result = await self._session.execute(
            update(RefreshTokenRow)
            .where(RefreshTokenRow.family_id == family_id, RefreshTokenRow.revoked_at.is_(None))
            .values(revoked_at=at)
        )
        if not isinstance(result, CursorResult):  # pragma: no cover - UPDATE всегда возвращает CursorResult
            raise TypeError("UPDATE должен вернуть CursorResult")
        return result.rowcount

    async def revoke_all_for_user(self, user_id: UserId, *, at: datetime) -> int:
        """Отозвать все живые токены пользователя – все его сессии на всех устройствах. Возвращает, сколько."""
        result = await self._session.execute(
            update(RefreshTokenRow)
            .where(RefreshTokenRow.user_id == user_id, RefreshTokenRow.revoked_at.is_(None))
            .values(revoked_at=at)
        )
        if not isinstance(result, CursorResult):  # pragma: no cover - UPDATE всегда возвращает CursorResult
            raise TypeError("UPDATE должен вернуть CursorResult")
        return result.rowcount


def _to_domain(row: RefreshTokenRow) -> RefreshToken:
    return RefreshToken(
        id=RefreshTokenId(row.id),
        user_id=UserId(row.user_id),
        family_id=SessionFamilyId(row.family_id),
        token_hash=row.token_hash,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        replaced_by=RefreshTokenId(row.replaced_by) if row.replaced_by is not None else None,
    )
