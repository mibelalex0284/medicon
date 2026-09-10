import os
import re
from typing import Any, Dict, List, Optional, Tuple
import joblib


class SymptomClassifier:
    """Inference engine for predicting symptom patterns and routing to clinical specialties.
    
    IMPORTANT CLINICAL NOTE:
    This model performs prototype supervised symptom-text classification on the held-out
    Symptom2Disease dataset. It does NOT provide a confirmed clinical diagnosis or medical-grade
    validation. Output is phrased as symptom patterns and triage navigation suggestions.
    """

    DEFAULT_ARTIFACT_PATH = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "artifacts", "symptom_classifier.joblib"
    )

    def __init__(self, artifact_path: Optional[str] = None):
        self.artifact_path = artifact_path or self.DEFAULT_ARTIFACT_PATH
        self._bundle: Optional[Dict[str, Any]] = None

    def _ensure_loaded(self) -> None:
        """Loads the serialized model artifact if not already in memory."""
        if self._bundle is not None:
            return

        if not os.path.exists(self.artifact_path):
            raise FileNotFoundError(
                f"Symptom classifier artifact not found at '{self.artifact_path}'. "
                "Please run `python ml/training/train.py` first."
            )

        self._bundle = joblib.load(self.artifact_path)

    @property
    def is_ready(self) -> bool:
        """Checks if the artifact file exists on disk."""
        return os.path.exists(self.artifact_path)

    @property
    def default_threshold(self) -> float:
        """Returns the empirically selected confidence threshold from the artifact."""
        self._ensure_loaded()
        return float(self._bundle.get("confidence_threshold", 0.50))

    def _check_input_quality(self, text: str) -> Tuple[bool, str]:
        """Heuristic input-quality guard for detecting unfamiliar, empty, or low-information inputs.
        
        NOTE: This is a conservative heuristic guard, not a formal out-of-domain (OOD) detector.
        It flags inputs that lack minimum length, alphabetical tokens, or TF-IDF vocabulary overlap.
        """
        cleaned = text.strip()
        if not cleaned:
            return False, "Input is empty or contains only whitespace"

        # Check for minimum length (at least 4 non-whitespace chars)
        if len(cleaned) < 4:
            return False, "Input text is too short to describe clinical symptoms"

        # Must contain alphabetical characters
        if not re.search(r"[a-zA-Z]", cleaned):
            return False, "Input does not contain alphabetical characters"

        # Tokenize words
        words = re.findall(r"\b[a-zA-Z]{2,}\b", cleaned)
        if len(words) < 1:
            return False, "Input text lacks valid word tokens"

        # Check TF-IDF vocabulary overlap if vectorizer is available
        vectorizer = self._bundle.get("vectorizer")
        if vectorizer is not None:
            features = vectorizer.transform([cleaned])
            if features.nnz == 0:
                return False, "Input text contains no recognizable clinical symptom vocabulary"

        return True, "Valid"

    def predict(
        self,
        text: str,
        top_k: int = 3,
        confidence_threshold: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Predicts symptom pattern candidates and recommended specialty.
        
        Parameters:
            text: Patient-reported symptom description.
            top_k: Number of internal top candidate patterns to retrieve.
            confidence_threshold: Calibrated probability threshold for abstention.
                                 If None, uses the artifact's validated default (0.50).
        
        Returns:
            Dictionary containing prediction candidates, confidence, routing specialty,
            abstention/uncertainty status, and descriptive rationales.
        """
        self._ensure_loaded()

        effective_threshold = (
            confidence_threshold if confidence_threshold is not None else self.default_threshold
        )

        is_valid, quality_reason = self._check_input_quality(text)
        if not is_valid:
            return {
                "predicted_disease": "Unknown",
                "possible_condition_pattern": "Uncertain / Insufficient Information",
                "confidence": 0.0,
                "recommended_specialty": "GEN-MED",
                "top_predictions": [],
                "is_uncertain": True,
                "abstention_reason": quality_reason,
                "input_quality_status": "INSUFFICIENT_INFORMATION",
            }

        cleaned_text = text.strip()
        pipeline = self._bundle["pipeline"]
        disease_to_specialty = self._bundle.get("disease_to_specialty", {})
        classes = self._bundle.get("classes", pipeline.classes_)

        # Compute calibrated probability distribution
        probabilities = pipeline.predict_proba([cleaned_text])[0]

        # Top-k predictions sorted descending
        top_indices = probabilities.argsort()[::-1][:top_k]

        top_predictions: List[Dict[str, Any]] = []
        for idx in top_indices:
            disease_name = str(classes[idx])
            prob = float(probabilities[idx])
            # Robust specialty lookup (exact, lower, or title-case)
            spec_code = (
                disease_to_specialty.get(disease_name)
                or disease_to_specialty.get(disease_name.lower())
                or disease_to_specialty.get(disease_name.title(), "GEN-MED")
            )
            top_predictions.append(
                {
                    "disease": disease_name,
                    "probability": round(prob, 4),
                    "specialty": spec_code,
                }
            )

        top_match = top_predictions[0]
        confidence = top_match["probability"]
        is_uncertain = bool(confidence < effective_threshold)

        if is_uncertain:
            abstention_reason = (
                f"Calibrated confidence ({confidence:.4f}) is below validated threshold "
                f"({effective_threshold:.2f})"
            )
            pattern_label = f"Uncertain symptom pattern (low confidence: {top_match['disease']})"
        else:
            abstention_reason = None
            pattern_label = f"Symptom-pattern classification: {top_match['disease']}"

        return {
            "predicted_disease": top_match["disease"],
            "possible_condition_pattern": pattern_label,
            "confidence": confidence,
            "recommended_specialty": top_match["specialty"],
            "top_predictions": top_predictions,
            "is_uncertain": is_uncertain,
            "abstention_reason": abstention_reason,
            "input_quality_status": "VALID",
        }
symptom_classifier = SymptomClassifier()
