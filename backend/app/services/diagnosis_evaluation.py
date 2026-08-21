from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any


KNOWN_TOOL_NAMES = (
    "get_alert_context",
    "get_target_status",
    "get_target_metrics",
    "search_target_logs",
    "get_related_alerts",
    "get_kubernetes_events",
    "get_service_dependencies",
    "get_incident_timeline",
)
_TOOL_NAME_SET = frozenset(KNOWN_TOOL_NAMES)
_TOOL_PATTERN = re.compile(r"\b(" + "|".join(KNOWN_TOOL_NAMES) + r")\b")


def ordered_tool_names(values: Iterable[str]) -> list[str]:
    values_set = {str(value) for value in values if str(value) in _TOOL_NAME_SET}
    return [name for name in KNOWN_TOOL_NAMES if name in values_set]


def cited_tool_names(report: str | None) -> list[str]:
    if not report:
        return []
    return ordered_tool_names(_TOOL_PATTERN.findall(report))


def score_diagnosis_evaluation(
    *,
    expected_tool_names: Iterable[str],
    audit_rows: Iterable[Any],
    report: str | None,
    expected_evidence_terms: Iterable[str] = (),
) -> dict[str, Any]:
    """Score auditable tool usage, not the semantic truth of an AI conclusion."""
    rows = list(audit_rows)
    expected = ordered_tool_names(expected_tool_names)
    successful_rows = [row for row in rows if getattr(row, "status", None) == "success"]
    successful = ordered_tool_names(row.tool_name for row in successful_rows)
    cited = cited_tool_names(report)
    successful_set = set(successful)
    cited_set = set(cited)
    expected_set = set(expected)
    evidence_terms = _ordered_evidence_terms(expected_evidence_terms)
    report_text = (report or "").lower()
    successful_evidence = "\n".join(str(getattr(row, "result_summary", "") or "") for row in successful_rows).lower()
    matched_terms = [term for term in evidence_terms if term.lower() in report_text and term.lower() in successful_evidence]
    unsupported_terms = [term for term in evidence_terms if term.lower() in report_text and term not in matched_terms]
    return {
        "expected_tool_names": expected,
        "expected_evidence_terms": evidence_terms,
        "successful_tool_names": successful,
        "cited_tool_names": cited,
        "unsupported_cited_tool_names": ordered_tool_names(cited_set - successful_set),
        "matched_evidence_terms": matched_terms,
        "unsupported_evidence_terms": unsupported_terms,
        "tool_call_score": len(expected_set & successful_set) / len(expected_set) if expected_set else 0.0,
        "evidence_citation_score": len(cited_set & successful_set) / len(cited_set) if cited_set else 0.0,
        "evidence_term_score": len(matched_terms) / len(evidence_terms) if evidence_terms else 0.0,
    }


def _ordered_evidence_terms(values: Iterable[str]) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for value in values:
        term = str(value).strip()[:200]
        key = term.lower()
        if term and key not in seen:
            terms.append(term)
            seen.add(key)
    return terms