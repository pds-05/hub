#!/usr/bin/env python3
"""
Batch service health check script.

Checks:
- TCP port connectivity
- TLS certificate expiry for HTTPS domains
- HTTP/HTTPS endpoint availability

Outputs:
- Markdown summary report
- JSON details
- CSV details
"""

from __future__ import annotations

import argparse
import csv
import json
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_TIMEOUT_SECONDS = 5
DEFAULT_CERT_WARN_DAYS = 30


@dataclass
class CheckResult:
    category: str
    name: str
    target: str
    status: str
    latency_ms: int | None = None
    detail: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def now_local_string() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")


def load_config(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise SystemExit(f"Config file not found: {path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON config: {path}, {exc}")


def elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def check_tcp_port(item: dict[str, Any], timeout: int) -> CheckResult:
    name = item.get("name", "unnamed-port")
    host = item["host"]
    port = int(item["port"])
    target = f"{host}:{port}"
    start = time.perf_counter()

    try:
        with socket.create_connection((host, port), timeout=timeout):
            return CheckResult(
                category="port",
                name=name,
                target=target,
                status="ok",
                latency_ms=elapsed_ms(start),
                detail="TCP connection succeeded",
            )
    except OSError as exc:
        return CheckResult(
            category="port",
            name=name,
            target=target,
            status="critical",
            latency_ms=elapsed_ms(start),
            detail=f"TCP connection failed: {exc}",
        )


def parse_cert_not_after(not_after: str) -> datetime:
    parsed = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
    return parsed.replace(tzinfo=timezone.utc)


def check_tls_cert(item: dict[str, Any], timeout: int, warn_days: int) -> CheckResult:
    name = item.get("name", "unnamed-cert")
    host = item["host"]
    port = int(item.get("port", 443))
    server_name = item.get("server_name", host)
    target = f"{server_name} ({host}:{port})"
    start = time.perf_counter()

    try:
        context = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=server_name) as tls_sock:
                cert = tls_sock.getpeercert()

        not_after = cert.get("notAfter")
        if not_after is None:
            return CheckResult(
                category="certificate",
                name=name,
                target=target,
                status="critical",
                latency_ms=elapsed_ms(start),
                detail="Certificate has no notAfter field",
            )

        expires_at = parse_cert_not_after(not_after)
        remaining_days = int((expires_at - datetime.now(timezone.utc)).total_seconds() // 86400)

        if remaining_days < 0:
            status = "critical"
            detail = f"Certificate expired {-remaining_days} day(s) ago"
        elif remaining_days <= warn_days:
            status = "warning"
            detail = f"Certificate expires in {remaining_days} day(s)"
        else:
            status = "ok"
            detail = f"Certificate valid for {remaining_days} day(s)"

        return CheckResult(
            category="certificate",
            name=name,
            target=target,
            status=status,
            latency_ms=elapsed_ms(start),
            detail=detail,
            extra={
                "expires_at_utc": expires_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "remaining_days": remaining_days,
                "issuer": cert.get("issuer", []),
                "subject": cert.get("subject", []),
            },
        )
    except Exception as exc:
        return CheckResult(
            category="certificate",
            name=name,
            target=target,
            status="critical",
            latency_ms=elapsed_ms(start),
            detail=f"Certificate check failed: {exc}",
        )


def check_http_endpoint(item: dict[str, Any], timeout: int) -> CheckResult:
    name = item.get("name", "unnamed-endpoint")
    url = item["url"]
    method = item.get("method", "GET").upper()
    expected_status = item.get("expected_status", [200, 204, 301, 302])
    if isinstance(expected_status, int):
        expected_status = [expected_status]
    target = f"{method} {url}"
    start = time.perf_counter()

    request = urllib.request.Request(
        url=url,
        method=method,
        headers={"User-Agent": "service-health-check/1.0"},
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status_code = response.getcode()
            response.read(256)

        if status_code in expected_status:
            status = "ok"
            detail = f"HTTP {status_code}"
        else:
            status = "warning"
            detail = f"Unexpected HTTP status: {status_code}, expected {expected_status}"

        return CheckResult(
            category="endpoint",
            name=name,
            target=target,
            status=status,
            latency_ms=elapsed_ms(start),
            detail=detail,
            extra={"status_code": status_code},
        )
    except urllib.error.HTTPError as exc:
        status = "ok" if exc.code in expected_status else "critical"
        return CheckResult(
            category="endpoint",
            name=name,
            target=target,
            status=status,
            latency_ms=elapsed_ms(start),
            detail=f"HTTP error status: {exc.code}",
            extra={"status_code": exc.code},
        )
    except Exception as exc:
        return CheckResult(
            category="endpoint",
            name=name,
            target=target,
            status="critical",
            latency_ms=elapsed_ms(start),
            detail=f"Endpoint check failed: {exc}",
        )


def result_to_dict(result: CheckResult) -> dict[str, Any]:
    return {
        "category": result.category,
        "name": result.name,
        "target": result.target,
        "status": result.status,
        "latency_ms": result.latency_ms,
        "detail": result.detail,
        "extra": result.extra,
    }


def status_counts(results: list[CheckResult]) -> dict[str, int]:
    counts = {"ok": 0, "warning": 0, "critical": 0}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    return counts


def write_json_report(path: Path, config_name: str, results: list[CheckResult]) -> None:
    payload = {
        "config_name": config_name,
        "generated_at": now_local_string(),
        "summary": status_counts(results),
        "results": [result_to_dict(result) for result in results],
    }
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def write_csv_report(path: Path, results: list[CheckResult]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["category", "name", "target", "status", "latency_ms", "detail"],
        )
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "category": result.category,
                    "name": result.name,
                    "target": result.target,
                    "status": result.status,
                    "latency_ms": result.latency_ms,
                    "detail": result.detail,
                }
            )


def write_markdown_report(path: Path, config_name: str, results: list[CheckResult]) -> None:
    counts = status_counts(results)
    lines = [
        "# Service Health Check Report",
        "",
        f"- Config: `{config_name}`",
        f"- Generated At: `{now_local_string()}`",
        f"- OK: `{counts.get('ok', 0)}`",
        f"- Warning: `{counts.get('warning', 0)}`",
        f"- Critical: `{counts.get('critical', 0)}`",
        "",
        "| Category | Name | Target | Status | Latency | Detail |",
        "| --- | --- | --- | --- | ---: | --- |",
    ]

    for result in results:
        latency = "" if result.latency_ms is None else f"{result.latency_ms} ms"
        lines.append(
            "| {category} | {name} | {target} | {status} | {latency} | {detail} |".format(
                category=escape_markdown_table(result.category),
                name=escape_markdown_table(result.name),
                target=escape_markdown_table(result.target),
                status=escape_markdown_table(result.status),
                latency=escape_markdown_table(latency),
                detail=escape_markdown_table(result.detail),
            )
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def escape_markdown_table(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def run_checks(config: dict[str, Any]) -> list[CheckResult]:
    timeout = int(config.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
    warn_days = int(config.get("certificate_warn_days", DEFAULT_CERT_WARN_DAYS))
    results: list[CheckResult] = []

    for item in config.get("ports", []):
        results.append(check_tcp_port(item, timeout))

    for item in config.get("certificates", []):
        results.append(check_tls_cert(item, timeout, warn_days))

    for item in config.get("endpoints", []):
        results.append(check_http_endpoint(item, timeout))

    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Batch service health check")
    parser.add_argument(
        "-c",
        "--config",
        default="config/health_check.example.json",
        help="Path to JSON config file",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default="outputs/health-check",
        help="Directory for generated reports",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config_path = Path(args.config)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    config = load_config(config_path)
    results = run_checks(config)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base_name = f"health-check-{timestamp}"
    write_markdown_report(output_dir / f"{base_name}.md", config_path.name, results)
    write_json_report(output_dir / f"{base_name}.json", config_path.name, results)
    write_csv_report(output_dir / f"{base_name}.csv", results)

    counts = status_counts(results)
    print(f"Generated reports in: {output_dir}")
    print(f"OK={counts.get('ok', 0)} WARNING={counts.get('warning', 0)} CRITICAL={counts.get('critical', 0)}")

    return 1 if counts.get("critical", 0) else 0


if __name__ == "__main__":
    sys.exit(main())
