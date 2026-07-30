_runtime_api_token = ""


def set_api_token(token: str) -> None:
    global _runtime_api_token
    _runtime_api_token = token.strip()


def get_api_token() -> str:
    return _runtime_api_token
