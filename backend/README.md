# Backend

FastAPI backend for the K8s intelligent monitoring platform.

## Local run

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

API docs:

```text
http://127.0.0.1:8000/docs
```

## In-cluster service addresses

```text
PostgreSQL: postgresql.platform.svc:5432
Redis: redis.platform.svc:6379
Prometheus: monitoring-ack-prometheus-prometheus.monitoring.svc:9090
Alertmanager: monitoring-ack-prometheus-alertmanager.monitoring.svc:9093
Loki: loki-gateway.logging.svc.cluster.local
```


## DeepSeek AI Assistant

The AI Assistant uses DeepSeek-compatible chat completions by default.

Local `.env` example:

```env
AI_API_BASE_URL=https://api.deepseek.com
AI_API_KEY=sk-your-deepseek-api-key
AI_MODEL=deepseek-v4-flash
```

Restart the backend after editing `.env`:

```bash
uvicorn app.main:app --reload
```

The assistant sends monitoring context plus matched ops runbooks to the model. If `AI_API_KEY` is empty or the provider request fails, the backend returns local rule-based analysis instead.

Do not commit a real API key. Keep it only in `.env` locally or in a Kubernetes Secret in production.


AI call boundary:

- Normal monitoring, target checks, alert evaluation, and notification sending do not call DeepSeek.
- DeepSeek is called only by the authenticated `POST /api/v1/assistant/analyze` endpoint.
- The frontend calls that endpoint only when the user clicks an AI analysis button.
- The request contains only the current question, selected target/check data, recent alert summaries, recent notification summaries, and matched runbooks.
- Keep full logs, secrets, passwords, tokens, and unnecessary private data out of AI context.
