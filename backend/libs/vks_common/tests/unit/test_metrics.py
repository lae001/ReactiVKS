"""Метрики используют шаблон маршрута и отдельный реестр каждого приложения."""

from vks_common.app import create_app
from vks_common.config import BaseServiceSettings
from vks_common.testing import app_client


async def test_metrics_have_bounded_route_labels() -> None:
    app = create_app(BaseServiceSettings(service_name="metrics-test"))

    @app.get("/items/{item_id}")
    async def item(item_id: str) -> dict[str, str]:
        return {"id": item_id}

    async with app_client(app) as client:
        await client.get("/items/sensitive-id")
        await client.get("/unknown/sensitive-id")
        metrics = (await client.get("/metrics")).text
    assert 'route="/items/{item_id}"' in metrics
    assert 'route="unmatched"' in metrics
    assert "sensitive-id" not in metrics
    create_app(BaseServiceSettings(service_name="other-metrics-test"))
