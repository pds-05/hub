# AI Diagnosis Upgrade Guide

## Scope

This delivery upgrades the existing single-alert, read-only Dify diagnosis Agent through phases 2 and 3:

1. Phase 2 adds bounded alert correlation, Kubernetes warning-event context, service dependency topology, and an incident timeline.
2. Phase 3 adds reusable evaluation cases, auditable evaluation results, and human feedback.
3. Phase 4 change-risk analysis is explicitly out of scope. It will not read Git diffs, deployment manifests, or release history in this delivery.

## Phase 2: Multi-alert Correlation and Timeline

The Agent can call four additional read-only tools. Every call requires the short-lived `diagnosis_token` generated for the current diagnosis and the existing `X-Dify-Tool-Secret` header.

| Tool | Purpose | Evidence boundary |
| --- | --- | --- |
| `get_related_alerts` | Return recent platform alerts associated with the selected target or one direct configured dependency. | An endpoint match or configured dependency supports correlation only; it does not prove a root cause. |
| `get_kubernetes_events` | Return recent Kubernetes warning reports from clusters owned by the current user. | Target-to-cluster binding is not implemented. These results are cluster context, not target evidence. |
| `get_service_dependencies` | Return user-maintained topology edges for the selected target. | Dependency entries guide diagnosis order and do not establish causality. |
| `get_incident_timeline` | Return a time-ordered view of the selected alert, alert activities, target checks, related alerts, and Kubernetes context. | A temporal relationship is not proof of cause and effect. |

Calls remain limited to eight per diagnosis, are audited, and accept only bounded time windows and result limits. The API does not expose arbitrary PromQL, LogQL, SQL, shell commands, `kubectl` arguments, or resource identifiers to Dify.

### Configure Dependency Topology

Create topology edges from the platform UI's Dify diagnosis panel, or call the authenticated platform API:

```http
POST /api/v1/dependencies
Content-Type: application/json

{
  "source_target_id": 12,
  "destination_target_id": 18,
  "dependency_type": "runtime",
  "description": "Application uses RabbitMQ for asynchronous jobs"
}
```

`source_target_id` depends on `destination_target_id`. Both targets must belong to the signed-in user. Valid types are `runtime`, `data`, `network`, and `deployment`.

## Phase 3: Evaluation and Feedback

Evaluation is evidence-based and intentionally conservative. It measures whether a diagnosis made the expected successful tool calls, whether tool names cited in the report have successful audit rows, and whether configured evidence terms appear both in the final report and in successful tool audit results. It does not automatically decide whether the root-cause conclusion is true.

### APIs

| API | Purpose |
| --- | --- |
| `POST /api/v1/assistant/evaluation-cases` | Create a reusable diagnosis test case. |
| `GET /api/v1/assistant/evaluation-cases` | List the current user's test cases. |
| `POST /api/v1/assistant/evaluation-cases/{case_id}/evaluate` | Score an existing diagnosis against a test case. |
| `GET /api/v1/assistant/diagnoses/{diagnosis_id}/evaluations` | Read evaluation results for one diagnosis. |
| `PUT /api/v1/assistant/diagnoses/{diagnosis_id}/feedback` | Record a human verdict and optional note. |

Use an `expected_tool_names` list when creating a case. Valid values are the four existing tools plus `get_related_alerts`, `get_kubernetes_events`, `get_service_dependencies`, and `get_incident_timeline`. Add up to 20 concise `expected_evidence_terms` such as `connections=0`, `OOMKilled`, or `memory_alarm`; the evaluator checks them against the completed report and successful audit summaries.

### Score Interpretation

- `tool_call_score`: fraction of expected tools with a successful immutable audit record.
- `evidence_citation_score`: fraction of tool names cited in the final report that have a successful audit record.
- `unsupported_cited_tool_names`: cited known tool names with no successful audit record; investigate these before accepting the report.
- `evidence_term_score`: fraction of expected evidence terms that occur in both the report and successful audit result summaries. `unsupported_evidence_terms` identifies terms cited in the report but absent from successful audit evidence.
- Human verdicts: `accepted`, `partially_accepted`, `rejected`, and `insufficient_evidence`.

The feedback buttons in the diagnosis panel store the verdict for the completed diagnosis. Treat feedback as the authoritative signal for whether the root-cause assessment was useful.

## Dify Refresh and Verification

After deployment, refresh the existing Swagger/OpenAPI tool in Dify from:

`https://pdsaiops.com/api/v1/assistant/tools/openapi.json`

Keep the existing `X-Dify-Tool-Secret`. Do not set a static `diagnosis_token`; the backend generates a short-lived token per diagnosis.

Update the Agent note to call correlation tools only when they add evidence, label Kubernetes data as context, and distinguish correlation from causal proof. Publish the Agent, then run a new diagnosis and inspect the platform's tool-call audit and feedback result.
