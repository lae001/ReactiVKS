"""ORM-модели схемы ``meeting`` – отображение таблиц, без логики (docs/backend/database.md)."""

from meeting_service.models.base import Base
from meeting_service.models.consent import ConsentRow
from meeting_service.models.meeting import MeetingRow
from meeting_service.models.organizer_settings import OrganizerSettingsRow
from meeting_service.models.participant import ParticipantRow

__all__ = ["Base", "ConsentRow", "MeetingRow", "OrganizerSettingsRow", "ParticipantRow"]
