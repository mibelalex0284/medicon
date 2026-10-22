import datetime
import json
from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import TriageLLMUnavailableError
from app.models.profile import UserRole
from app.models.triage_assessment import TriageUrgency
from app.models.triage_session import TriageSessionStatus
from app.schemas.patient import PatientCreate
from app.schemas.profile import ProfileCreate
from app.schemas.specialty import SpecialtyCreate
from app.schemas.triage import TriageSessionCreate
from app.services.llm import (
    EvidenceStatus,
    ExtractedEvidenceItem,
    ExtractedEvidenceResult,
    GeminiProvider,
    LLMProvider,
    get_llm_provider,
    close_llm_provider,
    set_llm_provider,
)
from app.services.llm.gemini import (
    FAILURE_CATEGORY_QUOTA_EXCEEDED,
    FAILURE_CATEGORY_SERVICE_UNAVAILABLE,
    clear_gemini_metrics,
    get_gemini_metrics,
)
from app.services.patient_service import patient_service
from app.services.profile_service import profile_service
from app.services.specialty_service import specialty_service
from app.services.triage.evidence_provider import ddxplus_provider
from app.services.triage.orchestrator import ConversationalTriageOrchestrator
from app.services.triage_service import triage_service


def _make_mock_response(text: str, finish_reason: str = "STOP", prompt_tokens: int = 150, output_tokens: int = 50):
    mock_resp = MagicMock()
    mock_cand = MagicMock()
    mock_cand.finish_reason = finish_reason
    mock_resp.candidates = [mock_cand]
    mock_resp.text = text

    # Mock UsageMetadata with concrete integers
    mock_usage = MagicMock()
    mock_usage.prompt_token_count = prompt_tokens
    mock_usage.candidates_token_count = output_tokens
    mock_usage.total_token_count = prompt_tokens + output_tokens
    mock_resp.usage_metadata = mock_usage

    return mock_resp


@pytest.fixture(autouse=True)
def clean_metrics_and_provider():
    clear_gemini_metrics()
    close_llm_provider()
    yield
    clear_gemini_metrics()
    close_llm_provider()


@pytest.fixture
def test_patient(db_session: Session):
    prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="pat-opt-usr-1",
            role=UserRole.PATIENT,
            full_name="Optimization Test Patient",
            email="opt.patient@test.org",
        ),
    )
    patient = patient_service.create_patient(
        db_session,
        PatientCreate(profile_id=prof.id, date_of_birth=datetime.date(1990, 1, 1)),
    )
    for name, code in [
        ("General Medicine", "GEN"),
        ("Cardiology", "CARDIO"),
        ("ENT", "ENT"),
        ("Dermatology", "DERM"),
        ("Orthopedics", "ORTHO"),
    ]:
        try:
            specialty_service.create_specialty(
                db_session, SpecialtyCreate(name=name, code=code)
            )
        except Exception:
            pass
    return patient


# ==============================================================================
# TEST 1: Normal evidence extraction with structured SDK metrics observability
# ==============================================================================
def test_normal_evidence_extraction_with_sdk_metrics():
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()

    valid_json = json.dumps({
        "chief_complaint": "persistent cough",
        "duration": "4 days",
        "severity": 5,
        "measurements": [],
        "items": [{"evidence_code": "E_201", "status": "PRESENT", "confidence": 0.95}],
    })
    mock_resp = _make_mock_response(valid_json, prompt_tokens=142, output_tokens=38)
    mock_client.models.generate_content.return_value = mock_resp

    with patch.object(gemini, "_get_client", return_value=mock_client), patch("time.sleep"):
        res = gemini.extract_patient_evidence(
            message="I have had a persistent cough for 4 days.",
            context={"session_id": "sess-123", "turn_index": 1},
        )

        assert isinstance(res, ExtractedEvidenceResult)
        assert res.chief_complaint == "persistent cough"
        assert res.duration == "4 days"
        assert res.severity == 5
        assert len(res.items) == 1
        assert res.items[0].evidence_code == "E_201"

        # Verify structured observability metrics
        metrics = get_gemini_metrics()
        assert len(metrics) == 1
        m = metrics[0]
        assert m["provider"] == "gemini"
        assert m["operation"] == "evidence_extraction"
        assert m["attempts"] == 1
        assert m["status"] == "SUCCESS"
        assert m["retry_occurred"] is False
        assert m["duration_ms"] >= 0.0
        assert m["input_tokens"] == 142
        assert m["output_tokens"] == 38
        assert m["total_tokens"] == 180
        assert m["session_id"] == "sess-123"
        assert m["turn_index"] == 1


# ==============================================================================
# TEST 2: Transient 503 followed by success (bounded retry & metrics)
# ==============================================================================
class MockGeminiAPIError(Exception):
    """Deterministic mock of google.genai APIError/ServerError."""
    def __init__(self, message: str, code: int = 503, status: str = "UNAVAILABLE", headers: dict = None, details: dict = None):
        super().__init__(message)
        self.code = code
        self.status = status
        self.response = MagicMock()
        self.response.status_code = code
        self.response.headers = headers or {}
        self.details = details


# ==============================================================================
# TEST 2: HTTP 503 with a valid bounded Retry-After value
# ==============================================================================
def test_transient_503_with_valid_retry_after():
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()

    valid_json = json.dumps({
        "chief_complaint": "fever",
        "duration": "2 days",
        "severity": 3,
        "measurements": [],
        "items": [{"evidence_code": "E_181", "status": "PRESENT", "confidence": 0.9}],
    })
    mock_resp = _make_mock_response(valid_json, prompt_tokens=100, output_tokens=25)

    # 503 with Retry-After: 3.5 in headers
    err_with_retry_after = MockGeminiAPIError(
        message="503 Service Unavailable",
        code=503,
        status="UNAVAILABLE",
        headers={"Retry-After": "3.5"},
        details={"error": {"details": [{"reason": "MODEL_OVERLOADED"}]}},
    )
    mock_client.models.generate_content.side_effect = [err_with_retry_after, mock_resp]

    with patch.object(gemini, "_get_client", return_value=mock_client), patch("time.sleep") as mock_sleep:
        res = gemini.extract_patient_evidence("I have a fever since yesterday.")

        assert isinstance(res, ExtractedEvidenceResult)
        assert mock_client.models.generate_content.call_count == 2
        assert mock_sleep.call_count == 1
        # Exactly respects the 3.5s Retry-After value
        assert mock_sleep.call_args[0][0] == 3.5

        # Verify metrics captured attempt and retry
        metrics = get_gemini_metrics()
        assert len(metrics) == 1
        m = metrics[0]
        assert m["operation"] == "evidence_extraction"
        assert m["attempts"] == 2
        assert m["retry_occurred"] is True
        assert m["status"] == "SUCCESS"


# ==============================================================================
# TEST 3: HTTP 503 without Retry-After uses adaptive exponential backoff + jitter
# ==============================================================================
def test_transient_503_without_retry_after_uses_adaptive_jitter():
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()

    valid_json = json.dumps({
        "chief_complaint": "headache",
        "duration": "1 day",
        "severity": 4,
        "measurements": [],
        "items": [{"evidence_code": "E_127", "status": "PRESENT", "confidence": 1.0}],
    })
    mock_resp = _make_mock_response(valid_json, prompt_tokens=120, output_tokens=30)
    mock_client.models.generate_content.side_effect = [
        Exception("503 The service is temporarily unavailable. Please retry."),
        mock_resp,
    ]

    with patch.object(gemini, "_get_client", return_value=mock_client), patch("time.sleep") as mock_sleep:
        res = gemini.extract_patient_evidence("I have a headache since yesterday.")

        assert isinstance(res, ExtractedEvidenceResult)
        assert mock_client.models.generate_content.call_count == 2
        assert mock_sleep.call_count == 1
        # Adaptive backoff for attempt 0: base 2.0s + jitter [0.1, 0.4] => [2.1, 2.5]
        sleep_duration = mock_sleep.call_args[0][0]
        assert 2.1 <= sleep_duration <= 2.5

        metrics = get_gemini_metrics()
        assert len(metrics) == 1
        assert metrics[0]["attempts"] == 2
        assert metrics[0]["retry_occurred"] is True
        assert metrics[0]["status"] == "SUCCESS"


# ==============================================================================
# TEST 4: Malformed or unreasonable Retry-After values fall back or are bounded
# ==============================================================================
def test_malformed_or_unreasonable_retry_after():
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()

    valid_json = json.dumps({
        "chief_complaint": "ear pain",
        "duration": "1 day",
        "severity": 2,
        "measurements": [],
        "items": [{"evidence_code": "E_45", "status": "PRESENT", "confidence": 0.8}],
    })
    mock_resp = _make_mock_response(valid_json)

    # Sub-case A: Unreasonable Retry-After (e.g. 3600 seconds) -> rejected (>30s), falls back to adaptive
    err_unreasonable = MockGeminiAPIError(
        message="503 Service Unavailable",
        headers={"Retry-After": "3600"},
    )
    mock_client.models.generate_content.side_effect = [err_unreasonable, mock_resp]

    with patch.object(gemini, "_get_client", return_value=mock_client), patch("time.sleep") as mock_sleep:
        gemini.extract_patient_evidence("Ear pain")
        assert mock_sleep.call_count == 1
        # Rejected unreasonable 3600s, fell back to 2.1 - 2.5s
        assert 2.1 <= mock_sleep.call_args[0][0] <= 2.5

    # Sub-case B: Malformed Retry-After (e.g. "not-a-number") -> rejected, falls back to adaptive
    mock_sleep.reset_mock()
    err_malformed = MockGeminiAPIError(
        message="503 Service Unavailable",
        headers={"Retry-After": "invalid-timestamp-value"},
    )
    mock_client.models.generate_content.side_effect = [err_malformed, mock_resp]

    with patch.object(gemini, "_get_client", return_value=mock_client), patch("time.sleep") as mock_sleep:
        gemini.extract_patient_evidence("Ear pain")
        assert mock_sleep.call_count == 1
        assert 2.1 <= mock_sleep.call_args[0][0] <= 2.5

    # Sub-case C: Bounded Retry-After (e.g. 15.0s is <= 30s so accepted, but capped at 6.0s max delay)
    mock_sleep.reset_mock()
    err_large_bounded = MockGeminiAPIError(
        message="503 Service Unavailable",
        headers={"Retry-After": "15.0"},
    )
    mock_client.models.generate_content.side_effect = [err_large_bounded, mock_resp]

    with patch.object(gemini, "_get_client", return_value=mock_client), patch("time.sleep") as mock_sleep:
        gemini.extract_patient_evidence("Ear pain")
        assert mock_sleep.call_count == 1
        assert mock_sleep.call_args[0][0] == 6.0  # strictly capped to 6.0s max delay


# ==============================================================================
# TEST 5: Repeated 503 responses exhaust attempt budget and fail closed
# ==============================================================================
def test_repeated_503_exhausts_attempt_budget_and_fails_closed():
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()

    err_503_1 = MockGeminiAPIError("503 Service Unavailable", code=503, status="UNAVAILABLE")
    err_503_2 = MockGeminiAPIError("503 Service Unavailable", code=503, status="UNAVAILABLE")
    mock_client.models.generate_content.side_effect = [err_503_1, err_503_2]

    with patch.object(gemini, "_get_client", return_value=mock_client), patch("time.sleep") as mock_sleep:
        with pytest.raises(TriageLLMUnavailableError) as exc_info:
            gemini.extract_patient_evidence("Persistent fever")

        assert exc_info.value.code == "TRIAGE_LLM_SERVICE_UNAVAILABLE"
        assert exc_info.value.status_code == 503

        # Budget verification: strictly 2 attempts (1 initial + 1 retry), exactly 1 sleep
        assert mock_client.models.generate_content.call_count == 2
        assert mock_sleep.call_count == 1

        # Observability verification
        metrics = get_gemini_metrics()
        assert len(metrics) == 1
        m = metrics[0]
        assert m["operation"] == "evidence_extraction"
        assert m["attempts"] == 2
        assert m["status"] == FAILURE_CATEGORY_SERVICE_UNAVAILABLE
        assert m["retry_occurred"] is True
        assert m["http_status"] == 503
        assert m["upstream_status"] == "UNAVAILABLE"


# ==============================================================================
# TEST 6: HTTP 429 quota exhaustion is distinguished from 503 and fails fast
# ==============================================================================
def test_http_429_quota_exhaustion_distinguished_and_fails_fast():
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()

    permanent_quota_err = MockGeminiAPIError(
        message="429 Resource exhausted: prepayment credits are depleted for project 12345678.",
        code=429,
        status="RESOURCE_EXHAUSTED",
        details={"error": {"details": [{"reason": "QUOTA_EXHAUSTED"}]}},
    )
    mock_client.models.generate_content.side_effect = permanent_quota_err

    with patch.object(gemini, "_get_client", return_value=mock_client), patch("time.sleep") as mock_sleep:
        with pytest.raises(TriageLLMUnavailableError) as exc_info:
            gemini.extract_patient_evidence("I have a sore throat.")

        assert exc_info.value.code == "TRIAGE_LLM_SERVICE_UNAVAILABLE"
        assert exc_info.value.status_code == 503
        # Strict fail-fast: exactly 1 call, 0 sleep/retries
        assert mock_client.models.generate_content.call_count == 1
        assert mock_sleep.call_count == 0

        # Verify failure metric: is_quota_limit=True, status=QUOTA_EXCEEDED
        metrics = get_gemini_metrics()
        assert len(metrics) == 1
        m = metrics[0]
        assert m["operation"] == "evidence_extraction"
        assert m["attempts"] == 1
        assert m["retry_occurred"] is False
        assert m["status"] == FAILURE_CATEGORY_QUOTA_EXCEEDED
        assert m["http_status"] == 429
        assert m["upstream_status"] == "RESOURCE_EXHAUSTED"
        assert m["upstream_reason"] == "QUOTA_EXHAUSTED"


# ==============================================================================
# TEST 7: Authentication errors fail fast with zero retries
# ==============================================================================
def test_authentication_error_fails_immediately_without_retry():
    gemini = GeminiProvider(api_key="test-mock-key")
    mock_client = MagicMock()

    auth_err = MockGeminiAPIError(
        message="401 UNAUTHENTICATED: API key not valid. Please pass a valid API key.",
        code=401,
        status="UNAUTHENTICATED",
        details={"error": {"details": [{"reason": "API_KEY_INVALID"}]}},
    )
    mock_client.models.generate_content.side_effect = auth_err

    with patch.object(gemini, "_get_client", return_value=mock_client), patch("time.sleep") as mock_sleep:
        with pytest.raises(TriageLLMUnavailableError) as exc_info:
            gemini.extract_patient_evidence("I have joint pain.")

        assert exc_info.value.code == "TRIAGE_LLM_SERVICE_UNAVAILABLE"
        assert exc_info.value.status_code == 503
        # Strict fail-fast: exactly 1 call, 0 sleep/retries
        assert mock_client.models.generate_content.call_count == 1
        assert mock_sleep.call_count == 0

        metrics = get_gemini_metrics()
        assert len(metrics) == 1
        m = metrics[0]
        assert m["attempts"] == 1
        assert m["retry_occurred"] is False
        assert m["status"] == "AUTHENTICATION_ERROR"
        assert m["http_status"] == 401
        assert m["upstream_status"] == "UNAUTHENTICATED"
        assert m["upstream_reason"] == "API_KEY_INVALID"


# ==============================================================================
# TEST 8: Safe logging excludes secrets, patient prompts, and health details
# ==============================================================================
def test_safe_logging_never_exposes_secrets_or_patient_text(caplog):
    import logging
    caplog.set_level(logging.DEBUG)

    gemini = GeminiProvider(api_key="AIzaSyD-super-secret-api-key-999")
    mock_client = MagicMock()

    # Exception containing API key and upstream prompt reference
    leaky_upstream_err = MockGeminiAPIError(
        message="503 Service Unavailable for key AIzaSyD-super-secret-api-key-999 on model gemini-3.6-flash",
        code=503,
        status="UNAVAILABLE",
    )
    mock_client.models.generate_content.side_effect = [leaky_upstream_err, leaky_upstream_err]

    sensitive_patient_prompt = "Patient SSN 999-88-7777 has severe private genital rash and acute pain."

    with patch.object(gemini, "_get_client", return_value=mock_client), patch("time.sleep"):
        with pytest.raises(TriageLLMUnavailableError):
            gemini.extract_patient_evidence(
                message=sensitive_patient_prompt,
                context={"session_id": "sess-safe-1", "turn_index": 2},
            )

    captured_text = caplog.text

    # 1. API key must NEVER appear in logs
    assert "AIzaSyD-super-secret-api-key-999" not in captured_text

    # 2. Raw patient text and sensitive health identifiers must NEVER appear in logs
    assert "999-88-7777" not in captured_text
    assert "genital rash" not in captured_text
    assert sensitive_patient_prompt not in captured_text

    # 3. Safe telemetry markers MUST appear
    assert "[GEMINI_FAILURE]" in captured_text
    assert "[GEMINI_METRIC]" in captured_text


# ==============================================================================
# TEST 4: Question selection uses controlled wording without phrasing call
# ==============================================================================
def test_question_selection_uses_controlled_wording_without_phrasing_call(db_session: Session, test_patient):
    session = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="Mild cough"),
        actor_auth_user_id="pat-opt-usr-1",
    )

    # Mock LLMProvider where phrase_question must NOT be invoked
    mock_llm = MagicMock(spec=LLMProvider)
    mock_llm.extract_patient_evidence.return_value = ExtractedEvidenceResult(
        chief_complaint="Mild cough",
        items=[ExtractedEvidenceItem(evidence_code="E_201", status=EvidenceStatus.PRESENT)],
    )

    orchestrator = ConversationalTriageOrchestrator(
        db=db_session,
        llm_provider=mock_llm,
    )

    turn = orchestrator.process_patient_turn(
        session_id=session.id,
        patient_message_text="I have had a mild cough for two days.",
        actor_auth_user_id="pat-opt-usr-1",
    )

    # 1. Verification: Evidence extraction was called exactly once
    assert mock_llm.extract_patient_evidence.call_count == 1

    # 2. Critical request saving verification: phrase_question was NOT called at all
    assert mock_llm.phrase_question.call_count == 0

    # 3. Controlled wording matches ontology question text exactly
    assert turn.is_complete is False
    assert turn.selected_question is not None
    assert turn.assistant_message == turn.selected_question.question_text
    assert len(turn.assistant_message) > 0


# ==============================================================================
# TEST 5: Emergency safety behavior remains unchanged
# ==============================================================================
def test_emergency_safety_pre_extraction_red_flag_makes_zero_llm_calls(db_session: Session, test_patient):
    session = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="Emergency chest pain"),
        actor_auth_user_id="pat-opt-usr-1",
    )

    mock_llm = MagicMock(spec=LLMProvider)
    orchestrator = ConversationalTriageOrchestrator(
        db=db_session,
        llm_provider=mock_llm,
    )

    turn = orchestrator.process_patient_turn(
        session_id=session.id,
        patient_message_text="I have severe crushing chest pain radiating to my left arm.",
        actor_auth_user_id="pat-opt-usr-1",
    )

    # Pre-extraction deterministic screening escalates immediately
    assert turn.is_complete is True
    assert turn.stop_reason == "EMERGENCY_RED_FLAG"
    assert "RED_FLAG_CHEST_PAIN_SEVERE" in turn.safety_flags
    assert turn.assessment.urgency == TriageUrgency.HIGH
    assert turn.assessment.red_flag_detected is True

    # Zero LLM requests consumed on emergency pre-screening
    assert mock_llm.extract_patient_evidence.call_count == 0
    assert mock_llm.phrase_question.call_count == 0


def test_emergency_safety_post_extraction_critical_evidence_escalates(db_session: Session, test_patient):
    session = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="Breathing difficulty"),
        actor_auth_user_id="pat-opt-usr-1",
    )

    mock_llm = MagicMock(spec=LLMProvider)
    # E_66 is critical dyspnea
    mock_llm.extract_patient_evidence.return_value = ExtractedEvidenceResult(
        chief_complaint="trouble breathing",
        items=[ExtractedEvidenceItem(evidence_code="E_66", status=EvidenceStatus.PRESENT)],
    )

    orchestrator = ConversationalTriageOrchestrator(
        db=db_session,
        llm_provider=mock_llm,
    )

    turn = orchestrator.process_patient_turn(
        session_id=session.id,
        patient_message_text="I am struggling to catch my breath.",
        actor_auth_user_id="pat-opt-usr-1",
    )

    # Post-extraction gate catches E_66 and escalates
    assert turn.is_complete is True
    assert turn.stop_reason == "EMERGENCY_RED_FLAG"
    assert "RED_FLAG_BREATHING_DIFFICULTY" in turn.safety_flags
    assert turn.assessment.urgency == TriageUrgency.HIGH
    assert turn.assessment.red_flag_detected is True
    assert mock_llm.phrase_question.call_count == 0


# ==============================================================================
# TEST 6: No fake successful result when required AI extraction fails
# ==============================================================================
def test_no_fake_successful_result_when_required_extraction_fails(db_session: Session, test_patient):
    session = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="Skin rash"),
        actor_auth_user_id="pat-opt-usr-1",
    )

    failing_llm = MagicMock(spec=LLMProvider)
    failing_llm.extract_patient_evidence.side_effect = TriageLLMUnavailableError(
        message="Conversational triage is temporarily unavailable. Please try again later or contact your care provider directly.",
        code="TRIAGE_LLM_SERVICE_UNAVAILABLE",
    )

    orchestrator = ConversationalTriageOrchestrator(
        db=db_session,
        llm_provider=failing_llm,
    )

    with pytest.raises(TriageLLMUnavailableError) as exc_info:
        orchestrator.process_patient_turn(
            session_id=session.id,
            patient_message_text="I have red patches on my skin.",
            actor_auth_user_id="pat-opt-usr-1",
        )

    # Verify fail-closed behavior: 503 raised, session remains IN_PROGRESS (not fake completed)
    assert exc_info.value.code == "TRIAGE_LLM_SERVICE_UNAVAILABLE"
    assert exc_info.value.status_code == 503

    db_session.refresh(session)
    assert session.status == TriageSessionStatus.IN_PROGRESS
    assert session.completed_at is None


# ==============================================================================
# TEST 7: Controlled question bank validation
# ==============================================================================
def test_controlled_question_bank_wording_quality():
    """Verify that clinical ontology contains reviewed patient-facing wording for questions."""
    evidences = ddxplus_provider.get_all_evidences()
    assert len(evidences) > 0

    critical_codes = ["E_66", "E_159", "E_45", "E_211", "E_53", "E_201", "E_91", "E_181"]
    for code in critical_codes:
        q_text = ddxplus_provider.get_evidence_question(code, lang="en")
        assert q_text is not None
        assert len(q_text.strip()) > 10
        assert q_text.strip().endswith("?")


# ==============================================================================
# OPTIMIZATION A TESTS: Provider & Client Lifecycle Reuse
# ==============================================================================
def test_provider_reuse_and_client_lifecycle():
    """Verify application-lifetime provider and underlying client reuse and closing."""
    # 1. Multiple get_llm_provider calls return the same singleton instance
    p1 = get_llm_provider()
    p2 = get_llm_provider()
    assert p1 is p2
    assert isinstance(p1, GeminiProvider)

    # 2. Underlying genai.Client reuse across calls
    mock_genai_client = MagicMock()
    with patch("google.genai.Client", return_value=mock_genai_client):
        c1 = p1._get_client()
        c2 = p1._get_client()
        assert c1 is c2
        assert c1 is mock_genai_client

    # 3. Correct cleanup during application shutdown
    close_llm_provider()
    mock_genai_client.close.assert_called_once()
    assert p1._client is None

    # 4. Next get_llm_provider call creates a fresh singleton
    p3 = get_llm_provider()
    assert p3 is not p1


# ==============================================================================
# OPTIMIZATION B TESTS: Deterministic Extraction of Unambiguous Answers
# ==============================================================================
def _setup_session_with_active_question(db_session: Session, evidence_id: str, question_text: str):
    """Helper to create a session with an active assistant question in message history."""
    from app.repositories.triage_repository import triage_repo
    session = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="Initial complaint"),
        actor_auth_user_id="pat-opt-usr-1",
    )
    triage_repo.add_message(
        db=db_session,
        session_id=session.id,
        sender="patient",
        content="I have an initial complaint",
        turn_index=1,
        extracted_evidence=json.dumps([{"evidence_code": "E_201", "status": "PRESENT"}]),
    )
    triage_repo.add_message(
        db=db_session,
        session_id=session.id,
        sender="assistant",
        content=question_text,
        turn_index=1,
        extracted_evidence=json.dumps({
            "selected_evidence_id": evidence_id,
            "information_gain": 0.45,
        }),
    )
    db_session.commit()
    return session


def test_deterministic_extraction_yes_mapped_to_present(db_session: Session, test_patient):
    """Exact 'yes' answer maps to PRESENT and bypasses Gemini."""
    session = _setup_session_with_active_question(
        db_session,
        evidence_id="E_91",
        question_text="Do you have chills or shivering?",
    )

    mock_llm = MagicMock(spec=LLMProvider)
    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=mock_llm)

    turn = orchestrator.process_patient_turn(
        session_id=session.id,
        patient_message_text="Yes.",
        actor_auth_user_id="pat-opt-usr-1",
    )

    # Gemini must NOT be called
    assert mock_llm.extract_patient_evidence.call_count == 0
    assert turn.is_complete is False
    assert len(turn.extracted_evidences) == 1
    assert turn.extracted_evidences[0]["evidence_code"] == "E_91"
    assert turn.extracted_evidences[0]["status"] == "PRESENT"


def test_deterministic_extraction_no_mapped_to_absent(db_session: Session, test_patient):
    """Exact 'no' or 'nope' answer maps to ABSENT and bypasses Gemini."""
    session = _setup_session_with_active_question(
        db_session,
        evidence_id="E_91",
        question_text="Do you have chills or shivering?",
    )

    mock_llm = MagicMock(spec=LLMProvider)
    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=mock_llm)

    turn_strict_no = orchestrator.process_patient_turn(
        session_id=session.id,
        patient_message_text="No.",
        actor_auth_user_id="pat-opt-usr-1",
    )

    # Gemini must NOT be called for strict "No."
    assert mock_llm.extract_patient_evidence.call_count == 0
    assert turn_strict_no.is_complete is False
    assert len(turn_strict_no.extracted_evidences) == 1
    assert turn_strict_no.extracted_evidences[0]["evidence_code"] == "E_91"
    assert turn_strict_no.extracted_evidences[0]["status"] == "ABSENT"


def test_deterministic_extraction_ambiguous_answers_use_gemini(db_session: Session, test_patient):
    """Ambiguous replies such as 'not sure' or 'maybe' must NOT be shortcut and must invoke Gemini."""
    session = _setup_session_with_active_question(
        db_session,
        evidence_id="E_91",
        question_text="Do you have chills or shivering?",
    )

    mock_llm = MagicMock(spec=LLMProvider)
    mock_llm.extract_patient_evidence.return_value = ExtractedEvidenceResult(
        items=[ExtractedEvidenceItem(evidence_code="E_91", status=EvidenceStatus.UNKNOWN)]
    )
    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=mock_llm)

    # 1. "not sure" must invoke Gemini
    orchestrator.process_patient_turn(
        session_id=session.id,
        patient_message_text="not sure",
        actor_auth_user_id="pat-opt-usr-1",
    )
    assert mock_llm.extract_patient_evidence.call_count == 1

    # 2. "maybe" must invoke Gemini
    mock_llm.reset_mock()
    orchestrator.process_patient_turn(
        session_id=session.id,
        patient_message_text="maybe",
        actor_auth_user_id="pat-opt-usr-1",
    )
    assert mock_llm.extract_patient_evidence.call_count == 1


def test_deterministic_extraction_additional_symptoms_use_gemini(db_session: Session, test_patient):
    """Replies containing additional non-emergency symptoms must invoke full Gemini extraction."""
    session = _setup_session_with_active_question(
        db_session,
        evidence_id="E_91",
        question_text="Do you have chills or shivering?",
    )

    mock_llm = MagicMock(spec=LLMProvider)
    mock_llm.extract_patient_evidence.return_value = ExtractedEvidenceResult(
        items=[
            ExtractedEvidenceItem(evidence_code="E_91", status=EvidenceStatus.ABSENT),
            ExtractedEvidenceItem(evidence_code="E_201", status=EvidenceStatus.PRESENT),
        ]
    )
    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=mock_llm)

    orchestrator.process_patient_turn(
        session_id=session.id,
        patient_message_text="No, but I also have a mild cough",
        actor_auth_user_id="pat-opt-usr-1",
    )

    # Must retain full Gemini extraction
    assert mock_llm.extract_patient_evidence.call_count == 1


def test_deterministic_extraction_additional_duration_uses_gemini(db_session: Session, test_patient):
    """Replies containing duration details (e.g. 'Yes for 3 days') must invoke Gemini to extract duration."""
    session = _setup_session_with_active_question(
        db_session,
        evidence_id="E_91",
        question_text="Do you have chills or shivering?",
    )

    mock_llm = MagicMock(spec=LLMProvider)
    mock_llm.extract_patient_evidence.return_value = ExtractedEvidenceResult(
        duration="3 days",
        items=[ExtractedEvidenceItem(evidence_code="E_91", status=EvidenceStatus.PRESENT)],
    )
    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=mock_llm)

    orchestrator.process_patient_turn(
        session_id=session.id,
        patient_message_text="Yes for 3 days",
        actor_auth_user_id="pat-opt-usr-1",
    )

    # Must retain full Gemini extraction to parse duration
    assert mock_llm.extract_patient_evidence.call_count == 1


def test_deterministic_extraction_missing_or_compound_question_uses_gemini(db_session: Session, test_patient):
    """When active question is missing or compound (multiple questions), Gemini is invoked."""
    mock_llm = MagicMock(spec=LLMProvider)
    mock_llm.extract_patient_evidence.return_value = ExtractedEvidenceResult(
        items=[ExtractedEvidenceItem(evidence_code="E_201", status=EvidenceStatus.PRESENT)]
    )

    # Case A: Turn 1 (no prior assistant question)
    session_no_q = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="Cough"),
        actor_auth_user_id="pat-opt-usr-1",
    )
    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=mock_llm)

    orchestrator.process_patient_turn(
        session_id=session_no_q.id,
        patient_message_text="Yes",
        actor_auth_user_id="pat-opt-usr-1",
    )
    assert mock_llm.extract_patient_evidence.call_count == 1

    # Case B: Compound question with multiple question marks
    mock_llm.reset_mock()
    session_compound = _setup_session_with_active_question(
        db_session,
        evidence_id="E_91",
        question_text="Do you have chills? Do you also have a fever?",
    )
    orchestrator.process_patient_turn(
        session_id=session_compound.id,
        patient_message_text="Yes",
        actor_auth_user_id="pat-opt-usr-1",
    )
    assert mock_llm.extract_patient_evidence.call_count == 1


def test_deterministic_extraction_emergency_red_flag_escalates_immediately(db_session: Session, test_patient):
    """When active question investigates an emergency red-flag evidence (E_66), 'yes' escalates immediately."""
    session = _setup_session_with_active_question(
        db_session,
        evidence_id="E_66",
        question_text="Are you struggling to breathe?",
    )

    mock_llm = MagicMock(spec=LLMProvider)
    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=mock_llm)

    turn = orchestrator.process_patient_turn(
        session_id=session.id,
        patient_message_text="Yes",
        actor_auth_user_id="pat-opt-usr-1",
    )

    # Gemini extraction was bypassed
    assert mock_llm.extract_patient_evidence.call_count == 0
    # But emergency safety post-screening caught E_66 and escalated immediately
    assert turn.is_complete is True
    assert turn.stop_reason == "EMERGENCY_RED_FLAG"
    assert "RED_FLAG_BREATHING_DIFFICULTY" in turn.safety_flags
    assert turn.assessment.urgency == TriageUrgency.HIGH
    assert turn.assessment.red_flag_detected is True

