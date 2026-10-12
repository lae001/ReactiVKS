"""Ключи из JWKS auth-service с кешем (05-security-privacy.md, §5.2).

Ключи загружаются при первом запросе и кешируются на час. Неизвестный ``kid`` – повод перезагрузить JWKS раньше
(auth-service мог сменить ключ), но не чаще раза в ``refresh_min_interval_seconds``: иначе поток токенов с
выдуманным ``kid`` превратился бы в поток запросов к auth-service.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

import httpx
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

from vks_common.auth.keys import UnknownSigningKey, key_from_jwk
from vks_common.logging import get_logger

__all__ = ["JwksKeys"]

_logger = get_logger(__name__)


class JwksKeys:
    """Источник ключей, загружаемых по HTTP из ``JWKS_URL``."""

    def __init__(
        self,
        url: str,
        *,
        http_client: httpx.AsyncClient,
        cache_ttl_seconds: float = 3600.0,
        refresh_min_interval_seconds: float = 10.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._url = url
        self._http = http_client
        self._cache_ttl = cache_ttl_seconds
        self._refresh_min_interval = refresh_min_interval_seconds
        self._monotonic = monotonic
        self._keys: dict[str, RSAPublicKey] = {}
        self._fetched_at: float | None = None
        self._attempted_at: float | None = None
        self._lock = asyncio.Lock()

    async def key_for(self, kid: str) -> RSAPublicKey:
        if self._should_refresh(kid):
            async with self._lock:
                # Пока ждали блокировку, ключи мог загрузить соседний запрос.
                if self._should_refresh(kid):
                    await self._refresh()
        try:
            return self._keys[kid]
        except KeyError as error:
            raise UnknownSigningKey(kid) from error

    def _should_refresh(self, kid: str) -> bool:
        now = self._monotonic()
        # Частота попыток ограничена всегда – и при неизвестном kid, и при недоступном auth-service.
        if self._attempted_at is not None and now - self._attempted_at < self._refresh_min_interval:
            return False
        is_stale = self._fetched_at is None or now - self._fetched_at >= self._cache_ttl
        return is_stale or kid not in self._keys

    async def _refresh(self) -> None:
        """Загрузить JWKS. При сбое остаются прежние ключи: ненадолго недоступный auth-service – не повод отвергать
        токены, подписанные уже известным ключом."""
        self._attempted_at = self._monotonic()
        try:
            response = await self._http.get(self._url)
            response.raise_for_status()
            document = response.json()
        except (httpx.HTTPError, ValueError) as error:
            _logger.warning("jwks refresh failed", error=type(error).__name__)
            return

        keys: dict[str, RSAPublicKey] = {}
        for entry in document.get("keys", []) if isinstance(document, dict) else []:
            kid = entry.get("kid") if isinstance(entry, dict) else None
            if not isinstance(kid, str):
                continue
            try:
                keys[kid] = key_from_jwk(entry)
            except ValueError as error:
                _logger.warning("jwks entry skipped", kid=kid, reason=str(error))
        self._keys = keys
        self._fetched_at = self._monotonic()
        _logger.info("jwks refreshed", kids=sorted(keys))
