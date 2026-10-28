"""Сборка сценариев для запроса.

Одиночки сервиса (настройки, часы, шлюз LiveKit) создаются в ``main.py`` и лежат в ``app.state``; здесь они
достаются оттуда и передаются в конструкторы сценариев.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from meeting_service.domain.errors import ParticipantTokenInvalid
from meeting_service.domain.identifiers import UserId
from meeting_service.domain.livekit import LiveKitGateway
from meeting_service.domain.meetings import Organizer
from meeting_service.domain.participants import PARTICIPANT_TOKEN_PREFIX
from meeting_service.services.joining import (
    GetJoinInfo,
    JoinAsGuest,
    JoinAsOrganizer,
    RejoinAsGuest,
    RequestOrigin,
)
from meeting_service.services.meetings import (
    CreateMeeting,
    DeleteMeeting,
    EndMeeting,
    GetMeeting,
    ListMeetings,
    UpdateMeeting,
)
from meeting_service.services.organizer_settings import GetOrganizerSettings, SaveOrganizerSettings
from meeting_service.settings import MeetingSettings
from vks_common.auth import CurrentUser
from vks_common.clock import Clock
from vks_common.db import get_session

__all__ = [
    "CallingOrganizer",
    "CreateMeetingScenario",
    "DeleteMeetingScenario",
    "EndMeetingScenario",
    "GetJoinInfoScenario",
    "GetMeetingScenario",
    "GetOrganizerSettingsScenario",
    "GuestToken",
    "JoinAsGuestScenario",
    "JoinAsOrganizerScenario",
    "ListMeetingsScenario",
    "Origin",
    "RejoinAsGuestScenario",
    "SaveOrganizerSettingsScenario",
    "Settings",
    "UpdateMeetingScenario",
]


def get_settings(request: Request) -> MeetingSettings:
    settings = request.app.state.settings
    if not isinstance(settings, MeetingSettings):  # pragma: no cover - выставляет create_application
        raise RuntimeError("в app.state нет настроек meeting-service")
    return settings


def get_clock(request: Request) -> Clock:
    clock: Clock = request.app.state.clock
    return clock


def get_livekit(request: Request) -> LiveKitGateway:
    """Шлюз создается в lifespan: ему нужен работающий цикл событий."""
    livekit = getattr(request.app.state, "livekit", None)
    if not isinstance(livekit, LiveKitGateway):  # pragma: no cover - выставляет lifespan
        raise RuntimeError("в app.state нет livekit: шлюз создается в lifespan")
    return livekit


Settings = Annotated[MeetingSettings, Depends(get_settings)]
CurrentClock = Annotated[Clock, Depends(get_clock)]
LiveKit = Annotated[LiveKitGateway, Depends(get_livekit)]
Session = Annotated[AsyncSession, Depends(get_session)]


def get_organizer(caller: CurrentUser) -> Organizer:
    """Организатор по access-токену: ``sub`` и снимок имени для лобби гостей."""
    return Organizer(user_id=UserId(caller.user_id), name=caller.name)


CallingOrganizer = Annotated[Organizer, Depends(get_organizer)]


def get_origin(request: Request) -> RequestOrigin:
    """Адрес клиента – за Nginx его передает uvicorn с ``--proxy-headers``."""
    return RequestOrigin(
        ip=request.client.host if request.client is not None else None,
        user_agent=request.headers.get("user-agent"),
    )


Origin = Annotated[RequestOrigin, Depends(get_origin)]

# auto_error=False: отсутствие заголовка отклоняется ответом problem+json, а не телом FastAPI по умолчанию.
_participant_header = APIKeyHeader(
    name="Authorization",
    scheme_name="ParticipantToken",
    description="`Participant <participant_token>` из ответа `POST /api/v1/join/{invite_code}`",
    auto_error=False,
)


def get_guest_token(header: Annotated[str | None, Security(_participant_header)]) -> str:
    """Токен гостя из ``Authorization: Participant <токен>`` (conventions.md, §12)."""
    scheme, _, token = (header or "").partition(" ")
    token = token.strip()
    if scheme.lower() != "participant" or not token.startswith(PARTICIPANT_TOKEN_PREFIX):
        raise ParticipantTokenInvalid()
    return token


GuestToken = Annotated[str, Depends(get_guest_token)]


def build_create_meeting(session: Session, clock: CurrentClock) -> CreateMeeting:
    return CreateMeeting(session=session, clock=clock)


def build_list_meetings(session: Session) -> ListMeetings:
    return ListMeetings(session=session)


def build_get_meeting(session: Session) -> GetMeeting:
    return GetMeeting(session=session)


def build_update_meeting(session: Session, clock: CurrentClock) -> UpdateMeeting:
    return UpdateMeeting(session=session, clock=clock)


def build_end_meeting(session: Session, clock: CurrentClock, livekit: LiveKit) -> EndMeeting:
    return EndMeeting(session=session, clock=clock, livekit=livekit)


def build_delete_meeting(session: Session, clock: CurrentClock, livekit: LiveKit) -> DeleteMeeting:
    return DeleteMeeting(session=session, clock=clock, livekit=livekit)


CreateMeetingScenario = Annotated[CreateMeeting, Depends(build_create_meeting)]
ListMeetingsScenario = Annotated[ListMeetings, Depends(build_list_meetings)]
GetMeetingScenario = Annotated[GetMeeting, Depends(build_get_meeting)]
UpdateMeetingScenario = Annotated[UpdateMeeting, Depends(build_update_meeting)]
EndMeetingScenario = Annotated[EndMeeting, Depends(build_end_meeting)]
DeleteMeetingScenario = Annotated[DeleteMeeting, Depends(build_delete_meeting)]


def build_get_organizer_settings(session: Session) -> GetOrganizerSettings:
    return GetOrganizerSettings(session=session)


def build_save_organizer_settings(session: Session, clock: CurrentClock) -> SaveOrganizerSettings:
    return SaveOrganizerSettings(session=session, clock=clock)


GetOrganizerSettingsScenario = Annotated[GetOrganizerSettings, Depends(build_get_organizer_settings)]
SaveOrganizerSettingsScenario = Annotated[SaveOrganizerSettings, Depends(build_save_organizer_settings)]


def build_join_as_organizer(session: Session, clock: CurrentClock, livekit: LiveKit) -> JoinAsOrganizer:
    return JoinAsOrganizer(session=session, clock=clock, livekit=livekit)


def build_get_join_info(session: Session) -> GetJoinInfo:
    return GetJoinInfo(session=session)


def build_join_as_guest(session: Session, clock: CurrentClock, livekit: LiveKit) -> JoinAsGuest:
    return JoinAsGuest(session=session, clock=clock, livekit=livekit)


def build_rejoin_as_guest(session: Session, livekit: LiveKit) -> RejoinAsGuest:
    return RejoinAsGuest(session=session, livekit=livekit)


JoinAsOrganizerScenario = Annotated[JoinAsOrganizer, Depends(build_join_as_organizer)]
GetJoinInfoScenario = Annotated[GetJoinInfo, Depends(build_get_join_info)]
JoinAsGuestScenario = Annotated[JoinAsGuest, Depends(build_join_as_guest)]
RejoinAsGuestScenario = Annotated[RejoinAsGuest, Depends(build_rejoin_as_guest)]
