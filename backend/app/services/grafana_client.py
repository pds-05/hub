import httpx
from urllib.parse import urlsplit

from app.core.config import get_settings
from app.services.grafana_runtime import get_api_token


class GrafanaError(Exception):
    pass


class GrafanaUnavailableError(GrafanaError):
    pass


class GrafanaUnauthorizedError(GrafanaError):
    pass


class GrafanaClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.grafana_url.rstrip("/")
        self.api_key = settings.grafana_api_key
        self.public_url = settings.grafana_public_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        token = self.api_key or get_api_token()
        if not token:
            return {}
        return {"Authorization": f"Bearer {token}"}

    def dashboard_public_url(self, path: str) -> str:
        if path.startswith(("http://", "https://")):
            return path
        normalized_path = path if path.startswith("/") else f"/{path}"
        public_path = urlsplit(self.public_url).path.rstrip("/")
        if public_path and (normalized_path == public_path or normalized_path.startswith(f"{public_path}/")):
            normalized_path = normalized_path[len(public_path):] or "/"
        return f"{self.public_url}{normalized_path}"

    async def dashboards(self, query: str | None = None, limit: int = 200) -> list[dict]:
        params = {"type": "dash-db", "limit": limit}
        if query:
            params["query"] = query
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self.base_url}/api/search",
                    params=params,
                    headers=self._headers(),
                )
            if response.status_code in {401, 403}:
                raise GrafanaUnauthorizedError("Grafana API Token 尚未配置或无权访问")
            response.raise_for_status()
            rows = response.json()
        except GrafanaUnauthorizedError:
            raise
        except httpx.HTTPError as exc:
            raise GrafanaUnavailableError(f"Grafana is unavailable at {self.base_url}") from exc

        dashboards: list[dict] = []
        for row in rows:
            if row.get("type") != "dash-db":
                continue
            url = row.get("url") or (f"/d/{row.get('uid')}" if row.get("uid") else "/dashboards")
            dashboards.append(
                {
                    "id": row.get("id"),
                    "uid": row.get("uid"),
                    "title": row.get("title") or "Untitled dashboard",
                    "uri": row.get("uri"),
                    "url": url,
                    "full_url": self.dashboard_public_url(url),
                    "folder_id": row.get("folderId"),
                    "folder_uid": row.get("folderUid"),
                    "folder_title": row.get("folderTitle") or "General",
                    "folder_url": row.get("folderUrl"),
                    "tags": row.get("tags") or [],
                    "is_starred": bool(row.get("isStarred")),
                }
            )
        return sorted(dashboards, key=lambda item: (item["folder_title"], item["title"]))

    async def health(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/api/health", headers=self._headers())
            if response.status_code in {401, 403}:
                raise GrafanaUnauthorizedError("Grafana API Token 尚未配置或无权访问")
            response.raise_for_status()
            data = response.json()
        except GrafanaUnauthorizedError:
            raise
        except httpx.HTTPError as exc:
            raise GrafanaUnavailableError(f"Grafana is unavailable at {self.base_url}") from exc
        return {"url": self.base_url, "public_url": self.public_url, **data}


def get_grafana_client() -> GrafanaClient:
    return GrafanaClient()


