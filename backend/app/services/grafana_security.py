import hashlib
import hmac


def effective_proxy_secret(settings: object) -> str:
    configured = str(getattr(settings, "grafana_data_proxy_secret", "") or "").strip()
    if configured:
        return configured
    secret_key = str(getattr(settings, "secret_key", "") or "").encode("utf-8")
    return hmac.new(secret_key, b"monitor-platform-grafana-proxy", hashlib.sha256).hexdigest()
