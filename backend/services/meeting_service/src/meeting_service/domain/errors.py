"""Ошибки, которые обнаруживают правила meeting-service. Коды – из реестра docs/api/rest-api.md."""

from vks_common.errors import Conflict, DependencyUnavailable, Forbidden, NotFound, Unauthorized, ValidationFailed

__all__ = [
    "ConsentRequired",
    "InvalidAnalysisFps",
    "InvalidDisplayName",
    "InvalidTitle",
    "LiveKitUnavailable",
    "MeetingCancelled",
    "MeetingEnded",
    "MeetingFull",
    "MeetingNotEditable",
    "MeetingNotFound",
    "MeetingNotStarted",
    "NoticeOutdated",
    "OrganizerBlocked",
    "OrganizerNotRemovable",
    "ParticipantNotFound",
    "ParticipantRemoved",
    "ParticipantTokenInvalid",
    "WebhookRejected",
]


class InvalidTitle(ValidationFailed):
    """Название встречи пустое или длиннее допустимого."""

    title = "Meeting title is not valid"


class InvalidDisplayName(ValidationFailed):
    """Имя участника пустое или длиннее допустимого."""

    title = "Display name is not valid"


class InvalidAnalysisFps(ValidationFailed):
    """Частота анализа вне допустимого диапазона."""

    title = "Analysis rate is not valid"


class MeetingNotFound(NotFound):
    """Встречи нет, она удалена или принадлежит другому организатору – ответ не различает эти случаи."""


class ParticipantNotFound(NotFound):
    """Участника нет в этой встрече."""


class OrganizerNotRemovable(ValidationFailed):
    """Организатор не удаляет себя из своей встречи: для этого встречу завершают."""

    title = "Organizer cannot be removed"


class MeetingNotStarted(Conflict):
    """Организатор еще не вошел: гостю рано, клиент повторяет запрос."""

    code = "meeting_not_started"
    title = "Meeting has not started yet"


class MeetingEnded(Conflict):
    code = "meeting_ended"
    title = "Meeting has ended"


class MeetingCancelled(Conflict):
    code = "meeting_cancelled"
    title = "Meeting is cancelled"


class MeetingNotEditable(Conflict):
    """Время и параметры анализа меняются только у встречи, которая еще не началась."""

    code = "meeting_not_editable"
    title = "Meeting can no longer be changed"


class MeetingFull(Conflict):
    """В комнате уже 10 участников – предел встречи."""

    code = "meeting_full"
    title = "Meeting is full"


class OrganizerBlocked(Forbidden):
    """Администратор заблокировал организатора: его access-токен еще действует, но во встречи он не входит."""

    code = "user_blocked"
    title = "User is blocked"


class ConsentRequired(Conflict):
    """Анализ во встрече включен, а решения о согласии в запросе нет."""

    code = "consent_required"
    title = "Consent decision is required"


class NoticeOutdated(Conflict):
    """Участник видел не ту версию уведомления, что действует сейчас: решение принято не о том тексте."""

    code = "notice_outdated"
    title = "Consent notice version is outdated"


class ParticipantRemoved(Conflict):
    """Организатор удалил участника из встречи: повторный вход по его токену запрещен."""

    code = "participant_removed"
    title = "Participant was removed from the meeting"


class ParticipantTokenInvalid(Unauthorized):
    """Токен гостя неизвестен. Причина не уточняется."""


class LiveKitUnavailable(DependencyUnavailable):
    """LiveKit не ответил после повторов: войти во встречу сейчас нельзя."""

    code = "livekit_unavailable"
    title = "Media server is unavailable"


class WebhookRejected(Unauthorized):
    """Вебхук без подписи LiveKit или с чужой подписью."""
