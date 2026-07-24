import time

import httpx

from app.core.config import get_settings


class LokiClient:
    def __init__(self) -> None:
        self.base_url = get_settings().loki_url.rstrip("/")

    async def query_range(self, logql: str, limit: int = 100, minutes: int = 30) -> dict:
        now_ns = int(time.time() * 1_000_000_000)
        start_ns = now_ns - minutes * 60 * 1_000_000_000
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f"{self.base_url}/loki/api/v1/query_range",
                params={
                    "query": logql,
                    "limit": limit,
                    "start": start_ns,
                    "end": now_ns,
                    "direction": "backward",
                },
            )
            response.raise_for_status()
            return response.json()


def get_loki_client() -> LokiClient:
    return LokiClient()
