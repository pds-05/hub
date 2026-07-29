def normalize_agent_public_api_url(url: str) -> str:
    return url.strip().rstrip("/")
