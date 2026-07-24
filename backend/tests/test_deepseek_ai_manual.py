import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.ai_assistant import AIAssistantService


async def main():
    result = await AIAssistantService().analyze_incident(
        "请简单判断这个测试告警应该如何排查",
        {
            "target": {"name": "test-web", "target_type": "website", "endpoint": "https://example.com"},
            "latest_check": {
                "status": "down",
                "status_code": 500,
                "response_time_ms": 1200,
                "message": "HTTP status is 500",
                "details": {"dns_ok": True, "tls_ok": True},
            },
            "recent_alerts": [],
        },
    )
    print("enabled=" + str(result.get("enabled")))
    print("provider=" + str(result.get("provider")))
    print("model=" + str(result.get("model")))
    print("summary_preview=" + str(result.get("summary", ""))[:300].replace("\n", " "))
    print("note=" + str(result.get("note", "")))


asyncio.run(main())
