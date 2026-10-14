"""Общие правила ORM-моделей сервисов.

Соглашение об именах ограничений – не косметика: без него Alembic придумывает имена сам, и ``downgrade``, которому
нужно удалить ограничение, превращается в ручную работу. Имена – по database.md: ``<таблица>_<поле>_uk``, ``_ck``,
``_idx``, ``_fkey``, ``_pkey``.

Каждый сервис объявляет свою базу моделей со своей схемой::

    class Base(DeclarativeBase):
        metadata = create_metadata("auth")
        type_annotation_map = TYPE_ANNOTATION_MAP
        __mapper_args__ = MAPPER_ARGS
"""

from __future__ import annotations

import datetime

from sqlalchemy import MetaData
from sqlalchemy.dialects.postgresql import TIMESTAMP

__all__ = ["MAPPER_ARGS", "NAMING_CONVENTION", "TYPE_ANNOTATION_MAP", "create_metadata"]

NAMING_CONVENTION = {
    "ix": "%(table_name)s_%(column_0_N_name)s_idx",
    "uq": "%(table_name)s_%(column_0_N_name)s_uk",
    "ck": "%(table_name)s_%(constraint_name)s_ck",
    "fk": "%(table_name)s_%(column_0_N_name)s_fkey",
    "pk": "%(table_name)s_pkey",
}

# Каждая колонка datetime – timestamptz: наивное время в БД делает момент неоднозначным.
TYPE_ANNOTATION_MAP: dict[type, TIMESTAMP] = {datetime.datetime: TIMESTAMP(timezone=True)}

# eager_defaults: значения, которые заполняет БД (created_at), возвращаются через RETURNING того же запроса. Без
# этого атрибут после flush «протухает», а его чтение – неявный запрос, которого в asyncio нет (MissingGreenlet).
MAPPER_ARGS: dict[str, object] = {"eager_defaults": True}


def create_metadata(schema: str) -> MetaData:
    """Метаданные моделей сервиса: все таблицы – в его схеме, имена ограничений – по соглашению."""
    return MetaData(schema=schema, naming_convention=NAMING_CONVENTION)
