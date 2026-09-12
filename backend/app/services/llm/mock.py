import re
from typing import Any, Dict, List, Optional
from app.services.llm.provider import (
    EvidenceStatus,
    ExtractedEvidenceItem,
    ExtractedEvidenceResult,
    LLMProvider,
)


class MockLLMProvider:
    """Mock/fallback LLM provider for deterministic offline testing and system resilience

    when Gemini API credentials are not configured or the network is unavailable.
    """

    WORD_NUMS = {
        "one": "1",
        "two": "2",
        "three": "3",
        "four": "4",
        "five": "5",
        "six": "6",
        "seven": "7",
        "eight": "8",
        "nine": "9",
        "ten": "10",
    }

    def __init__(
        self,
        default_extracted: Optional[ExtractedEvidenceResult] = None,
        raise_on_call: Optional[Exception] = None,
    ):
        self.default_extracted = default_extracted
        self.raise_on_call = raise_on_call
        self.call_history: List[Dict[str, Any]] = []

    def extract_patient_evidence(
        self, message: str, context: Optional[Dict[str, Any]] = None
    ) -> ExtractedEvidenceResult:
        if self.raise_on_call:
            raise self.raise_on_call

        self.call_history.append({"method": "extract_patient_evidence", "message": message})

        if self.default_extracted:
            return self.default_extracted

        # Basic deterministic rule-based extractor for common keywords
        text = message.lower()
        items: List[ExtractedEvidenceItem] = []
        severity = None
        duration = None

        # Detect duration (digits or word numbers like "three days")
        dur_match = re.search(
            r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+(days?|weeks?|hours?|months?)\b",
            text,
        )
        if dur_match:
            n_raw = dur_match.group(1)
            unit_raw = dur_match.group(2)
            n = self.WORD_NUMS.get(n_raw, n_raw)
            unit = unit_raw if unit_raw.endswith("s") else f"{unit_raw}s"
            duration = f"{n} {unit}"

        # Detect severity: numeric rating scale ("7 out of 10" or "7/10") first
        num_sev_match = re.search(r"\b(\d{1,2})\s*(?:out of|\/)\s*10\b", text)
        if num_sev_match:
            severity = min(10, max(1, int(num_sev_match.group(1))))
        elif any(w in text for w in ["severe", "excruciating", "unbearable", "intense"]):
            severity = 8
        elif any(w in text for w in ["moderate", "medium"]):
            severity = 5
        elif any(w in text for w in ["mild", "slight", "minor"]):
            severity = 2

        # Expanded negation prefixes
        neg_prefixes = [
            r"\bno\b",
            r"\bnot\b",
            r"\bwithout\b",
            r"\bdenies\b",
            r"\bnever had\b",
            r"\bdon['’]?t have(?:\s+a|\s+any)?\b",
            r"\bdo not have(?:\s+a|\s+any)?\b",
            r"\bfree of\b",
            r"\bnegative for\b",
        ]

        # Uncertainty prefixes
        unk_prefixes = [
            r"\bnot\s+sure\b",
            r"\bunsure\b",
            r"\bmaybe\b",
            r"\bpossibly\b",
            r"\bmight have\b",
        ]

        # Symptom keywords mapping to standard DDXPlus evidence codes
        symptom_map = [
            # Multi-word first to avoid partial substring matching
            ("shortness of breath", "E_88"),
            ("chest pain", "E_54_@_V_180"),
            ("neck stiffness", "E_97"),
            ("stiff neck", "E_97"),
            ("vision gets blurry", "E_212"),
            ("blurry vision", "E_212"),
            ("blurred vision", "E_212"),
            ("coughing up blood", "E_45"),
            # Single word
            ("headache", "E_127"),
            ("exhausted", "E_24"),
            ("fatigue", "E_24"),
            ("tired", "E_24"),
            ("fever", "E_91"),
            ("cough", "E_50"),
            ("vomiting", "E_14"),
            ("nausea", "E_13"),
            ("diarrhea", "E_82"),
            ("rash", "E_130"),
            ("pain", "E_53"),
        ]

        matched_codes = set()
        for kw, code in symptom_map:
            m = re.search(rf"\b{re.escape(kw)}\b", text)
            if m and code not in matched_codes:
                matched_codes.add(code)
                prefix = text[max(0, m.start() - 35) : m.start()].strip()

                is_unk = any(re.search(pat, prefix) for pat in unk_prefixes) or (
                    "not sure" in text and kw in text
                )
                is_neg = any(re.search(pat, prefix) for pat in neg_prefixes)

                if is_unk:
                    items.append(
                        ExtractedEvidenceItem(evidence_code=code, status=EvidenceStatus.UNKNOWN)
                    )
                elif is_neg:
                    items.append(
                        ExtractedEvidenceItem(evidence_code=code, status=EvidenceStatus.ABSENT)
                    )
                else:
                    items.append(
                        ExtractedEvidenceItem(evidence_code=code, status=EvidenceStatus.PRESENT)
                    )

        return ExtractedEvidenceResult(
            chief_complaint=message[:100],
            duration=duration,
            severity=severity,
            items=items,
        )

    def phrase_question(
        self, controlled_question: str, evidence_id: str, context: Optional[Dict[str, Any]] = None
    ) -> str:
        if self.raise_on_call:
            raise self.raise_on_call

        self.call_history.append(
            {"method": "phrase_question", "question": controlled_question, "evidence_id": evidence_id}
        )
        return f"To help determine the best care pathway: {controlled_question}"

    def summarize_conversation(self, messages: List[Dict[str, str]]) -> str:
        user_msgs = [m["content"] for m in messages if m.get("sender") == "patient"]
        return "Patient reported: " + "; ".join(user_msgs)
