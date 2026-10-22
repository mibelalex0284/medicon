import pytest
from app.core.exceptions import TriageLLMUnavailableError
from app.services.llm import (
    EvidenceStatus,
    ExtractedEvidenceItem,
    ExtractedEvidenceResult,
    GeminiProvider,
    LLMExtractionError,
    get_llm_provider,
)
from app.services.llm.gemini import (
    FAILURE_CATEGORY_QUOTA_EXCEEDED,
    FAILURE_CATEGORY_AUTHENTICATION_ERROR,
    FAILURE_CATEGORY_NETWORK_ERROR,
    FAILURE_CATEGORY_VALIDATION_ERROR,
    classify_gemini_error,
    log_gemini_failure,
)


def test_classify_gemini_error_categories():
    """Verify classification of Gemini exceptions into required categories."""
    # 429 Quota Exceeded
    cat, status, is_quota = classify_gemini_error(RuntimeError("429 RESOURCE_EXHAUSTED Quota exceeded"))
    assert cat == FAILURE_CATEGORY_QUOTA_EXCEEDED
    assert status == 429
    assert is_quota is True

    # 401 Authentication
    cat, status, is_quota = classify_gemini_error(RuntimeError("401 UNAUTHENTICATED Invalid API key"))
    assert cat == FAILURE_CATEGORY_AUTHENTICATION_ERROR
    assert status == 401
    assert is_quota is False

    # Network / Timeout
    cat, status, is_quota = classify_gemini_error(ConnectionError("Connection timeout to api.generativelanguage.google.com"))
    assert cat == FAILURE_CATEGORY_NETWORK_ERROR
    assert is_quota is False

    # Validation
    cat, status, is_quota = classify_gemini_error(ValueError("JSON malformed response"))
    assert cat == FAILURE_CATEGORY_VALIDATION_ERROR
    assert is_quota is False


def test_gemini_provider_missing_key_raises_unavailable():
    """Verify GeminiProvider raises TriageLLMUnavailableError (HTTP 503) when API key is missing."""
    gemini = GeminiProvider(api_key="")
    with pytest.raises(TriageLLMUnavailableError) as exc_info:
        gemini.extract_patient_evidence("I have a cough.")
    assert exc_info.value.code == "TRIAGE_LLM_SERVICE_UNAVAILABLE"
    assert exc_info.value.status_code == 503


def test_get_llm_provider_fallback():
    """Verify provider factory returns a usable provider."""
    provider = get_llm_provider()
    assert hasattr(provider, "extract_patient_evidence")
    assert hasattr(provider, "phrase_question")


# ==============================================================================
# STAGE 4B.3A REGRESSION: GEMINI DEVELOPER API SCHEMA COMPATIBILITY
# ==============================================================================


def _find_key_recursive(schema: dict | list, target_key: str) -> list:
    """Recursively search for target_key within nested schema dictionaries and lists."""
    matches = []
    if isinstance(schema, dict):
        for k, v in schema.items():
            if k == target_key:
                matches.append((k, v))
            if isinstance(v, (dict, list)):
                matches.extend(_find_key_recursive(v, target_key))
    elif isinstance(schema, list):
        for item in schema:
            if isinstance(item, (dict, list)):
                matches.extend(_find_key_recursive(item, target_key))
    return matches


def test_extracted_evidence_result_schema_has_no_additional_properties():
    """A. Verify generated JSON schema contains ZERO additionalProperties.

    Gemini Developer API strictly rejects schemas with additionalProperties for objects.
    """
    schema = ExtractedEvidenceResult.model_json_schema()
    matches = _find_key_recursive(schema, "additionalProperties")
    assert len(matches) == 0, f"Found forbidden additionalProperties in schema: {matches}"


def test_measurements_representation_without_additional_properties():
    """B. Verify measurements can be represented without additionalProperties using bounded list."""
    from app.services.llm.provider import MeasurementItem

    item = MeasurementItem(name="temperature", value=38.5, unit="C")
    assert item.name == "temperature"
    assert item.value == 38.5
    assert item.unit == "C"

    # Verify MeasurementItem schema itself does not introduce additionalProperties
    item_schema = MeasurementItem.model_json_schema()
    assert len(_find_key_recursive(item_schema, "additionalProperties")) == 0


def test_pydantic_validation_still_succeeds():
    """C. Verify Pydantic validation still succeeds on structured JSON with measurements and items."""
    sample_json = {
        "chief_complaint": "fever and headache",
        "duration": "3 days",
        "severity": 7,
        "measurements": [
            {"name": "temperature", "value": 38.5, "unit": "C"}
        ],
        "items": [
            {"evidence_code": "E_91", "status": "PRESENT", "confidence": 0.95},
            {"evidence_code": "E_127", "status": "PRESENT", "confidence": 0.90},
            {"evidence_code": "E_77", "status": "ABSENT", "confidence": 1.0},
        ],
    }
    validated = ExtractedEvidenceResult.model_validate(sample_json)
    assert validated.chief_complaint == "fever and headache"
    assert validated.duration == "3 days"
    assert validated.severity == 7
    assert len(validated.measurements) == 1
    assert validated.measurements[0].name == "temperature"
    assert validated.measurements[0].value == 38.5
    assert validated.measurements[0].unit == "C"
    assert len(validated.items) == 3


def test_gemini_generate_content_config_accepts_schema():
    """Verify that google.genai.types.GenerateContentConfig accepts ExtractedEvidenceResult."""
    try:
        from google.genai import types

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ExtractedEvidenceResult,
            temperature=0.0,
            max_output_tokens=1500,
        )
        assert config.response_schema is ExtractedEvidenceResult
        assert config.response_mime_type == "application/json"
    except ImportError:
        pytest.skip("google-genai SDK not installed")


# ==============================================================================
# STAGE 4B.3B: GEMINI 429 RELIABILITY TESTS (FAIL FAST VS BOUNDED RETRY)
# ==============================================================================
from unittest.mock import MagicMock, patch


def test_gemini_quota_depleted_fails_fast_without_retry():
    """Requirement 7: 429 RESOURCE_EXHAUSTED + 'prepayment credits are depleted'

    MUST FAIL FAST: exactly 1 call, zero retries, zero sleep.
    """
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception(
        "429 RESOURCE_EXHAUSTED. Your prepayment credits are depleted. Please check billing at https://ai.studio/projects"
    )

    with patch.object(gemini, "_get_client", return_value=mock_client), patch("time.sleep") as mock_sleep:
        with pytest.raises(TriageLLMUnavailableError) as exc_info:
            gemini.extract_patient_evidence("I have a fever")

        assert exc_info.value.code == "TRIAGE_LLM_SERVICE_UNAVAILABLE"
        # Exactly 1 call was made (FAIL FAST, NO RETRY)
        assert mock_client.models.generate_content.call_count == 1
        # Zero sleep occurred
        assert mock_sleep.call_count == 0


def test_gemini_transient_429_retries_and_succeeds():
    """Requirement 8: Transient 429 with retry info MUST execute bounded retry and succeed."""
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()

    mock_resp = MagicMock()
    mock_resp.text = '{"chief_complaint": "fever", "duration": "2 days", "severity": 6, "items": [{"evidence_code": "E_91", "status": "PRESENT"}]}'

    # First attempt: transient 429; second attempt: success
    mock_client.models.generate_content.side_effect = [
        Exception("429 RESOURCE_EXHAUSTED. Rate limit exceeded. Please retry in 3s."),
        mock_resp,
    ]

    with patch.object(gemini, "_get_client", return_value=mock_client), patch("time.sleep") as mock_sleep:
        res = gemini.extract_patient_evidence("I have a fever")

        assert isinstance(res, ExtractedEvidenceResult)
        assert len(res.items) == 1
        assert res.items[0].evidence_code == "E_91"
        # Successfully retried: exactly 2 calls made
        assert mock_client.models.generate_content.call_count == 2
        # Exactly 1 sleep occurred with bounded delay
        assert mock_sleep.call_count == 1
        sleep_delay = mock_sleep.call_args[0][0]
        assert sleep_delay == 4  # 3 + 1 bounded backoff


def test_gemini_phrase_question_quota_depleted_fails_fast():
    """Verify phrase_question also fails fast without sleep or retry on quota depletion."""
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception(
        "429 RESOURCE_EXHAUSTED. prepayment credits are depleted"
    )

    with patch.object(gemini, "_get_client", return_value=mock_client), patch("time.sleep") as mock_sleep:
        with pytest.raises(TriageLLMUnavailableError) as exc_info:
            gemini.phrase_question("Do you have a fever?", "E_91")

        assert exc_info.value.code == "TRIAGE_LLM_SERVICE_UNAVAILABLE"
        assert mock_client.models.generate_content.call_count == 1
        assert mock_sleep.call_count == 0


def test_is_diagnostic_claim_distinguishes_interrogative_from_diagnostic():
    """Verify is_diagnostic_claim properly separates interrogative queries from affirmative diagnoses."""
    from app.services.llm import is_diagnostic_claim

    not_diagnostic = [
        "Do you have a fever?",
        "Have you experienced coughing?",
        "Are you having chest pain?",
        "Do you have stomach or abdominal pain?",
        "Do you have a cough?",
        "Are you experiencing a headache?",
        "Are you having shortness of breath?",
        "Did you have chills last night?",
        "Can you tell me if you have nausea?",
    ]

    diagnostic_claims = [
        "You have the flu.",
        "You may have pneumonia.",
        "I think you have asthma.",
        "You probably have bronchitis.",
        "You might have COVID-19.",
        "You suffer from migraine.",
        "My diagnosis is asthma.",
        "Based on your symptoms, you have an infection.",
        "It seems you have pneumonia.",
    ]

    for q in not_diagnostic:
        assert is_diagnostic_claim(q) is False, f"Expected '{q}' to NOT be considered diagnostic"

    for d in diagnostic_claims:
        assert is_diagnostic_claim(d) is True, f"Expected '{d}' to BE considered diagnostic"


# ==============================================================================
# QUESTION PHRASING ROBUSTNESS & FALLBACK TESTS
# ==============================================================================


def test_gemini_phrase_question_valid_response():
    """Verify valid phrased question ending with '?' is returned."""
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_cand = MagicMock()
    mock_cand.finish_reason = "STOP"
    mock_resp.candidates = [mock_cand]
    mock_resp.text = "Have you noticed any persistent coughing recently?"
    mock_client.models.generate_content.return_value = mock_resp

    with patch.object(gemini, "_get_client", return_value=mock_client):
        result = gemini.phrase_question("Do you have a cough?", "E_201")
        assert result == "Have you noticed any persistent coughing recently?"


def test_gemini_phrase_question_max_tokens_truncated_falls_back_to_controlled():
    """Verify response truncated by MAX_TOKENS falls back to controlled question without appending '?'."""
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_cand = MagicMock()
    mock_cand.finish_reason = "MAX_TOKENS"
    mock_resp.candidates = [mock_cand]
    mock_resp.text = "Have you been experiencing a"
    mock_client.models.generate_content.return_value = mock_resp

    with patch.object(gemini, "_get_client", return_value=mock_client):
        result = gemini.phrase_question("Do you have a cough?", "E_201")
        # Must NOT return 'Have you been experiencing a?'
        assert result == "Do you have a cough?"


def test_gemini_phrase_question_incomplete_without_question_mark_falls_back():
    """Verify incomplete response lacking '?' falls back to controlled question without appending '?'."""
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_cand = MagicMock()
    mock_cand.finish_reason = "STOP"
    mock_resp.candidates = [mock_cand]
    mock_resp.text = "Have you been experiencing a"
    mock_client.models.generate_content.return_value = mock_resp

    with patch.object(gemini, "_get_client", return_value=mock_client):
        result = gemini.phrase_question("Do you have a cough?", "E_201")
        assert result == "Do you have a cough?"


def test_gemini_phrase_question_dangling_truncation_falls_back():
    """Verify obvious truncation ending in dangling words before '?' falls back to controlled question."""
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_cand = MagicMock()
    mock_cand.finish_reason = "STOP"
    mock_resp.candidates = [mock_cand]
    mock_resp.text = "Have you been experiencing a?"
    mock_client.models.generate_content.return_value = mock_resp

    with patch.object(gemini, "_get_client", return_value=mock_client):
        result = gemini.phrase_question("Do you have a cough?", "E_201")
        assert result == "Do you have a cough?"


def test_gemini_phrase_question_diagnostic_claim_rejected_falls_back():
    """Verify any diagnostic assertion introduced in phrasing is rejected and falls back."""
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_cand = MagicMock()
    mock_cand.finish_reason = "STOP"
    mock_resp.candidates = [mock_cand]
    mock_resp.text = "I think you have bronchitis, do you have a cough?"
    mock_client.models.generate_content.return_value = mock_resp

    with patch.object(gemini, "_get_client", return_value=mock_client):
        result = gemini.phrase_question("Do you have a cough?", "E_201")
        assert result == "Do you have a cough?"


def test_gemini_phrase_question_config_has_expanded_token_budget():
    """Verify generate_content config provides at least 1000 max_output_tokens for thinking headroom."""
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_cand = MagicMock()
    mock_cand.finish_reason = "STOP"
    mock_resp.candidates = [mock_cand]
    mock_resp.text = "Are you experiencing any coughing?"
    mock_client.models.generate_content.return_value = mock_resp

    with patch.object(gemini, "_get_client", return_value=mock_client):
        gemini.phrase_question("Do you have a cough?", "E_201")

        assert mock_client.models.generate_content.call_count >= 1
        call_kwargs = mock_client.models.generate_content.call_args.kwargs
        config = call_kwargs.get("config")
        assert config is not None
        assert getattr(config, "max_output_tokens", 0) >= 1000


def test_gemini_metric_logging_captures_thoughts_and_finish_reason():
    """Verify log_gemini_metric and provider include thoughts_token_count and finish_reason."""
    from app.services.llm.gemini import (
        clear_gemini_metrics,
        get_gemini_metrics,
        log_gemini_metric,
        _extract_token_counts,
        _extract_finish_reason,
    )

    clear_gemini_metrics()

    # Direct log_gemini_metric check
    log_gemini_metric(
        operation="test_op",
        attempts=1,
        status="SUCCESS",
        duration_ms=123.45,
        retry_occurred=False,
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        thoughts_token_count=35,
        finish_reason="STOP",
    )
    metrics = get_gemini_metrics()
    assert len(metrics) == 1
    m = metrics[0]
    assert m["thoughts_token_count"] == 35
    assert m["finish_reason"] == "STOP"
    assert m["input_tokens"] == 100
    assert m["output_tokens"] == 50
    assert m["total_tokens"] == 150

    # Helper extraction check
    class DummyUsage:
        prompt_token_count = 10
        candidates_token_count = 20
        total_token_count = 30
        thoughts_token_count = 5

    class DummyCandidate:
        finish_reason = "STOP"

    class DummyResponse:
        usage_metadata = DummyUsage()
        candidates = [DummyCandidate()]

    in_tok, out_tok, tot_tok, th_tok = _extract_token_counts(DummyResponse())
    assert (in_tok, out_tok, tot_tok, th_tok) == (10, 20, 30, 5)
    fr = _extract_finish_reason(DummyResponse())
    assert fr == "STOP"




