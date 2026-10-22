import json
import os
from typing import Any, Dict, List, Optional, Set, Tuple
import zipfile

from app.core.config import settings
from app.core.logging import logger


# Validated definitions for supported adaptive intake questions
ADAPTIVE_EVIDENCE_REGISTRY: Dict[str, Dict[str, Any]] = {
    "adaptive_functional_impact": {
        "name": "Functional Impact on Daily Activities or Sleep",
        "question_en": "Is this condition significantly interfering with your daily activities or sleep?",
        "data_type": "B",
        "possible-values": [True, False, "Yes", "No"],
        "category": "FUNCTIONAL_IMPACT",
        "is_antecedent": False,
        "allow_affirmative": True,
        "allow_negative": True,
        "state_field": "functional_impact",
        "affirmative_value": "Significant interference with daily activities or sleep",
        "negative_value": "No significant functional impact reported",
    },
    "adaptive_associated_symptoms_and_pertinent_negatives": {
        "name": "Associated Symptoms and Pertinent Negatives",
        "question_en": "Are you experiencing any other accompanying symptoms?",
        "data_type": "B",
        "possible-values": [True, False, "Yes", "No"],
        "category": "ASSOCIATED_SYMPTOM",
        "is_antecedent": False,
        "allow_affirmative": False,  # Unsafe: "yes" alone does not specify which symptoms are present
        "allow_negative": True,      # "no" safely confirms absence of additional symptoms
        "state_field": "associated_symptoms",
        "affirmative_value": None,
        "negative_value": False,
    },
}


class DDXPlusEvidenceProvider:
    """Provides high-performance, in-memory access to the clinical evidence and symptom ontology.

    Maintains controlled evidence questions, possible values, and parent/child question dependencies.
    Does NOT load, cache, or predict disease conditions.
    """

    _instance: Optional["DDXPlusEvidenceProvider"] = None

    def __init__(self, data_path: Optional[str] = None):
        self.data_path = data_path or settings.DDXPLUS_DATA_PATH
        self._evidences: Dict[str, Dict[str, Any]] = {}
        self._parent_evidences: Dict[str, str] = {}
        self._child_evidences: Dict[str, Set[str]] = {}
        self._loaded: bool = False
        self._load_ontology()

    def _load_ontology(self) -> None:
        if self._loaded:
            return

        candidate_paths = [
            self.data_path,
            r"D:\22687585.zip",
            os.path.join(os.path.dirname(__file__), "..", "..", "data", "22687585.zip"),
            os.path.join(os.path.dirname(__file__), "..", "..", "data", "ddxplus"),
        ]

        loaded_path = None
        for path in candidate_paths:
            if path and os.path.exists(path):
                loaded_path = path
                break

        if not loaded_path:
            logger.warning(
                f"Clinical evidence ontology file not found at '{self.data_path}' or candidate locations. "
                "Evidence provider initialized in empty mode."
            )
            return

        try:
            if zipfile.is_zipfile(loaded_path):
                with zipfile.ZipFile(loaded_path, "r") as z:
                    if "release_evidences.json" in z.namelist():
                        ev_bytes = z.read("release_evidences.json")
                        self._evidences = json.loads(ev_bytes.decode("utf-8"))
            elif os.path.isdir(loaded_path):
                ev_file = os.path.join(loaded_path, "release_evidences.json")
                if os.path.exists(ev_file):
                    with open(ev_file, "r", encoding="utf-8") as f:
                        self._evidences = json.load(f)

            # Build parent-child dependency mapping from code_question
            for ev_id, ev_info in self._evidences.items():
                code_q = ev_info.get("code_question")
                if code_q and code_q != ev_id:
                    self._parent_evidences[ev_id] = code_q
                    self._child_evidences.setdefault(code_q, set()).add(ev_id)

            self._loaded = True
            logger.info(
                f"Clinical evidence ontology successfully indexed: {len(self._evidences)} evidences "
                f"loaded from '{loaded_path}'."
            )
        except Exception as exc:
            logger.error(f"Failed to load clinical evidence ontology from '{loaded_path}': {exc}")

    @property
    def is_loaded(self) -> bool:
        return self._loaded and len(self._evidences) > 0

    def get_evidence(self, evidence_id: str) -> Optional[Dict[str, Any]]:
        """Lookup evidence metadata by base ID or composite code (e.g. 'E_53' or 'adaptive_functional_impact')."""
        base_id = evidence_id.split("_@_")[0]
        return self._evidences.get(base_id) or ADAPTIVE_EVIDENCE_REGISTRY.get(base_id)

    def get_all_evidences(self) -> Dict[str, Dict[str, Any]]:
        return self._evidences

    def get_evidence_question(self, evidence_id: str, lang: str = "en") -> str:
        ev = self.get_evidence(evidence_id)
        if not ev:
            return f"Do you have symptoms related to {evidence_id}?"
        if lang == "fr":
            return ev.get("question_fr") or ev.get("question_en", "")
        return ev.get("question_en") or ev.get("question_fr", "")

    def get_evidence_name(self, evidence_id: str) -> str:
        """Returns human-readable name or question for an evidence code."""
        ev = self.get_evidence(evidence_id)
        if not ev:
            return evidence_id
        q = ev.get("question_en")
        if q:
            return q.strip().rstrip("?")
        return ev.get("name") or evidence_id

    def get_evidence_type(self, evidence_id: str) -> str:
        """Returns 'B' (binary), 'C' (categorical), 'M' (multichoice), or 'N' (numeric)."""
        ev = self.get_evidence(evidence_id)
        if not ev:
            return "B"
        return ev.get("data_type", "B")

    def get_possible_values(self, evidence_id: str) -> List[str]:
        ev = self.get_evidence(evidence_id)
        if not ev:
            return []
        return ev.get("possible-values", [])

    def is_antecedent(self, evidence_id: str) -> bool:
        ev = self.get_evidence(evidence_id)
        if not ev:
            return False
        return bool(ev.get("is_antecedent", False))

    def get_parent_evidence(self, evidence_id: str) -> Optional[str]:
        """Returns the parent evidence ID if this evidence depends on a parent question."""
        base_id = evidence_id.split("_@_")[0]
        return self._parent_evidences.get(base_id)

    def get_child_evidences(self, evidence_id: str) -> List[str]:
        """Returns child evidence IDs that depend on this question."""
        base_id = evidence_id.split("_@_")[0]
        return sorted(list(self._child_evidences.get(base_id, set())))

    def is_dependency_satisfied(
        self,
        evidence_id: str,
        known_present: Dict[str, Any],
        known_absent: List[str],
    ) -> bool:
        """Determines if question dependency rules allow asking this evidence.

        Rules:
        - Root question (no parent): Always eligible (True).
        - Parent is ABSENT: Strictly INELIGIBLE (False).
        - Parent is PRESENT: Eligible (True).
        - Parent is UNKNOWN (not yet answered): NOT eligible yet (parent must be asked first).
        """
        parent_id = self.get_parent_evidence(evidence_id)
        if not parent_id:
            return True

        # Check if parent is explicitly absent
        absent_bases = {k.split("_@_")[0] for k in known_absent}
        if parent_id in absent_bases or parent_id in known_absent:
            return False

        # Check if parent is confirmed present
        present_bases = {k.split("_@_")[0] for k in known_present.keys()}
        if parent_id in present_bases or parent_id in known_present:
            return True

        # Parent is unknown / not yet asked
        return False

    def validate_evidence(self, evidence_id: str, value: Any = None) -> Tuple[bool, Optional[str]]:
        """Validates that evidence exists in the ontology and its value is legitimate."""
        ev = self.get_evidence(evidence_id)
        if not ev:
            return False, f"Unknown evidence code '{evidence_id}'"

        dtype = ev.get("data_type", "B")
        possible_vals = ev.get("possible-values", [])

        if dtype in ["C", "M"] and value is not None:
            if isinstance(value, list):
                invalid_vals = [v for v in value if v not in possible_vals]
                if invalid_vals:
                    return False, f"Invalid values {invalid_vals} for evidence '{evidence_id}'"
            elif isinstance(value, str) and value not in possible_vals:
                return False, f"Invalid value '{value}' for evidence '{evidence_id}'"
        elif dtype == "B" and value is not None and possible_vals:
            # Check boolean equivalence or registered descriptive value
            valid_set = set(possible_vals) | {
                True, False, 1, 0, "1", "0", "True", "False",
                "present", "absent", "Present", "Absent", "yes", "no", "Yes", "No",
            }
            if ev.get("affirmative_value"):
                valid_set.add(ev.get("affirmative_value"))
            if ev.get("negative_value"):
                valid_set.add(ev.get("negative_value"))
            if value not in valid_set:
                return False, f"Invalid value '{value}' for binary evidence '{evidence_id}'"

        return True, None


ddxplus_provider = DDXPlusEvidenceProvider()
