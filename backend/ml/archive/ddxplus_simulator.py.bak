import argparse
import ast
import csv
import io
import json
import logging
import sys
import zipfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.schemas.patient_state import PatientState
from app.services.triage.evidence_provider import ddxplus_provider
from app.services.triage.question_selector import InformationGainQuestionSelector
from app.services.triage.stopping_policy import TriageStoppingPolicy

logger = logging.getLogger("ddxplus_simulator")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


@dataclass
class SimulationMetrics:
    total_patients: int = 0
    top_1_correct: int = 0
    top_3_correct: int = 0
    top_5_correct: int = 0
    total_questions_asked: int = 0
    total_entropy_reduction: float = 0.0
    stop_reasons: Dict[str, int] = field(default_factory=dict)
    high_severity_cases: int = 0
    high_severity_escalated: int = 0
    dependency_violations: int = 0
    total_target_ranks: int = 0
    ranked_patients_count: int = 0

    @property
    def top_1_recall(self) -> float:
        return self.top_1_correct / max(1, self.total_patients)

    @property
    def top_3_recall(self) -> float:
        return self.top_3_correct / max(1, self.total_patients)

    @property
    def top_5_recall(self) -> float:
        return self.top_5_correct / max(1, self.total_patients)

    @property
    def avg_turns(self) -> float:
        return self.total_questions_asked / max(1, self.total_patients)

    @property
    def avg_entropy_reduction(self) -> float:
        return self.total_entropy_reduction / max(1, self.total_patients)

    @property
    def avg_target_rank(self) -> float:
        return self.total_target_ranks / max(1, self.ranked_patients_count)


def parse_patient_row(row: Dict[str, str]) -> Dict[str, Any]:
    """Parses raw CSV row from DDXPlus release_validate_patients."""
    pathology = row.get("PATHOLOGY", "").strip()
    initial_evidence = row.get("INITIAL_EVIDENCE", "").strip()
    evidences_raw = row.get("EVIDENCES", "[]")

    try:
        evidences = ast.literal_eval(evidences_raw)
    except Exception:
        evidences = []

    return {
        "pathology": pathology,
        "initial_evidence": initial_evidence,
        "all_evidences": set(evidences),
        "age": row.get("AGE", "30"),
        "sex": row.get("SEX", "M"),
    }


def run_ddxplus_simulation(
    n_patients: int = 100,
    zip_path: Optional[str] = None,
    max_turns: int = 7,
    min_entropy: float = 0.65,
) -> SimulationMetrics:
    """Simulates active conversational triage against ground-truth DDXPlus synthetic patients."""
    zip_file_path = zip_path or settings.DDXPLUS_DATA_PATH

    selector = InformationGainQuestionSelector(evidence_provider=ddxplus_provider)
    policy = TriageStoppingPolicy(max_turns=max_turns, min_entropy=min_entropy)
    metrics = SimulationMetrics()

    logger.info(f"Opening DDXPlus package from: {zip_file_path}")
    with zipfile.ZipFile(zip_file_path, "r") as z_outer:
        if "release_validate_patients.zip" not in z_outer.namelist():
            raise FileNotFoundError("release_validate_patients.zip not found in DDXPlus archive")

        inner_bytes = z_outer.read("release_validate_patients.zip")
        with zipfile.ZipFile(io.BytesIO(inner_bytes), "r") as z_inner:
            val_filename = z_inner.namelist()[0]
            with z_inner.open(val_filename, "r") as f:
                reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))

                for idx, row in enumerate(reader):
                    if idx >= n_patients:
                        break

                    patient = parse_patient_row(row)
                    target_pathology = patient["pathology"]
                    patient_evidences = patient["all_evidences"]

                    # Initialize patient state
                    state = PatientState(
                        session_id=f"sim_{idx}",
                        patient_id=f"sim_pat_{idx}",
                        chief_complaint=f"Initial complaint: {patient['initial_evidence']}",
                    )

                    # Seed initial evidence
                    init_ev = patient["initial_evidence"]
                    if init_ev:
                        matching_init = [
                            e for e in patient_evidences if e == init_ev or e.startswith(f"{init_ev}_@_")
                        ]
                        if matching_init:
                            for m_init in matching_init:
                                val = m_init.split("_@_")[1] if "_@_" in m_init else True
                                state.mark_present(m_init, val)
                        else:
                            state.mark_present(init_ev, True)

                    # Initial entropy & differential
                    initial_candidates, initial_entropy = selector.compute_candidate_distribution(
                        state.known_present_evidence, state.known_absent_evidence
                    )
                    state.candidate_conditions = initial_candidates
                    state.uncertainty_score = initial_entropy

                    target_severity = ddxplus_provider.get_condition_severity(target_pathology)
                    if target_severity >= 3:
                        metrics.high_severity_cases += 1

                    # Adaptive question loop
                    turn = 0
                    stop_reason = "MAX_CONVERSATION_TURNS_REACHED"
                    needs_escalation = False

                    while turn < max_turns:
                        turn += 1
                        state.conversation_turn = turn

                        # 1. Select adaptive next question
                        next_question = selector.select_next_question(state)

                        # 2. Check stopping criteria
                        should_stop, reason, needs_esc = policy.should_stop(state, next_question)
                        if should_stop or next_question is None:
                            stop_reason = reason
                            needs_escalation = needs_esc
                            break

                        q_ev_id = next_question.evidence_id

                        # Check dependency compliance
                        parent = ddxplus_provider.get_parent_evidence(q_ev_id)
                        if parent and parent in state.known_absent_evidence:
                            metrics.dependency_violations += 1

                        # 3. Simulate patient answer with categorical value preservation
                        matching_evs = [
                            e for e in patient_evidences if e == q_ev_id or e.startswith(f"{q_ev_id}_@_")
                        ]

                        if matching_evs:
                            for m_ev in matching_evs:
                                val = m_ev.split("_@_")[1] if "_@_" in m_ev else True
                                state.mark_present(m_ev, val)
                        else:
                            state.mark_absent(q_ev_id)

                        state.record_question_asked(q_ev_id)

                        # 4. Recompute differential & uncertainty
                        new_cands, new_entropy = selector.compute_candidate_distribution(
                            state.known_present_evidence, state.known_absent_evidence
                        )
                        state.candidate_conditions = new_cands
                        state.uncertainty_score = new_entropy

                    # Record metrics
                    metrics.total_patients += 1
                    metrics.total_questions_asked += len(state.questions_asked)
                    metrics.total_entropy_reduction += max(0.0, initial_entropy - state.uncertainty_score)
                    metrics.stop_reasons[stop_reason] = metrics.stop_reasons.get(stop_reason, 0) + 1

                    if target_severity >= 3 and (needs_escalation or state.uncertainty_score > min_entropy):
                        metrics.high_severity_escalated += 1

                    # Check diagnostic recall
                    top_candidates = [c.condition for c in state.candidate_conditions]
                    if top_candidates:
                        top_1 = top_candidates[0].lower()
                        top_3 = [c.lower() for c in top_candidates[:3]]
                        top_5 = [c.lower() for c in top_candidates[:5]]
                        t_lower = target_pathology.lower()

                        if t_lower in top_1 or top_1 in t_lower:
                            metrics.top_1_correct += 1
                        if any(t_lower in c or c in t_lower for c in top_3):
                            metrics.top_3_correct += 1
                        if any(t_lower in c or c in t_lower for c in top_5):
                            metrics.top_5_correct += 1

                        # Target rank
                        for r_idx, c in enumerate(top_candidates, 1):
                            if t_lower in c.lower() or c.lower() in t_lower:
                                metrics.total_target_ranks += r_idx
                                metrics.ranked_patients_count += 1
                                break

    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CareRoute-X DDXPlus Adaptive Triage Simulator")
    parser.add_argument("--n", type=int, default=100, help="Number of synthetic patients to simulate")
    parser.add_argument("--max_turns", type=int, default=7, help="Maximum conversation turns")
    args = parser.parse_args()

    print(f"\n=======================================================")
    print(f"CareRoute-X Adaptive Conversational Triage Evaluation")
    print(f"Dataset: DDXPlus release_validate_patients (N={args.n})")
    print(f"=======================================================\n")

    m = run_ddxplus_simulation(n_patients=args.n, max_turns=args.max_turns)

    print(f"Total Patients Simulated:       {m.total_patients}")
    print(f"Top-1 Diagnostic Recall:        {m.top_1_recall:.2%}")
    print(f"Top-3 Diagnostic Recall:        {m.top_3_recall:.2%}")
    print(f"Top-5 Diagnostic Recall:        {m.top_5_recall:.2%}")
    print(f"Average Target Condition Rank:  {m.avg_target_rank:.2f}")
    print(f"Average Questions Asked:        {m.avg_turns:.2f} turns")
    print(f"Average Entropy Reduction:      {m.avg_entropy_reduction:.4f}")
    print(f"Dependency Violations:          {m.dependency_violations}")
    if m.high_severity_cases > 0:
        esc_rate = m.high_severity_escalated / m.high_severity_cases
        print(f"High-Severity Escalation Rate:  {esc_rate:.2%} ({m.high_severity_escalated}/{m.high_severity_cases})")
    print(f"\nStopping Reason Breakdown:")
    for reason, count in m.stop_reasons.items():
        print(f"  - {reason}: {count} ({count/m.total_patients:.1%})")
    print("\n=======================================================\n")
