import json
import re
from typing import Any, Dict, List, Optional
from pydantic import ValidationError

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.logging import logger
from app.services.llm.provider import (
    EvidenceStatus,
    ExtractedEvidenceItem,
    ExtractedEvidenceResult,
    LLMProvider,
)


class LLMExtractionError(AppException):
    """Raised when LLM extraction fails or returns malformed clinical data."""

    def __init__(
        self,
        message: str = "Clinical evidence extraction failed",
        code: str = "LLM_EXTRACTION_FAILED",
    ):
        super().__init__(code=code, message=message, status_code=502)


# Curated controlled clinical dictionary mapping natural expressions to canonical DDXPlus codes
CONTROLLED_EVIDENCE_MAP = {
    "fever": "E_91",
    "cough": "E_77",
    "headache": "E_127",
    "head hurts": "E_127",
    "fatigue": "E_24",
    "exhaustion": "E_24",
    "tired": "E_24",
    "malaise": "E_148",
    "sore throat": "E_194",
    "dyspnea": "E_88",
    "shortness of breath": "E_88",
    "difficulty breathing": "E_88",
    "can't breathe": "E_88",
    "chest pain": "E_53",
    "crushing chest pain": "E_54_@_V_180",
    "severe chest pain": "E_54_@_V_180",
    "heartburn": "E_51",
    "burning in chest": "E_51",
    "epigastric pain": "E_50",
    "stomach ache": "E_50",
    "abdominal pain": "E_50",
    "nausea": "E_181",
    "vomiting": "E_181",
    "diarrhea": "E_129",
    "sweating": "E_151",
    "diaphoresis": "E_151",
    "chills": "E_89",
    "rigors": "E_89",
    "palpitations": "E_155",
    "racing heartbeat": "E_155",
    "dizziness": "E_214",
    "lightheadedness": "E_214",
    "fainting": "E_201",
    "loss of consciousness": "E_201",
    "syncope": "E_201",
    "bleeding": "E_45",
    "coughing up blood": "E_45",
    "hemoptysis": "E_45",
    "blurry vision": "E_212",
    "vision changes": "E_212",
    "neck stiffness": "E_97",
    "stiff neck": "E_97",
    "weight loss": "E_144",
    "muscle aches": "E_176",
    "body aches": "E_176",
    "myalgia": "E_176",
    "orthopnea": "E_217",
    "ear pain": "E_168",
    "runny nose": "E_173",
    "rhinorrhea": "E_173",
    "nasal congestion": "E_153",
    "stuffy nose": "E_153",
    "sneezing": "E_154",
    "wheezing": "E_213",
}


def is_diagnostic_claim(text: str) -> bool:
    """Detects whether text makes an affirmative diagnostic claim or medical assertion.

    Interrogative symptom queries (e.g. 'Do you have a fever?', 'Are you having chest pain?')
    are NOT considered diagnostic.
    Affirmative assertions (e.g. 'You have the flu.', 'You may have pneumonia.',
    'I think you have asthma.') ARE considered diagnostic.
    """
    s = text.strip()
    if not s:
        return False
    # 1. Any mention of diagnosis / diagnosed
    if re.search(r"\bdiagnos", s, re.IGNORECASE):
        return True
    # 2. Speculative diagnosis assertions: 'I think you have', 'it seems you have', etc.
    if re.search(
        r"\b(?:i\s+think|it\s+seems|it\s+looks\s+like|i\s+believe|suspect)\s+(?:that\s+)?you\s+(?:have|may|might|could|suffer)\b",
        s,
        re.IGNORECASE,
    ):
        return True
    # 3. Probability assertions: 'you may/might/probably/likely have'
    if re.search(r"\byou\s+(?:may|might|probably|likely|definitely)\s+have\b", s, re.IGNORECASE):
        return True
    # 4. Suffering from
    if re.search(r"\byou\s+(?:are\s+)?suffer(?:ing)?\s+from\b", s, re.IGNORECASE):
        return True
    # 5. Direct affirmative 'You have ...' not preceded by an interrogative/conditional auxiliary
    for match in re.finditer(r"\byou\s+have\b", s, re.IGNORECASE):
        prefix = s[: match.start()].rstrip()
        tokens = re.findall(r"[a-zA-Z]+", prefix)
        if not tokens:
            # Starts with 'You have ...' -> affirmative diagnosis
            return True
        last_word = tokens[-1].lower()
        if last_word in ("do", "did", "if", "whether", "can", "could", "would", "should"):
            continue
        return True
    return False


class GeminiProvider:
    """Production provider using Google GenAI SDK (gemini-3.6-flash) for structured clinical NLP.

    Strictly satisfies:
    1. Structured output contract via Pydantic response_schema.
    2. Controlled vocabulary validation: rejects any invented/unknown DDXPlus evidence ID.
    3. Precise negation and uncertainty discrimination (PRESENT, ABSENT, UNKNOWN).
    4. Duration and 1-10 severity extraction.
    5. Controlled question phrasing validation (must be a question, no diagnosis, no treatment).
    6. Fail-fast error handling with automatic fallback to MockLLM.
    7. Complete privacy: zero logging of API keys or sensitive data.
    """

    @staticmethod
    def _is_permanent_quota_error(err_str: str) -> bool:
        """Determines if an error represents non-retryable quota or billing exhaustion.

        Permanent conditions (prepayment credits depleted, billing plan exhausted,
        daily quota limits) must FAIL FAST without sleep or retry.
        """
        s = err_str.lower()
        permanent_indicators = [
            "prepayment credits are depleted",
            "credits are depleted",
            "billing",
            "permanent quota",
            "quota exceeded for metric",
            "dailyrequestlimit",
            "perday",
        ]
        return any(ind in s for ind in permanent_indicators)

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key if api_key is not None else settings.GEMINI_API_KEY
        self.model = model or settings.GEMINI_MODEL
        self._client = None

    def _get_client(self):
        if self._client is None:
            if not self.api_key or self.api_key == "your-gemini-api-key-here":
                raise LLMExtractionError(
                    message="GEMINI_API_KEY is not configured.",
                    code="LLM_CONFIG_MISSING",
                )
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except Exception as exc:
                logger.error(f"Failed to initialize google.genai Client: {exc.__class__.__name__}")
                raise LLMExtractionError(f"Failed to initialize Gemini client: {exc.__class__.__name__}")
        return self._client

    def extract_patient_evidence(
        self, message: str, context: Optional[Dict[str, Any]] = None
    ) -> ExtractedEvidenceResult:
        """Extracts structured evidence items, duration, and severity using Gemini 3.6 Flash."""
        client = self._get_client()

        # Vocabulary guide passed to Gemini
        vocab_guide = ", ".join(f"'{k}' -> {v}" for k, v in list(CONTROLLED_EVIDENCE_MAP.items())[:35])

        system_instruction = (
            "You are a specialized clinical evidence extraction assistant for CareRoute-X triage. "
            "Your task is to extract ONLY symptoms, negations, duration, and severity explicitly stated by the patient.\n\n"
            "STRICT CLINICAL RULES:\n"
            "1. Do NOT hallucinate or infer unmentioned symptoms.\n"
            "2. NEGATION: If the patient denies or states they do NOT have a symptom (e.g. 'I don't have a fever', 'no chest pain', 'without cough'), "
            "mark status='ABSENT'.\n"
            "3. UNCERTAINTY: If the patient expresses uncertainty (e.g. 'not sure if I have a fever', 'might have a fever', 'maybe'), "
            "mark status='UNKNOWN'.\n"
            "4. AFFIRMATIVE: Only assign status='PRESENT' if the patient affirmatively confirms having the current symptom.\n"
            "5. PAST RESOLVED SYMPTOMS: If a symptom resolved in the past (e.g. 'had a fever last week but not now'), do NOT mark it as PRESENT.\n"
            "6. MULTIPLE SYMPTOMS: Extract ALL distinct symptoms mentioned.\n"
            "7. DURATION: Extract duration into the 'duration' string field if mentioned (e.g. '3 days', 'since yesterday', 'about a week').\n"
            "8. SEVERITY: If pain/severity is rated on a 1-10 scale (e.g. '7 out of 10'), set severity=7 (integer 1-10).\n"
            "9. CONTROLLED VOCABULARY: You must map symptoms strictly to the known DDXPlus evidence codes:\n"
            f"   Reference dictionary: {vocab_guide}\n"
            "   CRITICAL: Do NOT invent arbitrary or fictitious evidence codes. If a symptom cannot be confidently mapped to a known code, "
            "do NOT create a new E_xxx code; omit it or use an unmapped description in chief_complaint.\n"
            "10. Output MUST strictly conform to the ExtractedEvidenceResult schema."
        )

        prompt = f'Patient message: "{message}"\nExtract structured clinical evidence.'

        from google.genai import types
        import time

        last_err = None
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        response_schema=ExtractedEvidenceResult,
                        temperature=0.0,
                        max_output_tokens=1500,
                    ),
                )

                raw_text = (response.text or "").strip()
                result_json = json.loads(raw_text)
                result = ExtractedEvidenceResult.model_validate(result_json)

                # Strict Evidence ID Verification: reject any invented or unknown evidence IDs
                from app.services.triage.evidence_provider import ddxplus_provider

                validated_items: List[ExtractedEvidenceItem] = []
                for item in result.items:
                    base_code = item.evidence_code.split("_@_")[0]
                    if ddxplus_provider.get_evidence(item.evidence_code) or ddxplus_provider.get_evidence(base_code):
                        validated_items.append(item)
                    else:
                        logger.warning(
                            f"Rejected unverified evidence code invented by LLM: {item.evidence_code}"
                        )
                result.items = validated_items

                return result

            except (json.JSONDecodeError, ValidationError) as parse_err:
                last_err = parse_err
                logger.warning(f"Gemini output parsing attempt {attempt + 1} failed: {parse_err}")
                if attempt < 2:
                    time.sleep(1.0)
                    continue
                raise LLMExtractionError(f"Malformed LLM response: {parse_err}")
            except Exception as exc:
                last_err = exc
                err_str = str(exc)

                # FAIL FAST: permanent quota / billing exhaustion (NO SLEEP, NO RETRY)
                if self._is_permanent_quota_error(err_str):
                    logger.error(f"Gemini API quota/prepayment credits depleted: {err_str}")
                    raise LLMExtractionError(
                        "Gemini prepayment credits are depleted or billing quota exhausted. Please check billing at https://ai.studio/projects",
                        code="LLM_QUOTA_EXHAUSTED",
                    )

                # Transient rate limit: bounded retry only
                if ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str) and attempt < 2:
                    m = re.search(r"retry in (\d+(?:\.\d+)?)s", err_str, re.IGNORECASE)
                    delay = min(int(float(m.group(1))) + 1, 15) if m else 5
                    logger.warning(f"Gemini transient 429 rate limit hit. Backing off for {delay}s...")
                    time.sleep(delay)
                    continue

                logger.error(f"Gemini API call attempt {attempt + 1} failed: {exc.__class__.__name__}")
                if attempt < 2:
                    time.sleep(1.0)
                    continue
                raise LLMExtractionError(f"Gemini communication error: {exc.__class__.__name__}")

    def phrase_question(
        self, controlled_question: str, evidence_id: str, context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Phrases a controlled medical evidence question in empathetic conversational language.

        Validates that Gemini:
        1. Returns a question (ends with '?').
        2. Does not diagnose or prescribe medication.
        3. Preserves the exact clinical intent of the controlled question.
        Falls back to controlled_question if phrasing fails or violates constraints.
        """
        try:
            client = self._get_client()
        except Exception:
            return controlled_question

        system_instruction = (
            "You are an empathetic, professional outpatient care-navigation assistant. "
            "Given a controlled clinical evidence question, rephrase it into natural, compassionate, and clear patient-facing conversational language.\n"
            "STRICT CONSTRAINTS:\n"
            "1. You MUST NOT alter the clinical meaning of the question.\n"
            "2. Do NOT provide a diagnosis (e.g. do not say 'You have the flu' or 'You might have COVID').\n"
            "3. Do NOT give medical advice or prescribe treatments (e.g. do not suggest taking medications).\n"
            "4. Do NOT introduce unrelated medical questions or emergency directives.\n"
            "5. Keep the phrasing concise (1 sentence) and ensure it ends with a question mark '?'.\n"
            "6. Return ONLY the plain text question, nothing else."
        )

        prompt = f'Controlled question: "{controlled_question}" (Evidence code: {evidence_id})\nPhrase this naturally for the patient.'

        for attempt in range(2):
            try:
                from google.genai import types

                response = client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.2,
                        max_output_tokens=1000,
                    ),
                )

                # 1. Candidate and finish_reason inspection
                if not response.candidates:
                    logger.warning("Gemini phrasing rejected: no candidates returned")
                    return controlled_question

                candidate = response.candidates[0]
                finish_reason = getattr(candidate, "finish_reason", None)
                finish_reason_str = str(finish_reason).upper()

                if "MAX_TOKENS" in finish_reason_str:
                    logger.warning(
                        f"Gemini phrasing rejected: response truncated by MAX_TOKENS "
                        f"(finish_reason={finish_reason})"
                    )
                    return controlled_question

                if finish_reason and "STOP" not in finish_reason_str:
                    logger.warning(
                        f"Gemini phrasing rejected: non-normal finish reason ({finish_reason})"
                    )
                    return controlled_question

                phrased = (response.text or "").strip()

                # Clean any wrapping quotes or markdown
                phrased = phrased.strip('"\'`')

                # 2. Validation: Must be non-empty and within character length bounds
                if not phrased or len(phrased) < 10 or len(phrased) > 280:
                    logger.warning(f"Gemini phrasing rejected: length out of bounds ({len(phrased)})")
                    return controlled_question

                # 3. Validation: Must be a complete-looking sentence with at least 3 words
                words = phrased.split()
                if len(words) < 3:
                    logger.warning(f"Gemini phrasing rejected: sentence too short ({len(words)} words)")
                    return controlled_question

                # 4. Validation: Incomplete response without question mark must NOT be accepted or blindly patched
                if not phrased.endswith("?"):
                    logger.warning(
                        f"Gemini phrasing rejected: incomplete response without question mark in '{phrased}'"
                    )
                    return controlled_question

                # 5. Validation: Reject obvious truncation before question mark (e.g. '...?', dangling articles/conjunctions)
                if phrased.endswith("...?") or "..." in phrased:
                    logger.warning(f"Gemini phrasing rejected: detected ellipsis truncation in '{phrased}'")
                    return controlled_question

                dangling_pattern = r"\b(a|an|the|of|in|to|with|for|or|and|that|been|having)\s*\?$"
                if re.search(dangling_pattern, phrased, re.IGNORECASE):
                    logger.warning(f"Gemini phrasing rejected: dangling truncation detected in '{phrased}'")
                    return controlled_question

                # 6. Safety check: must not diagnose or prescribe
                if is_diagnostic_claim(phrased):
                    logger.warning(f"Gemini phrasing rejected: matched diagnostic claim in '{phrased}'")
                    return controlled_question

                forbidden_rx_patterns = [
                    r"\btake\s+(some|a|an|two|ibuprofen|tylenol|aspirin|antibiotic)",
                    r"\bprescrib",
                ]
                for pattern in forbidden_rx_patterns:
                    if re.search(pattern, phrased, re.IGNORECASE):
                        logger.warning(f"Gemini phrasing rejected: matched forbidden pattern '{pattern}'")
                        return controlled_question

                return phrased

            except Exception as exc:
                err_str = str(exc)
                if self._is_permanent_quota_error(err_str):
                    logger.error(f"Gemini API quota/prepayment credits depleted: {err_str}")
                    return controlled_question
                if ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str) and attempt == 0:
                    import time
                    m = re.search(r"retry in (\d+(?:\.\d+)?)s", err_str, re.IGNORECASE)
                    delay = min(int(float(m.group(1))) + 1, 15) if m else 5
                    logger.warning(f"Gemini phrasing transient 429 rate limit hit. Backing off for {delay}s...")
                    time.sleep(delay)
                    continue
                logger.warning(f"Gemini phrasing failed, falling back to controlled question: {exc.__class__.__name__}")
                return controlled_question

    def summarize_conversation(self, messages: List[Dict[str, str]]) -> str:
        """Summarizes dialogue history for clinician handoff."""
        try:
            client = self._get_client()
            conversation_text = "\n".join(
                f"{m.get('sender', 'user')}: {m.get('content', '')}" for m in messages
            )
            prompt = (
                "Summarize the patient's reported symptoms, timeline, and negative findings in 2-3 concise sentences:\n"
                f"{conversation_text}"
            )
            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            return response.text.strip()
        except Exception as exc:
            logger.warning(f"Gemini dialogue summarization failed: {exc.__class__.__name__}")
            return "Patient reported outpatient symptoms requiring clinical evaluation."
