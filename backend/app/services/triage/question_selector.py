import math
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel

from app.schemas.patient_state import PatientState, CandidateCondition
from app.services.triage.evidence_provider import DDXPlusEvidenceProvider, ddxplus_provider


class ControlledQuestion(BaseModel):
    evidence_id: str
    question_text: str
    data_type: str = "B"
    possible_values: List[str] = []
    category: str = "GENERAL"
    is_antecedent: bool = False
    expected_information_gain: float = 0.0
    is_safety_priority: bool = False


class InformationGainQuestionSelector:
    """Adaptive question selection engine implementing true Mutual Information (Information Gain)

    and Bayesian posterior distribution updates over the DDXPlus clinical ontology.

    ARCHITECTURE & SAFETY DESIGN:
    1. Safety Eligibility: High-severity conditions (severity >= 4) with unruled-out
       critical symptoms are checked through an explicit safety path, rather than an
       additive bonus that distorts differential ranking.
    2. Dependency Eligibility: Enforces DDXPlus parent-child dependencies derived from
       the ontology's `code_question` relationships. Child questions are prohibited if
       the parent symptom is absent or unconfirmed.
    3. Information-Value Ranking: Eligible questions are ranked by true Mutual Information:
       IG(E; C) = H(C) - E_v[H(C | E=v)]

    NOTE: The conditional likelihoods P(E | C) used herein represent an information-value
    approximation derived deterministically from the DDXPlus evidence/condition structure,
    not a clinically calibrated disease probability model.
    """

    # Critical evidence codes that warrant safety-priority consideration if relevant
    CRITICAL_SAFETY_EVIDENCES = ["E_88", "E_201", "E_54_@_V_180", "E_45"]

    def __init__(self, evidence_provider: Optional[DDXPlusEvidenceProvider] = None):
        self.evidence_provider = evidence_provider or ddxplus_provider

    def compute_candidate_distribution(
        self,
        known_present: Dict[str, Any],
        known_absent: List[str],
        prior_hints: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[List[CandidateCondition], float]:
        """Calculates normalized posterior probability distribution over all 49 conditions

        given currently known positive and negative evidence, along with Shannon entropy.
        Uses a principled log-likelihood scoring model derived from DDXPlus condition profiles.
        """
        all_conditions = self.evidence_provider.get_all_conditions()
        if not all_conditions:
            return [], 1.0

        n_conds = len(all_conditions)
        log_prior = -math.log(n_conds)

        # Gentle blending of Symptom2Disease prior hints if available (85% uniform + 15% S2D)
        priors: Dict[str, float] = {}
        if prior_hints:
            for hint in prior_hints:
                disease = hint.get("disease", "")
                prob = hint.get("probability", 0.0)
                for cond_name in all_conditions.keys():
                    if disease.lower() in cond_name.lower() or cond_name.lower() in disease.lower():
                        priors[cond_name] = priors.get(cond_name, 0.0) + prob

        # Base IDs for presence and absence
        present_bases = {k.split("_@_")[0] for k in known_present.keys()}
        absent_bases = {k.split("_@_")[0] for k in known_absent}

        log_likelihoods: Dict[str, float] = {}

        for cond_name, cond_info in all_conditions.items():
            symptoms = set(cond_info.get("symptoms", {}).keys())
            antecedents = set(cond_info.get("antecedents", {}).keys())
            all_cond_evidences = symptoms | antecedents
            cond_ev_bases = {k.split("_@_")[0] for k in all_cond_evidences}

            # Prior probability
            s2d_weight = priors.get(cond_name, 0.0)
            cond_prior = (0.85 / n_conds) + (0.15 * s2d_weight)
            log_l = math.log(max(1e-6, cond_prior))

            # Update for PRESENT evidence
            for p_base in present_bases:
                if p_base in cond_ev_bases:
                    # Symptom is in condition profile: sensitivity proxy
                    assoc_count = len(self.evidence_provider.get_conditions_for_evidence(p_base))
                    p_sens = 0.85 - 0.15 * ((assoc_count - 1) / max(1, n_conds - 1))
                    log_l += math.log(p_sens)
                else:
                    # Symptom unexpected for this condition: baseline false-positive rate
                    log_l += math.log(0.04)

            # Update for ABSENT evidence
            for a_base in absent_bases:
                if a_base in cond_ev_bases:
                    # Condition expected symptom, but patient denied it
                    assoc_count = len(self.evidence_provider.get_conditions_for_evidence(a_base))
                    p_sens = 0.85 - 0.15 * ((assoc_count - 1) / max(1, n_conds - 1))
                    log_l += math.log(1.0 - p_sens)
                else:
                    # Condition did not expect symptom, consistent with denial
                    log_l += math.log(0.96)

            log_likelihoods[cond_name] = log_l

        # Log-sum-exp normalization to prevent underflow
        max_log_l = max(log_likelihoods.values())
        unnormalized = {c: math.exp(log_l - max_log_l) for c, log_l in log_likelihoods.items()}
        total_unnormalized = sum(unnormalized.values())

        candidates: List[CandidateCondition] = []
        for cond_name, unnorm_val in unnormalized.items():
            prob = unnorm_val / total_unnormalized
            severity = self.evidence_provider.get_condition_severity(cond_name)
            candidates.append(
                CandidateCondition(
                    condition=cond_name,
                    probability=round(prob, 4),
                    severity=severity,
                )
            )

        # Sort descending by probability
        candidates.sort(key=lambda c: c.probability, reverse=True)

        # Normalized Shannon entropy: H(C) = - sum(p * log2(p)) / log2(N)
        raw_entropy = -sum(
            c.probability * math.log2(c.probability)
            for c in candidates
            if c.probability > 0
        )
        max_entropy = math.log2(n_conds) if n_conds > 1 else 1.0
        normalized_entropy = min(1.0, max(0.0, raw_entropy / max_entropy))

        return candidates, round(normalized_entropy, 4)

    def compute_mutual_information(
        self,
        evidence_id: str,
        candidate_probs: Dict[str, float],
    ) -> float:
        """Calculates the true Mutual Information (Information Gain) for candidate evidence E:

        IG(E; C) = H(C) - E_v[ H(C | E=v) ]
        """
        all_conditions = self.evidence_provider.get_all_conditions()
        n_conds = len(all_conditions)
        base_id = evidence_id.split("_@_")[0]
        associated_conds = self.evidence_provider.get_conditions_for_evidence(base_id)
        m_count = len(associated_conds)

        # Prior entropy H(C)
        h_prior = -sum(
            p * math.log2(p) for p in candidate_probs.values() if p > 0
        )
        if h_prior <= 1e-6:
            return 0.0

        # Conditional likelihoods P(E=1 | C=c)
        p_e1_given_c: Dict[str, float] = {}
        for c in all_conditions.keys():
            if c in associated_conds:
                p_e1_given_c[c] = 0.85 - 0.15 * ((m_count - 1) / max(1, n_conds - 1))
            else:
                p_e1_given_c[c] = 0.04

        # Marginal P(E=1) and P(E=0)
        p_e1 = sum(candidate_probs[c] * p_e1_given_c[c] for c in all_conditions.keys())
        p_e0 = 1.0 - p_e1

        if p_e1 <= 1e-6 or p_e0 <= 1e-6:
            return 0.0

        # Posteriors P(C=c | E=1) and P(C=c | E=0)
        post_e1 = {
            c: candidate_probs[c] * p_e1_given_c[c] / p_e1 for c in all_conditions.keys()
        }
        post_e0 = {
            c: candidate_probs[c] * (1.0 - p_e1_given_c[c]) / p_e0 for c in all_conditions.keys()
        }

        # Conditional entropies H(C | E=1) and H(C | E=0)
        h_e1 = -sum(p * math.log2(p) for p in post_e1.values() if p > 0)
        h_e0 = -sum(p * math.log2(p) for p in post_e0.values() if p > 0)

        # Expected conditional entropy E[H(C|E)]
        expected_h = (p_e1 * h_e1) + (p_e0 * h_e0)

        # Information Gain in bits
        ig = max(0.0, h_prior - expected_h)
        return ig

    def select_next_question(
        self,
        state: PatientState,
        top_k_candidates: int = 10,
    ) -> Optional[ControlledQuestion]:
        """Selects the single most discriminative question from the DDXPlus ontology

        by strictly separating:
        1. Safety eligibility
        2. Dependency eligibility
        3. True Information-Value ranking
        """
        all_evidences = self.evidence_provider.get_all_evidences()
        if not all_evidences:
            return None

        prob_map = {c.condition: c.probability for c in state.candidate_conditions}

        # =========================================================================
        # STAGE 1: SAFETY ELIGIBILITY PATH
        # =========================================================================
        # If the top active condition has high acuity (severity >= 4) and a critical
        # safety symptom is relevant and unruled-out, prioritize ruling it out explicitly.
        if state.candidate_conditions:
            top_cand = state.candidate_conditions[0]
            if top_cand.severity >= 4 and top_cand.probability >= 0.20:
                top_symptoms = self.evidence_provider.get_condition_symptoms(top_cand.condition)
                for crit_ev in self.CRITICAL_SAFETY_EVIDENCES:
                    crit_base = crit_ev.split("_@_")[0]
                    if (
                        crit_base in top_symptoms
                        and not state.is_known(crit_base)
                        and crit_base not in state.questions_asked
                        and self.evidence_provider.is_dependency_satisfied(
                            crit_base, state.known_present_evidence, state.known_absent_evidence
                        )
                    ):
                        q_text = self.evidence_provider.get_evidence_question(crit_base, lang="en")
                        return ControlledQuestion(
                            evidence_id=crit_base,
                            question_text=q_text,
                            data_type=self.evidence_provider.get_evidence_type(crit_base),
                            possible_values=[
                                str(v) for v in self.evidence_provider.get_possible_values(crit_base)
                            ],
                            category="SAFETY",
                            is_antecedent=self.evidence_provider.is_antecedent(crit_base),
                            expected_information_gain=1.0,
                            is_safety_priority=True,
                        )

        # =========================================================================
        # STAGE 2: DEPENDENCY ELIGIBILITY FILTERING
        # =========================================================================
        # Gather relevant candidate evidences that appear in active conditions
        active_conditions = [c.condition for c in state.candidate_conditions[:top_k_candidates]]
        if not active_conditions:
            active_conditions = list(self.evidence_provider.get_all_conditions().keys())[:10]

        candidate_ev_ids: Set[str] = set()
        for cond_name in active_conditions:
            symptoms = self.evidence_provider.get_condition_symptoms(cond_name)
            for ev_key in symptoms.keys():
                base_id = ev_key.split("_@_")[0]
                if not state.is_known(base_id) and base_id not in state.questions_asked:
                    candidate_ev_ids.add(base_id)

        # Fallback to broader candidate set if none remaining in active conditions
        if not candidate_ev_ids:
            for ev_id in all_evidences.keys():
                if not state.is_known(ev_id) and ev_id not in state.questions_asked:
                    candidate_ev_ids.add(ev_id)

        # Filter strictly by ontology dependency rules (parent must be satisfied)
        valid_candidates: List[str] = []
        for ev_id in candidate_ev_ids:
            if self.evidence_provider.is_dependency_satisfied(
                ev_id, state.known_present_evidence, state.known_absent_evidence
            ):
                valid_candidates.append(ev_id)

        if not valid_candidates:
            return None

        # =========================================================================
        # STAGE 3: TRUE INFORMATION-VALUE RANKING
        # =========================================================================
        scored_candidates: List[Tuple[str, float]] = []

        for ev_id in sorted(valid_candidates):  # Sort first for deterministic tie-breaking
            ev = all_evidences.get(ev_id)
            if not ev:
                continue

            ig = self.compute_mutual_information(ev_id, prob_map)

            # Redundancy discount for antecedents if 2+ antecedents already asked
            if ev.get("is_antecedent", False):
                ant_count = sum(
                    1 for q in state.questions_asked if self.evidence_provider.is_antecedent(q)
                )
                if ant_count >= 2:
                    ig = max(0.0, ig - 0.05)

            scored_candidates.append((ev_id, ig))

        # Sort descending by Information Gain; ties broken by evidence ID alphabetically
        scored_candidates.sort(key=lambda item: (item[1], -ord(item[0][0]) if item[0] else 0), reverse=True)

        best_ev_id, best_ig = scored_candidates[0]

        question_text = self.evidence_provider.get_evidence_question(best_ev_id, lang="en")
        data_type = self.evidence_provider.get_evidence_type(best_ev_id)
        possible_vals = [str(v) for v in self.evidence_provider.get_possible_values(best_ev_id)]
        is_ant = self.evidence_provider.is_antecedent(best_ev_id)

        return ControlledQuestion(
            evidence_id=best_ev_id,
            question_text=question_text,
            data_type=data_type,
            possible_values=possible_vals,
            category="ANTECEDENT" if is_ant else "SYMPTOM",
            is_antecedent=is_ant,
            expected_information_gain=round(best_ig, 4),
            is_safety_priority=False,
        )


question_selector = InformationGainQuestionSelector()
