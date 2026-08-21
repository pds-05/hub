import unittest
from types import SimpleNamespace

from app.services.diagnosis_evaluation import cited_tool_names, score_diagnosis_evaluation


class DiagnosisEvaluationScoreTest(unittest.TestCase):
    def test_scores_expected_successful_tools_and_real_citations(self) -> None:
        result = score_diagnosis_evaluation(
            expected_tool_names=["get_alert_context", "get_target_status", "get_target_metrics"],
            audit_rows=[
                SimpleNamespace(tool_name="get_alert_context", status="success"),
                SimpleNamespace(tool_name="get_target_status", status="success"),
                SimpleNamespace(tool_name="get_target_metrics", status="failed"),
            ],
            report="Evidence: get_alert_context and get_target_status. The failed get_target_metrics call is not evidence.",
        )

        self.assertEqual(result["successful_tool_names"], ["get_alert_context", "get_target_status"])
        self.assertEqual(result["unsupported_cited_tool_names"], ["get_target_metrics"])
        self.assertAlmostEqual(result["tool_call_score"], 2 / 3)
        self.assertAlmostEqual(result["evidence_citation_score"], 2 / 3)

    def test_evidence_terms_require_both_report_and_successful_audit_evidence(self) -> None:
        result = score_diagnosis_evaluation(
            expected_tool_names=["get_target_status"],
            expected_evidence_terms=["connections=0", "consumers=0", "authentication_failure"],
            audit_rows=[
                SimpleNamespace(
                    tool_name="get_target_status",
                    status="success",
                    result_summary="Exporter metrics: connections=0 and consumers=0",
                ),
            ],
            report="The diagnosis cites connections=0, consumers=0, and authentication_failure.",
        )

        self.assertEqual(result["matched_evidence_terms"], ["connections=0", "consumers=0"])
        self.assertEqual(result["unsupported_evidence_terms"], ["authentication_failure"])
        self.assertAlmostEqual(result["evidence_term_score"], 2 / 3)
    def test_no_expected_or_cited_tool_is_not_reported_as_perfect(self) -> None:
        result = score_diagnosis_evaluation(expected_tool_names=[], audit_rows=[], report="No tool citation")

        self.assertEqual(result["tool_call_score"], 0.0)
        self.assertEqual(result["evidence_citation_score"], 0.0)
        self.assertEqual(cited_tool_names("get_target_status, get_target_status"), ["get_target_status"])


if __name__ == "__main__":
    unittest.main()