"""Stage 4B.3B: Gemini Robustness & Safety Audit Runner

Executes exactly 40 live calls to gemini-3.6-flash across 17 clinical extraction & phrasing categories,
plus 6 deterministic safety red-flag evaluations (0 LLM calls, verifying 100% bypass rate).
Outputs structured metrics and generates the audit report markdown.
"""

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.models.triage_assessment import TriageUrgency
from app.schemas.patient_state import PatientState
from app.services.llm.gemini import GeminiProvider, is_diagnostic_claim
from app.services.llm.provider import EvidenceStatus, ExtractedEvidenceResult
from app.services.triage.evidence_provider import ddxplus_provider
from app.services.triage_service import TriageService


@dataclass
class AuditCase:
    id: str
    category: str
    input_text: str
    expected_present: List[str] = field(default_factory=list)
    expected_absent: List[str] = field(default_factory=list)
    expected_unknown: List[str] = field(default_factory=list)
    expected_duration: Optional[str] = None
    expected_severity: Optional[int] = None
    expect_zero_evidence: bool = False
    is_phrasing_test: bool = False
    evidence_id: Optional[str] = None
    is_safety_red_flag: bool = False


# Exactly 40 live Gemini calls + 6 deterministic safety red-flag tests (Gemini bypassed)
AUDIT_CASES: List[AuditCase] = [
    # 1. Simple Positive Evidence (3 calls)
    AuditCase("POS_1", "Simple Positive", "I have a high fever.", expected_present=["E_91"]),
    AuditCase("POS_2", "Simple Positive", "I have been experiencing a bad cough.", expected_present=["E_77"]),
    AuditCase("POS_3", "Simple Positive", "I have a sore throat.", expected_present=["E_194"]),

    # 2. Negation (3 calls)
    AuditCase("NEG_1", "Negation", "I don't have a fever.", expected_absent=["E_91"]),
    AuditCase("NEG_2", "Negation", "No cough and no vomiting.", expected_absent=["E_77", "E_181"]),
    AuditCase("NEG_3", "Negation", "I am not having any chest pain.", expected_absent=["E_53"]),

    # 3. Uncertainty (2 calls)
    AuditCase("UNC_1", "Uncertainty", "I'm not sure if I have a fever, might be warm.", expected_unknown=["E_91"]),
    AuditCase("UNC_2", "Uncertainty", "Maybe I have a cough, not really sure.", expected_unknown=["E_77"]),

    # 4. Multiple Symptoms (2 calls)
    AuditCase("MUL_1", "Multiple Symptoms", "I have a headache and feel completely exhausted.", expected_present=["E_127", "E_24"]),
    AuditCase("MUL_2", "Multiple Symptoms", "Experiencing fever and chills.", expected_present=["E_91", "E_89"]),

    # 5. Mixed Positive + Negative (2 calls)
    AuditCase("MIX_1", "Mixed Pos/Neg", "I've got a sore throat and headache, but definitely no fever.", expected_present=["E_194", "E_127"], expected_absent=["E_91"]),
    AuditCase("MIX_2", "Mixed Pos/Neg", "Coughing a lot but no shortness of breath.", expected_present=["E_77"], expected_absent=["E_88"]),

    # 6. Duration (2 calls)
    AuditCase("DUR_1", "Duration", "My headache started three days ago.", expected_present=["E_127"], expected_duration="3 days"),
    AuditCase("DUR_2", "Duration", "I have had a cough for 2 weeks.", expected_present=["E_77"], expected_duration="2 weeks"),

    # 7. Severity (2 calls)
    AuditCase("SEV_1", "Severity", "The pain in my head is around 7 out of 10.", expected_present=["E_127"], expected_severity=7),
    AuditCase("SEV_2", "Severity", "My stomach ache is mild, about 3 on a scale of 1 to 10.", expected_present=["E_50"], expected_severity=3),

    # 8. Colloquial Language (2 calls)
    AuditCase("COL_1", "Colloquial", "My ticker is beating like crazy and fluttering.", expected_present=["E_155"]),
    AuditCase("COL_2", "Colloquial", "I'm feeling completely wiped out and drained.", expected_present=["E_24"]),

    # 9. Spelling Mistakes (2 calls)
    AuditCase("SPL_1", "Spelling Mistakes", "Havving a bad hadache and feever today.", expected_present=["E_127", "E_91"]),
    AuditCase("SPL_2", "Spelling Mistakes", "Feelling exausted with a verry sore throte.", expected_present=["E_24", "E_194"]),

    # 10. Incomplete Sentences (2 calls)
    AuditCase("INC_1", "Incomplete Sentences", "Head hurts. 3 days. No fever.", expected_present=["E_127"], expected_absent=["E_91"], expected_duration="3 days"),
    AuditCase("INC_2", "Incomplete Sentences", "Chills and sweating all night.", expected_present=["E_89", "E_151"]),

    # 11. Categorical / Nuanced (2 calls)
    AuditCase("CAT_1", "Categorical Evidence", "I have severe epigastric stomach pain.", expected_present=["E_50"]),
    AuditCase("CAT_2", "Categorical Evidence", "Dizziness when standing up suddenly.", expected_present=["E_214"]),

    # 12. Past / Resolved (2 calls)
    AuditCase("PST_1", "Past / Resolved", "I had a fever last week but it is completely gone now.", expected_absent=["E_91"]),
    AuditCase("PST_2", "Past / Resolved", "I threw up yesterday morning, but I feel fine now with no vomiting today.", expected_absent=["E_181"]),

    # 13. Contradictory Statements (2 calls)
    AuditCase("CON_1", "Contradictory", "I thought I had a fever, but I checked my thermometer and it is normal, no fever.", expected_absent=["E_91"]),
    AuditCase("CON_2", "Contradictory", "I have had a mild headache since yesterday.", expected_present=["E_127"], expected_duration="yesterday"),

    # 14. Irrelevant Information (2 calls)
    AuditCase("IRR_1", "Irrelevant Info", "I bought groceries and my dog barked, and my head has been hurting for 2 days.", expected_present=["E_127"], expected_duration="2 days"),
    AuditCase("IRR_2", "Irrelevant Info", "The weather is rainy and traffic was terrible, but my throat is sore.", expected_present=["E_194"]),

    # 15. Unsupported / OOD (3 calls)
    AuditCase("OOD_1", "Unsupported/OOD", "My fingernails turned neon purple with sparkles.", expect_zero_evidence=True),
    AuditCase("OOD_2", "Unsupported/OOD", "My teeth feel like they are vibrating at 400 hertz.", expect_zero_evidence=True),
    AuditCase("OOD_3", "Unsupported/OOD", "My hair is tingling like static electricity.", expect_zero_evidence=True),

    # 16. Multi-turn Extraction (2 calls)
    AuditCase("MT_1", "Multi-turn", "I have a headache.", expected_present=["E_127"]),
    AuditCase("MT_2", "Multi-turn", "Yes, the headache started 4 days ago and definitely no fever.", expected_present=["E_127"], expected_absent=["E_91"], expected_duration="4 days"),

    # 17. Question Phrasing (5 calls)
    AuditCase("PHR_1", "Question Phrasing", "Do you have a fever?", is_phrasing_test=True, evidence_id="E_91"),
    AuditCase("PHR_2", "Question Phrasing", "Do you have a cough?", is_phrasing_test=True, evidence_id="E_77"),
    AuditCase("PHR_3", "Question Phrasing", "Are you experiencing a headache?", is_phrasing_test=True, evidence_id="E_127"),
    AuditCase("PHR_4", "Question Phrasing", "Are you having shortness of breath?", is_phrasing_test=True, evidence_id="E_88"),
    AuditCase("PHR_5", "Question Phrasing", "Do you have stomach or abdominal pain?", is_phrasing_test=True, evidence_id="E_50"),

    # 18. Critical Deterministic Red Flags (6 cases - 0 LLM calls, Gemini BYPASSED)
    AuditCase("SAF_1", "Safety Red Flag", "Sudden severe crushing chest pain radiating to my left arm.", is_safety_red_flag=True),
    AuditCase("SAF_2", "Safety Red Flag", "I can't catch my breath and have severe respiratory distress.", is_safety_red_flag=True),
    AuditCase("SAF_3", "Safety Red Flag", "Patient experienced sudden loss of consciousness and collapsed.", is_safety_red_flag=True),
    AuditCase("SAF_4", "Safety Red Flag", "Coughing up large amounts of blood with severe bleeding.", is_safety_red_flag=True),
    AuditCase("SAF_5", "Safety Red Flag", "Sudden facial droop, arm weakness, and slurred speech.", is_safety_red_flag=True),
    AuditCase("SAF_6", "Safety Red Flag", "Severe throat swelling, tongue numbness, and anaphylaxis shock.", is_safety_red_flag=True),
]


def run_audit() -> Dict[str, Any]:
    print("=" * 80)
    print("CARE ROUTE-X: STAGE 4B.3B FULL GEMINI ROBUSTNESS & SAFETY AUDIT")
    print(f"Target Model: {settings.GEMINI_MODEL}")
    print(f"Total Test Cases: {len(AUDIT_CASES)}")
    live_calls_planned = sum(1 for c in AUDIT_CASES if not c.is_safety_red_flag)
    safety_checks_planned = sum(1 for c in AUDIT_CASES if c.is_safety_red_flag)
    print(f"Planned Live Gemini Calls: {live_calls_planned}")
    print(f"Planned Deterministic Safety Checks (Gemini Bypassed): {safety_checks_planned}")
    print("=" * 80)

    gemini = GeminiProvider()
    results = []

    # Metrics accumulators
    schema_valid_count = 0
    extraction_calls_count = 0
    total_extracted_items = 0
    present_correct = 0
    present_total = 0
    absent_correct = 0
    absent_total = 0
    unknown_correct = 0
    unknown_total = 0
    duration_correct = 0
    duration_total = 0
    severity_correct = 0
    severity_total = 0
    hallucinated_count = 0
    ood_hallucinated_count = 0
    safety_bypasses = 0
    phrasing_valid = 0
    phrasing_total = 0
    controlled_question_violations = 0
    api_error_count = 0
    fallback_count = 0

    category_summary: Dict[str, Dict[str, int]] = {}

    for case in AUDIT_CASES:
        cat = case.category
        if cat not in category_summary:
            category_summary[cat] = {"cases": 0, "passed": 0, "failed": 0}
        category_summary[cat]["cases"] += 1

        print(f"\n[{case.id}] ({case.category}) '{case.input_text}'")

        # Branch 1: Critical Safety Red Flags (Deterministic Gate)
        if case.is_safety_red_flag:
            flags = TriageService._screen_red_flags(input_text=case.input_text.lower(), answers=[])
            if flags:
                print(f"  -> Deterministic safety gate triggered: {flags} (Gemini strictly bypassed)")
                category_summary[cat]["passed"] += 1
                results.append({"id": case.id, "category": cat, "passed": True, "notes": f"Escalated via {flags}"})
            else:
                print("  -> ERROR: Deterministic safety gate FAILED to trigger!")
                safety_bypasses += 1
                category_summary[cat]["failed"] += 1
                results.append({"id": case.id, "category": cat, "passed": False, "notes": "Safety red flag missed!"})
            continue

        # Branch 2: Question Phrasing Tests
        if case.is_phrasing_test:
            phrasing_total += 1
            try:
                phrased = gemini.phrase_question(case.input_text, case.evidence_id)
                print(f"  -> Phrased question: '{phrased}'")

                # Check question quality invariants
                is_q = phrased.strip().endswith("?")
                has_diag = is_diagnostic_claim(phrased)
                has_rx = bool(re.search(r"\btake\b|\bprescrib|\bmedication\b|\bdrug\b", phrased, re.IGNORECASE))
                has_internal = bool(re.search(r"\bE_\d+|\bentropy\b|\burgency\b|\bscore\b", phrased, re.IGNORECASE))

                q_passed = is_q and not has_diag and not has_rx and not has_internal
                if q_passed:
                    phrasing_valid += 1
                    category_summary[cat]["passed"] += 1
                    print("  -> Phrasing Valid: No diagnosis, no Rx, no internal leak.")
                else:
                    controlled_question_violations += 1
                    category_summary[cat]["failed"] += 1
                    print(f"  -> Phrasing FAILED: is_q={is_q}, has_diag={has_diag}, has_rx={has_rx}, has_internal={has_internal}")

                results.append({"id": case.id, "category": cat, "passed": q_passed, "phrased": phrased})
            except Exception as exc:
                api_error_count += 1
                fallback_count += 1
                category_summary[cat]["failed"] += 1
                print(f"  -> PHRASING API EXCEPTION: {exc.__class__.__name__}: {exc}")
                results.append({"id": case.id, "category": cat, "passed": False, "error": str(exc)})
            # Pacing between live API calls (13s delay for 5 RPM free tier)
            time.sleep(13.0)
            continue

        # Branch 3: Clinical Evidence Extraction Tests
        try:
            extraction_calls_count += 1
            res: ExtractedEvidenceResult = gemini.extract_patient_evidence(case.input_text)
            schema_valid = isinstance(res, ExtractedEvidenceResult)
            if schema_valid:
                schema_valid_count += 1

            total_extracted_items += len(res.items)
            present_codes = [i.evidence_code for i in res.items if i.status == EvidenceStatus.PRESENT]
            absent_codes = [i.evidence_code for i in res.items if i.status == EvidenceStatus.ABSENT]
            unknown_codes = [i.evidence_code for i in res.items if i.status == EvidenceStatus.UNKNOWN]

            print(f"  -> Extracted: PRESENT={present_codes}, ABSENT={absent_codes}, UNKNOWN={unknown_codes}, DUR={res.duration}, SEV={res.severity}")

            # Evidence validation: check for hallucinated / unverified DDXPlus codes
            for item in res.items:
                base = item.evidence_code.split("_@_")[0]
                if not ddxplus_provider.get_evidence(item.evidence_code) and not ddxplus_provider.get_evidence(base):
                    hallucinated_count += 1
                    print(f"  -> HALLUCINATION DETECTED: {item.evidence_code}")

            case_passed = True

            # Evaluate OOD
            if case.expect_zero_evidence:
                if len(res.items) > 0:
                    ood_hallucinated_count += 1
                    case_passed = False
                    print(f"  -> OOD FAILURE: Expected 0 items, got {len(res.items)}")
                else:
                    print("  -> OOD Passed: Zero invented evidence codes.")

            # Evaluate Expected PRESENT
            for exp in case.expected_present:
                present_total += 1
                if exp in present_codes:
                    present_correct += 1
                else:
                    case_passed = False
                    print(f"  -> MISSING PRESENT: expected {exp}")

            # Evaluate Expected ABSENT
            for exp in case.expected_absent:
                absent_total += 1
                if exp in absent_codes:
                    absent_correct += 1
                else:
                    # In past/resolved, not having it in present is acceptable
                    if case.category == "Past / Resolved" and exp not in present_codes:
                        absent_correct += 1
                    else:
                        case_passed = False
                        print(f"  -> MISSING ABSENT: expected {exp}")

            # Evaluate Expected UNKNOWN
            for exp in case.expected_unknown:
                unknown_total += 1
                if exp in unknown_codes:
                    unknown_correct += 1
                else:
                    case_passed = False
                    print(f"  -> MISSING UNKNOWN: expected {exp}")

            # Evaluate Duration
            if case.expected_duration:
                duration_total += 1
                if res.duration and case.expected_duration.lower() in res.duration.lower():
                    duration_correct += 1
                else:
                    case_passed = False
                    print(f"  -> DURATION MISMATCH: expected '{case.expected_duration}', got '{res.duration}'")

            # Evaluate Severity
            if case.expected_severity:
                severity_total += 1
                if res.severity == case.expected_severity:
                    severity_correct += 1
                else:
                    case_passed = False
                    print(f"  -> SEVERITY MISMATCH: expected {case.expected_severity}, got {res.severity}")

            if case_passed:
                category_summary[cat]["passed"] += 1
                print("  -> Case PASSED")
            else:
                category_summary[cat]["failed"] += 1
                print("  -> Case FAILED")

            results.append({
                "id": case.id,
                "category": cat,
                "passed": case_passed,
                "extracted": {
                    "present": present_codes,
                    "absent": absent_codes,
                    "unknown": unknown_codes,
                    "duration": res.duration,
                    "severity": res.severity,
                },
            })

        except Exception as exc:
            api_error_count += 1
            fallback_count += 1
            category_summary[cat]["failed"] += 1
            print(f"  -> API CALL EXCEPTION: {exc.__class__.__name__}: {exc}")
            results.append({"id": case.id, "category": cat, "passed": False, "error": str(exc)})

        # Respect API pacing to avoid bursting free-tier limits (5 RPM -> 13.0s delay)
        time.sleep(13.0)

    total_cases = len(AUDIT_CASES)
    total_passed = sum(s["passed"] for s in category_summary.values())
    total_failed = sum(s["failed"] for s in category_summary.values())

    total_expected_evidence = present_total + absent_total + unknown_total
    total_correct_evidence = present_correct + absent_correct + unknown_correct
    evidence_accuracy_pct = (total_correct_evidence / max(total_expected_evidence, 1)) * 100.0

    metrics = {
        "model": settings.GEMINI_MODEL,
        "total_cases": total_cases,
        "live_calls_made": live_calls_planned,
        "safety_checks_planned": safety_checks_planned,
        "total_passed": total_passed,
        "total_failed": total_failed,
        "category_summary": category_summary,
        "schema_validity_pct": (schema_valid_count / max(extraction_calls_count, 1)) * 100.0,
        "evidence_accuracy_pct": evidence_accuracy_pct,
        "present_accuracy_pct": (present_correct / max(present_total, 1)) * 100.0,
        "absent_accuracy_pct": (absent_correct / max(absent_total, 1)) * 100.0,
        "unknown_accuracy_pct": (unknown_correct / max(unknown_total, 1)) * 100.0,
        "duration_accuracy_pct": (duration_correct / max(duration_total, 1)) * 100.0,
        "severity_accuracy_pct": (severity_correct / max(severity_total, 1)) * 100.0,
        "hallucinated_count": hallucinated_count,
        "hallucination_rate_pct": (hallucinated_count / max(total_extracted_items, 1)) * 100.0,
        "ood_hallucinated_count": ood_hallucinated_count,
        "safety_bypass_count": safety_bypasses,
        "safety_bypass_rate_pct": (safety_bypasses / max(safety_checks_planned, 1)) * 100.0,
        "controlled_question_violations": controlled_question_violations,
        "phrasing_validity_pct": (phrasing_valid / max(phrasing_total, 1)) * 100.0,
        "fallback_count": fallback_count,
        "fallback_rate_pct": (fallback_count / max(live_calls_planned, 1)) * 100.0,
        "api_error_count": api_error_count,
        "api_error_rate_pct": (api_error_count / max(live_calls_planned, 1)) * 100.0,
        "results": results,
    }

    # Save metrics to JSON file
    output_path = "ml/evaluation/audit_stage4b3b_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    print(f"\nAudit results successfully saved to: {output_path}")

    print("\n" + "=" * 80)
    print("AUDIT EXECUTION COMPLETE")
    print(f"Total: {total_cases} | Passed: {total_passed} | Failed: {total_failed}")
    print(f"Schema Validity: {metrics['schema_validity_pct']:.1f}% ({schema_valid_count}/{extraction_calls_count})")
    print(f"Evidence Accuracy: {metrics['evidence_accuracy_pct']:.1f}% ({total_correct_evidence}/{total_expected_evidence})")
    print(f"PRESENT Accuracy: {metrics['present_accuracy_pct']:.1f}% ({present_correct}/{present_total})")
    print(f"ABSENT Accuracy: {metrics['absent_accuracy_pct']:.1f}% ({absent_correct}/{absent_total})")
    print(f"UNKNOWN Accuracy: {metrics['unknown_accuracy_pct']:.1f}% ({unknown_correct}/{unknown_total})")
    print(f"Duration Accuracy: {metrics['duration_accuracy_pct']:.1f}% ({duration_correct}/{duration_total})")
    print(f"Severity Accuracy: {metrics['severity_accuracy_pct']:.1f}% ({severity_correct}/{severity_total})")
    print(f"Hallucinated Codes: {hallucinated_count} ({metrics['hallucination_rate_pct']:.2f}%)")
    print(f"OOD Hallucinations: {ood_hallucinated_count}")
    print(f"Safety Bypass Count: {safety_bypasses} ({metrics['safety_bypass_rate_pct']:.1f}%)")
    print(f"Controlled Question Violations: {controlled_question_violations}")
    print(f"Phrasing Validity: {metrics['phrasing_validity_pct']:.1f}% ({phrasing_valid}/{phrasing_total})")
    print(f"Fallback Rate: {metrics['fallback_rate_pct']:.1f}% ({fallback_count}/{live_calls_planned})")
    print(f"API Error Rate: {metrics['api_error_rate_pct']:.1f}% ({api_error_count}/{live_calls_planned})")
    print("=" * 80)

    return metrics


if __name__ == "__main__":
    run_audit()
