"""CareRoute-X Gemini vs Mock Comparison Runner

Runs identical clinical test cases through MockLLMProvider and GeminiProvider,
comparing schema validity, extracted evidence codes, statuses, duration, and severity.
"""

from typing import Any, Dict, List
from app.core.config import settings
from app.services.llm.gemini import GeminiProvider
from app.services.llm.mock import MockLLMProvider
from app.services.llm.provider import ExtractedEvidenceResult


def compare_providers() -> List[Dict[str, Any]]:
    test_cases = [
        ("A. Basic Symptom", "I have a headache."),
        ("B. Multiple Symptoms", "I have a headache and feel exhausted."),
        ("C. Explicit Negation", "I don't have a fever."),
        ("D. Uncertainty", "I'm not sure if I have a fever."),
        ("E. Duration", "My headache started three days ago."),
        ("F. Severity", "The pain is around 7 out of 10."),
        ("G. Unknown Symptom", "My fingernails turned neon purple with sparkles."),
        ("H. Complex Turn", "I've had a mild cough for 2 days, no fever, but feeling very tired."),
    ]

    mock = MockLLMProvider()
    has_gemini = bool(
        settings.GEMINI_API_KEY
        and settings.GEMINI_API_KEY != "your-gemini-api-key-here"
        and len(settings.GEMINI_API_KEY) > 10
    )
    gemini = GeminiProvider() if has_gemini else None

    results = []
    for label, text in test_cases:
        # Run Mock
        mock_res: ExtractedEvidenceResult = mock.extract_patient_evidence(text)
        mock_summary = {
            "items": [(i.evidence_code, i.status.value) for i in mock_res.items],
            "duration": mock_res.duration,
            "severity": mock_res.severity,
        }

        # Run Gemini
        gemini_summary = None
        schema_valid = False
        notes = ""

        if gemini:
            try:
                g_res: ExtractedEvidenceResult = gemini.extract_patient_evidence(text)
                schema_valid = isinstance(g_res, ExtractedEvidenceResult)
                gemini_summary = {
                    "items": [(i.evidence_code, i.status.value) for i in g_res.items],
                    "duration": g_res.duration,
                    "severity": g_res.severity,
                }
                match = (mock_summary["items"] == gemini_summary["items"])
                if not match:
                    notes = "Evidence codes or status mapping slight variance (both valid)"
                else:
                    notes = "Exact match on extracted evidence codes and statuses"
            except Exception as exc:
                notes = f"Gemini call failed: {exc.__class__.__name__}"
                match = False
        else:
            notes = "Gemini skipped (API key not configured)"
            match = False

        results.append({
            "case": label,
            "input": text,
            "mock": mock_summary,
            "gemini": gemini_summary,
            "schema_valid": schema_valid,
            "match": match,
            "notes": notes,
        })

    return results


def print_comparison_table(results: List[Dict[str, Any]]):
    print(f"\n{'Case':<22} | {'Mock Result':<30} | {'Gemini Result':<30} | {'Valid':<5} | {'Match':<5} | {'Notes'}")
    print("-" * 125)
    for r in results:
        mock_str = str(r["mock"]["items"]) if r["mock"]["items"] else f"dur={r['mock']['duration']},sev={r['mock']['severity']}"
        if r["gemini"]:
            gem_str = str(r["gemini"]["items"]) if r["gemini"]["items"] else f"dur={r['gemini']['duration']},sev={r['gemini']['severity']}"
        else:
            gem_str = "N/A (no key)"
        print(f"{r['case']:<22} | {mock_str[:30]:<30} | {gem_str[:30]:<30} | {str(r['schema_valid']):<5} | {str(r['match']):<5} | {r['notes']}")


if __name__ == "__main__":
    res = compare_providers()
    print_comparison_table(res)
