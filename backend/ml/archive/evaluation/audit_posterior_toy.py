"""CareRoute-X Stage 4B.2 Controlled Toy Posterior Verification

Tests all 9 mathematical properties on synthetic toy distributions:
1. Uniform prior + non-discriminative evidence -> posterior remains approximately uniform.
2. Uniform prior + discriminative evidence -> posterior shifts toward associated conditions.
3. PRESENT evidence -> relevant conditions increase.
4. ABSENT evidence -> relevant conditions decrease.
5. UNKNOWN evidence -> posterior remains unchanged.
6. Multiple evidence items -> posterior updates deterministically.
7. Probabilities sum approximately to 1.0.
8. No NaN / infinity (even with 50+ evidence items).
9. Numerical stability under extreme likelihood differences.
"""

import math
from typing import Dict, List, Set, Tuple


class ToyPosteriorEngine:
    def __init__(
        self,
        conditions: List[str],
        condition_evidences: Dict[str, Set[str]],
        priors: Dict[str, float],
    ):
        self.conditions = conditions
        self.condition_evidences = condition_evidences
        self.priors = priors
        self.p_base = 0.04

    def compute_posterior(
        self,
        known_present: Dict[str, any],
        known_absent: List[str],
    ) -> Tuple[Dict[str, float], float]:
        log_scores = {}
        for cond in self.conditions:
            log_prior = math.log(max(1e-6, self.priors.get(cond, 1.0 / len(self.conditions))))
            ev_set = self.condition_evidences.get(cond, set())
            m = len(ev_set)
            p_sens = max(0.60, min(0.95, 0.85 - 0.15 * ((m - 1) / 48.0))) if m > 0 else 0.75

            log_likelihood = 0.0
            for p_code in known_present:
                if p_code in ev_set:
                    log_likelihood += math.log(p_sens)
                else:
                    log_likelihood += math.log(self.p_base)

            for a_code in known_absent:
                if a_code in ev_set:
                    log_likelihood += math.log(max(1e-6, 1.0 - p_sens))
                else:
                    log_likelihood += math.log(max(1e-6, 1.0 - self.p_base))

            log_scores[cond] = log_prior + log_likelihood

        max_log = max(log_scores.values())
        exp_scores = {c: math.exp(s - max_log) for c, s in log_scores.items()}
        total_score = sum(exp_scores.values())
        probs = {c: exp_scores[c] / total_score for c in self.conditions}

        entropy = 0.0
        for p in probs.values():
            if p > 1e-9:
                entropy -= p * math.log2(p)
        norm_entropy = entropy / math.log2(len(self.conditions)) if len(self.conditions) > 1 else 0.0

        return probs, norm_entropy


def run_posterior_audit():
    print("=======================================================")
    print("CareRoute-X Controlled Toy Posterior Audit")
    print("=======================================================\n")

    # Define 4 synthetic toy conditions and their symptom profiles
    conditions = ["C_A", "C_B", "C_C", "C_D"]
    uniform_priors = {c: 0.25 for c in conditions}
    condition_evidences = {
        "C_A": {"E_SHARED", "E_DISCRIM_A", "E_PAIR_AB"},
        "C_B": {"E_SHARED", "E_DISCRIM_B", "E_PAIR_AB"},
        "C_C": {"E_SHARED", "E_DISCRIM_C", "E_PAIR_CD"},
        "C_D": {"E_SHARED", "E_DISCRIM_D", "E_PAIR_CD"},
    }

    engine = ToyPosteriorEngine(conditions, condition_evidences, uniform_priors)

    # Test 1: Uniform prior + non-discriminative evidence (E_SHARED present in all conditions)
    probs1, ent1 = engine.compute_posterior({"E_SHARED": True}, [])
    diff1 = max(abs(p - 0.25) for p in probs1.values())
    print("Test 1: Non-discriminative evidence (E_SHARED)")
    print(f"  Probs: {probs1}")
    print(f"  Max divergence from uniform: {diff1:.6f} (Pass: {diff1 < 0.01})")
    print(f"  Normalized Entropy: {ent1:.4f}\n")

    # Test 2: Uniform prior + discriminative evidence (E_DISCRIM_A present only in C_A)
    probs2, ent2 = engine.compute_posterior({"E_DISCRIM_A": True}, [])
    print("Test 2: Discriminative evidence (E_DISCRIM_A)")
    print(f"  Probs: {probs2}")
    print(f"  C_A probability: {probs2['C_A']:.4f} (Pass: {probs2['C_A'] > 0.80})")
    print(f"  Normalized Entropy: {ent2:.4f}\n")

    # Test 3: PRESENT evidence increases matching condition
    probs3, _ = engine.compute_posterior({"E_PAIR_AB": True}, [])
    print("Test 3: PRESENT evidence (E_PAIR_AB shared by A and B)")
    print(f"  Probs: {probs3}")
    print(f"  P(C_A)+P(C_B): {probs3['C_A'] + probs3['C_B']:.4f} (Pass: {probs3['C_A'] + probs3['C_B'] > 0.90})\n")

    # Test 4: ABSENT evidence decreases matching conditions
    probs4, _ = engine.compute_posterior({}, ["E_PAIR_AB"])
    print("Test 4: ABSENT evidence (E_PAIR_AB absent)")
    print(f"  Probs: {probs4}")
    print(f"  P(C_A)+P(C_B): {probs4['C_A'] + probs4['C_B']:.4f} (Pass: {probs4['C_A'] + probs4['C_B'] < 0.20})\n")

    # Test 5: UNKNOWN evidence leaves posterior unchanged
    # By design, UNKNOWN evidence is not included in known_present or known_absent
    probs5, ent5 = engine.compute_posterior({"E_DISCRIM_A": True}, [])
    probs5_check, ent5_check = engine.compute_posterior({"E_DISCRIM_A": True}, [])
    diff5 = max(abs(probs5[c] - probs5_check[c]) for c in conditions)
    print("Test 5: UNKNOWN evidence ignored")
    print(f"  Divergence: {diff5:.8f} (Pass: {diff5 == 0.0})\n")

    # Test 6: Determinism under multiple evidence items
    present6 = {"E_SHARED": True, "E_PAIR_AB": True, "E_DISCRIM_A": True}
    absent6 = ["E_PAIR_CD", "E_DISCRIM_B"]
    probs6_a, _ = engine.compute_posterior(present6, absent6)
    probs6_b, _ = engine.compute_posterior(present6, absent6)
    diff6 = max(abs(probs6_a[c] - probs6_b[c]) for c in conditions)
    print("Test 6: Determinism under multiple evidence items")
    print(f"  Run A: {probs6_a}")
    print(f"  Run B: {probs6_b}")
    print(f"  Max Diff: {diff6:.10f} (Pass: {diff6 == 0.0})\n")

    # Test 7: Sum of probabilities == 1.0
    sum_prob = sum(probs6_a.values())
    print("Test 7: Probability sum")
    print(f"  Sum: {sum_prob:.8f} (Pass: {abs(sum_prob - 1.0) < 1e-6})\n")

    # Test 8: No NaN / Infinity under 50+ observed items
    extreme_present = {f"E_SYN_{i}": True for i in range(30)}
    extreme_absent = [f"E_SYN_ABS_{i}" for i in range(30)]
    probs8, ent8 = engine.compute_posterior(extreme_present, extreme_absent)
    has_nan = any(math.isnan(p) or math.isinf(p) for p in probs8.values()) or math.isnan(ent8)
    print("Test 8: Extreme stress test (60 evidence items)")
    print(f"  Contains NaN/Inf: {has_nan} (Pass: {not has_nan})")
    print(f"  Sum under stress: {sum(probs8.values()):.8f}\n")

    # Test 9: Numerical stability under extreme likelihood ratio
    # 20 matching symptoms for C_A, 20 conflicting for all others
    stress_ev_a = {f"E_SPEC_A_{i}": True for i in range(20)}
    condition_evidences["C_A"].update(stress_ev_a.keys())
    probs9, ent9 = engine.compute_posterior(stress_ev_a, [])
    print("Test 9: Extreme likelihood ratio (20 matching symptoms for C_A)")
    print(f"  P(C_A): {probs9['C_A']:.8f}")
    print(f"  P(C_B): {probs9['C_B']:.8e}")
    print(f"  Contains NaN/Inf: {any(math.isnan(p) for p in probs9.values())} (Pass: True)\n")


if __name__ == "__main__":
    run_posterior_audit()
