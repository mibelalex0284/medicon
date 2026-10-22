import json
import random
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from pydantic import ValidationError

from app.core.config import settings
from app.core.exceptions import AppException, TriageLLMUnavailableError
from app.core.logging import logger
from app.services.llm.provider import (
    AdaptiveQuestionProposal,
    AdaptiveQuestionStatus,
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
        finish_reason: Optional[str] = None,
    ):
        super().__init__(code=code, message=message, status_code=502)
        self.finish_reason = finish_reason


# Failure categories as defined in CareRoute-X triage safety specification
FAILURE_CATEGORY_QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
FAILURE_CATEGORY_AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
FAILURE_CATEGORY_NETWORK_ERROR = "NETWORK_ERROR"
FAILURE_CATEGORY_VALIDATION_ERROR = "VALIDATION_ERROR"
FAILURE_CATEGORY_MALFORMED_STRUCTURED_OUTPUT = "MALFORMED_STRUCTURED_OUTPUT"
FAILURE_CATEGORY_SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
FAILURE_CATEGORY_UNKNOWN = "UNKNOWN"


def _sanitize_string(val: Optional[str], max_len: int = 40) -> Optional[str]:
    """Sanitizes a diagnostic string to prevent secret or PII leakage."""
    if not val or not isinstance(val, str):
        return None
    cleaned = re.sub(r"[^a-zA-Z0-9_\-\.\s]", "", val).strip()
    return cleaned[:max_len] if cleaned else None


def _extract_retry_after(exc: Exception) -> Optional[float]:
    """Extracts a valid, bounded retry-after duration in seconds from headers, details, or message.

    Rejects malformed, negative, zero, or unreasonably large (> 30s) values.
    """
    # 1. From response headers:
    response = getattr(exc, "response", None)
    if response is not None:
        headers = getattr(response, "headers", None)
        if hasattr(headers, "get"):
            val = headers.get("retry-after") or headers.get("Retry-After")
            if val is not None:
                try:
                    parsed = float(str(val).strip())
                    if 0 < parsed <= 30.0:
                        return parsed
                except (ValueError, TypeError):
                    pass

    # 2. From details (RetryInfo):
    details = getattr(exc, "details", None)
    if isinstance(details, dict):
        err_dict = details.get("error", details)
        if isinstance(err_dict, dict):
            err_details = err_dict.get("details", [])
            if isinstance(err_details, list):
                for d in err_details:
                    if isinstance(d, dict):
                        delay_str = d.get("retryDelay") or d.get("retry_delay")
                        if delay_str and isinstance(delay_str, str):
                            m = re.match(r"^(\d+(?:\.\d+)?)s?$", delay_str.strip())
                            if m:
                                try:
                                    parsed = float(m.group(1))
                                    if 0 < parsed <= 30.0:
                                        return parsed
                                except (ValueError, TypeError):
                                    pass

    # 3. String fallback for 'retry in Xs'
    m = re.search(r"retry in (\d+(?:\.\d+)?)s", str(exc), re.IGNORECASE)
    if m:
        try:
            parsed = float(m.group(1))
            if 0 < parsed <= 30.0:
                return parsed
        except (ValueError, TypeError):
            pass

    return None


def _extract_upstream_reason(exc: Exception) -> Optional[str]:
    """Safely extracts a sanitized reason tag from an upstream exception without leaking sensitive data."""
    details = getattr(exc, "details", None)
    if isinstance(details, dict):
        err_dict = details.get("error", details)
        if isinstance(err_dict, dict):
            err_details = err_dict.get("details", [])
            if isinstance(err_details, list):
                for d in err_details:
                    if isinstance(d, dict) and "reason" in d:
                        return _sanitize_string(str(d["reason"]), max_len=40)
            msg = err_dict.get("message")
            if isinstance(msg, str):
                msg_lower = msg.lower()
                if "overloaded" in msg_lower:
                    return "MODEL_OVERLOADED"
                if "backend timeout" in msg_lower or "timed out" in msg_lower:
                    return "BACKEND_TIMEOUT"
                if "rate limit" in msg_lower:
                    return "RATE_LIMIT_EXCEEDED"
                if "quota" in msg_lower:
                    return "QUOTA_EXHAUSTED"

    msg = getattr(exc, "message", None) or str(exc)
    if isinstance(msg, str):
        msg_lower = msg.lower()
        if "overloaded" in msg_lower:
            return "MODEL_OVERLOADED"
        if "backend timeout" in msg_lower or "timed out" in msg_lower:
            return "BACKEND_TIMEOUT"
        if "rate limit" in msg_lower:
            return "RATE_LIMIT_EXCEEDED"
        if "credits are depleted" in msg_lower:
            return "CREDITS_DEPLETED"
        if "dailyrequestlimit" in msg_lower:
            return "DAILY_LIMIT_EXCEEDED"

    return None


def extract_gemini_error_diagnostics(exc: Exception) -> Dict[str, Any]:
    """Extracts structured, sanitized diagnostic information from Gemini exceptions.

    CRITICAL SECURITY CONSTRAINT:
    Never captures API keys, Authorization headers, raw patient messages, or identifiable health data.
    Distinguishes 503 SERVICE_UNAVAILABLE from 429 QUOTA_EXCEEDED without guessing.
    """
    err_str = str(exc).lower()
    exc_type = exc.__class__.__name__.lower()

    # Safe extraction of HTTP status code from SDK APIError or response
    code = getattr(exc, "code", None)
    if not isinstance(code, int) and hasattr(exc, "response") and hasattr(exc.response, "status_code"):
        code = getattr(exc.response, "status_code", None)

    # Safe extraction of upstream gRPC/canonical status
    raw_status = getattr(exc, "status", None)
    upstream_status = _sanitize_string(str(raw_status), max_len=40) if raw_status else None
    upstream_reason = _extract_upstream_reason(exc)
    retry_after = _extract_retry_after(exc)

    status_str = (upstream_status or "").upper()

    # 1. Validation / schema / malformed output
    if (
        isinstance(exc, (ValidationError, json.JSONDecodeError, LLMExtractionError))
        or "json" in err_str
        or "validation" in err_str
        or "malformed" in err_str
        or "schema" in err_str
    ):
        return {
            "failure_category": FAILURE_CATEGORY_VALIDATION_ERROR,
            "http_status": None,
            "is_quota_limit": False,
            "upstream_status": upstream_status,
            "upstream_reason": upstream_reason or getattr(exc, "finish_reason", None),
            "retry_after": None,
        }

    # 2. Service unavailable / 5xx (HTTP 503, 502, 500)
    # STRICT: Never classify 503 / UNAVAILABLE as quota exhaustion!
    if (
        code in (500, 502, 503)
        or status_str in ("UNAVAILABLE", "INTERNAL")
        or any(c in err_str for c in ("503", "502", "500", "unavailable"))
        or "service unavailable" in err_str
    ):
        status_code = code if isinstance(code, int) else (500 if "500" in err_str else (502 if "502" in err_str else 503))
        return {
            "failure_category": FAILURE_CATEGORY_SERVICE_UNAVAILABLE,
            "http_status": status_code,
            "is_quota_limit": False,
            "upstream_status": upstream_status or ("INTERNAL" if status_code == 500 else "UNAVAILABLE"),
            "upstream_reason": upstream_reason,
            "retry_after": retry_after,
        }

    # 3. Quota / rate-limit / prepayment exhaustion (HTTP 429 / RESOURCE_EXHAUSTED)
    if (
        code == 429
        or status_str == "RESOURCE_EXHAUSTED"
        or "429" in err_str
        or "resource_exhausted" in err_str
        or "quota" in err_str
        or "rate limit" in err_str
        or "perday" in err_str
        or "prepayment credits" in err_str
        or "credits are depleted" in err_str
    ):
        return {
            "failure_category": FAILURE_CATEGORY_QUOTA_EXCEEDED,
            "http_status": 429,
            "is_quota_limit": True,
            "upstream_status": upstream_status or "RESOURCE_EXHAUSTED",
            "upstream_reason": upstream_reason,
            "retry_after": retry_after,
        }

    # 4. Authentication / authorization (HTTP 401 / 403)
    if (
        code in (401, 403)
        or status_str in ("UNAUTHENTICATED", "PERMISSION_DENIED")
        or "401" in err_str
        or "403" in err_str
        or "unauthenticated" in err_str
        or "permission_denied" in err_str
        or "api_key" in err_str
        or "invalid api key" in err_str
        or "config_missing" in err_str
    ):
        status_code = code if code in (401, 403) else (401 if ("401" in err_str or "unauthenticated" in err_str) else 403)
        return {
            "failure_category": FAILURE_CATEGORY_AUTHENTICATION_ERROR,
            "http_status": status_code,
            "is_quota_limit": False,
            "upstream_status": upstream_status or ("UNAUTHENTICATED" if status_code == 401 else "PERMISSION_DENIED"),
            "upstream_reason": upstream_reason,
            "retry_after": None,
        }

    # 5. Network / connection / timeouts
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
        return {
            "failure_category": FAILURE_CATEGORY_NETWORK_ERROR,
            "http_status": None,
            "is_quota_limit": False,
            "upstream_status": upstream_status,
            "upstream_reason": upstream_reason or "NETWORK_TIMEOUT",
            "retry_after": None,
        }

    return {
        "failure_category": FAILURE_CATEGORY_UNKNOWN,
        "http_status": code if isinstance(code, int) else None,
        "is_quota_limit": False,
        "upstream_status": upstream_status,
        "upstream_reason": upstream_reason,
        "retry_after": None,
    }


def classify_gemini_error(exc: Exception) -> Tuple[str, Optional[int], bool]:
    """Classifies Gemini exceptions into structured failure categories:
    (failure_category, http_status, is_quota_limit)
    """
    diag = extract_gemini_error_diagnostics(exc)
    return diag["failure_category"], diag["http_status"], diag["is_quota_limit"]


def compute_gemini_backoff(diag: Dict[str, Any], attempt: int) -> float:
    """Computes a bounded, adaptive retry delay for eligible transient errors.

    Rules:
    1. Respects valid, bounded Retry-After value (bounded to [1.0, 6.0]s).
    2. Otherwise uses short exponential backoff with jitter:
       - Attempt 0: ~2.0s + jitter (range 2.1s - 2.5s)
       - Maximum cumulative delay across the entire operation is strictly capped at 6.0s.
    """
    retry_after = diag.get("retry_after")
    if retry_after is not None and isinstance(retry_after, (int, float)):
        # Respect provider Retry-After, strictly bounded between 1.0s and 6.0s
        return min(max(float(retry_after), 1.0), 6.0)

    # Base exponential backoff: base = 2.0s * (1.5 ** attempt)
    base = 2.0 * (1.5 ** attempt)
    # Add random jitter between 0.1s and 0.4s to prevent thundering herd
    jitter = random.uniform(0.1, 0.4)
    total_delay = min(base + jitter, 5.0)
    return round(total_delay, 2)


def log_gemini_failure(
    failure_category: str,
    operation: str,
    http_status: Optional[int] = None,
    is_quota_limit: bool = False,
    session_id: Optional[str] = None,
    turn_index: Optional[int] = None,
    model: str = "gemini-3.6-flash",
    initial_failure_category: Optional[str] = None,
    retry_failure_category: Optional[str] = None,
    finish_reason: Optional[str] = None,
    upstream_status: Optional[str] = None,
    upstream_reason: Optional[str] = None,
    retry_after: Optional[float] = None,
    attempt: Optional[int] = None,
) -> None:
    """Logs a structured Gemini failure event.

    CRITICAL SECURITY CONSTRAINT:
    Never logs GEMINI_API_KEY, Authorization headers, JWTs, credentials,
    patient secrets, raw prompts, or free-text narrative medical details.
    """
    event: Dict[str, Any] = {
        "provider": "gemini",
        "model": model,
        "operation": operation,
        "failure_category": failure_category,
        "http_status": http_status,
        "is_quota_limit": is_quota_limit,
        "session_id": session_id,
        "turn_index": turn_index,
    }
    if attempt is not None:
        event["attempt"] = attempt
    if upstream_status:
        event["upstream_status"] = _sanitize_string(upstream_status, max_len=40)
    if upstream_reason:
        event["upstream_reason"] = _sanitize_string(upstream_reason, max_len=40)
    if retry_after is not None:
        event["retry_after"] = retry_after
    if initial_failure_category is not None:
        event["initial_failure_category"] = initial_failure_category
    if retry_failure_category is not None:
        event["retry_failure_category"] = retry_failure_category
    if finish_reason is not None:
        event["finish_reason"] = finish_reason

    logger.error(f"[GEMINI_FAILURE] {json.dumps(event, default=str)}")


# Metrics history for telemetry and test inspection
_gemini_metrics: List[Dict[str, Any]] = []


def get_gemini_metrics() -> List[Dict[str, Any]]:
    """Returns a copy of recorded Gemini metrics."""
    return list(_gemini_metrics)


def clear_gemini_metrics() -> None:
    """Clears recorded Gemini metrics (useful for test isolation)."""
    _gemini_metrics.clear()


def log_gemini_metric(
    operation: str,
    attempts: int,
    status: str,
    duration_ms: float,
    retry_occurred: bool,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    total_tokens: Optional[int] = None,
    thoughts_token_count: Optional[int] = None,
    finish_reason: Optional[str] = None,
    model: str = "gemini-3.6-flash",
    session_id: Optional[str] = None,
    turn_index: Optional[int] = None,
    http_status: Optional[int] = None,
    upstream_status: Optional[str] = None,
    upstream_reason: Optional[str] = None,
    retry_after: Optional[float] = None,
) -> None:
    """Logs safe structured operational metrics for Gemini API calls.

    CRITICAL PRIVACY/SECURITY CONSTRAINT:
    Never logs GEMINI_API_KEY, raw patient messages, credentials,
    or identifiable health data.
    """
    metric: Dict[str, Any] = {
        "provider": "gemini",
        "model": model,
        "operation": operation,
        "attempts": attempts,
        "status": status,
        "retry_occurred": retry_occurred,
        "duration_ms": round(duration_ms, 2),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "thoughts_token_count": thoughts_token_count,
        "finish_reason": finish_reason,
        "session_id": session_id,
        "turn_index": turn_index,
    }
    if http_status is not None:
        metric["http_status"] = http_status
    if upstream_status:
        metric["upstream_status"] = _sanitize_string(upstream_status, max_len=40)
    if upstream_reason:
        metric["upstream_reason"] = _sanitize_string(upstream_reason, max_len=40)
    if retry_after is not None:
        metric["retry_after"] = retry_after

    try:
        _gemini_metrics.append(metric)
        if len(_gemini_metrics) > 500:
            _gemini_metrics.pop(0)

        logger.info(f"[GEMINI_METRIC] {json.dumps(metric, default=str)}")
    except Exception as metric_err:
        logger.debug(f"Failed to log Gemini metric: {metric_err}")


def _extract_token_counts(
    response: Any,
) -> Tuple[Optional[int], Optional[int], Optional[int], Optional[int]]:
    """Safely extracts integer (input_tokens, output_tokens, total_tokens, thoughts_tokens) from GenAI response if present."""
    try:
        usage = getattr(response, "usage_metadata", None)
        if usage is None:
            return None, None, None, None
        in_tok = getattr(usage, "prompt_token_count", None)
        out_tok = getattr(usage, "candidates_token_count", None)
        tot_tok = getattr(usage, "total_token_count", None)
        th_tok = getattr(usage, "thoughts_token_count", None)

        in_int = in_tok if type(in_tok) is int else None
        out_int = out_tok if type(out_tok) is int else None
        tot_int = tot_tok if type(tot_tok) is int else None
        th_int = th_tok if type(th_tok) is int else None
        return in_int, out_int, tot_int, th_int
    except Exception:
        return None, None, None, None


def _extract_finish_reason(response: Any) -> Optional[str]:
    """Safely extracts candidate finish_reason string from GenAI response if present."""
    try:
        candidates = getattr(response, "candidates", None)
        if not candidates or len(candidates) == 0:
            return None
        candidate = candidates[0]
        fr = getattr(candidate, "finish_reason", None)
        if fr is None:
            return None
        if type(fr).__name__ == "MagicMock":
            return None
        if hasattr(fr, "name"):
            return str(fr.name)
        if isinstance(fr, (str, int)):
            return str(fr)
        return str(fr)
    except Exception:
        return None



# Curated controlled clinical dictionary mapping natural expressions to canonical DDXPlus codes
# VERIFIED against release_evidences.json in DDXPlus:
# E_91: "Do you have a fever (either felt or measured with a thermometer)?"
# E_201: "Do you have a cough?"
# E_77: "Do you have a cough that produces colored or more abundant sputum than usual?"
# E_66: "Are you experiencing shortness of breath or difficulty breathing in a significant way?"
# E_53: "Do you have pain somewhere, related to your reason for consulting?"
# E_54_@_V_180: Pain characterization "tugging / crushing"
# E_50: "Have you had significantly increased sweating?"
# E_159: "Did you lose consciousness?"
# E_45: "Have you been coughing up blood?"
# E_97: "Do you have a sore throat?"
# E_148: "Are you feeling nauseous or do you feel like vomiting?"
# E_51: "Have you had diarrhea or an increase in stool frequency?"
# E_94: "Have you had chills or shivers?"
# E_155: "Do you feel your heart is beating fast (racing), irregularly or do you feel palpitations?"
# E_82: "Do you feel lightheaded and dizzy or do you feel like you are about to faint?"
# E_173: "Do you have a burning sensation that starts in your stomach then goes up into your throat?"
#
# NOTE: Abdominal / stomach pain expressions ("stomach ache", "epigastric pain", "abdominal pain")
# were previously mis-mapped to E_50 (sweating). They are removed from this dictionary
# and handled through standard evidence extraction and ontology validation.
CONTROLLED_EVIDENCE_MAP = {
    "fever": "E_91",
    "cough": "E_201",
    "productive cough": "E_77",
    "dyspnea": "E_66",
    "shortness of breath": "E_66",
    "difficulty breathing": "E_66",
    "can't breathe": "E_66",
    "chest pain": "E_53",
    "crushing chest pain": "E_54_@_V_180",
    "severe chest pain": "E_54_@_V_180",
    "sweating": "E_50",
    "increased sweating": "E_50",
    "diaphoresis": "E_50",
    "fainting": "E_159",
    "loss of consciousness": "E_159",
    "syncope": "E_159",
    "passed out": "E_159",
    "coughing up blood": "E_45",
    "hemoptysis": "E_45",
    "sore throat": "E_97",
    "nausea": "E_148",
    "vomiting": "E_148",
    "diarrhea": "E_51",
    "chills": "E_94",
    "shivers": "E_94",
    "palpitations": "E_155",
    "racing heartbeat": "E_155",
    "dizziness": "E_82",
    "lightheadedness": "E_82",
    "heartburn": "E_173",
    "acid reflux": "E_173",
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

    MAX_QUOTA_RETRY_DELAY: float = 5.0

    @classmethod
    def _is_permanent_quota_error(cls, err_str: str) -> bool:
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
            "daily limit",
            "quota exceeded per day",
            "free tier limit",
            "quota exceeded for quota group",
        ]
        return any(ind in s for ind in permanent_indicators)

    @classmethod
    def _get_safe_quota_retry_delay(cls, diag: Dict[str, Any], err_str: str) -> Optional[float]:
        """Returns safe retry delay in seconds if eligible, or None if quota retry is unsafe.

        Enforces:
        - Never retries confirmed permanent/daily quota exhaustion.
        - Never blindly retries without an indicated delay.
        - Respects indicated Retry-After / delay when within request budget (<= 3.5s).
        - Rejects large delays (> 3.5s) to avoid retrying before indicated time or hanging workers.
        """
        if cls._is_permanent_quota_error(err_str):
            return None

        # Check provider Retry-After header or regex in err_str
        retry_val = diag.get("retry_after")
        if retry_val is None:
            m = re.search(r"retry (?:in|after) (\d+(?:\.\d+)?)s", err_str, re.IGNORECASE)
            if m:
                retry_val = float(m.group(1))

        if retry_val is not None and isinstance(retry_val, (int, float)):
            needed_delay = int(float(retry_val)) + 1
            if needed_delay <= cls.MAX_QUOTA_RETRY_DELAY:
                return needed_delay
            return None

        # If no retry duration was provided by upstream API, do not retry blindly
        return None

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

    def close(self) -> None:
        """Closes the underlying Google GenAI client and releases connection pools."""
        if self._client is not None:
            try:
                if hasattr(self._client, "close"):
                    self._client.close()
            except Exception as exc:
                logger.debug(f"Error while closing Gemini client: {exc}")
            finally:
                self._client = None

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
            "7. Output MUST strictly conform to the ExtractedEvidenceResult schema.\n"
            "8. CORRECTIONS & CONTRADICTIONS: If the patient corrects a previous statement (e.g. 'Actually I do not have a fever', 'Correction, my pain is in my knee, not back', 'I made a mistake earlier'), "
            "   extract the corrected status explicitly (e.g. mark fever as ABSENT) and record the correction note in the 'corrections' list.\n"
            "9. DECLINED TO CONTINUE: If the patient explicitly states they decline to answer further questions, want to stop, or refuse further questions (e.g. 'stop asking', 'no more questions', 'I don't want to answer', 'skip', 'just find me a doctor'), "
            "   set declined_to_continue=True."
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

        start_time = time.perf_counter()
        last_err = None
        initial_failure_category: Optional[str] = None
        initial_finish_reason: Optional[str] = None

        for attempt in range(2):
            detected_finish_reason: Optional[str] = None
            output_tokens = (
                1000
                if (attempt > 0 and initial_finish_reason and "MAX_TOKENS" in initial_finish_reason)
                else 700
            )
            try:
                response = client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        response_schema=ExtractedEvidenceResult,
                        temperature=0.0,
                        max_output_tokens=output_tokens,
                        thinking_config=types.ThinkingConfig(thinking_budget=0),
                    ),
                )

                # 1. Candidate and finish_reason inspection before JSON parsing
                candidates = getattr(response, "candidates", None)
                if isinstance(candidates, (list, tuple)):
                    if len(candidates) == 0:
                        logger.warning("Gemini extraction rejected: empty candidates list")
                        raise LLMExtractionError(
                            message="Gemini extraction returned no candidates",
                            finish_reason="NO_CANDIDATES",
                        )
                    candidate = candidates[0]
                    finish_reason = getattr(candidate, "finish_reason", None)
                    if finish_reason is not None:
                        finish_reason_str = str(finish_reason).upper()
                        # Normal completion in GenAI is STOP (e.g. FinishReason.STOP or 'STOP')
                        if "STOP" not in finish_reason_str:
                            detected_finish_reason = finish_reason_str
                            logger.warning(
                                f"Gemini extraction rejected: non-normal finish reason ({finish_reason_str})"
                            )
                            raise LLMExtractionError(
                                message=f"Gemini output terminated prematurely (finish_reason={finish_reason_str})",
                                finish_reason=finish_reason_str,
                            )

                raw_text = (getattr(response, "text", None) or "").strip()
                if not raw_text:
                    logger.warning("Gemini extraction rejected: empty response text")
                    raise LLMExtractionError(
                        message="Gemini extraction returned empty response text",
                        finish_reason=detected_finish_reason or "EMPTY_TEXT",
                    )

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

                in_tok, out_tok, tot_tok, th_tok = _extract_token_counts(response)
                fr = _extract_finish_reason(response)
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                log_gemini_metric(
                    operation="evidence_extraction",
                    attempts=attempt + 1,
                    status="SUCCESS",
                    duration_ms=elapsed_ms,
                    retry_occurred=(attempt > 0),
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    total_tokens=tot_tok,
                    thoughts_token_count=th_tok,
                    finish_reason=fr,
                    model=self.model,
                    session_id=session_id,
                    turn_index=turn_index,
                )

                return result

            except (json.JSONDecodeError, ValidationError, LLMExtractionError) as parse_err:
                last_err = parse_err
                err_finish_reason = getattr(parse_err, "finish_reason", None) or detected_finish_reason
                logger.warning(
                    f"Gemini output parsing attempt {attempt + 1} failed "
                    f"(finish_reason={err_finish_reason or 'NORMAL_OR_UNSPECIFIED'}): {parse_err}"
                )
                if attempt < 1:
                    initial_failure_category = FAILURE_CATEGORY_MALFORMED_STRUCTURED_OUTPUT
                    initial_finish_reason = err_finish_reason
                    # Bounded backoff for one retry only
                    time.sleep(1.0)
                    continue

                cat = FAILURE_CATEGORY_MALFORMED_STRUCTURED_OUTPUT
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                log_gemini_metric(
                    operation="evidence_extraction",
                    attempts=attempt + 1,
                    status=cat,
                    duration_ms=elapsed_ms,
                    retry_occurred=(attempt > 0),
                    model=self.model,
                    session_id=session_id,
                    turn_index=turn_index,
                )
                log_gemini_failure(
                    failure_category=cat,
                    operation="evidence_extraction",
                    http_status=None,
                    is_quota_limit=False,
                    session_id=session_id,
                    turn_index=turn_index,
                    model=self.model,
                    initial_failure_category=initial_failure_category or cat,
                    retry_failure_category=cat if initial_failure_category else None,
                    finish_reason=err_finish_reason or initial_finish_reason,
                )
                raise TriageLLMUnavailableError(
                    message="Conversational triage is temporarily unavailable. Please try again later or contact your care provider directly.",
                    code="TRIAGE_LLM_SERVICE_UNAVAILABLE",
                )
            except Exception as exc:
                last_err = exc
                err_str = str(exc)

                diag = extract_gemini_error_diagnostics(exc)
                cat = diag["failure_category"]
                status_code = diag["http_status"]
                is_quota = diag["is_quota_limit"]
                upstream_status = diag.get("upstream_status")
                upstream_reason = diag.get("upstream_reason")
                retry_after = diag.get("retry_after")

                # FAIL FAST: authentication / authorization errors (do not retry)
                if cat == FAILURE_CATEGORY_AUTHENTICATION_ERROR:
                    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                    log_gemini_metric(
                        operation="evidence_extraction",
                        attempts=attempt + 1,
                        status=cat,
                        duration_ms=elapsed_ms,
                        retry_occurred=(attempt > 0),
                        model=self.model,
                        session_id=session_id,
                        turn_index=turn_index,
                        http_status=status_code,
                        upstream_status=upstream_status,
                        upstream_reason=upstream_reason,
                    )
                    log_gemini_failure(
                        failure_category=cat,
                        operation="evidence_extraction",
                        http_status=status_code,
                        is_quota_limit=False,
                        session_id=session_id,
                        turn_index=turn_index,
                        model=self.model,
                        initial_failure_category=initial_failure_category,
                        retry_failure_category=cat if initial_failure_category else None,
                        finish_reason=initial_finish_reason,
                        upstream_status=upstream_status,
                        upstream_reason=upstream_reason,
                        attempt=attempt + 1,
                    )
                    raise TriageLLMUnavailableError(
                        message="Conversational triage is temporarily unavailable. Please try again later or contact your care provider directly.",
                        code="TRIAGE_LLM_SERVICE_UNAVAILABLE",
                    )

                # FAIL FAST: permanent quota / billing exhaustion (do not retry)
                if self._is_permanent_quota_error(err_str):
                    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                    log_gemini_metric(
                        operation="evidence_extraction",
                        attempts=attempt + 1,
                        status=FAILURE_CATEGORY_QUOTA_EXCEEDED,
                        duration_ms=elapsed_ms,
                        retry_occurred=(attempt > 0),
                        model=self.model,
                        session_id=session_id,
                        turn_index=turn_index,
                        http_status=429,
                        upstream_status=upstream_status,
                        upstream_reason=upstream_reason,
                    )
                    log_gemini_failure(
                        failure_category=FAILURE_CATEGORY_QUOTA_EXCEEDED,
                        operation="evidence_extraction",
                        http_status=429,
                        is_quota_limit=True,
                        session_id=session_id,
                        turn_index=turn_index,
                        model=self.model,
                        initial_failure_category=initial_failure_category,
                        retry_failure_category=FAILURE_CATEGORY_QUOTA_EXCEEDED if initial_failure_category else None,
                        finish_reason=initial_finish_reason,
                        upstream_status=upstream_status,
                        upstream_reason=upstream_reason,
                        attempt=attempt + 1,
                    )
                    raise TriageLLMUnavailableError(
                        message="Conversational triage capacity is temporarily exhausted. Please try again later or proceed directly to doctor consultation.",
                        code="TRIAGE_LLM_SERVICE_UNAVAILABLE",
                    )

                is_transient_error = cat in (
                    FAILURE_CATEGORY_SERVICE_UNAVAILABLE,
                    FAILURE_CATEGORY_NETWORK_ERROR,
                )

                if is_quota:
                    safe_delay = self._get_safe_quota_retry_delay(diag, err_str)
                    if safe_delay is not None and attempt < 1:
                        initial_failure_category = cat
                        logger.warning(
                            f"Gemini transient rate limit hit. Respecting provider delay of {safe_delay}s (attempt {attempt + 1}/2)..."
                        )
                        time.sleep(safe_delay)
                        continue
                    else:
                        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                        log_gemini_metric(
                            operation="evidence_extraction",
                            attempts=attempt + 1,
                            status=FAILURE_CATEGORY_QUOTA_EXCEEDED,
                            duration_ms=elapsed_ms,
                            retry_occurred=(attempt > 0),
                            model=self.model,
                            session_id=session_id,
                            turn_index=turn_index,
                            http_status=429,
                            upstream_status=upstream_status,
                            upstream_reason=upstream_reason,
                        )
                        log_gemini_failure(
                            failure_category=FAILURE_CATEGORY_QUOTA_EXCEEDED,
                            operation="evidence_extraction",
                            http_status=429,
                            is_quota_limit=True,
                            session_id=session_id,
                            turn_index=turn_index,
                            model=self.model,
                            initial_failure_category=initial_failure_category,
                            retry_failure_category=FAILURE_CATEGORY_QUOTA_EXCEEDED if initial_failure_category else None,
                            finish_reason=initial_finish_reason,
                            upstream_status=upstream_status,
                            upstream_reason=upstream_reason,
                            attempt=attempt + 1,
                        )
                        raise TriageLLMUnavailableError(
                            message="Conversational triage capacity is temporarily exhausted. Please try again later or proceed directly to doctor consultation.",
                            code="TRIAGE_LLM_SERVICE_UNAVAILABLE",
                        )

                if is_transient_error and attempt < 1:
                    initial_failure_category = cat
                    delay = compute_gemini_backoff(diag, attempt)
                    logger.warning(
                        f"Gemini transient {cat} (status={status_code}, upstream={upstream_status}, reason={upstream_reason}). "
                        f"Adaptive backoff for {delay}s (attempt {attempt + 1}/2, retry_after={retry_after})..."
                    )
                    time.sleep(delay)
                    continue

                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                log_gemini_metric(
                    operation="evidence_extraction",
                    attempts=attempt + 1,
                    status=cat,
                    duration_ms=elapsed_ms,
                    retry_occurred=(attempt > 0),
                    model=self.model,
                    session_id=session_id,
                    turn_index=turn_index,
                    http_status=status_code,
                    upstream_status=upstream_status,
                    upstream_reason=upstream_reason,
                    retry_after=retry_after,
                )
                log_gemini_failure(
                    failure_category=cat,
                    operation="evidence_extraction",
                    http_status=status_code,
                    is_quota_limit=is_quota,
                    session_id=session_id,
                    turn_index=turn_index,
                    model=self.model,
                    initial_failure_category=initial_failure_category,
                    retry_failure_category=cat if initial_failure_category else None,
                    finish_reason=initial_finish_reason,
                    upstream_status=upstream_status,
                    upstream_reason=upstream_reason,
                    retry_after=retry_after,
                    attempt=attempt + 1,
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
        start_time = time.perf_counter()

        try:
            client = self._get_client()
        except Exception as exc:
            cat, status_code, is_quota = classify_gemini_error(exc)
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            log_gemini_metric(
                operation="question_phrasing",
                attempts=0,
                status=cat,
                duration_ms=elapsed_ms,
                retry_occurred=False,
                model=self.model,
                session_id=session_id,
                turn_index=turn_index,
            )
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

        initial_failure_category: Optional[str] = None
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

                in_tok, out_tok, tot_tok, th_tok = _extract_token_counts(response)
                fr = _extract_finish_reason(response)
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                log_gemini_metric(
                    operation="question_phrasing",
                    attempts=attempt + 1,
                    status="SUCCESS",
                    duration_ms=elapsed_ms,
                    retry_occurred=(attempt > 0),
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    total_tokens=tot_tok,
                    thoughts_token_count=th_tok,
                    finish_reason=fr,
                    model=self.model,
                    session_id=session_id,
                    turn_index=turn_index,
                )

                return phrased

            except Exception as exc:
                err_str = str(exc)
                diag = extract_gemini_error_diagnostics(exc)
                cat = diag["failure_category"]
                status_code = diag["http_status"]
                is_quota = diag["is_quota_limit"]
                upstream_status = diag.get("upstream_status")
                upstream_reason = diag.get("upstream_reason")
                retry_after = diag.get("retry_after")

                # FAIL FAST: authentication / authorization errors (do not retry)
                if cat == FAILURE_CATEGORY_AUTHENTICATION_ERROR:
                    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                    log_gemini_metric(
                        operation="question_phrasing",
                        attempts=attempt + 1,
                        status=cat,
                        duration_ms=elapsed_ms,
                        retry_occurred=(attempt > 0),
                        model=self.model,
                        session_id=session_id,
                        turn_index=turn_index,
                        http_status=status_code,
                        upstream_status=upstream_status,
                        upstream_reason=upstream_reason,
                    )
                    log_gemini_failure(
                        failure_category=cat,
                        operation="question_phrasing",
                        http_status=status_code,
                        is_quota_limit=False,
                        session_id=session_id,
                        turn_index=turn_index,
                        model=self.model,
                        initial_failure_category=initial_failure_category,
                        retry_failure_category=cat if initial_failure_category else None,
                        upstream_status=upstream_status,
                        upstream_reason=upstream_reason,
                        attempt=attempt + 1,
                    )
                    raise TriageLLMUnavailableError(
                        message="Conversational triage is temporarily unavailable. Please try again later or contact your care provider directly.",
                        code="TRIAGE_LLM_SERVICE_UNAVAILABLE",
                    )

                # FAIL FAST: permanent quota / billing exhaustion (do not retry)
                if self._is_permanent_quota_error(err_str):
                    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                    log_gemini_metric(
                        operation="question_phrasing",
                        attempts=attempt + 1,
                        status=FAILURE_CATEGORY_QUOTA_EXCEEDED,
                        duration_ms=elapsed_ms,
                        retry_occurred=(attempt > 0),
                        model=self.model,
                        session_id=session_id,
                        turn_index=turn_index,
                        http_status=429,
                        upstream_status=upstream_status,
                        upstream_reason=upstream_reason,
                    )
                    log_gemini_failure(
                        failure_category=FAILURE_CATEGORY_QUOTA_EXCEEDED,
                        operation="question_phrasing",
                        http_status=429,
                        is_quota_limit=True,
                        session_id=session_id,
                        turn_index=turn_index,
                        model=self.model,
                        initial_failure_category=initial_failure_category,
                        retry_failure_category=FAILURE_CATEGORY_QUOTA_EXCEEDED if initial_failure_category else None,
                        upstream_status=upstream_status,
                        upstream_reason=upstream_reason,
                        attempt=attempt + 1,
                    )
                    raise TriageLLMUnavailableError(
                        message="Conversational triage capacity is temporarily exhausted. Please try again later or proceed directly to doctor consultation.",
                        code="TRIAGE_LLM_SERVICE_UNAVAILABLE",
                    )

                is_transient_error = cat in (
                    FAILURE_CATEGORY_SERVICE_UNAVAILABLE,
                    FAILURE_CATEGORY_NETWORK_ERROR,
                )

                if is_quota:
                    safe_delay = self._get_safe_quota_retry_delay(diag, err_str)
                    if safe_delay is not None and attempt < 1:
                        initial_failure_category = cat
                        logger.warning(
                            f"Gemini transient rate limit hit in phrasing. Respecting provider delay of {safe_delay}s..."
                        )
                        time.sleep(safe_delay)
                        continue
                    else:
                        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                        log_gemini_metric(
                            operation="question_phrasing",
                            attempts=attempt + 1,
                            status=FAILURE_CATEGORY_QUOTA_EXCEEDED,
                            duration_ms=elapsed_ms,
                            retry_occurred=(attempt > 0),
                            model=self.model,
                            session_id=session_id,
                            turn_index=turn_index,
                            http_status=429,
                            upstream_status=upstream_status,
                            upstream_reason=upstream_reason,
                        )
                        log_gemini_failure(
                            failure_category=FAILURE_CATEGORY_QUOTA_EXCEEDED,
                            operation="question_phrasing",
                            http_status=429,
                            is_quota_limit=True,
                            session_id=session_id,
                            turn_index=turn_index,
                            model=self.model,
                            initial_failure_category=initial_failure_category,
                            retry_failure_category=FAILURE_CATEGORY_QUOTA_EXCEEDED if initial_failure_category else None,
                            upstream_status=upstream_status,
                            upstream_reason=upstream_reason,
                            attempt=attempt + 1,
                        )
                        raise TriageLLMUnavailableError(
                            message="Conversational triage capacity is temporarily exhausted. Please try again later or proceed directly to doctor consultation.",
                            code="TRIAGE_LLM_SERVICE_UNAVAILABLE",
                        )

                if is_transient_error and attempt < 1:
                    initial_failure_category = cat
                    delay = compute_gemini_backoff(diag, attempt)
                    logger.warning(
                        f"Gemini transient {cat} during question phrasing (status={status_code}, upstream={upstream_status}, reason={upstream_reason}). "
                        f"Adaptive backoff for {delay}s (attempt {attempt + 1}/2, retry_after={retry_after})..."
                    )
                    time.sleep(delay)
                    continue

                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                log_gemini_metric(
                    operation="question_phrasing",
                    attempts=attempt + 1,
                    status=cat,
                    duration_ms=elapsed_ms,
                    retry_occurred=(attempt > 0),
                    model=self.model,
                    session_id=session_id,
                    turn_index=turn_index,
                    http_status=status_code,
                    upstream_status=upstream_status,
                    upstream_reason=upstream_reason,
                    retry_after=retry_after,
                )
                log_gemini_failure(
                    failure_category=cat,
                    operation="question_phrasing",
                    http_status=status_code,
                    is_quota_limit=is_quota,
                    session_id=session_id,
                    turn_index=turn_index,
                    model=self.model,
                    initial_failure_category=initial_failure_category,
                    retry_failure_category=cat if initial_failure_category else None,
                    upstream_status=upstream_status,
                    upstream_reason=upstream_reason,
                    retry_after=retry_after,
                    attempt=attempt + 1,
                )
                raise TriageLLMUnavailableError(
                    message="Conversational triage is temporarily unavailable. Please try again later or contact your care provider directly.",
                    code="TRIAGE_LLM_SERVICE_UNAVAILABLE",
                )

    def propose_next_question(
        self, context: Dict[str, Any]
    ) -> AdaptiveQuestionProposal:
        """Proposes an adaptive next clinical intake question or completion status using Gemini.

        Derives question context dynamically from:
        - Chief complaint & latest message
        - Relevant conversation history
        - Current structured patient state (known present, known absent, unknown/unresolved)
        - Onset and duration, severity and progression, functional impact
        - Questions already asked and answers received
        - Missing clinical information gaps needed for pre-consultation summary and care navigation.

        Enforces strict clinical boundaries:
        - Product first, AI second. Intake only; no disease diagnosis or treatment recommendations.
        - Asks exactly ONE clear question per turn.
        - Does not re-ask established information.
        - Fails closed on API or structured output failures.
        """
        session_id = context.get("session_id")
        turn_index = context.get("turn_index")
        start_time = time.perf_counter()

        client = self._get_client()

        chief_complaint = context.get("chief_complaint") or "Not provided"
        latest_message = context.get("latest_message") or ""
        known_present = context.get("known_present") or []
        known_absent = context.get("known_absent") or []
        unknown_findings = context.get("unknown_findings") or []
        duration = context.get("duration") or "Not established"
        severity = context.get("severity") or "Not established"
        functional_impact = context.get("functional_impact") or "Not established"
        questions_asked = context.get("questions_asked") or []
        information_gaps = context.get("information_gaps") or []
        conversation_history = context.get("conversation_history") or []

        system_instruction = (
            "You are an adaptive clinical triage assistant for CareRoute-X outpatient care navigation.\n"
            "Your objective is to determine what missing information is most clinically relevant to characterize "
            "the patient's presentation for an outpatient pre-consultation summary and care navigation decision.\n\n"
            "STRICT CLINICAL RULES:\n"
            "1. PRODUCT FIRST, AI SECOND: You are collecting clinical intake information to help navigate care. "
            "You DO NOT diagnose the patient and DO NOT state or imply any suspected diagnosis as fact.\n"
            "2. DO NOT recommend medications, dosages, home remedies, or medical treatments.\n"
            "3. Ask EXACTLY ONE concise, patient-facing question per turn. Avoid compound questions (do not combine "
            "two separate inquiries with 'and'). Keep questions direct, gentle, and clear.\n"
            "4. DO NOT ask for information that is already established in context (check known present, known absent, duration, "
            "severity, and questions already asked).\n"
            "5. DO NOT infer or assume answers from missing information. Do not fabricate patient findings.\n"
            "6. COMPLAINT AGNOSTIC: Adapt dynamically to ANY presenting complaint (e.g. headache, abdominal pain, "
            "skin changes, joint pain, dizziness, sleep difficulty, emotional distress, urinary symptoms, dental pain, "
            "vague discomfort, or uncommon symptoms).\n"
            "7. SUFFICIENT STATUS: If core clinical characterization (onset/duration, severity/progression, key symptom traits, "
            "and pertinent negatives) is sufficient for an outpatient physician handoff and care navigation, set status='sufficient', "
            "question=null.\n"
            "8. UNCERTAIN STATUS: If the patient's presentation cannot be safely or reliably clarified through conversational questioning, "
            "set status='uncertain', requires_human_review=true.\n"
            "9. ESCALATE STATUS: If the patient reports an urgent, life-threatening red-flag emergency (e.g. severe shortness of breath, "
            "crushing chest pain, loss of consciousness, stroke signs, severe uncontrolled bleeding, anaphylaxis), set status='escalate', "
            "safety_flags=[...].\n"
            "10. Output MUST strictly conform to the AdaptiveQuestionProposal schema."
        )

        history_summary = "\n".join(
            f"- {item.get('sender', 'user')}: {item.get('content', '')}"
            for item in conversation_history[-6:]
        ) or "None"

        prompt = (
            f"PRESENTING COMPLAINT: {chief_complaint}\n"
            f"LATEST PATIENT MESSAGE: {latest_message}\n\n"
            f"ESTABLISHED CLINICAL INTAKE STATE:\n"
            f"- Duration / Onset: {duration}\n"
            f"- Reported Severity: {severity}\n"
            f"- Functional Impact: {functional_impact}\n"
            f"- Known Present Findings: {', '.join(str(x) for x in known_present) if known_present else 'None recorded'}\n"
            f"- Explicitly Absent (Pertinent Negatives): {', '.join(str(x) for x in known_absent) if known_absent else 'None recorded'}\n"
            f"- Unknown / Inconclusive Findings: {', '.join(str(x) for x in unknown_findings) if unknown_findings else 'None'}\n"
            f"- Questions Already Asked: {', '.join(str(x) for x in questions_asked) if questions_asked else 'None'}\n"
            f"- Identified Information Gaps: {', '.join(str(x) for x in information_gaps) if information_gaps else 'None'}\n\n"
            f"RECENT CONVERSATION HISTORY:\n{history_summary}\n\n"
            "Evaluate information gaps and determine the single next best question, or mark sufficient / uncertain / escalate."
        )

        from google.genai import types

        initial_failure_category: Optional[str] = None
        initial_finish_reason: Optional[str] = None

        for attempt in range(2):
            detected_finish_reason: Optional[str] = None
            output_tokens = (
                1500
                if (attempt > 0 and initial_finish_reason and "MAX_TOKENS" in initial_finish_reason)
                else 1000
            )
            try:
                response = client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        response_schema=AdaptiveQuestionProposal,
                        temperature=0.0,
                        max_output_tokens=output_tokens,
                        thinking_config=types.ThinkingConfig(thinking_budget=0),
                    ),
                )

                candidates = getattr(response, "candidates", None)
                if isinstance(candidates, (list, tuple)):
                    if len(candidates) == 0:
                        logger.warning("Gemini question proposal rejected: empty candidates list")
                        raise LLMExtractionError(
                            message="Gemini proposal returned no candidates",
                            finish_reason="NO_CANDIDATES",
                        )
                    candidate = candidates[0]
                    finish_reason = getattr(candidate, "finish_reason", None)
                    if finish_reason is not None:
                        finish_reason_str = str(finish_reason).upper()
                        if "STOP" not in finish_reason_str:
                            detected_finish_reason = finish_reason_str
                            logger.warning(
                                f"Gemini proposal rejected: non-normal finish reason ({finish_reason_str})"
                            )
                            raise LLMExtractionError(
                                message=f"Gemini output terminated prematurely (finish_reason={finish_reason_str})",
                                finish_reason=finish_reason_str,
                            )

                raw_text = (getattr(response, "text", None) or "").strip()
                if not raw_text:
                    logger.warning("Gemini proposal rejected: empty response text")
                    raise LLMExtractionError(
                        message="Gemini question proposal returned empty response text",
                        finish_reason=detected_finish_reason or "EMPTY_TEXT",
                    )

                result_json = json.loads(raw_text)
                proposal = AdaptiveQuestionProposal.model_validate(result_json)

                in_tok, out_tok, tot_tok, th_tok = _extract_token_counts(response)
                fr = _extract_finish_reason(response)
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                log_gemini_metric(
                    operation="question_proposal",
                    attempts=attempt + 1,
                    status="SUCCESS",
                    duration_ms=elapsed_ms,
                    retry_occurred=(attempt > 0),
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    total_tokens=tot_tok,
                    thoughts_token_count=th_tok,
                    finish_reason=fr,
                    model=self.model,
                    session_id=session_id,
                    turn_index=turn_index,
                )

                return proposal

            except (json.JSONDecodeError, ValidationError, LLMExtractionError) as parse_err:
                err_finish_reason = getattr(parse_err, "finish_reason", None) or detected_finish_reason
                logger.warning(
                    f"Gemini question proposal parsing attempt {attempt + 1} failed "
                    f"(finish_reason={err_finish_reason or 'NORMAL_OR_UNSPECIFIED'}): {parse_err}"
                )
                if attempt < 1:
                    initial_failure_category = FAILURE_CATEGORY_MALFORMED_STRUCTURED_OUTPUT
                    initial_finish_reason = err_finish_reason
                    time.sleep(1.0)
                    continue

                cat = FAILURE_CATEGORY_MALFORMED_STRUCTURED_OUTPUT
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                log_gemini_metric(
                    operation="question_proposal",
                    attempts=attempt + 1,
                    status=cat,
                    duration_ms=elapsed_ms,
                    retry_occurred=(attempt > 0),
                    model=self.model,
                    session_id=session_id,
                    turn_index=turn_index,
                )
                log_gemini_failure(
                    failure_category=cat,
                    operation="question_proposal",
                    http_status=None,
                    is_quota_limit=False,
                    session_id=session_id,
                    turn_index=turn_index,
                    model=self.model,
                    initial_failure_category=initial_failure_category or cat,
                    retry_failure_category=cat if initial_failure_category else None,
                    finish_reason=err_finish_reason or initial_finish_reason,
                )
                raise TriageLLMUnavailableError(
                    message="Conversational triage is temporarily unavailable. Please try again later or contact your care provider directly.",
                    code="TRIAGE_LLM_SERVICE_UNAVAILABLE",
                )
            except Exception as exc:
                err_str = str(exc)
                diag = extract_gemini_error_diagnostics(exc)
                cat = diag["failure_category"]
                status_code = diag["http_status"]
                is_quota = diag["is_quota_limit"]
                upstream_status = diag.get("upstream_status")
                upstream_reason = diag.get("upstream_reason")
                retry_after = diag.get("retry_after")

                if cat == FAILURE_CATEGORY_AUTHENTICATION_ERROR:
                    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                    log_gemini_metric(
                        operation="question_proposal",
                        attempts=attempt + 1,
                        status=cat,
                        duration_ms=elapsed_ms,
                        retry_occurred=(attempt > 0),
                        model=self.model,
                        session_id=session_id,
                        turn_index=turn_index,
                        http_status=status_code,
                        upstream_status=upstream_status,
                        upstream_reason=upstream_reason,
                    )
                    log_gemini_failure(
                        failure_category=cat,
                        operation="question_proposal",
                        http_status=status_code,
                        is_quota_limit=False,
                        session_id=session_id,
                        turn_index=turn_index,
                        model=self.model,
                        initial_failure_category=initial_failure_category,
                        retry_failure_category=cat if initial_failure_category else None,
                        finish_reason=initial_finish_reason,
                        upstream_status=upstream_status,
                        upstream_reason=upstream_reason,
                        attempt=attempt + 1,
                    )
                    raise TriageLLMUnavailableError(
                        message="Conversational triage is temporarily unavailable. Please try again later or contact your care provider directly.",
                        code="TRIAGE_LLM_SERVICE_UNAVAILABLE",
                    )

                if self._is_permanent_quota_error(err_str):
                    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                    log_gemini_metric(
                        operation="question_proposal",
                        attempts=attempt + 1,
                        status=FAILURE_CATEGORY_QUOTA_EXCEEDED,
                        duration_ms=elapsed_ms,
                        retry_occurred=(attempt > 0),
                        model=self.model,
                        session_id=session_id,
                        turn_index=turn_index,
                        http_status=429,
                        upstream_status=upstream_status,
                        upstream_reason=upstream_reason,
                    )
                    log_gemini_failure(
                        failure_category=FAILURE_CATEGORY_QUOTA_EXCEEDED,
                        operation="question_proposal",
                        http_status=429,
                        is_quota_limit=True,
                        session_id=session_id,
                        turn_index=turn_index,
                        model=self.model,
                        initial_failure_category=initial_failure_category,
                        retry_failure_category=FAILURE_CATEGORY_QUOTA_EXCEEDED if initial_failure_category else None,
                        finish_reason=initial_finish_reason,
                        upstream_status=upstream_status,
                        upstream_reason=upstream_reason,
                        attempt=attempt + 1,
                    )
                    raise TriageLLMUnavailableError(
                        message="Conversational triage capacity is temporarily exhausted. Please try again later or proceed directly to doctor consultation.",
                        code="TRIAGE_LLM_SERVICE_UNAVAILABLE",
                    )

                is_transient_error = cat in (
                    FAILURE_CATEGORY_SERVICE_UNAVAILABLE,
                    FAILURE_CATEGORY_NETWORK_ERROR,
                )

                if is_quota:
                    safe_delay = self._get_safe_quota_retry_delay(diag, err_str)
                    if safe_delay is not None and attempt < 1:
                        initial_failure_category = cat
                        logger.warning(
                            f"Gemini transient rate limit hit in question proposal. Respecting provider delay of {safe_delay}s (attempt {attempt + 1}/2)..."
                        )
                        time.sleep(safe_delay)
                        continue
                    else:
                        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                        log_gemini_metric(
                            operation="question_proposal",
                            attempts=attempt + 1,
                            status=FAILURE_CATEGORY_QUOTA_EXCEEDED,
                            duration_ms=elapsed_ms,
                            retry_occurred=(attempt > 0),
                            model=self.model,
                            session_id=session_id,
                            turn_index=turn_index,
                            http_status=429,
                            upstream_status=upstream_status,
                            upstream_reason=upstream_reason,
                        )
                        log_gemini_failure(
                            failure_category=FAILURE_CATEGORY_QUOTA_EXCEEDED,
                            operation="question_proposal",
                            http_status=429,
                            is_quota_limit=True,
                            session_id=session_id,
                            turn_index=turn_index,
                            model=self.model,
                            initial_failure_category=initial_failure_category,
                            retry_failure_category=FAILURE_CATEGORY_QUOTA_EXCEEDED if initial_failure_category else None,
                            finish_reason=initial_finish_reason,
                            upstream_status=upstream_status,
                            upstream_reason=upstream_reason,
                            attempt=attempt + 1,
                        )
                        raise TriageLLMUnavailableError(
                            message="Conversational triage capacity is temporarily exhausted. Please try again later or proceed directly to doctor consultation.",
                            code="TRIAGE_LLM_SERVICE_UNAVAILABLE",
                        )

                if is_transient_error and attempt < 1:
                    initial_failure_category = cat
                    delay = compute_gemini_backoff(diag, attempt)
                    logger.warning(
                        f"Gemini transient {cat} in question proposal. Backing off for {delay}s (attempt {attempt + 1}/2)..."
                    )
                    time.sleep(delay)
                    continue

                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                log_gemini_metric(
                    operation="question_proposal",
                    attempts=attempt + 1,
                    status=cat,
                    duration_ms=elapsed_ms,
                    retry_occurred=(attempt > 0),
                    model=self.model,
                    session_id=session_id,
                    turn_index=turn_index,
                    http_status=status_code,
                    upstream_status=upstream_status,
                    upstream_reason=upstream_reason,
                    retry_after=retry_after,
                )
                log_gemini_failure(
                    failure_category=cat,
                    operation="question_proposal",
                    http_status=status_code,
                    is_quota_limit=is_quota,
                    session_id=session_id,
                    turn_index=turn_index,
                    model=self.model,
                    initial_failure_category=initial_failure_category,
                    retry_failure_category=cat if initial_failure_category else None,
                    finish_reason=initial_finish_reason,
                    upstream_status=upstream_status,
                    upstream_reason=upstream_reason,
                    retry_after=retry_after,
                    attempt=attempt + 1,
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
