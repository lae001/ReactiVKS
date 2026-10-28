"""Встреча, ее жизненный цикл и правила полей."""

from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import Enum, StrEnum
from uuid import UUID

from meeting_service.domain.errors import (
    InvalidAnalysisFps,
    InvalidTitle,
    MeetingCancelled,
    MeetingEnded,
    MeetingNotEditable,
    MeetingNotStarted,
)
from meeting_service.domain.identifiers import MeetingId, UserId

__all__ = [
    "DEFAULT_ANALYSIS_FPS",
    "INVITE_CODE_ENTROPY_BYTES",
    "MAX_ANALYSIS_FPS",
    "MAX_TITLE_LENGTH",
    "MIN_ANALYSIS_FPS",
    "UNCHANGED",
    "AnalysisDefaults",
    "EndReason",
    "InvalidCursor",
    "Meeting",
    "MeetingCursor",
    "MeetingEdit",
    "MeetingOverview",
    "MeetingQuery",
    "MeetingStatus",
    "Organizer",
    "Unchanged",
    "check_analysis_fps",
    "invite_code_from",
    "is_invite_code",
    "normalize_title",
]

MAX_TITLE_LENGTH = 200
MIN_ANALYSIS_FPS = 2
MAX_ANALYSIS_FPS = 5
DEFAULT_ANALYSIS_FPS = 3

# Код приглашения – 10 символов base32 в нижнем регистре (50 бит): короткий для ссылки и непредсказуемый для
# перебора. 7 случайных байт дают 56 бит, из которых берутся первые 50.
INVITE_CODE_LENGTH = 10
INVITE_CODE_ENTROPY_BYTES = 7
_INVITE_CODE_PATTERN = re.compile(r"^[a-z2-7]{10}$")


class MeetingStatus(StrEnum):
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    ENDED = "ended"
    CANCELLED = "cancelled"


class EndReason(StrEnum):
    ORGANIZER = "organizer"
    EMPTY_TIMEOUT = "empty_timeout"
    ADMIN = "admin"


class Unchanged(Enum):
    """Поле не передано в ``PATCH`` – в отличие от явного ``null`` (``scheduled_at: null`` – встреча «сейчас»)."""

    UNCHANGED = "unchanged"


UNCHANGED = Unchanged.UNCHANGED


@dataclass(frozen=True, slots=True)
class Organizer:
    """Вызывающий организатор – по проверенному access-токену."""

    user_id: UserId
    name: str


@dataclass(frozen=True, slots=True)
class AnalysisDefaults:
    """Настройки анализа, которые получает новая встреча, если организатор их не указал."""

    enabled: bool = True
    fps: int = DEFAULT_ANALYSIS_FPS


@dataclass(frozen=True, slots=True)
class MeetingEdit:
    """Изменение параметров встречи. ``None`` (и ``UNCHANGED`` у времени) – поле оставить как есть."""

    title: str | None = None
    scheduled_at: datetime | None | Unchanged = UNCHANGED
    analysis_enabled: bool | None = None
    analysis_fps: int | None = None


@dataclass(frozen=True, slots=True)
class Meeting:
    """Встреча. ``id`` – одновременно имя комнаты LiveKit.

    Жизненный цикл (04-data-model.md): ``scheduled → active`` первым входом организатора, ``active → ended``
    завершением; ``scheduled → cancelled`` – отменой. Из ``ended`` и ``cancelled`` переходов нет.
    """

    id: MeetingId
    owner_id: UserId
    owner_name: str
    title: str
    invite_code: str
    status: MeetingStatus
    analysis_enabled: bool
    analysis_fps: int
    created_at: datetime
    scheduled_at: datetime | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    end_reason: EndReason | None = None

    @classmethod
    def schedule(
        cls,
        *,
        meeting_id: MeetingId,
        organizer: Organizer,
        title: str,
        invite_code: str,
        scheduled_at: datetime | None,
        analysis_enabled: bool,
        analysis_fps: int,
        now: datetime,
    ) -> Meeting:
        """Новая встреча организатора. Встреча «сейчас» (без времени) тоже начинается как ``scheduled``."""
        return cls(
            id=meeting_id,
            owner_id=organizer.user_id,
            # Имя из токена – снимок для лобби гостя. auth-service выдает имя 1–100 символов.
            owner_name=organizer.name,
            title=normalize_title(title),
            invite_code=invite_code,
            status=MeetingStatus.SCHEDULED,
            analysis_enabled=analysis_enabled,
            analysis_fps=check_analysis_fps(analysis_fps),
            scheduled_at=scheduled_at,
            created_at=now,
        )

    def started(self, now: datetime) -> Meeting:
        """Вход организатора: первый вход активирует встречу, повторный ничего не меняет."""
        if self.status is MeetingStatus.SCHEDULED:
            return replace(self, status=MeetingStatus.ACTIVE, started_at=now)
        self._ensure_not_closed()
        return self

    def ensure_open_for_guests(self) -> None:
        """Гость входит только в идущую встречу: до входа организатора ему отвечают «еще не началась»."""
        self.ensure_in_progress()

    def ensure_in_progress(self) -> None:
        """Встреча идет: в ней есть кого модерировать и куда входить."""
        if self.status is MeetingStatus.SCHEDULED:
            raise MeetingNotStarted()
        self._ensure_not_closed()

    def ended(self, now: datetime, reason: EndReason) -> Meeting:
        """Завершение. Повторное – без изменений: ``POST /end`` идемпотентен.

        Незапущенную встречу завершить нельзя: ее отменяют (``DELETE``), иначе в истории появилась бы «прошедшая»
        встреча, которой не было.
        """
        if self.status is MeetingStatus.ENDED:
            return self
        if self.status is MeetingStatus.CANCELLED:
            raise MeetingCancelled()
        if self.status is MeetingStatus.SCHEDULED:
            raise MeetingNotStarted("Meeting that has not started can be cancelled, not ended")
        return replace(self, status=MeetingStatus.ENDED, ended_at=now, end_reason=reason)

    def edited(self, edit: MeetingEdit) -> Meeting:
        """Встреча с новыми параметрами; без изменений – тот же объект.

        Название меняется в любом статусе. Время и анализ – только до начала: идущей встречей уже пользуются
        участники и ML-агент, а у прошедшей это история. Переданное, но совпадающее значение изменением не считается –
        форма фронтенда может прислать все поля разом.
        """
        changed = replace(
            self,
            title=normalize_title(edit.title) if edit.title is not None else self.title,
            scheduled_at=self.scheduled_at if isinstance(edit.scheduled_at, Unchanged) else edit.scheduled_at,
            analysis_enabled=self.analysis_enabled if edit.analysis_enabled is None else edit.analysis_enabled,
            analysis_fps=self.analysis_fps if edit.analysis_fps is None else check_analysis_fps(edit.analysis_fps),
        )
        if changed == self:
            return self
        settings_changed = (changed.scheduled_at, changed.analysis_enabled, changed.analysis_fps) != (
            self.scheduled_at,
            self.analysis_enabled,
            self.analysis_fps,
        )
        if settings_changed and self.status is not MeetingStatus.SCHEDULED:
            raise MeetingNotEditable()
        return changed

    def closed(self, now: datetime) -> Meeting:
        """Перед удалением: идущая встреча завершается организатором, незапущенная отменяется.

        Завершенная и отмененная остаются как есть – удаляется уже закрытая встреча.
        """
        if self.status is MeetingStatus.ACTIVE:
            return self.ended(now, EndReason.ORGANIZER)
        if self.status is MeetingStatus.SCHEDULED:
            return replace(self, status=MeetingStatus.CANCELLED)
        return self

    def room_closed(self, now: datetime) -> Meeting:
        """LiveKit закрыл пустую комнату (``room_finished``): идущая встреча завершается по ``empty_timeout``.

        Встреча, завершенная организатором раньше (его ``DeleteRoom`` и вызвал вебхук), остается как есть.
        """
        if self.status is MeetingStatus.ACTIVE:
            return self.ended(now, EndReason.EMPTY_TIMEOUT)
        return self

    def _ensure_not_closed(self) -> None:
        if self.status is MeetingStatus.ENDED:
            raise MeetingEnded()
        if self.status is MeetingStatus.CANCELLED:
            raise MeetingCancelled()


@dataclass(frozen=True, slots=True)
class MeetingOverview:
    """Встреча и число ее участников – то, что показывают карточка и список."""

    meeting: Meeting
    participants_count: int


@dataclass(frozen=True, slots=True)
class MeetingQuery:
    """Фильтры истории встреч. Даты сравниваются с моментом встречи: началом, иначе плановым временем, иначе
    созданием."""

    statuses: frozenset[MeetingStatus] = frozenset()
    text: str | None = None
    date_from: date | None = None
    date_to: date | None = None


class InvalidCursor(ValueError):
    """Курсор не выдан этим сервисом или поврежден."""


@dataclass(frozen=True, slots=True)
class MeetingCursor:
    """Позиция в списке встреч: ключ сортировки и ``id`` последней выданной встречи (курсорная пагинация)."""

    sort_key: datetime
    meeting_id: UUID

    def encode(self) -> str:
        payload = json.dumps({"k": self.sort_key.isoformat(), "id": str(self.meeting_id)}, separators=(",", ":"))
        return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")

    @classmethod
    def decode(cls, value: str) -> MeetingCursor:
        try:
            raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
            payload = json.loads(raw)
            sort_key = datetime.fromisoformat(payload["k"])
            meeting_id = UUID(payload["id"])
        except (binascii.Error, ValueError, TypeError, KeyError) as error:
            raise InvalidCursor("cursor is not valid") from error
        if sort_key.tzinfo is None:
            raise InvalidCursor("cursor is not valid")
        return cls(sort_key=sort_key, meeting_id=meeting_id)


def normalize_title(raw: str) -> str:
    """Название без пробелов по краям, от 1 до 200 символов."""
    title = raw.strip()
    if not title or len(title) > MAX_TITLE_LENGTH:
        raise InvalidTitle(f"Title must be 1 to {MAX_TITLE_LENGTH} characters long", field="title")
    return title


def check_analysis_fps(fps: int) -> int:
    """Частота анализа – 2–5 кадров в секунду: реже панель запаздывает, чаще не тянет CPU ML-сервиса."""
    if not MIN_ANALYSIS_FPS <= fps <= MAX_ANALYSIS_FPS:
        raise InvalidAnalysisFps(
            f"Analysis rate must be {MIN_ANALYSIS_FPS} to {MAX_ANALYSIS_FPS} frames per second",
            field="analysis_fps",
        )
    return fps


def invite_code_from(entropy: bytes) -> str:
    """Код приглашения из случайных байт. Случайность приносит вызывающий: домен ее не создает."""
    if len(entropy) < INVITE_CODE_ENTROPY_BYTES:
        raise ValueError(f"нужно не меньше {INVITE_CODE_ENTROPY_BYTES} случайных байт")
    return base64.b32encode(entropy[:INVITE_CODE_ENTROPY_BYTES]).decode("ascii").lower()[:INVITE_CODE_LENGTH]


def is_invite_code(value: str) -> bool:
    """Похожа ли строка на код приглашения – чтобы мусор из адресной строки не доходил до БД."""
    return _INVITE_CODE_PATTERN.match(value) is not None
