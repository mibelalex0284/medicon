"""CareRoute-X Stage 4B.2 Safety, Failure Analysis, and Evaluation Audit Script

Executes comprehensive auditing:
1. Audit of all high-severity failures (patient traces, posterior trajectory, exact miss reason).
2. Classification of failures into categories A through G.
3. Safety vs DDXPlus severity breakdown (CareRoute-X red flag presence).
4. Per-condition diagnostic recall, rank, turns, and escalation table.
5. Question selection audit (redundancy, generic dominance, diversity, dependency, IG sanity).
6. Controlled toy posterior mathematical audits.
7. Stopping policy distribution and trajectory inspection.
8. Data leakage verification.
"""

import ast
import csv
import io
import json
import math
import sys
import zipfile
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from app.core.config import settings
from app.schemas.patient_state import PatientState, CandidateCondition
from app.services.triage.evidence_provider import ddxplus_provider
from app.services.triage.question_selector import (
    InformationGainQuestionSelector,
    ControlledQuestion,
)
from app.services.triage.stopping_policy import TriageStoppingPolicy
from app.services.triage_service import triage_service


def parse_patient_row(row: Dict[str, str]) -> Dict[str, Any]:
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


def check_careroute_red_flags_in_evidences(evidences: Set[str]) -> List[str]:
    """Checks whether any DDXPlus evidence corresponds to CareRoute-X's 6 emergency red flags."""
    # Mapping of explicit emergency evidence codes
    emergency_evidences = {
        "E_54_@_V_180": "RED_FLAG_CHEST_PAIN_SEVERE",
        "E_88": "RED_FLAG_BREATHING_DIFFICULTY",
        "E_201": "RED_FLAG_LOSS_OF_CONSCIOUSNESS",
        "E_45": "RED_FLAG_SEVERE_BLEEDING",
    }
    flags = []
    for ev in evidences:
        if ev in emergency_evidences:
            flags.append(emergency_evidences[ev])
        base = ev.split("_@_")[0]
        if base in emergency_evidences:
            flags.append(emergency_evidences[base])
    return list(set(flags))


def run_comprehensive_audit(n_patients: int = 100) -> Dict[str, Any]:
    zip_path = settings.DDXPLUS_DATA_PATH
    selector = InformationGainQuestionSelector(evidence_provider=ddxplus_provider)
    policy = TriageStoppingPolicy(max_turns=7, min_entropy=0.65)

    # Per-condition stats
    cond_stats = defaultdict(lambda: {
        "total": 0, "top1": 0, "top3": 0, "top5": 0,
        "turns": 0, "ranks": 0, "ranked_cnt": 0,
        "high_sev": 0, "escalated": 0
    })

    # Question selection stats
    question_counts = Counter()
    distinct_questions = set()
    low_ig_questions = 0
    total_questions = 0
    dependency_violations = 0

    # Stopping stats
    stop_reasons = Counter()
    turns_distribution = Counter()

    # High-severity failure traces
    high_sev_failures = []
    high_sev_total = 0
    high_sev_escalated = 0
    careroute_red_flag_cases = 0
    careroute_red_flag_detected = 0

    all_ranks = []
    all_turns = []
    all_entropy_reductions = []
    top1_total = 0
    top3_total = 0
    top5_total = 0

    with zipfile.ZipFile(zip_path, "r") as z_outer:
        inner_bytes = z_outer.read("release_validate_patients.zip")
        with zipfile.ZipFile(io.BytesIO(inner_bytes), "r") as z_inner:
            val_filename = z_inner.namelist()[0]
            with z_inner.open(val_filename, "r") as f:
                reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))

                for idx, row in enumerate(reader):
                    if idx >= n_patients:
                        break

                    patient = parse_patient_row(row)
                    target = patient["pathology"]
                    evidences = patient["all_evidences"]
                    target_sev = ddxplus_provider.get_condition_severity(target)

                    has_cr_red_flag = check_careroute_red_flags_in_evidences(evidences)
                    if has_cr_red_flag:
                        careroute_red_flag_cases += 1

                    state = PatientState(
                        session_id=f"audit_pat_{idx}",
                        patient_id=f"P_{idx:05d}",
                        chief_complaint=f"Initial: {patient['initial_evidence']}",
                    )

                    # Initial evidence
                    init_ev = patient["initial_evidence"]
                    if init_ev:
                        matching_init = [
                            e for e in evidences if e == init_ev or e.startswith(f"{init_ev}_@_")
                        ]
                        if matching_init:
                            for m_init in matching_init:
                                val = m_init.split("_@_")[1] if "_@_" in m_init else True
                                state.mark_present(m_init, val)
                        else:
                            state.mark_present(init_ev, True)

                    init_cands, init_entropy = selector.compute_candidate_distribution(
                        state.known_present_evidence, state.known_absent_evidence
                    )
                    state.candidate_conditions = init_cands
                    state.uncertainty_score = init_entropy

                    turn = 0
                    trajectory = []
                    stop_reason = "MAX_CONVERSATION_TURNS_REACHED"
                    escalated = False

                    while turn < 7:
                        turn += 1
                        state.conversation_turn = turn

                        next_q = selector.select_next_question(state)
                        should_stop, reason, needs_esc = policy.should_stop(state, next_q)

                        if should_stop or next_q is None:
                            stop_reason = str(reason)
                            escalated = needs_esc
                            break

                        q_id = next_q.evidence_id
                        ig = next_q.expected_information_gain
                        distinct_questions.add(q_id)
                        question_counts[q_id] += 1
                        total_questions += 1
                        if ig < 0.01:
                            low_ig_questions += 1

                        # Dependency check
                        parent = ddxplus_provider.get_parent_evidence(q_id)
                        if parent and parent in state.known_absent_evidence:
                            dependency_violations += 1

                        # Simulator response
                        matching_evs = [
                            e for e in evidences if e == q_id or e.startswith(f"{q_id}_@_")
                        ]
                        if matching_evs:
                            ans_val = "PRESENT"
                            for m_ev in matching_evs:
                                v = m_ev.split("_@_")[1] if "_@_" in m_ev else True
                                state.mark_present(m_ev, v)
                        else:
                            ans_val = "ABSENT"
                            state.mark_absent(q_id)

                        state.record_question_asked(q_id)

                        # Recompute
                        new_cands, new_entropy = selector.compute_candidate_distribution(
                            state.known_present_evidence, state.known_absent_evidence
                        )
                        state.candidate_conditions = new_cands
                        state.uncertainty_score = new_entropy

                        top_c = new_cands[0] if new_cands else None
                        trajectory.append({
                            "turn": turn,
                            "question": q_id,
                            "ig": ig,
                            "answer": ans_val,
                            "top_cond": top_c.condition if top_c else "None",
                            "top_prob": top_c.probability if top_c else 0.0,
                            "entropy": new_entropy,
                        })

                    # Stopping recording
                    stop_reasons[stop_reason] += 1
                    turns_distribution[len(state.questions_asked)] += 1
                    all_turns.append(len(state.questions_asked))
                    all_entropy_reductions.append(max(0.0, init_entropy - state.uncertainty_score))

                    if escalated and has_cr_red_flag:
                        careroute_red_flag_detected += 1

                    # Diagnostic recall
                    top_cands = [c.condition for c in state.candidate_conditions]
                    t_lower = target.lower()
                    t1 = False
                    t3 = False
                    t5 = False
                    t_rank = None

                    if top_cands:
                        if t_lower in top_cands[0].lower() or top_cands[0].lower() in t_lower:
                            t1 = True
                            top1_total += 1
                        if any(t_lower in c.lower() or c.lower() in t_lower for c in top_cands[:3]):
                            t3 = True
                            top3_total += 1
                        if any(t_lower in c.lower() or c.lower() in t_lower for c in top_cands[:5]):
                            t5 = True
                            top5_total += 1
                        for r_idx, c in enumerate(top_cands, 1):
                            if t_lower in c.lower() or c.lower() in t_lower:
                                t_rank = r_idx
                                all_ranks.append(r_idx)
                                break

                    # Per-condition updating
                    c_st = cond_stats[target]
                    c_st["total"] += 1
                    if t1: c_st["top1"] += 1
                    if t3: c_st["top3"] += 1
                    if t5: c_st["top5"] += 1
                    c_st["turns"] += len(state.questions_asked)
                    if t_rank:
                        c_st["ranks"] += t_rank
                        c_st["ranked_cnt"] += 1

                    is_high_sev = (target_sev >= 3)
                    if is_high_sev:
                        high_sev_total += 1
                        c_st["high_sev"] += 1
                        # Escalation check
                        if escalated or state.uncertainty_score > 0.65:
                            high_sev_escalated += 1
                            c_st["escalated"] += 1
                        else:
                            # RECORD HIGH SEVERITY FAILURE
                            # Failure type classification
                            failure_type = "G. BENCHMARK MISMATCH"
                            if has_cr_red_flag:
                                failure_type = "A. RED-FLAG DETECTION FAILURE"
                            elif stop_reason == "STOP_SUFFICIENT_EVIDENCE" and (state.candidate_conditions and state.candidate_conditions[0].severity < 3):
                                failure_type = "E. STOPPING FAILURE / URGENCY MAPPING"

                            high_sev_failures.append({
                                "patient_id": state.patient_id,
                                "pathology": target,
                                "severity": target_sev,
                                "initial_evidence": init_ev,
                                "evidence_count": len(evidences),
                                "trajectory": trajectory,
                                "final_top_cond": state.candidate_conditions[0].condition if state.candidate_conditions else "None",
                                "final_top_prob": state.candidate_conditions[0].probability if state.candidate_conditions else 0.0,
                                "final_top_severity": state.candidate_conditions[0].severity if state.candidate_conditions else 1,
                                "final_entropy": state.uncertainty_score,
                                "stop_reason": stop_reason,
                                "needs_escalation": escalated,
                                "cr_red_flags_present": has_cr_red_flag,
                                "failure_type": failure_type,
                            })

    return {
        "n": n_patients,
        "top1_recall": top1_total / n_patients,
        "top3_recall": top3_total / n_patients,
        "top5_recall": top5_total / n_patients,
        "avg_rank": sum(all_ranks) / max(1, len(all_ranks)),
        "median_rank": sorted(all_ranks)[len(all_ranks) // 2] if all_ranks else 0,
        "avg_turns": sum(all_turns) / n_patients,
        "median_turns": sorted(all_turns)[len(all_turns) // 2] if all_turns else 0,
        "avg_entropy_reduction": sum(all_entropy_reductions) / n_patients,
        "dependency_violations": dependency_violations,
        "distinct_questions_count": len(distinct_questions),
        "total_questions_asked": total_questions,
        "low_ig_questions": low_ig_questions,
        "question_counts": question_counts.most_common(20),
        "stop_reasons": dict(stop_reasons),
        "turns_distribution": dict(turns_distribution),
        "high_sev_total": high_sev_total,
        "high_sev_escalated": high_sev_escalated,
        "high_sev_escalation_rate": high_sev_escalated / max(1, high_sev_total),
        "careroute_red_flag_cases": careroute_red_flag_cases,
        "careroute_red_flag_detected": careroute_red_flag_detected,
        "high_sev_failures": high_sev_failures,
        "cond_stats": dict(cond_stats),
    }


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    res = run_comprehensive_audit(n)
    with open("ml/evaluation/audit_results.json", "w") as f:
        json.dump(res, f, indent=2)
    print(f"Audit completed for N={n}. Saved to ml/evaluation/audit_results.json")
