"""Фоновая сборка готовых к расчету отчетов."""

import asyncio

from sqlalchemy.exc import SQLAlchemyError

from analytics_service.services.reports import BuildReports
from vks_common.logging import get_logger

_logger = get_logger(__name__)


async def run_reports(builder: BuildReports) -> None:
    while True:
        try:
            await builder.execute()
        except SQLAlchemyError:
            _logger.exception("report worker database error")
        await asyncio.sleep(0.5)
