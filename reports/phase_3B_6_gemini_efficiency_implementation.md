# CareRoute-X — Phase 3B.6 Implementation Report
## Gemini Request Efficiency and Reliability Hardening

**Project Root:** `D:\medcon5`  
**Phase:** 3B.6  
**Execution Date:** 2026-10-21  
**Status:** Completed & Validated  

---

### Executive Summary

In Phase 3B.6, CareRoute-X implemented comprehensive efficiency and reliability hardening for the Gemini-powered conversational triage pipeline. The implementation directly resolves the root causes identified in `reports/gemini_request_efficiency_audit.md`:
1. **Quota Retry Hardening:** Eliminated futile and blind retries on permanent/daily quota exhaustion and unannotated HTTP 429 responses; enforced strict bounded backoff for valid transient provider rate limits within a 5.0s budget; preserved bounded retries for transient HTTP 502/503 service unavailability.
2. **Deterministic Adaptive Extraction:** Repaired `_try_deterministic_answer_extraction` by registering supported `adaptive_*` clinical inquiry schemas (`adaptive_functional_impact`, `adaptive_associated_symptoms_and_pertinent_negatives`) in `ADAPTIVE_EVIDENCE_REGISTRY`, validating them against the clinical ontology, respecting question-specific semantic polarity, and verifying that patient corrections or ambiguous replies safely fall through to LLM extraction.
3. **Stopping-Policy Ordering & Gating:** Added `should_stop_pre_question` in `TriageStoppingPolicy` and integrated it at Step 5b of `ConversationalTriageOrchestrator.process_patient_turn`. This ensures that terminal intake conditions (maximum turns reached, patient decline, emergency red flags, or human review triggers) terminate intake immediately *prior* to invoking Gemini question proposal, saving 1 expensive LLM request per terminal session.
4. **Structured Output Token Limits:** Calibrated `max_output_tokens` based on empirical schema analysis (700 tokens for `extract_patient_evidence` and 500 tokens for `propose_next_question`, down from an over-provisioned 1500 tokens each).
5. **Frontend Triage Error Experience:** Updated `src/app/patient/triage/page.tsx` to detect capacity/quota exhaustion, preserve session history and unsent input, suppress unhelpful immediate retry prompts, and provide an immediate, accessible navigation path (`"Find Available Doctors"`) to doctor matching without faking completion or generating invalid diagnoses.

All unit and integration suites passed (236 unit tests passed, 27 API tests passed, TypeScript compiled with 0 errors). Zero live Gemini API calls, zero remote database calls, and zero database migrations were performed.

---

### 1. Files Changed and Rationale

| File | Nature of Change | Clinical & Architectural Rationale |
|---|---|---|
| `backend/app/services/triage/evidence_provider.py` | Added `ADAPTIVE_EVIDENCE_REGISTRY`, updated `get_evidence` and `validate_evidence` | Resolves ontology lookup failure for valid adaptive clinical inquiries (`adaptive_functional_impact`, `adaptive_associated_symptoms_and_pertinent_negatives`). Allows binary validation to recognize `"present"`, `"absent"`, `"yes"`, `"no"`, and registered clinical values without skipping validation. |
| `backend/app/services/triage/stopping_policy.py` | Added `should_stop_pre_question(state)` | Enables pre-question stopping evaluation on updated state to detect terminal conditions (emergency red flag, patient decline, max turns, human review) before question generation is invoked. |
| `backend/app/services/triage/orchestrator.py` | Added Step 5b pre-question stopping check; enhanced `_try_deterministic_answer_extraction`; updated state & payload persistence | Prevents question proposal calls on terminal paths. Bypasses LLM extraction only on unambiguous exact affirmative/negative answers matching active question polarity; preserves `functional_impact` in state reconstruction and persistence. |
| `backend/app/services/llm/gemini.py` | Implemented `_is_permanent_quota_error`, `_get_safe_quota_retry_delay`, `MAX_QUOTA_RETRY_DELAY = 5.0`; tuned `max_output_tokens` | Distinctly classifies permanent vs transient 429 errors; sleeps only when provider indicates a valid retry delay within budget; fails fast without sleeping on daily/permanent quota; calibrated tokens to 700 (evidence extraction) and 500 (question proposal). |
| `src/app/patient/triage/page.tsx` | Added `isQuotaExhausted` state, capacity error handling, and recovery UI | Prevents frantic repeated retries on quota exhaustion; preserves unsent message and conversation history; provides direct recovery link to doctor matching; preserves distinction between incomplete intake and completed assessment. |
| `backend/tests/unit/test_phase_3b_6_efficiency.py` | Created comprehensive unit test suite (19 test cases) | Verified quota fast-fail, bounded delay sleep, transient 503 retry, deterministic extraction on adaptive questions, polarity enforcement, fall-through on ambiguous/correction text, pre-question terminal gating, and token limit calibration. |

---

### 2. Root Causes Fixed

1. **Blind and Futile 429 Retries:**
   - *Previous state:* Gemini provider treated all 429 responses with identical exponential backoff, sleeping up to several seconds even when daily quota was exhausted or no retry timing was returned.
   - *Fix:* Integrated `_is_permanent_quota_error` to catch `daily quota limit reached`, `prepayment credits are depleted`, `billing`, and permanent resource exhaustion. Evaluates `_get_safe_quota_retry_delay` against `MAX_QUOTA_RETRY_DELAY = 5.0s`. If delay is absent or exceeds budget, it fails fast on Attempt 1 with zero sleep.

2. **Deterministic Extraction Failure on Adaptive Questions:**
   - *Previous state:* Adaptive questions used synthetic IDs like `adaptive_functional_impact` and `adaptive_associated_symptoms_and_pertinent_negatives`. Because these IDs were not present in the DDXPlus ontology, `evidence_provider.get_evidence(...)` returned `None`, causing `_try_deterministic_answer_extraction` to abort and fall through to Gemini extraction on every turn.
   - *Fix:* Added `ADAPTIVE_EVIDENCE_REGISTRY` with explicit clinical metadata, state field mappings, and polarity permissions. Updated `validate_evidence` to validate both DDXPlus and adaptive registry items.

3. **Unchecked Question Proposal on Terminal Paths:**
   - *Previous state:* Orchestrator always invoked `select_next_adaptive_question` (and thus Gemini `propose_next_question`) before evaluating the stopping policy, even when `turn_count >= 7`, the patient had opted out, or an emergency red flag was identified.
   - *Fix:* Added Step 5b pre-question evaluation using `stopping_policy.should_stop_pre_question(state)`. When a terminal condition is met, question selection is completely skipped and the session transitions directly to clinical finalization.

4. **Over-Provisioned Output Token Limits:**
   - *Previous state:* Both structured extraction and question proposal requested 1500 tokens, inflating resource reservations.
   - *Fix:* Right-sized limits to 700 tokens for evidence extraction and 500 tokens for question proposal based on actual Pydantic schema sizes and empirical maximum token lengths.

5. **Suboptimal Frontend Quota Handling:**
   - *Previous state:* Frontend treated quota exhaustion as a generic retryable error, displaying a "Retry" button that encouraged repeated failed requests against an exhausted quota.
   - *Fix:* Differentiated capacity exhaustion from transient errors. Displays guidance explaining that intake is saved, hides the immediate retry prompt, and displays a `"Find Available Doctors"` recovery action.

---

### 3. Before-and-After Gemini Request Counts

| Scenario | Turn Index / Action | Before (Audit) | After (Hardened) | Reduction | Clinical Safety Guarantee |
|---|---|---|---|---|---|
| **Simple Yes/No to Functional Impact** | Turn 2: Patient answers `"Yes"` to `"Does this prevent normal daily activities?"` | 2 requests (Extraction + Proposal) | 1 request (Proposal only; extraction deterministic) | **-50%** | Affirmative answer safely mapped to `functional_impact=True`; validated by ontology provider. |
| **Simple No to Associated Symptoms** | Turn 3: Patient answers `"No"` to `"Do you have other accompanying symptoms?"` | 2 requests (Extraction + Proposal) | 1 request (Proposal only; extraction deterministic) | **-50%** | Negative answer safely mapped to `associated_symptoms=False`; validated by ontology provider. |
| **Ambiguous / Narrative Answer** | Turn 2: Patient answers `"Maybe a little bit when I walk upstairs"` | 2 requests | 2 requests | 0% (Retained) | Ambiguity safely falls through to LLM; no loss of clinical fidelity. |
| **Patient Correction / Contradiction** | Turn 2: Patient answers `"No wait, actually yes it does hurt"` | 2 requests | 2 requests | 0% (Retained) | Disallowed clause markers trigger fall-through to LLM extraction. |
| **Turn Limit Reached (Max 7 Turns)** | Turn 7: Patient answers final question | 2 requests (Extraction + Proposal, then discarded) | 1 request (Extraction only; proposal skipped) | **-50%** | Final answer is fully extracted and analyzed; stopping policy executes before proposal. |
| **Patient Opt-Out / Decline** | Patient requests stop / doctor direct | 2 requests | 1 request (Extraction only; proposal skipped) | **-50%** | Patient's final message is processed; proposal skipped. |
| **Emergency Red Flag Detected** | Critical red flag finding in message | 2 requests (or failed proposal before escalate) | 0 or 1 request (Proposal never called; immediate escalation) | **-50% to -100%** | Pre-extraction and post-extraction safety gates trigger emergency banner and immediate escalation. |
| **Exhausted Daily Quota** | Provider returns 429 quota exhausted | 2 failed attempts with sleep (failing slowly) | 1 attempt, 0 sleep, fails fast in < 5ms | **Faster fail-safe** | Error mapped to typed 503 response; patient routed to doctor directory. |

---

### 4. Retry Behaviour Matrix

| HTTP Status / Condition | Provider Error Substring | Classification | Retry Behaviour | Sleep Duration | Metrics & Logging |
|---|---|---|---|---|---|
| **HTTP 429** | `daily quota limit reached`, `prepayment credits are depleted`, `check billing` | `QUOTA_EXCEEDED` (Permanent) | **Do NOT retry.** Fail fast immediately on Attempt 1. | 0s (No sleep) | `FAILURE_CATEGORY_QUOTA_EXCEEDED`, `is_quota_limit=True` |
| **HTTP 429** | `Please retry in 2s` (delay ≤ 5.0s) | `QUOTA_EXCEEDED` (Transient Rate Limit) | **Bounded retry:** Sleep indicated duration (+1s buffer), retry once on Attempt 2. | Indicated delay (e.g. 3s or 4s) | Log warning on Attempt 1; if Attempt 2 succeeds, log `status=SUCCESS, retry_occurred=True`. |
| **HTTP 429** | `Please retry in 15s` (delay > 5.0s) | `QUOTA_EXCEEDED` (Excessive Delay) | **Do NOT retry.** Exceeds request budget. Fail fast on Attempt 1. | 0s (No sleep) | Log `QUOTA_EXCEEDED`; raise `TriageLLMUnavailableError`. |
| **HTTP 429** | Generic rate limit (no delay indicated) | `QUOTA_EXCEEDED` (Unannotated) | **Do NOT retry blindly.** Fail fast on Attempt 1. | 0s (No sleep) | Log `QUOTA_EXCEEDED`; raise `TriageLLMUnavailableError`. |
| **HTTP 502 / 503** | `Service Unavailable`, `Bad Gateway`, `Network Error` | `SERVICE_UNAVAILABLE` | **Bounded retry:** Retry once with adaptive exponential backoff (1s - 2.5s). | 1.0s - 2.5s | Log warning; log metric with duration and attempt count. |
| **HTTP 400 / 401 / 404** | `Invalid argument`, `API key invalid`, `Model not found` | `AUTHENTICATION_ERROR` / `CLIENT_ERROR` | **Do NOT retry.** Fail fast on Attempt 1. | 0s (No sleep) | Distinct error category; never misclassified as quota limit. |

---

### 5. Deterministic Answer Mapping and Validation Behaviour

#### Registered Adaptive Inquiries
```python
ADAPTIVE_EVIDENCE_REGISTRY = {
    "adaptive_functional_impact": {
        "name": "Functional Impact on Daily Activities or Sleep",
        "question_en": "Does this symptom prevent you from doing your normal daily activities or sleeping?",
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
        "allow_affirmative": False,  # Unsafe: "yes" alone does not specify WHICH symptoms exist
        "allow_negative": True,      # "no" safely confirms absence of additional symptoms
        "state_field": "associated_symptoms",
        "affirmative_value": None,
        "negative_value": False,
    },
}
```

#### Polarity and Safety Rules:
1. **Unambiguous Affirmatives / Negatives Only:**
   - Affirmatives: `{"yes", "yeah", "yep", "yup", "definitely", "sure", "correct", "true", "i do", "i have", "affirmative"}`
   - Negatives: `{"no", "nope", "nah", "negative", "i don't", "i do not", "none", "not really", "never", "i don't have it", "i do not have it"}`
2. **Disallowed Clause Markers:**
   Any message containing digits, connective conjunctions (`but`, `and`, `also`, `except`), temporal markers (`days`, `hours`), symptom nouns (`fever`, `cough`, `pain`, `headache`), or correction indicators (`actually`, `wait`, `instead`, `mistake`, `scratch that`) immediately bypasses deterministic extraction and invokes LLM clinical extraction.
3. **Semantic Polarity Gating:**
   For `adaptive_associated_symptoms_and_pertinent_negatives`, `"no"` deterministically records `absent` (`associated_symptoms=False`), but `"yes"` has `allow_affirmative=False` and safely falls through to LLM extraction to capture the specific accompanying symptoms.
4. **Validation Path:**
   Extracted evidence items pass through `evidence_provider.validate_evidence(item.evidence_code, item.value)`. The binary validator accepts `True`, `False`, `"present"`, `"absent"`, and registered descriptive values.

---

### 6. Stopping-Policy Order and Safety Guarantees

#### Execution Sequence in `process_patient_turn`:
1. **Ownership & Session Validation**
2. **Reconstruct Patient State & Message History**
3. **Pre-Extraction Red-Flag Screen:** Immediate escalation if emergency red flags are found in the incoming message.
4. **Clinical Evidence Extraction:**
   - Attempt deterministic extraction if active question context exists and answer is exact.
   - Fall back to Gemini structured extraction if answer is narrative, ambiguous, or contains corrections.
5. **Ontology Validation & State Updating:** Evidence validated and updated in `PatientState`.
6. **Post-Extraction Red-Flag Screen:** Immediate escalation if extracted evidence indicates clinical emergency.
7. **Step 5b (NEW) — Pre-Question Stopping Evaluation:**
   ```python
   should_stop_pre, pre_stop_reason, pre_needs_esc = self.stopping_policy.should_stop_pre_question(state)
   if should_stop_pre:
       return self._finalize_session(...)
   ```
8. **Adaptive Question Selection & Proposal:** Invoked *only* if `should_stop_pre` is `False`.
9. **Final Stopping Evaluation & Empathy Phrasing**
10. **Atomic Database Persistence**

#### Safety Guarantees:
- **No Discarded Answers:** The patient's final message is always extracted, validated, and updated in state before stopping is evaluated.
- **No Bypassed Safety Screens:** Pre-extraction and post-extraction red-flag gates execute unconditionally prior to stopping policy evaluation.
- **Uncertainty Preserved:** If interaction terminates with low completeness (`completeness_score < 0.55`) or unresolved symptoms, `needs_escalation=True` and `uncertainty_detected=True` are flagged, triggering human review routing.

---

### 7. Structured-Output Token-Limit Decisions

| Operation | Previous Limit | Hardened Limit | Schema Output Requirements | Largest Legitimate Response Tested | Justification |
|---|---|---|---|---|---|
| **`extract_patient_evidence`** | 1500 tokens | **700 tokens** | Pydantic schema with chief complaint, duration, severity, measurements list, items list (evidence_code, status, confidence), corrections, and decline flag. | 8 items + 2 measurements + 2 corrections ≈ 280-350 tokens. | 700 tokens provides a 2x safety margin over the maximum legitimate clinical extraction payload while eliminating 800 tokens of unnecessary reservation. |
| **`propose_next_question`** | 1500 tokens | **500 tokens** | Pydantic schema with status enum, question text, intent, target_information list, reason, safety_flags, uncertainties, covered_information, requires_human_review. | Complete question proposal with 4 target items and rationale ≈ 180-220 tokens. | 500 tokens provides a 2.5x safety margin for question phrasing and clinical reasoning without risk of schema truncation. |

---

### 8. Frontend Error and Recovery Behaviour

In `src/app/patient/triage/page.tsx`:
1. **Differentiated Error Presentation:**
   - When the backend returns a quota exhaustion error (message includes `"capacity is temporarily exhausted"` or error code `TRIAGE_LLM_QUOTA_EXHAUSTED`), the UI displays:
     - **Title:** `"Triage Capacity Limit Reached"`
     - **Body:** `"Your intake history has been saved. Due to temporary AI capacity limits, repeated attempts right now are unlikely to succeed. You can proceed directly to choose a doctor or check back later."`
2. **Suppression of Futile Retries:**
   - The primary action in the capacity limit banner is changed from `"Retry"` to `"Find Available Doctors"` (`<ArrowRight />`).
   - The patient is not prompted to repeatedly hit the backend during a capacity outage.
3. **Preservation of Conversation and Input:**
   - The session ID is maintained in `sessionStorage`.
   - The unsent message remains in `inputText` / `failedMessage` so the patient never loses their typed words.
4. **Clinical Safety Preservation:**
   - Incomplete triage is never marked as `COMPLETED`.
   - No synthetic diagnoses or fake assessments are created.
   - The navigation link passes `?session_id=...` so the doctor intake dashboard can access the partial conversation during consultation.

---

### 9. Test Suite Execution and Results

#### Targeted Phase 3B.6 Test Suite:
`python -m pytest tests/unit/test_phase_3b_6_efficiency.py -v`
- `test_permanent_daily_quota_fails_immediately_no_sleep`: **PASSED**
- `test_rate_limit_with_valid_delay_retries_and_succeeds`: **PASSED**
- `test_rate_limit_with_excessive_delay_fails_immediately_no_sleep`: **PASSED**
- `test_rate_limit_with_no_delay_fails_immediately_no_sleep`: **PASSED**
- `test_transient_503_preserves_bounded_retry`: **PASSED**
- `test_client_errors_do_not_misclassify_as_quota`: **PASSED**
- `test_adaptive_functional_impact_affirmative_deterministic_mapping`: **PASSED**
- `test_adaptive_functional_impact_negative_deterministic_mapping`: **PASSED**
- `test_adaptive_associated_symptoms_negative_deterministic_mapping`: **PASSED**
- `test_adaptive_associated_symptoms_affirmative_falls_through_to_llm`: **PASSED**
- `test_adaptive_ambiguous_answer_falls_through_to_llm`: **PASSED**
- `test_patient_correction_marker_falls_through_to_llm`: **PASSED**
- `test_unknown_adaptive_id_falls_through_to_llm`: **PASSED**
- `test_adaptive_evidence_registry_validation`: **PASSED**
- `test_pre_question_stopping_on_max_turns`: **PASSED**
- `test_pre_question_stopping_on_patient_decline`: **PASSED**
- `test_pre_question_stopping_on_emergency_red_flag`: **PASSED**
- `test_orchestrator_bypasses_question_proposal_on_max_turns`: **PASSED**
- `test_gemini_token_limits_are_calibrated`: **PASSED**
**Result: 19 passed in 2.53s**

#### Complete Backend Test Suites:
1. `tests/unit/test_phase_3b_6_efficiency.py` + `test_gemini_retry_hardening.py` + `test_adaptive_triage_engine.py` + `test_triage_orchestrator.py` + `test_stopping_policy.py` + `test_triage_safety_regression.py` + `test_question_selector.py` + `test_evidence_provider.py`:
   - **108 passed in 6.98s**
2. Full `tests/unit`:
   - **236 passed, 10 skipped in 12.97s**
3. Full `tests/api`:
   - **27 passed in 3.40s**

#### Frontend Verification:
`npx tsc --noEmit`
- **Exited with code 0 (Clean TypeScript compilation)**

---

### 10. Known Limitations and Unresolved Findings

1. **Free-Tier RPM / RPD Throttling:**
   While the client now fails fast and respects retry delays safely up to 5.0s, Google AI Studio free-tier quotas (15 RPM / 1,500 RPD) remain a structural infrastructure limitation for high-traffic outpatient spikes. Production environments should utilize dedicated Google Cloud Vertex AI quotas with enterprise rate limits.
2. **Adaptive Inquiries Scope:**
   Currently, `ADAPTIVE_EVIDENCE_REGISTRY` supports the two primary adaptive questions generated by the adaptive triage engine (`adaptive_functional_impact` and `adaptive_associated_symptoms_and_pertinent_negatives`). Custom dynamic questions generated by Gemini outside these registered IDs safely fall through to LLM extraction as designed.

---

### 11. Compliance and Safety Attestation

- **Live Gemini API Calls:** Zero live Gemini API requests were made during implementation or automated testing; all tests utilized deterministic mock and scripted fake providers.
- **Remote Database Access:** Zero remote Supabase or cloud databases were accessed or modified.
- **Database Migrations:** Zero Alembic migrations were created or executed.
- **Safety Gates:** Red-flag pre-extraction and post-extraction safety gates remain strictly enforced before any question generation or intake conclusion.
- **FastAPI API Contract:** The existing API contract (`/api/v1/triage/...`) was preserved completely with typed error handling and backward-compatible payloads.
