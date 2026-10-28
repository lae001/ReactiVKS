"""JSON Schema всех событий – для контрактного теста: схема сверяется со снимком в репозитории.

Совместимость проверяется в CI без Schema Registry (ADR-012): изменение контракта меняет снимок, а снимок
меняется только вместе с docs/api/events.md.

    uv run vks-contracts-schema > libs/vks_contracts/tests/snapshots/events.schema.json
"""

from __future__ import annotations

import json
import sys

from vks_contracts.envelope import EventEnvelope
from vks_contracts.registry import EVENT_TYPES

__all__ = ["events_schema", "main"]


def events_schema() -> dict[str, object]:
    """Конверт и payload каждого (типа, версии) с топиком и ключом – в детерминированном порядке."""
    events: dict[str, object] = {}
    for (event_type, version), model in sorted(EVENT_TYPES.items()):
        events[f"{event_type}.v{version}"] = {
            "topic": model.topic.value,
            "payload": model.model_json_schema(),
        }
    return {"envelope": EventEnvelope.model_json_schema(), "events": events}


def render() -> str:
    return json.dumps(events_schema(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> None:
    sys.stdout.write(render())
