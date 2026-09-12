import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import zipfile

from app.core.config import settings
from app.core.logging import logger


class DDXPlusEvidenceProvider:
    """Provides high-performance, in-memory access to the DDXPlus clinical evidence

    and condition ontologies. Caches parsed structures on initial load.
    """

    _instance: Optional["DDXPlusEvidenceProvider"] = None

    def __init__(self, data_path: Optional[str] = None):
        self.data_path = data_path or settings.DDXPLUS_DATA_PATH
        self._evidences: Dict[str, Dict[str, Any]] = {}
        self._conditions: Dict[str, Dict[str, Any]] = {}
        self._evidence_to_conditions: Dict[str, Set[str]] = {}
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
                f"DDXPlus ontology file not found at '{self.data_path}' or candidate locations. "
                "Evidence provider initialized in empty mode."
            )
            return

        try:
            if zipfile.is_zipfile(loaded_path):
                with zipfile.ZipFile(loaded_path, "r") as z:
                    if "release_evidences.json" in z.namelist():
                        ev_bytes = z.read("release_evidences.json")
                        self._evidences = json.loads(ev_bytes.decode("utf-8"))
                    if "release_conditions.json" in z.namelist():
                        cond_bytes = z.read("release_conditions.json")
                        self._conditions = json.loads(cond_bytes.decode("utf-8"))
            elif os.path.isdir(loaded_path):
                ev_file = os.path.join(loaded_path, "release_evidences.json")
                cond_file = os.path.join(loaded_path, "release_conditions.json")
                if os.path.exists(ev_file):
                    with open(ev_file, "r", encoding="utf-8") as f:
                        self._evidences = json.load(f)
                if os.path.exists(cond_file):
                    with open(cond_file, "r", encoding="utf-8") as f:
                        self._conditions = json.load(f)

            # Build reverse index: evidence_id -> set of condition names
            for cond_name, cond_info in self._conditions.items():
                symptoms = cond_info.get("symptoms", {})
                for ev_key in symptoms.keys():
                    base_ev = ev_key.split("_@_")[0]
                    self._evidence_to_conditions.setdefault(base_ev, set()).add(cond_name)
                    self._evidence_to_conditions.setdefault(ev_key, set()).add(cond_name)

                antecedents = cond_info.get("antecedents", {})
                for ant_key in antecedents.keys():
                    base_ant = ant_key.split("_@_")[0]
                    self._evidence_to_conditions.setdefault(base_ant, set()).add(cond_name)
                    self._evidence_to_conditions.setdefault(ant_key, set()).add(cond_name)

            # Build parent-child dependency mapping from code_question
            for ev_id, ev_info in self._evidences.items():
                code_q = ev_info.get("code_question")
                if code_q and code_q != ev_id:
                    self._parent_evidences[ev_id] = code_q
                    self._child_evidences.setdefault(code_q, set()).add(ev_id)

            self._loaded = True
            logger.info(
                f"DDXPlus ontology successfully indexed: {len(self._evidences)} evidences, "
                f"{len(self._conditions)} conditions loaded from '{loaded_path}'."
            )
        except Exception as exc:
            logger.error(f"Failed to load DDXPlus ontology from '{loaded_path}': {exc}")

    @property
    def is_loaded(self) -> bool:
        return self._loaded and len(self._evidences) > 0

    def get_evidence(self, evidence_id: str) -> Optional[Dict[str, Any]]:
        """Lookup evidence metadata by base ID or composite code (e.g. 'E_53' or 'E_54_@_V_180')."""
        base_id = evidence_id.split("_@_")[0]
        return self._evidences.get(base_id)

    def get_all_evidences(self) -> Dict[str, Dict[str, Any]]:
        return self._evidences

    def get_condition(self, condition_name: str) -> Optional[Dict[str, Any]]:
        return self._conditions.get(condition_name)

    def get_all_conditions(self) -> Dict[str, Dict[str, Any]]:
        return self._conditions

    def get_evidence_question(self, evidence_id: str, lang: str = "en") -> str:
        ev = self.get_evidence(evidence_id)
        if not ev:
            return f"Do you have symptoms related to {evidence_id}?"
        if lang == "fr":
            return ev.get("question_fr") or ev.get("question_en", "")
        return ev.get("question_en") or ev.get("question_fr", "")

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

    def get_condition_symptoms(self, condition_name: str) -> Dict[str, Any]:
        cond = self.get_condition(condition_name)
        if not cond:
            return {}
        return cond.get("symptoms", {})

    def get_condition_severity(self, condition_name: str) -> int:
        cond = self.get_condition(condition_name)
        if not cond:
            return 1
        return int(cond.get("severity", 1))

    def get_conditions_for_evidence(self, evidence_id: str) -> Set[str]:
        base_id = evidence_id.split("_@_")[0]
        return self._evidence_to_conditions.get(base_id, set())

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

        return True, None


ddxplus_provider = DDXPlusEvidenceProvider()
