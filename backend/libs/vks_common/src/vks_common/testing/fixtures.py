"""Общие фикстуры pytest – подключены плагином в ``backend/conftest.py`` и доступны тестам всех пакетов."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from vks_common.testing.kafka import start_kafka
from vks_common.testing.postgres import PostgresServer, docker_is_available, start_postgres

__all__ = ["kafka_bootstrap", "postgres"]


@pytest.fixture(scope="session")
def postgres() -> Iterator[PostgresServer]:
    """PostgreSQL с ролями и схемами сервисов – один контейнер на сессию pytest.

    Без Docker тест пропускается, а не падает: модульные тесты на ноутбуке без Docker продолжают работать, а в CI
    Docker есть.
    """
    if not docker_is_available():
        pytest.skip("Docker недоступен: интеграционным тестам нужен testcontainers")
    with start_postgres() as server:
        yield server


@pytest.fixture(scope="session")
def kafka_bootstrap() -> Iterator[str]:
    """Брокер Kafka (KRaft) – один контейнер на сессию pytest; значение – адрес для ``bootstrap_servers``."""
    if not docker_is_available():
        pytest.skip("Docker недоступен: интеграционным тестам нужен testcontainers")
    with start_kafka() as bootstrap:
        yield bootstrap
