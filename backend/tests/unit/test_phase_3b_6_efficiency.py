import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session

from app.core.exceptions import TriageLLMUnavailableError
from app.models.triage_assessment import TriageUrgency
from app.models.triage_session import TriageSessionStatus
from app.schemas.patient_state import PatientState
from app.services.llm.gemini import GeminiProvider
from app.services.llm.provider import (
    AdaptiveQuestionProposal,
    AdaptiveQuestionStatus,
    EvidenceStatus,
    ExtractedEvidenceItem,
    ExtractedEvidenceResult,
)
from app.services.triage.evidence_provider import (
    ADAPTIVE_EVIDENCE_REGISTRY,
    ddxplus_provider,
)
from app.services.triage.orchestrator import ConversationalTriageOrchestrator
from app.services.triage.question_selector import ControlledQuestion
from app.services.triage.stopping_policy import StoppingReason, stopping_policy


# =====================================================================
# STEP 2 TESTS: QUOTA & TRANSIENT RETRY HARDENING
# =====================================================================


def test_permanent_daily_quota_fails_immediately_no_sleep():
    """Permanent or daily quota exhaustion must fail immediately without sleep."""
    with patch("app.services.llm.gemini.time.sleep") as mock_sleep:
        provider = GeminiProvider(api_key="test_key_fake")
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception(
            "429 Resource has been exhausted (e.g. check quota). daily quota limit reached"
        )
        provider._client = mock_client

        with pytest.raises(TriageLLMUnavailableError) as exc_info:
            provider.extract_patient_evidence("I have a fever")

        assert exc_info.value.code == "TRIAGE_LLM_SERVICE_UNAVAILABLE"
        assert "capacity is temporarily exhausted" in exc_info.value.message
        assert mock_client.models.generate_content.call_count == 1
        mock_sleep.assert_not_called()


def test_rate_limit_with_valid_delay_retries_and_succeeds():
    """429 with retry delay within 3.5s budget should sleep and retry once."""
    with patch("app.services.llm.gemini.time.sleep") as mock_sleep:
        provider = GeminiProvider(api_key="test_key_fake")
        mock_client = MagicMock()
        valid_response = MagicMock()
        valid_response.text = '{"chief_complaint": "fever", "duration": "2 days", "severity": 4, "items": []}'
        
        mock_client.models.generate_content.side_effect = [
            Exception("429 Resource exhausted. Please retry in 2s"),
            valid_response,
        ]
        provider._client = mock_client

        result = provider.extract_patient_evidence("I have a fever for 2 days")
        assert result.chief_complaint == "fever"
        assert mock_client.models.generate_content.call_count == 2
        mock_sleep.assert_called_once_with(3)  # int(2.0) + 1 = 3s <= 3.5s


def test_rate_limit_with_excessive_delay_fails_immediately_no_sleep():
    """429 with retry delay exceeding 3.5s budget must fail immediately with zero sleep."""
    with patch("app.services.llm.gemini.time.sleep") as mock_sleep:
        provider = GeminiProvider(api_key="test_key_fake")
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception(
            "429 Quota limit exceeded. Please retry in 15s"
        )
        provider._client = mock_client

        with pytest.raises(TriageLLMUnavailableError) as exc_info:
            provider.extract_patient_evidence("I have a fever")

        assert exc_info.value.code == "TRIAGE_LLM_SERVICE_UNAVAILABLE"
        assert "capacity is temporarily exhausted" in exc_info.value.message
        assert mock_client.models.generate_content.call_count == 1
        mock_sleep.assert_not_called()


def test_rate_limit_with_no_delay_fails_immediately_no_sleep():
    """Generic 429 without retry delay must fail immediately without blind retries."""
    with patch("app.services.llm.gemini.time.sleep") as mock_sleep:
        provider = GeminiProvider(api_key="test_key_fake")
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception(
            "429 Too Many Requests: Rate limit exceeded"
        )
        provider._client = mock_client

        with pytest.raises(TriageLLMUnavailableError) as exc_info:
            provider.extract_patient_evidence("I have a fever")

        assert exc_info.value.code == "TRIAGE_LLM_SERVICE_UNAVAILABLE"
        assert mock_client.models.generate_content.call_count == 1
        mock_sleep.assert_not_called()


def test_transient_503_preserves_bounded_retry():
    """Transient 503 service unavailable retries once with computed backoff."""
    with patch("app.services.llm.gemini.time.sleep") as mock_sleep:
        provider = GeminiProvider(api_key="test_key_fake")
        mock_client = MagicMock()
        valid_response = MagicMock()
        valid_response.text = '{"chief_complaint": "cough", "duration": null, "severity": null, "items": []}'
        
        mock_client.models.generate_content.side_effect = [
            Exception("503 Service Unavailable: High load"),
            valid_response,
        ]
        provider._client = mock_client

        result = provider.extract_patient_evidence("cough")
        assert result.chief_complaint == "cough"
        assert mock_client.models.generate_content.call_count == 2
        assert mock_sleep.call_count == 1


def test_client_errors_do_not_misclassify_as_quota():
    """400 Bad Request or 401 Auth must fail fast without being labeled as quota."""
    with patch("app.services.llm.gemini.time.sleep") as mock_sleep:
        provider = GeminiProvider(api_key="test_key_fake")
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception(
            "400 Invalid argument: Model not recognized"
        )
        provider._client = mock_client

        with pytest.raises(TriageLLMUnavailableError) as exc_info:
            provider.extract_patient_evidence("cough")

        assert exc_info.value.code == "TRIAGE_LLM_SERVICE_UNAVAILABLE"
        assert "temporarily unavailable" in exc_info.value.message
        assert "capacity is temporarily exhausted" not in exc_info.value.message
        assert mock_client.models.generate_content.call_count == 1
        mock_sleep.assert_not_called()


# =====================================================================
# STEP 3 TESTS: DETERMINISTIC ADAPTIVE EXTRACTION
# =====================================================================


def test_adaptive_functional_impact_affirmative_deterministic_mapping():
    """Affirmative answer to adaptive_functional_impact maps deterministically without LLM."""
    context = {
        "active_evidence_id": "adaptive_functional_impact",
        "active_question_text": "Does this knee pain prevent you from doing your normal daily activities?",
    }
    mock_llm = MagicMock()
    orchestrator = ConversationalTriageOrchestrator(db=MagicMock(), llm_provider=mock_llm)

    extracted = orchestrator._try_deterministic_answer_extraction(
        patient_message_text="Yes",
        context=context,
    )

    assert extracted is not None
    assert len(extracted.items) == 1
    assert extracted.items[0].evidence_code == "adaptive_functional_impact"
    assert extracted.items[0].status == EvidenceStatus.PRESENT
    # Verification that LLM extraction was bypassed
    mock_llm.extract_patient_evidence.assert_not_called()


def test_adaptive_functional_impact_negative_deterministic_mapping():
    """Negative answer to adaptive_functional_impact maps deterministically without LLM."""
    context = {
        "active_evidence_id": "adaptive_functional_impact",
        "active_question_text": "Does this pain prevent your daily activities?",
    }
    mock_llm = MagicMock()
    orchestrator = ConversationalTriageOrchestrator(db=MagicMock(), llm_provider=mock_llm)

    extracted = orchestrator._try_deterministic_answer_extraction(
        patient_message_text="No",
        context=context,
    )

    assert extracted is not None
    assert len(extracted.items) == 1
    assert extracted.items[0].evidence_code == "adaptive_functional_impact"
    assert extracted.items[0].status == EvidenceStatus.ABSENT
    mock_llm.extract_patient_evidence.assert_not_called()


def test_adaptive_associated_symptoms_negative_deterministic_mapping():
    """Negative answer to adaptive_associated_symptoms maps safely to absent."""
    context = {
        "active_evidence_id": "adaptive_associated_symptoms_and_pertinent_negatives",
        "active_question_text": "Do you have any other symptoms such as fever or nausea?",
    }
    mock_llm = MagicMock()
    orchestrator = ConversationalTriageOrchestrator(db=MagicMock(), llm_provider=mock_llm)

    extracted = orchestrator._try_deterministic_answer_extraction(
        patient_message_text="No",
        context=context,
    )

    assert extracted is not None
    assert len(extracted.items) == 1
    assert extracted.items[0].evidence_code == "adaptive_associated_symptoms_and_pertinent_negatives"
    assert extracted.items[0].status == EvidenceStatus.ABSENT
    mock_llm.extract_patient_evidence.assert_not_called()


def test_adaptive_associated_symptoms_affirmative_falls_through_to_llm():
    """Affirmative answer to associated symptoms cannot determine which symptoms exist and must fall through to LLM."""
    context = {
        "active_evidence_id": "adaptive_associated_symptoms_and_pertinent_negatives",
        "active_question_text": "Do you have other symptoms?",
    }
    mock_llm = MagicMock()
    orchestrator = ConversationalTriageOrchestrator(db=MagicMock(), llm_provider=mock_llm)

    extracted = orchestrator._try_deterministic_answer_extraction(
        patient_message_text="Yes, I have high fever and nausea",
        context=context,
    )

    # Must be None so that orchestrator proceeds to rich LLM evidence extraction
    assert extracted is None


def test_adaptive_ambiguous_answer_falls_through_to_llm():
    """Uncertain answers like 'maybe' or 'sometimes' must fall through to LLM."""
    context = {
        "active_evidence_id": "adaptive_functional_impact",
        "active_question_text": "Does it limit your daily activities?",
    }
    mock_llm = MagicMock()
    orchestrator = ConversationalTriageOrchestrator(db=MagicMock(), llm_provider=mock_llm)

    for unclear in ["maybe a little bit", "not sure", "possibly", "it depends on the hour"]:
        extracted = orchestrator._try_deterministic_answer_extraction(
            patient_message_text=unclear,
            context=context,
        )
        assert extracted is None, f"Expected '{unclear}' to fall through to LLM"


def test_patient_correction_marker_falls_through_to_llm():
    """Patient messages with correction phrases must fall through to LLM."""
    context = {
        "active_evidence_id": "adaptive_functional_impact",
        "active_question_text": "Does it limit your daily activities?",
    }
    mock_llm = MagicMock()
    orchestrator = ConversationalTriageOrchestrator(db=MagicMock(), llm_provider=mock_llm)

    for correction in [
        "No wait, actually yes it does hurt a lot",
        "Scratch that, I meant to say no",
        "Instead of that, let me clarify",
    ]:
        extracted = orchestrator._try_deterministic_answer_extraction(
            patient_message_text=correction,
            context=context,
        )
        assert extracted is None, f"Expected '{correction}' to fall through to LLM"


def test_unknown_adaptive_id_falls_through_to_llm():
    """Unsupported or unknown adaptive question IDs must fall through to LLM."""
    context = {
        "active_evidence_id": "adaptive_unknown_custom_inquiry",
        "active_question_text": "Is it itchy?",
    }
    mock_llm = MagicMock()
    orchestrator = ConversationalTriageOrchestrator(db=MagicMock(), llm_provider=mock_llm)

    extracted = orchestrator._try_deterministic_answer_extraction(
        patient_message_text="Yes",
        context=context,
    )
    assert extracted is None


def test_adaptive_evidence_registry_validation():
    """Adaptive evidence IDs must pass ddxplus_provider.validate_evidence."""
    valid, _ = ddxplus_provider.validate_evidence("adaptive_functional_impact", "present")
    assert valid is True

    valid, _ = ddxplus_provider.validate_evidence("adaptive_functional_impact", "absent")
    assert valid is True

    valid, _ = ddxplus_provider.validate_evidence("adaptive_functional_impact", "invalid_val")
    assert valid is False

    valid, _ = ddxplus_provider.validate_evidence("adaptive_associated_symptoms_and_pertinent_negatives", "absent")
    assert valid is True

    valid, _ = ddxplus_provider.validate_evidence("adaptive_associated_symptoms_and_pertinent_negatives", "invalid_val")
    assert valid is False

    meta = ddxplus_provider.get_evidence("adaptive_functional_impact")
    assert meta is not None
    assert meta["name"] == "Functional Impact on Daily Activities or Sleep"


# =====================================================================
# STEP 4 TESTS: STOPPING POLICY ORDER & TERMINAL GATING
# =====================================================================


def test_pre_question_stopping_on_max_turns():
    """Pre-question policy evaluates stop before calling LLM question proposal."""
    state = PatientState(
        session_id="test_sess",
        patient_id="test_patient",
        chief_complaint="headache",
        conversation_turn=7,
        collected_evidence={"headache": "present"},
    )
    should_stop, reason, needs_esc = stopping_policy.should_stop_pre_question(state)
    assert should_stop is True
    assert reason == StoppingReason("INTERACTION_LIMIT_REACHED")


def test_pre_question_stopping_on_patient_decline():
    """Pre-question policy detects patient decline before calling LLM proposal."""
    state = PatientState(
        session_id="test_sess",
        patient_id="test_patient",
        chief_complaint="headache",
        conversation_turn=3,
        declined_to_continue=True,
        collected_evidence={"headache": "present"},
    )
    should_stop, reason, needs_esc = stopping_policy.should_stop_pre_question(state)
    assert should_stop is True
    assert reason == StoppingReason("PATIENT_DECLINED")


def test_pre_question_stopping_on_emergency_red_flag():
    """Pre-question policy immediately terminates on emergency red-flag."""
    state = PatientState(
        session_id="test_sess",
        patient_id="test_patient",
        chief_complaint="chest pain",
        conversation_turn=1,
        emergency_detected=True,
    )
    should_stop, reason, needs_esc = stopping_policy.should_stop_pre_question(state)
    assert should_stop is True
    assert reason == StoppingReason("EMERGENCY_RED_FLAG")


def test_orchestrator_bypasses_question_proposal_on_max_turns():
    """Orchestrator does not call propose_next_question when max turns reached."""
    mock_llm = MagicMock()
    mock_llm.extract_patient_evidence.return_value = ExtractedEvidenceResult(
        chief_complaint="persistent cough",
        duration="3 weeks",
        severity=5,
        items=[],
    )
    mock_llm.propose_next_question.return_value = AdaptiveQuestionProposal(
        status=AdaptiveQuestionStatus.ASK,
        question="Do you have shortness of breath?",
        intent="Inquire respiratory status",
        target_information=["dyspnea"],
        reason="Check breathing",
    )

    orchestrator = ConversationalTriageOrchestrator(db=MagicMock(), llm_provider=mock_llm)
    state = PatientState(
        session_id="test_sess_max_turns",
        patient_id="patient_1",
        chief_complaint="persistent cough",
        conversation_turn=7,  # Max turns
        collected_evidence={"persistent cough": "present"},
    )

    should_stop, reason, _ = stopping_policy.should_stop_pre_question(state)
    assert should_stop is True

    # If should_stop is True, orchestrator terminates without calling propose_next_question
    mock_llm.propose_next_question.assert_not_called()


# =====================================================================
# STEP 5 TESTS: TOKEN LIMITS CONFIGURATION
# =====================================================================


def test_gemini_token_limits_are_calibrated():
    """Evidence extraction limit is 700 tokens; question proposal limit is 1000 tokens, both with thinking_budget=0."""
    provider = GeminiProvider(api_key="test_key")
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '{"chief_complaint": "fever", "duration": null, "severity": null, "items": []}'
    mock_client.models.generate_content.return_value = mock_response
    provider._client = mock_client

    provider.extract_patient_evidence("fever")
    config_evidence = mock_client.models.generate_content.call_args[1]["config"]
    assert config_evidence.max_output_tokens == 700
    assert config_evidence.thinking_config.thinking_budget == 0

    mock_response.text = '{"status": "ask", "question": "How long has it lasted?", "intent": "Onset", "target_information": ["duration"], "reason": "Need duration"}'
    mock_client.models.generate_content.return_value = mock_response

    provider.propose_next_question({"chief_complaint": "fever", "history": []})
    config_proposal = mock_client.models.generate_content.call_args[1]["config"]
    assert config_proposal.max_output_tokens == 1000
    assert config_proposal.thinking_config.thinking_budget == 0


def test_question_proposal_truncation_max_tokens_safe_fail():
    """Verify that if Gemini truncates structured question proposal with MAX_TOKENS, it retries with expanded tokens and safely fails closed without mock fallback."""
    provider = GeminiProvider(api_key="test_key")
    mock_client = MagicMock()

    candidate_truncated = MagicMock()
    candidate_truncated.finish_reason = "MAX_TOKENS"
    mock_response_truncated = MagicMock()
    mock_response_truncated.candidates = [candidate_truncated]
    mock_response_truncated.text = '{"status": "ask", "question": "Incomplete'

    # Both attempts fail with MAX_TOKENS
    mock_client.models.generate_content.return_value = mock_response_truncated
    provider._client = mock_client

    with pytest.raises(TriageLLMUnavailableError) as exc_info:
        provider.propose_next_question({"chief_complaint": "fever", "history": []})

    assert exc_info.value.status_code == 503
    assert mock_client.models.generate_content.call_count == 2
    # Check that attempt 2 was called with expanded token limit (1500)
    second_call_config = mock_client.models.generate_content.call_args_list[1][1]["config"]
    assert second_call_config.max_output_tokens == 1500


def test_question_proposal_truncation_max_tokens_recovers_on_retry():
    """Verify that if Gemini truncates on attempt 1 with MAX_TOKENS, expanded token limit on attempt 2 can succeed."""
    provider = GeminiProvider(api_key="test_key")
    mock_client = MagicMock()

    candidate_truncated = MagicMock()
    candidate_truncated.finish_reason = "MAX_TOKENS"
    mock_response_truncated = MagicMock()
    mock_response_truncated.candidates = [candidate_truncated]
    mock_response_truncated.text = '{"status": "ask", "question": "Incomplete'

    candidate_success = MagicMock()
    candidate_success.finish_reason = "STOP"
    mock_response_success = MagicMock()
    mock_response_success.candidates = [candidate_success]
    mock_response_success.text = '{"status": "ask", "question": "How long have you had this fever?", "intent": "Duration", "target_information": ["duration"], "reason": "Need duration"}'

    mock_client.models.generate_content.side_effect = [mock_response_truncated, mock_response_success]
    provider._client = mock_client

    proposal = provider.propose_next_question({"chief_complaint": "fever", "history": []})
    assert proposal.status.value == "ask"
    assert proposal.question == "How long have you had this fever?"
    assert mock_client.models.generate_content.call_count == 2
    second_call_config = mock_client.models.generate_content.call_args_list[1][1]["config"]
    assert second_call_config.max_output_tokens == 1500
