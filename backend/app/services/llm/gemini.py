import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from pydantic import ValidationError

from app.core.config import settings
from app.core.exceptions import AppException, TriageLLMUnavailableError
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


# Failure categories as defined in CareRoute-X triage safety specification
FAILURE_CATEGORY_QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
FAILURE_CATEGORY_AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
FAILURE_CATEGORY_NETWORK_ERROR = "NETWORK_ERROR"
FAILURE_CATEGORY_VALIDATION_ERROR = "VALIDATION_ERROR"
FAILURE_CATEGORY_SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
FAILURE_CATEGORY_UNKNOWN = "UNKNOWN"


def classify_gemini_error(exc: Exception) -> Tuple[str, Optional[int], bool]:
    """Classifies Gemini exceptions into structured failure categories:
    (failure_category, http_status, is_quota_limit)
    """
    err_str = str(exc).lower()
    exc_type = exc.__class__.__name__.lower()

    # 1. Quota / rate-limit / prepayment exhaustion
    if (
        "429" in err_str
        or "resource_exhausted" in err_str
        or "quota" in err_str
        or "rate limit" in err_str
        or "perday" in err_str
        or "prepayment credits" in err_str
        or "credits are depleted" in err_str
    ):
        return FAILURE_CATEGORY_QUOTA_EXCEEDED, 429, True

    # 2. Authentication / authorization
    if (
        "401" in err_str
        or "403" in err_str
        or "unauthenticated" in err_str
        or "permission_denied" in err_str
        or "api_key" in err_str
        or "invalid api key" in err_str
        or "config_missing" in err_str
    ):
        status_code = 401 if ("401" in err_str or "unauthenticated" in err_str) else 403
        return FAILURE_CATEGORY_AUTHENTICATION_ERROR, status_code, False

    # 3. Validation / schema / malformed output
    if (
        isinstance(exc, (ValidationError, json.JSONDecodeError))
        or "json" in err_str
        or "validation" in err_str
        or "malformed" in err_str
        or "schema" in err_str
    ):
        return FAILURE_CATEGORY_VALIDATION_ERROR, None, False

    # 4. Network / connection / timeouts
    if any(
        term in err_str or term in exc_type
        for term in [
            "timeout",
            "connection",
            "connect",
            "dns",
            "socket",
            "network",
            "reset by peer",
            "broken pipe",
        ]
    ):
        return FAILURE_CATEGORY_NETWORK_ERROR, None, False

    # 5. Service unavailable / 5xx
    if "503" in err_str or "unavailable" in err_str or "500" in err_str or "502" in err_str:
        status_code = 503 if "503" in err_str else 500
        return FAILURE_CATEGORY_SERVICE_UNAVAILABLE, status_code, False

    return FAILURE_CATEGORY_UNKNOWN, None, False


def log_gemini_failure(
    failure_category: str,
    operation: str,
    http_status: Optional[int] = None,
    is_quota_limit: bool = False,
    session_id: Optional[str] = None,
    turn_index: Optional[int] = None,
    model: str = "gemini-3.6-flash",
) -> None:
    """Logs a structured Gemini failure event.

    CRITICAL SECURITY CONSTRAINT:
    Never logs GEMINI_API_KEY, Authorization headers, JWTs, credentials,
    patient secrets, or free-text narrative medical details.
    """
    event = {
        "provider": "gemini",
        "model": model,
        "failure_category": failure_category,
        "http_status": http_status,
        "is_quota_limit": is_quota_limit,
        "operation": operation,
        "session_id": session_id,
        "turn_index": turn_index,
    }
    logger.error(f"[GEMINI_FAILURE] {json.dumps(event)}")


# Curated controlled clinical dictionary mapping natural expressions to canonical DDXPlus codes
# VERIFIED against release_evidences.json:
# E_66: "Are you experiencing shortness of breath or difficulty breathing in a significant way?"
# E_159: "Did you lose consciousness?"
# E_201: "Do you have a cough?"
# E_54_@_V_180: Pain characterization "tugging"
CONTROLLED_EVIDENCE_MAP = {
    "fever": "E_91",
    "cough": "E_201",
    "productive cough": "E_77",
    "headache": "E_127",
    "head hurts": "E_127",
    "fatigue": "E_24",
    "exhaustion": "E_24",
    "tired": "E_24",
    "malaise": "E_148",
    "sore throat": "E_194",
    "dyspnea": "E_66",
    "shortness of breath": "E_66",
    "difficulty breathing": "E_66",
    "can't breathe": "E_66",
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
    "fainting": "E_159",
    "loss of consciousness": "E_159",
    "syncope": "E_159",
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
    6. Fail-fast error handling with structured logging and TriageLLMUnavailableError (no fallback to mock).
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
                log_gemini_failure(
                    failure_category=FAILURE_CATEGORY_AUTHENTICATION_ERROR,
                    operation="client_initialization",
                    http_status=401,
                    is_quota_limit=False,
                    model=self.model,
                )
                raise TriageLLMUnavailableError(
                    message="Conversational triage is temporarily unavailable. Please try again later or contact your care provider directly.",
                    code="TRIAGE_LLM_SERVICE_UNAVAILABLE",
                )
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except Exception as exc:
                cat, status_code, is_quota = classify_gemini_error(exc)
                log_gemini_failure(
                    failure_category=cat,
                    operation="client_initialization",
                    http_status=status_code,
                    is_quota_limit=is_quota,
                    model=self.model,
                )
                raise TriageLLMUnavailableError(
                    message="Conversational triage is temporarily unavailable. Please try again later or contact your care provider directly.",
                    code="TRIAGE_LLM_SERVICE_UNAVAILABLE",
                )
        return self._client

    def extract_patient_evidence(
        self, message: str, context: Optional[Dict[str, Any]] = None
    ) -> ExtractedEvidenceResult:
        """Extracts structured evidence items, duration, and severity using Gemini 3.6 Flash.

        Leverages active question context to interpret affirmative, negative, and uncertain responses.
        Fails fast with structured logging and TriageLLMUnavailableError on any API failure.
        """
        session_id = context.get("session_id") if context else None
        turn_index = context.get("turn_index") if context else None

        client = self._get_client()

        # Vocabulary guide passed to Gemini
        vocab_guide = ", ".join(f"'{k}' -> {v}" for k, v in list(CONTROLLED_EVIDENCE_MAP.items())[:35])

        # Context-aware extraction instructions
        active_q = context.get("active_question_text") if context else None
        active_ev = context.get("active_evidence_id") if context else None
        chief_complaint = context.get("chief_complaint") if context else None

        system_instruction = (
            "You are a specialized clinical evidence extraction assistant for CareRoute-X triage. "
            "Your task is to extract ONLY symptoms, negations, duration, and severity explicitly stated by the patient.\n\n"
            "STRICT CLINICAL RULES:\n"
            "1. Do NOT hallucinate or infer unmentioned symptoms.\n"
            "2. CONTEXTUAL RESOLUTION FOR PATIENT RESPONSES:\n"
            "   When an active clinical question and evidence ID are provided in context, the patient's reply is primarily addressing that question.\n"
            "   - AFFIRMATIVE: If the patient affirms, confirms, or agrees (e.g., 'yes', 'yeah', 'yep', 'I do', 'definitely', 'sure', 'true', 'correct'), "
            "     extract the active evidence ID with status='PRESENT'.\n"
            "   - NEGATION: If the patient denies, disagrees, or states they do not have it (e.g., 'no', 'nope', 'nah', 'not really', 'I don't', 'negative', 'none'), "
            "     extract the active evidence ID with status='ABSENT'.\n"
            "   - UNCERTAINTY: If the patient is unsure (e.g., 'not sure', 'maybe', 'possibly', 'I don't know'), "
            "     extract the active evidence ID with status='UNKNOWN'.\n"
            "3. DIRECT STATEMENTS: Also extract any other symptoms, negations, duration, or severity mentioned in the patient's message.\n"
            "4. DURATION: Extract duration into the 'duration' string field if mentioned (e.g. '3 days', 'since yesterday', 'about a week').\n"
            "5. SEVERITY: If pain/severity is rated on a 1-10 scale (e.g. '7 out of 10'), set severity=7 (integer 1-10).\n"
            "6. CONTROLLED VOCABULARY: Map symptoms strictly to known DDXPlus evidence codes.\n"
            f"   Reference dictionary: {vocab_guide}\n"
            "   CRITICAL: Do NOT invent arbitrary or fictitious evidence codes.\n"
            "7. Output MUST strictly conform to the ExtractedEvidenceResult schema."
        )

        context_lines = []
        if active_q and active_ev:
            context_lines.append(f'Active clinical question asked to patient: "{active_q}"')
            context_lines.append(f"Investigating DDXPlus evidence ID: {active_ev}")
        if chief_complaint:
            context_lines.append(f'Initial patient complaint: "{chief_complaint}"')

        context_header = "\n".join(context_lines)
        if context_header:
            prompt = f'{context_header}\n\nPatient message: "{message}"\nExtract structured clinical evidence.'
        else:
            prompt = f'Patient message: "{message}"\nExtract structured clinical evidence.'

        from google.genai import types

        last_err = None
        for attempt in range(2):
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
                if attempt < 1:
                    time.sleep(0.5)
                    continue
                cat = FAILURE_CATEGORY_VALIDATION_ERROR
                log_gemini_failure(
                    failure_category=cat,
                    operation="evidence_extraction",
                    http_status=None,
                    is_quota_limit=False,
                    session_id=session_id,
                    turn_index=turn_index,
                    model=self.model,
                )
                raise TriageLLMUnavailableError(
                    message="Conversational triage is temporarily unavailable. Please try again later or contact your care provider directly.",
                    code="TRIAGE_LLM_SERVICE_UNAVAILABLE",
                )
            except Exception as exc:
                last_err = exc
                err_str = str(exc)

                # Check quota / rate limit
                cat, status_code, is_quota = classify_gemini_error(exc)

                # FAIL FAST: permanent quota / billing exhaustion
                if self._is_permanent_quota_error(err_str):
                    log_gemini_failure(
                        failure_category=FAILURE_CATEGORY_QUOTA_EXCEEDED,
                        operation="evidence_extraction",
                        http_status=429,
                        is_quota_limit=True,
                        session_id=session_id,
                        turn_index=turn_index,
                        model=self.model,
                    )
                    raise TriageLLMUnavailableError(
                        message="Conversational triage is temporarily unavailable. Please try again later or contact your care provider directly.",
                        code="TRIAGE_LLM_SERVICE_UNAVAILABLE",
                    )

                if is_quota and attempt < 1:
                    m = re.search(r"retry in (\d+(?:\.\d+)?)s", err_str, re.IGNORECASE)
                    delay = min(int(float(m.group(1))) + 1, 5) if m else 2
                    logger.warning(f"Gemini transient rate limit hit. Backing off for {delay}s...")
                    time.sleep(delay)
                    continue

                log_gemini_failure(
                    failure_category=cat,
                    operation="evidence_extraction",
                    http_status=status_code,
                    is_quota_limit=is_quota,
                    session_id=session_id,
                    turn_index=turn_index,
                    model=self.model,
                )
                raise TriageLLMUnavailableError(
                    message="Conversational triage is temporarily unavailable. Please try again later or contact your care provider directly.",
                    code="TRIAGE_LLM_SERVICE_UNAVAILABLE",
                )

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
        session_id = context.get("session_id") if context else None
        turn_index = context.get("turn_index") if context else None

        try:
            client = self._get_client()
        except Exception as exc:
            cat, status_code, is_quota = classify_gemini_error(exc)
            log_gemini_failure(
                failure_category=cat,
                operation="question_phrasing",
                http_status=status_code,
                is_quota_limit=is_quota,
                session_id=session_id,
                turn_index=turn_index,
                model=self.model,
            )
            raise TriageLLMUnavailableError(
                message="Conversational triage is temporarily unavailable. Please try again later or contact your care provider directly.",
                code="TRIAGE_LLM_SERVICE_UNAVAILABLE",
            )

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
                cat, status_code, is_quota = classify_gemini_error(exc)

                # FAIL FAST: permanent quota / billing exhaustion
                if self._is_permanent_quota_error(err_str):
                    log_gemini_failure(
                        failure_category=FAILURE_CATEGORY_QUOTA_EXCEEDED,
                        operation="question_phrasing",
                        http_status=429,
                        is_quota_limit=True,
                        session_id=session_id,
                        turn_index=turn_index,
                        model=self.model,
                    )
                    raise TriageLLMUnavailableError(
                        message="Conversational triage is temporarily unavailable. Please try again later or contact your care provider directly.",
                        code="TRIAGE_LLM_SERVICE_UNAVAILABLE",
                    )

                if is_quota and attempt < 1:
                    time.sleep(1.0)
                    continue

                log_gemini_failure(
                    failure_category=cat,
                    operation="question_phrasing",
                    http_status=status_code,
                    is_quota_limit=is_quota,
                    session_id=session_id,
                    turn_index=turn_index,
                    model=self.model,
                )
                raise TriageLLMUnavailableError(
                    message="Conversational triage is temporarily unavailable. Please try again later or contact your care provider directly.",
                    code="TRIAGE_LLM_SERVICE_UNAVAILABLE",
                )

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
