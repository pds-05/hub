import asyncio
import sys
import unittest
from types import ModuleType
from unittest.mock import patch


class FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.text = "healthy response"


class FakeAsyncClient:
    response_status = 200

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        pass

    async def get(self, endpoint: str) -> FakeResponse:
        return FakeResponse(self.response_status)


# Keep this unit test independent from runtime packages and database setup.
httpx_stub = sys.modules.setdefault("httpx", ModuleType("httpx"))
httpx_stub.AsyncClient = FakeAsyncClient
httpx_stub.HTTPError = Exception

model_stub = sys.modules.setdefault("app.models.monitor_target", ModuleType("app.models.monitor_target"))
model_stub.MonitorTarget = object

from app.services.target_checker import check_http_target, is_http_error_status


class HttpStatusCheckTest(unittest.TestCase):
    def run_check(self, status_code: int):
        FakeAsyncClient.response_status = status_code
        with patch(
            "app.services.target_checker.resolve_dns",
            return_value={"dns_ok": True, "resolved_ips": ["203.0.113.10"]},
        ):
            return asyncio.run(check_http_target("http://example.com"))

    def test_status_below_400_is_healthy(self) -> None:
        result = self.run_check(399)

        self.assertFalse(is_http_error_status(399))
        self.assertEqual(result.status, "up")
        self.assertEqual(result.status_code, 399)

    def test_status_400_is_an_error(self) -> None:
        self.assertTrue(is_http_error_status(400))

    def test_status_404_is_an_error(self) -> None:
        result = self.run_check(404)

        self.assertTrue(is_http_error_status(404))
        self.assertEqual(result.status, "down")
        self.assertEqual(result.status_code, 404)
        self.assertIn("HTTP status is 404", result.message)

    def test_status_599_is_an_error(self) -> None:
        self.assertTrue(is_http_error_status(599))


if __name__ == "__main__":
    unittest.main()
