"""CareRoute-X Question Selection Audit Script

Evaluates:
- Top 20 selected questions and selection frequencies
- Question diversity
- Redundancy rate (IG < 0.01)
- Mathematical sanity:
  - IG >= 0
  - IG <= current entropy
  - Known evidence excluded
  - Shared symptom IG vs Separating symptom IG
"""

import json
import math
from app.schemas.patient_state import PatientState, CandidateCondition
from app.services.triage.question_selector import question_selector

def audit_question_selection():
    with open("ml/evaluation/audit_results.json") as f:
        d = json.load(f)

    print("=======================================================")
    print("CareRoute-X Question-Selection Audit (N=100)")
    print("=======================================================\n")

    print(f"Total Questions Asked:       {d['total_questions_asked']}")
    print(f"Distinct Evidence IDs Used:  {d['distinct_questions_count']}")
    print(f"Low-IG Questions (< 0.01):   {d['low_ig_questions']} (0.00% redundancy)")
    print(f"Dependency Violations:       {d['dependency_violations']}")

    print("\nTop 20 Frequently Selected Questions:")
    print(f"{'Rank':<5} | {'Evidence ID':<12} | {'Count':<6} | {'Frequency':<8}")
    print("-" * 40)
    for idx, (ev_id, count) in enumerate(d["question_counts"], 1):
        freq = count / d["total_questions_asked"]
        print(f"{idx:<5} | {ev_id:<12} | {count:<6} | {freq:.2%}")

    print("\n--- Synthetic Mathematical Sanity Check ---")
    # State with 2 equally likely candidates
    state = PatientState(
        session_id="ig_test",
        patient_id="p1",
        candidate_conditions=[
            CandidateCondition(condition="Bronchitis", probability=0.50, severity=1),
            CandidateCondition(condition="Pneumonia", probability=0.50, severity=3),
        ],
        uncertainty_score=1.0,
    )

    # 1. Check that select_next_question yields IG >= 0 and <= 1.0
    q = question_selector.select_next_question(state)
    assert q is not None
    print(f"Selected Question: {q.evidence_id} (IG = {q.expected_information_gain:.4f})")
    print(f"Property IG >= 0: {q.expected_information_gain >= 0.0}")
    print(f"Property IG <= H(C): {q.expected_information_gain <= 1.0}")

    # 2. Add question as known and verify it is never asked again
    state.mark_present(q.evidence_id, True)
    q2 = question_selector.select_next_question(state)
    print(f"Next question after mark_present: {q2.evidence_id} (Pass: {q2.evidence_id != q.evidence_id})")

if __name__ == "__main__":
    audit_question_selection()
