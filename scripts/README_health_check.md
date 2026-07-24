# Service Health Check Script

This script batches common operations checks:

- TCP port connectivity
- HTTPS certificate expiry
- HTTP/HTTPS endpoint availability

## Usage

Copy `config/health_check.example.json` and replace the sample hosts with your own desensitized targets.

```bash
python scripts/service_health_check.py -c config/health_check.example.json
```

Reports are generated under:

```text
outputs/health-check/
```

The script writes Markdown, JSON, and CSV reports.

## Resume Description

```text
使用 Python 编写服务巡检脚本，批量检测业务服务端口连通性、HTTPS 证书有效期和接口可用性，并自动生成 Markdown/JSON/CSV 巡检报告，辅助发布后验证和日常巡检。
```

## Notes

Do not commit real IP addresses, accounts, passwords, tokens, keys, or internal domain names.
