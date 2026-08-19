import asyncio
import unittest
from unittest.mock import patch

from app.services.dify_diagnosis_client import DifyDiagnosisClient, DifyDiagnosisNotConfiguredError


class FakeStreamResponse:
    def __init__(self, lines):
        self.lines = lines

    def raise_for_status(self):
        return None

    async def aiter_lines(self):
        for line in self.lines:
            yield line


class FakeStream:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, exc_type, exc, traceback):
        return None


class FakeAsyncClient:
    requests = []

    def __init__(self, **kwargs):
        self.timeout = kwargs["timeout"]

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    response_lines = []

    def stream(self, method, url, *, headers, json):
        self.requests.append({"url": url, "headers": headers, "json": json})
        return FakeStream(FakeStreamResponse(self.response_lines))


class DifyDiagnosisClientTest(unittest.TestCase):
    def test_requires_base_url_and_app_key(self):
        client = DifyDiagnosisClient(base_url="", api_key="")

        with self.assertRaises(DifyDiagnosisNotConfiguredError):
            asyncio.run(client.diagnose(question="diagnose", diagnosis_token="token", diagnosis_id=1))

    def test_sends_only_question_and_short_lived_diagnosis_token(self):
        client = DifyDiagnosisClient(base_url="https://dify.example.com/v1", api_key="app-key", timeout_seconds=90)
        FakeAsyncClient.requests = []
        FakeAsyncClient.response_lines = [
            "event: message",
            'data: {"conversation_id":"conversation-1","message_id":"message-1","answer":"diagnosis "}',
            "",
            'data: {"event":"agent_message","answer":"report"}',
            "",
            "event: message_end",
            'data: {"conversation_id":"conversation-1","id":"message-1","metadata":{"usage":{"total_tokens":12}}}',
            "",
        ]

        with patch("app.services.dify_diagnosis_client.httpx.AsyncClient", FakeAsyncClient):
            result = asyncio.run(client.diagnose(question="check RabbitMQ", diagnosis_token="short-lived-token", diagnosis_id=42))

        self.assertEqual(result.answer, "diagnosis report")
        self.assertEqual(result.conversation_id, "conversation-1")
        self.assertEqual(result.message_id, "message-1")
        self.assertEqual(result.metadata["usage"]["total_tokens"], 12)
        request = FakeAsyncClient.requests[0]
        self.assertEqual(request["url"], "https://dify.example.com/v1/chat-messages")
        self.assertEqual(request["headers"]["Authorization"], "Bearer app-key")
        self.assertEqual(request["json"]["inputs"], {"diagnosis_token": "short-lived-token"})
        self.assertEqual(request["json"]["response_mode"], "streaming")
        self.assertEqual(request["json"]["user"], "platform-diagnosis-42")
        self.assertNotIn("target_id", request["json"])
        self.assertNotIn("event_id", request["json"])


if __name__ == "__main__":
    unittest.main()