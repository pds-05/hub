import httpx

from app.core.config import get_settings


class AlertmanagerClient:
    def __init__(self) -> None:
        self.base_url = get_settings().alertmanager_url.rstrip("/")

    async def alerts(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{self.base_url}/api/v2/alerts")
            response.raise_for_status()
            return response.json()


def get_alertmanager_client() -> AlertmanagerClient:
    return AlertmanagerClient()

