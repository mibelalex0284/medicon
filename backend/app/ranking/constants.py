"""Centralized ranking weights, thresholds, and normalization constants for Stage 6.

All weights must sum to strictly 1.00.
No magic numbers should be scattered in scoring or ranking algorithms.
"""

from typing import Dict

# Centralized Factor Weights (Sum = 1.00)
WEIGHT_SPECIALTY_MATCH: float = 0.30
WEIGHT_AVAILABILITY: float = 0.20
WEIGHT_PREDICTED_WAIT: float = 0.15
WEIGHT_EXPERIENCE: float = 0.10
WEIGHT_RATING_RELIABILITY: float = 0.10
WEIGHT_PATIENT_PREFERENCE: float = 0.10
WEIGHT_LANGUAGE_MATCH: float = 0.05

RANKING_WEIGHTS: Dict[str, float] = {
    "specialty_match": WEIGHT_SPECIALTY_MATCH,
    "availability": WEIGHT_AVAILABILITY,
    "predicted_wait": WEIGHT_PREDICTED_WAIT,
    "experience": WEIGHT_EXPERIENCE,
    "rating_reliability": WEIGHT_RATING_RELIABILITY,
    "patient_preference": WEIGHT_PATIENT_PREFERENCE,
    "language_match": WEIGHT_LANGUAGE_MATCH,
}

# Validation: ensure weights strictly sum to 1.00
assert abs(sum(RANKING_WEIGHTS.values()) - 1.00) < 1e-6, "Ranking weights must sum exactly to 1.00"

# Specialty Scoring Constants
SPECIALTY_SCORE_PRIMARY: float = 1.0
SPECIALTY_SCORE_SECONDARY: float = 0.7

# Bayesian Rating Shrinkage Parameters
# adjusted_rating = (n / (n + m)) * rating + (m / (n + m)) * global_prior
RATING_SHRINKAGE_M: int = 10  # Smoothing strength
RATING_GLOBAL_PRIOR: float = 4.0  # System-level prior out of 5.0
RATING_MAX_SCALE: float = 5.0
RATING_NEUTRAL_SCORE: float = RATING_GLOBAL_PRIOR / RATING_MAX_SCALE  # 0.80

# Experience Normalization Reference
# Bounded to [0.0, 1.0] representing 0 to 30 years of clinical experience
MAX_REFERENCE_EXPERIENCE_YEARS: int = 30

# Wait Time Normalization Reference (Minutes)
# 5 minutes -> 1.0 (minimal operational wait)
# 125+ minutes -> 0.0 (high wait)
MIN_OPERATIONAL_WAIT_MINUTES: int = 5
MAX_REFERENCE_WAIT_MINUTES: int = 120

# Patient Preference Constants
PREFERENCE_SCORE_MATCH: float = 1.0
PREFERENCE_SCORE_PARTIAL: float = 0.7
PREFERENCE_SCORE_NEUTRAL: float = 0.5
PREFERENCE_SCORE_MISMATCH: float = 0.2

# Language Match Constants
LANGUAGE_SCORE_MATCH: float = 1.0
LANGUAGE_SCORE_NEUTRAL: float = 0.5  # When no language is explicitly requested
LANGUAGE_SCORE_MISMATCH: float = 0.0
