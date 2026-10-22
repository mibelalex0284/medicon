import json
from unittest.mock import MagicMock, patch
import pytest

from app.core.exceptions import TriageLLMUnavailableError
from app.services.llm import (
    EvidenceStatus,
    ExtractedEvidenceResult,
    GeminiProvider,
    LLMExtractionError,
)
from app.services.llm.gemini import (
    FAILURE_CATEGORY_AUTHENTICATION_ERROR,
    FAILURE_CATEGORY_MALFORMED_STRUCTURED_OUTPUT,
    FAILURE_CATEGORY_NETWORK_ERROR,
    FAILURE_CATEGORY_QUOTA_EXCEEDED,
    FAILURE_CATEGORY_SERVICE_UNAVAILABLE,
    classify_gemini_error,
)


def _make_mock_response(text: str, finish_reason: str = "STOP"):
    mock_resp = MagicMock()
    mock_cand = MagicMock()
    mock_cand.finish_reason = finish_reason
    mock_resp.candidates = [mock_cand]
    mock_resp.text = text
    return mock_resp


# ==============================================================================
# TEST A: Valid structured Gemini response -> successful evidence extraction
# ==============================================================================
def test_a_valid_structured_gemini_response_success():
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()

    valid_json = json.dumps({
        "chief_complaint": "fever",
        "duration": "3 days",
        "severity": 6,
        "measurements": [],
        "items": [{"evidence_code": "E_91", "status": "PRESENT", "confidence": 1.0}],
    })
    mock_resp = _make_mock_response(valid_json, finish_reason="STOP")
    mock_client.models.generate_content.return_value = mock_resp

    with patch.object(gemini, "_get_client", return_value=mock_client), patch("time.sleep") as mock_sleep:
        res = gemini.extract_patient_evidence("I have a fever for 3 days, 6 out of 10.")

        assert isinstance(res, ExtractedEvidenceResult)
        assert res.chief_complaint == "fever"
        assert res.duration == "3 days"
        assert res.severity == 6
        assert len(res.items) == 1
        assert res.items[0].evidence_code == "E_91"
        assert res.items[0].status == EvidenceStatus.PRESENT
        assert mock_client.models.generate_content.call_count == 1
        assert mock_sleep.call_count == 0


# ==============================================================================
# TEST B: Malformed/truncated JSON on attempt 1 -> parsing failure recorded & retried
# ==============================================================================
def test_b1_malformed_json_attempt1_succeeds_on_attempt2():
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()

    # Attempt 1: truncated JSON (unterminated string)
    truncated_json = '{"chief_complaint": "sore throat", "items": [{"evidence_code": "E_194", "status": "PR'
    resp_attempt1 = _make_mock_response(truncated_json, finish_reason="STOP")

    # Attempt 2: valid JSON
    valid_json = json.dumps({
        "chief_complaint": "sore throat",
        "duration": "2 days",
        "severity": None,
        "measurements": [],
        "items": [{"evidence_code": "E_194", "status": "PRESENT", "confidence": 1.0}],
    })
    resp_attempt2 = _make_mock_response(valid_json, finish_reason="STOP")

    mock_client.models.generate_content.side_effect = [resp_attempt1, resp_attempt2]

    with (
        patch.object(gemini, "_get_client", return_value=mock_client),
        patch("time.sleep") as mock_sleep,
        patch("app.services.llm.gemini.logger.warning") as mock_warn,
    ):
        res = gemini.extract_patient_evidence("sore throat for 2 days")

        assert isinstance(res, ExtractedEvidenceResult)
        assert len(res.items) == 1
        assert res.items[0].evidence_code == "E_194"
        # Bounded retry occurred: exactly 2 calls
        assert mock_client.models.generate_content.call_count == 2
        # Exactly 1 sleep of 1.0s bounded backoff
        assert mock_sleep.call_count == 1
        assert mock_sleep.call_args[0][0] == 1.0
        # Warning logged for attempt 1 failure
        warning_calls = [str(call) for call in mock_warn.call_args_list]
        assert any("parsing attempt 1 failed" in c for c in warning_calls)


def test_b2_malformed_json_both_attempts_fails_with_structured_log():
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()

    truncated_json = '{"chief_complaint": "fever", "items": [{"evidence_code": "E_91", "status": "AB'
    mock_client.models.generate_content.side_effect = [
        _make_mock_response(truncated_json),
        _make_mock_response(truncated_json),
    ]

    with (
        patch.object(gemini, "_get_client", return_value=mock_client),
        patch("time.sleep") as mock_sleep,
        patch("app.services.llm.gemini.log_gemini_failure") as mock_log_fail,
    ):
        with pytest.raises(TriageLLMUnavailableError) as exc_info:
            gemini.extract_patient_evidence("I have a fever")

        assert exc_info.value.code == "TRIAGE_LLM_SERVICE_UNAVAILABLE"
        assert exc_info.value.status_code == 503
        assert mock_client.models.generate_content.call_count == 2
        assert mock_sleep.call_count == 1

        mock_log_fail.assert_called_once()
        kwargs = mock_log_fail.call_args.kwargs
        assert kwargs["failure_category"] == FAILURE_CATEGORY_MALFORMED_STRUCTURED_OUTPUT
        assert kwargs["initial_failure_category"] == FAILURE_CATEGORY_MALFORMED_STRUCTURED_OUTPUT
        assert kwargs["retry_failure_category"] == FAILURE_CATEGORY_MALFORMED_STRUCTURED_OUTPUT


# ==============================================================================
# TEST C: Attempt 1 malformed JSON + Attempt 2 HTTP 503 -> preserves BOTH failures
# ==============================================================================
def test_c_attempt1_malformed_attempt2_http503_preserves_both_failures():
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()

    # Attempt 1: Truncated JSON
    truncated_json = '{"chief_complaint": "fever", "duration": "3 days", "items": [{"evidence_code": "E_66", "status": "AB'
    resp_attempt1 = _make_mock_response(truncated_json, finish_reason="STOP")

    # Attempt 2: Upstream 503 ServerError
    err_503 = Exception("503 UNAVAILABLE. The model is overloaded. Please try again later.")
    mock_client.models.generate_content.side_effect = [resp_attempt1, err_503]

    with (
        patch.object(gemini, "_get_client", return_value=mock_client),
        patch("time.sleep") as mock_sleep,
        patch("app.services.llm.gemini.log_gemini_failure") as mock_log_fail,
    ):
        with pytest.raises(TriageLLMUnavailableError) as exc_info:
            gemini.extract_patient_evidence(
                "no",
                context={"session_id": "test-session-123", "turn_index": 2},
            )

        # Fails closed
        assert exc_info.value.code == "TRIAGE_LLM_SERVICE_UNAVAILABLE"
        assert exc_info.value.status_code == 503
        assert mock_client.models.generate_content.call_count == 2
        assert mock_sleep.call_count == 1
        assert mock_sleep.call_args[0][0] == 1.0

        # Structured diagnostics preserve BOTH the initial parsing error and the retry 503
        mock_log_fail.assert_called_once()
        kwargs = mock_log_fail.call_args.kwargs
        assert kwargs["failure_category"] == FAILURE_CATEGORY_SERVICE_UNAVAILABLE
        assert kwargs["http_status"] == 503
        assert kwargs["initial_failure_category"] == FAILURE_CATEGORY_MALFORMED_STRUCTURED_OUTPUT
        assert kwargs["retry_failure_category"] == FAILURE_CATEGORY_SERVICE_UNAVAILABLE
        assert kwargs["operation"] == "evidence_extraction"
        assert kwargs["session_id"] == "test-session-123"
        assert kwargs["turn_index"] == 2


# ==============================================================================
# TEST D: Non-normal finish_reason detected and does NOT get treated as valid JSON
# ==============================================================================
def test_d1_max_tokens_finish_reason_rejected():
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()

    # Even if text happens to contain some JSON fragments, MAX_TOKENS must reject it
    partial_json = '{"chief_complaint": "cough", "items": [{"evidence_code": "E_201", "status": "PRESENT"}]}'
    resp_max_tokens = _make_mock_response(partial_json, finish_reason="MAX_TOKENS")
    mock_client.models.generate_content.side_effect = [resp_max_tokens, resp_max_tokens]

    with (
        patch.object(gemini, "_get_client", return_value=mock_client),
        patch("time.sleep"),
        patch("app.services.llm.gemini.log_gemini_failure") as mock_log_fail,
    ):
        with pytest.raises(TriageLLMUnavailableError):
            gemini.extract_patient_evidence("I have a cough")

        mock_log_fail.assert_called_once()
        kwargs = mock_log_fail.call_args.kwargs
        assert kwargs["failure_category"] == FAILURE_CATEGORY_MALFORMED_STRUCTURED_OUTPUT
        assert kwargs["finish_reason"] == "MAX_TOKENS"


def test_d2_safety_finish_reason_rejected():
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()

    resp_safety = _make_mock_response("", finish_reason="SAFETY")
    mock_client.models.generate_content.side_effect = [resp_safety, resp_safety]

    with (
        patch.object(gemini, "_get_client", return_value=mock_client),
        patch("time.sleep"),
        patch("app.services.llm.gemini.log_gemini_failure") as mock_log_fail,
    ):
        with pytest.raises(TriageLLMUnavailableError):
            gemini.extract_patient_evidence("test input")

        mock_log_fail.assert_called_once()
        kwargs = mock_log_fail.call_args.kwargs
        assert kwargs["failure_category"] == FAILURE_CATEGORY_MALFORMED_STRUCTURED_OUTPUT
        assert kwargs["finish_reason"] == "SAFETY"


def test_d3_empty_candidates_rejected():
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()

    mock_resp = MagicMock()
    mock_resp.candidates = []
    mock_resp.text = ""
    mock_client.models.generate_content.side_effect = [mock_resp, mock_resp]

    with (
        patch.object(gemini, "_get_client", return_value=mock_client),
        patch("time.sleep"),
        patch("app.services.llm.gemini.log_gemini_failure") as mock_log_fail,
    ):
        with pytest.raises(TriageLLMUnavailableError):
            gemini.extract_patient_evidence("test input")

        mock_log_fail.assert_called_once()
        kwargs = mock_log_fail.call_args.kwargs
        assert kwargs["finish_reason"] == "NO_CANDIDATES"


# ==============================================================================
# TEST E: Existing 429/503 classification behavior remains unchanged
# ==============================================================================
def test_e1_classify_gemini_error_429_503_unaltered():
    # 429 Rate limit
    cat, status, is_quota = classify_gemini_error(Exception("429 RESOURCE_EXHAUSTED Quota exceeded"))
    assert cat == FAILURE_CATEGORY_QUOTA_EXCEEDED
    assert status == 429
    assert is_quota is True

    # 503 Unavailable
    cat, status, is_quota = classify_gemini_error(Exception("503 UNAVAILABLE Service unavailable"))
    assert cat == FAILURE_CATEGORY_SERVICE_UNAVAILABLE
    assert status == 503
    assert is_quota is False

    # 500 Internal error
    cat, status, is_quota = classify_gemini_error(Exception("500 INTERNAL Internal server error"))
    assert cat == FAILURE_CATEGORY_SERVICE_UNAVAILABLE
    assert status == 500
    assert is_quota is False


def test_e2_direct_429_rate_limit_backoff_and_retry_unchanged():
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()

    valid_json = json.dumps({
        "chief_complaint": "cough",
        "items": [{"evidence_code": "E_201", "status": "PRESENT"}],
    })
    resp_success = _make_mock_response(valid_json)

    mock_client.models.generate_content.side_effect = [
        Exception("429 RESOURCE_EXHAUSTED. Rate limit exceeded. Please retry in 2s."),
        resp_success,
    ]

    with patch.object(gemini, "_get_client", return_value=mock_client), patch("time.sleep") as mock_sleep:
        res = gemini.extract_patient_evidence("I have a cough")
        assert len(res.items) == 1
        assert mock_client.models.generate_content.call_count == 2
        assert mock_sleep.call_count == 1
        assert mock_sleep.call_args[0][0] == 3  # 2 + 1


# ==============================================================================
# PART 2 DETERMINISTIC RETRY TESTS: SCENARIOS A - H
# ==============================================================================

# Scenario A: HTTP 503 followed by success
def test_part2_scenario_a_http503_followed_by_success():
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()

    valid_json = json.dumps({
        "chief_complaint": "fever",
        "items": [{"evidence_code": "E_91", "status": "PRESENT", "confidence": 1.0}],
    })
    resp_success = _make_mock_response(valid_json)
    err_503 = Exception("503 UNAVAILABLE. The model is overloaded. Please try again later.")
    mock_client.models.generate_content.side_effect = [err_503, resp_success]

    with (
        patch.object(gemini, "_get_client", return_value=mock_client),
        patch("time.sleep") as mock_sleep,
        patch("app.services.llm.gemini.log_gemini_failure") as mock_log_fail,
    ):
        res = gemini.extract_patient_evidence("fever")
        assert len(res.items) == 1
        assert res.items[0].evidence_code == "E_91"
        assert mock_client.models.generate_content.call_count == 2
        assert mock_sleep.call_count == 1
        assert 2.1 <= mock_sleep.call_args[0][0] <= 2.5
        mock_log_fail.assert_not_called()


# Scenario B: HTTP 503 followed by another HTTP 503
def test_part2_scenario_b_http503_followed_by_another_http503():
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()

    err_503 = Exception("503 UNAVAILABLE. Model overloaded.")
    mock_client.models.generate_content.side_effect = [err_503, err_503]

    with (
        patch.object(gemini, "_get_client", return_value=mock_client),
        patch("time.sleep") as mock_sleep,
        patch("app.services.llm.gemini.log_gemini_failure") as mock_log_fail,
    ):
        with pytest.raises(TriageLLMUnavailableError) as exc_info:
            gemini.extract_patient_evidence("fever", context={"session_id": "sess-503", "turn_index": 1})

        assert exc_info.value.code == "TRIAGE_LLM_SERVICE_UNAVAILABLE"
        assert exc_info.value.status_code == 503
        assert mock_client.models.generate_content.call_count == 2
        assert mock_sleep.call_count == 1
        assert 2.1 <= mock_sleep.call_args[0][0] <= 2.5

        mock_log_fail.assert_called_once()
        kwargs = mock_log_fail.call_args.kwargs
        assert kwargs["failure_category"] == FAILURE_CATEGORY_SERVICE_UNAVAILABLE
        assert kwargs["initial_failure_category"] == FAILURE_CATEGORY_SERVICE_UNAVAILABLE
        assert kwargs["retry_failure_category"] == FAILURE_CATEGORY_SERVICE_UNAVAILABLE
        assert kwargs["http_status"] == 503
        assert kwargs["session_id"] == "sess-503"
        assert kwargs["turn_index"] == 1


# Scenario C: A transient network failure followed by success
def test_part2_scenario_c_transient_network_failure_followed_by_success():
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()

    valid_json = json.dumps({
        "chief_complaint": "cough",
        "items": [{"evidence_code": "E_201", "status": "PRESENT", "confidence": 1.0}],
    })
    resp_success = _make_mock_response(valid_json)
    network_err = ConnectionResetError("Connection reset by peer during SSL handshake")
    mock_client.models.generate_content.side_effect = [network_err, resp_success]

    with (
        patch.object(gemini, "_get_client", return_value=mock_client),
        patch("time.sleep") as mock_sleep,
        patch("app.services.llm.gemini.log_gemini_failure") as mock_log_fail,
    ):
        res = gemini.extract_patient_evidence("cough")
        assert len(res.items) == 1
        assert res.items[0].evidence_code == "E_201"
        assert mock_client.models.generate_content.call_count == 2
        assert mock_sleep.call_count == 1
        assert 2.1 <= mock_sleep.call_args[0][0] <= 2.5
        mock_log_fail.assert_not_called()


# Scenario D: Permanent quota exhaustion fails without an additional retry
def test_part2_scenario_d_permanent_quota_exhaustion_fails_fast():
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()

    perm_quota_err = Exception("429 ResourceExhausted: prepayment credits are depleted for this project")
    mock_client.models.generate_content.side_effect = [perm_quota_err]

    with (
        patch.object(gemini, "_get_client", return_value=mock_client),
        patch("time.sleep") as mock_sleep,
        patch("app.services.llm.gemini.log_gemini_failure") as mock_log_fail,
    ):
        with pytest.raises(TriageLLMUnavailableError) as exc_info:
            gemini.extract_patient_evidence("fever")

        assert exc_info.value.code == "TRIAGE_LLM_SERVICE_UNAVAILABLE"
        assert exc_info.value.status_code == 503
        assert mock_client.models.generate_content.call_count == 1
        assert mock_sleep.call_count == 0

        mock_log_fail.assert_called_once()
        kwargs = mock_log_fail.call_args.kwargs
        assert kwargs["failure_category"] == FAILURE_CATEGORY_QUOTA_EXCEEDED
        assert kwargs["http_status"] == 429
        assert kwargs["is_quota_limit"] is True


# Scenario E: Authentication errors fail without an additional retry
def test_part2_scenario_e_authentication_error_fails_fast():
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()

    auth_err = Exception("401 UNAUTHENTICATED: API_KEY_INVALID: API key not valid. Please pass a valid API key.")
    mock_client.models.generate_content.side_effect = [auth_err]

    with (
        patch.object(gemini, "_get_client", return_value=mock_client),
        patch("time.sleep") as mock_sleep,
        patch("app.services.llm.gemini.log_gemini_failure") as mock_log_fail,
    ):
        with pytest.raises(TriageLLMUnavailableError) as exc_info:
            gemini.extract_patient_evidence("fever")

        assert exc_info.value.code == "TRIAGE_LLM_SERVICE_UNAVAILABLE"
        assert exc_info.value.status_code == 503
        assert mock_client.models.generate_content.call_count == 1
        assert mock_sleep.call_count == 0

        mock_log_fail.assert_called_once()
        kwargs = mock_log_fail.call_args.kwargs
        assert kwargs["failure_category"] == FAILURE_CATEGORY_AUTHENTICATION_ERROR
        assert kwargs["http_status"] == 401


# Scenario F: Malformed structured output retains the existing intended retry policy
def test_part2_scenario_f_malformed_structured_output_retains_intended_retry():
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()

    malformed_json = '{"chief_complaint": "headache", "items": [{"evidence_code":'
    valid_json = json.dumps({
        "chief_complaint": "headache",
        "items": [{"evidence_code": "E_127", "status": "PRESENT", "confidence": 1.0}],
    })
    mock_client.models.generate_content.side_effect = [
        _make_mock_response(malformed_json),
        _make_mock_response(valid_json),
    ]

    with (
        patch.object(gemini, "_get_client", return_value=mock_client),
        patch("time.sleep") as mock_sleep,
    ):
        res = gemini.extract_patient_evidence("headache")
        assert len(res.items) == 1
        assert res.items[0].evidence_code == "E_127"
        assert mock_client.models.generate_content.call_count == 2
        assert mock_sleep.call_count == 1
        assert mock_sleep.call_args[0][0] == 1.0


# Scenario G: Question phrasing uses the same safe retry policy
def test_part2_scenario_g1_question_phrasing_503_followed_by_success():
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()

    err_503 = Exception("503 UNAVAILABLE. The model is overloaded.")
    resp_success = _make_mock_response("Do you have a fever right now?")
    mock_client.models.generate_content.side_effect = [err_503, resp_success]

    with (
        patch.object(gemini, "_get_client", return_value=mock_client),
        patch("time.sleep") as mock_sleep,
        patch("app.services.llm.gemini.log_gemini_failure") as mock_log_fail,
    ):
        result = gemini.phrase_question("Do you have a fever?", "E_91")
        assert result == "Do you have a fever right now?"
        assert mock_client.models.generate_content.call_count == 2
        assert mock_sleep.call_count == 1
        assert 2.1 <= mock_sleep.call_args[0][0] <= 2.5
        mock_log_fail.assert_not_called()


def test_part2_scenario_g2_question_phrasing_503_both_attempts_fails_closed():
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()

    err_503 = Exception("503 UNAVAILABLE. Model overloaded.")
    mock_client.models.generate_content.side_effect = [err_503, err_503]

    with (
        patch.object(gemini, "_get_client", return_value=mock_client),
        patch("time.sleep") as mock_sleep,
        patch("app.services.llm.gemini.log_gemini_failure") as mock_log_fail,
    ):
        with pytest.raises(TriageLLMUnavailableError) as exc_info:
            gemini.phrase_question(
                "Do you have a fever?", "E_91", context={"session_id": "sess-g2", "turn_index": 2}
            )

        assert exc_info.value.code == "TRIAGE_LLM_SERVICE_UNAVAILABLE"
        assert exc_info.value.status_code == 503
        assert mock_client.models.generate_content.call_count == 2
        assert mock_sleep.call_count == 1
        assert 2.1 <= mock_sleep.call_args[0][0] <= 2.5

        mock_log_fail.assert_called_once()
        kwargs = mock_log_fail.call_args.kwargs
        assert kwargs["failure_category"] == FAILURE_CATEGORY_SERVICE_UNAVAILABLE
        assert kwargs["initial_failure_category"] == FAILURE_CATEGORY_SERVICE_UNAVAILABLE
        assert kwargs["retry_failure_category"] == FAILURE_CATEGORY_SERVICE_UNAVAILABLE
        assert kwargs["operation"] == "question_phrasing"
        assert kwargs["session_id"] == "sess-g2"
        assert kwargs["turn_index"] == 2


def test_part2_scenario_g3_question_phrasing_network_error_followed_by_success():
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()

    net_err = ConnectionResetError("Connection closed unexpectedly")
    resp_success = _make_mock_response("Are you experiencing difficulty breathing?")
    mock_client.models.generate_content.side_effect = [net_err, resp_success]

    with (
        patch.object(gemini, "_get_client", return_value=mock_client),
        patch("time.sleep") as mock_sleep,
        patch("app.services.llm.gemini.log_gemini_failure") as mock_log_fail,
    ):
        result = gemini.phrase_question("Do you have shortness of breath?", "E_66")
        assert result == "Are you experiencing difficulty breathing?"
        assert mock_client.models.generate_content.call_count == 2
        assert mock_sleep.call_count == 1
        assert 2.1 <= mock_sleep.call_args[0][0] <= 2.5
        mock_log_fail.assert_not_called()


def test_part2_scenario_g4_question_phrasing_permanent_quota_fails_fast():
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()

    perm_quota = Exception("429 ResourceExhausted: prepayment credits are depleted")
    mock_client.models.generate_content.side_effect = [perm_quota]

    with (
        patch.object(gemini, "_get_client", return_value=mock_client),
        patch("time.sleep") as mock_sleep,
        patch("app.services.llm.gemini.log_gemini_failure") as mock_log_fail,
    ):
        with pytest.raises(TriageLLMUnavailableError) as exc_info:
            gemini.phrase_question("Do you have a cough?", "E_201")

        assert exc_info.value.code == "TRIAGE_LLM_SERVICE_UNAVAILABLE"
        assert mock_client.models.generate_content.call_count == 1
        assert mock_sleep.call_count == 0
        mock_log_fail.assert_called_once()
        assert mock_log_fail.call_args.kwargs["failure_category"] == FAILURE_CATEGORY_QUOTA_EXCEEDED


# Scenario H: The maximum number of attempts is respected
def test_part2_scenario_h_maximum_number_of_attempts_is_respected():
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()

    # Even if 10 exceptions are queued, it must stop after attempt 2
    mock_client.models.generate_content.side_effect = [
        Exception("503 UNAVAILABLE"),
        Exception("503 UNAVAILABLE"),
        Exception("503 UNAVAILABLE"),
        Exception("503 UNAVAILABLE"),
    ]

    with (
        patch.object(gemini, "_get_client", return_value=mock_client),
        patch("time.sleep") as mock_sleep,
        patch("app.services.llm.gemini.log_gemini_failure"),
    ):
        with pytest.raises(TriageLLMUnavailableError):
            gemini.extract_patient_evidence("fever")

        assert mock_client.models.generate_content.call_count == 2
        assert mock_sleep.call_count == 1

