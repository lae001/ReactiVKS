"""Согласие на анализ эмоций (функция 6.4): какое решение принято и о каком тексте уведомления."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from meeting_service.domain.errors import ConsentRequired, NoticeOutdated
from meeting_service.domain.identifiers import MeetingId, ParticipantId
from meeting_service.domain.participants import ConsentState

__all__ = [
    "CURRENT_NOTICE",
    "ConsentDecision",
    "ConsentNotice",
    "ConsentRecord",
    "check_notice_version",
    "decide_consent",
]


class ConsentDecision(StrEnum):
    """Решение, которое участник принимает при входе."""

    GRANTED = "granted"
    DENIED = "denied"


@dataclass(frozen=True, slots=True)
class ConsentNotice:
    """Текст уведомления, который участник видит перед решением, и его версия – она пишется в журнал."""

    version: str
    text_md: str


# TODO(EMO-65): заменить черновик текстом consent-notice v1, согласованным с заказчиком.
CURRENT_NOTICE = ConsentNotice(
    version="v1-draft",
    text_md=(
        "Во время встречи Система распознает эмоции по выражению вашего лица и показывает их организатору. "
        "Видео не записывается и не сохраняется: хранятся только посекундные итоги распознавания для отчета "
        "организатора. Результаты носят вероятностный характер и не являются оценкой личности."
    ),
)


@dataclass(frozen=True, slots=True)
class ConsentRecord:
    """Строка журнала согласий. Имя и название – снимки: журнал переживает очистку встреч."""

    meeting_id: MeetingId
    participant_id: ParticipantId
    display_name: str
    meeting_title: str
    decision: ConsentState
    notice_version: str
    decided_at: datetime
    ip: str | None = None
    user_agent: str | None = None


def decide_consent(*, analysis_enabled: bool, decision: ConsentDecision | None) -> ConsentState:
    """Состояние согласия участника при входе.

    Во встрече без анализа согласие не спрашивается вовсе; с анализом решение обязательно – молчание согласием не
    считается.
    """
    if not analysis_enabled:
        return ConsentState.NOT_REQUIRED
    if decision is None:
        raise ConsentRequired()
    return ConsentState(decision.value)


def check_notice_version(shown_version: str | None, *, notice: ConsentNotice) -> None:
    """Участник решал, прочитав действующий текст уведомления. Иначе решение не о том, о чем спрашивают."""
    if shown_version is None:
        raise ConsentRequired("Version of the consent notice shown to the participant is required")
    if shown_version != notice.version:
        raise NoticeOutdated()
