"""База ORM-моделей auth-service."""

from sqlalchemy.orm import DeclarativeBase

from vks_common.db import MAPPER_ARGS, TYPE_ANNOTATION_MAP, create_metadata

__all__ = ["Base"]


class Base(DeclarativeBase):
    """Таблицы в схеме ``auth``, имена ограничений – по соглашению database.md."""

    metadata = create_metadata("auth")
    type_annotation_map = TYPE_ANNOTATION_MAP
    __mapper_args__ = MAPPER_ARGS
