# CareRoute-X — Backend

Modular monolithic FastAPI backend for **CareRoute-X**, an outpatient care-navigation and queue-management platform.

## Architecture & Integration

* **Framework**: FastAPI (Python 3.12+)
* **Data Validation**: Pydantic v2
* **ORM & Database**: SQLAlchemy 2 + Alembic (connecting to Supabase PostgreSQL)
* **Authentication**: Supabase Auth (JWT tokens validated server-side)
* **Testing**: Pytest + HTTPX

> **Note**: Supabase infrastructure is managed by the platform administrator. The FastAPI backend implements clean repository and data access layers, enforcing server-authoritative business rules, authorization guards, and state machines.

---

## Directory Structure

```text
backend/
├── app/
│   ├── main.py                  # Application entrypoint & middleware
│   ├── core/                    # Core configuration, security, auth dependencies, exceptions
│   ├── api/                     # REST API versioned endpoints (/api/v1)
│   ├── models/                  # SQLAlchemy 2 models (Phase 2+)
│   ├── schemas/                 # Pydantic v2 validation schemas
│   ├── repositories/            # Data access & repository abstractions
│   ├── services/                # Domain & business logic services
│   └── db/                      # Session management & migrations
├── tests/                       # Unit and API integration test suite
├── requirements.txt
├── Dockerfile
├── .env.example
└── README.md
```

---

## Local Setup

### 1. Create and Activate Virtual Environment

```bash
cd backend
python -m venv .venv

# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1

# Linux / macOS
source .venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

```bash
copy .env.example .env
```
Fill in `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET`, and `DATABASE_URL`.

### 4. Run the Development Server

```bash
uvicorn app.main:app --reload --port 8000
```

The interactive OpenAPI docs will be available at:
* Swagger UI: http://127.0.0.1:8000/docs
* ReDoc: http://127.0.0.1:8000/redoc
* Health Check: http://127.0.0.1:8000/api/v1/health

---

## Running Tests

Run the test suite using `pytest`:

```bash
pytest -v
```

---

## Stage 6: Explainable Doctor Recommendation & Ranking

CareRoute-X Stage 6 implements a two-stage operational recommendation and ranking pipeline:
`Patient symptoms -> Structured triage -> Recommended specialty -> Eligible doctors -> Deterministic ranking -> Explainable recommendations`

### 1. Two-Stage Architecture
* **Stage A — Hard Eligibility Filtering**:
  - **Doctor Status**: Must be active (`is_active = True`).
  - **Hospital Boundary**: Enforces tenant isolation; doctors must belong to the patient's hospital.
  - **Specialty Requirement**: Doctor must support the required clinical specialty (provided directly or derived from a completed triage assessment).
  - **Consultation Mode**: Doctor's supported mode (`in_person`, `teleconsultation`, `both`) must accommodate the requested mode.
  - **Scheduling Availability**: When `require_availability = True`, doctors with 0 open appointment slots on the target date are excluded.
* **Stage B — Explainable Scoring**:
  - Eligible doctors are scored and ranked using centralized, normalized weighted factors.
  - If no doctors pass eligibility, returns `status = "NO_ELIGIBLE_DOCTORS"` with an empty recommendations array.

### 2. Centralized Ranking Weights (Total = 1.00)
All weights are centralized in `app/ranking/constants.py`:
* **Specialty Match (0.30)**: Specialty is an eligibility gate; the 0.30 score differentiates primary specialty practice (`1.0`) from secondary clinical focus (`0.7`).
* **Availability (0.20)**: Derived from concrete `DoctorSchedule` and `AppointmentService` slot availability.
* **Predicted Wait (0.15)**: Reuses Stage 3 queue baseline wait calculation (`max(5, patients_ahead * 15)`), normalized so shorter wait scores higher.
* **Experience (0.10)**: Bounded operational factor (`years_of_experience / 30.0`).
* **Rating Reliability (0.10)**: Bayesian shrinkage toward global prior (`4.0` with smoothing strength `m = 10`), preventing sparse ratings (e.g. 4.9 from 2 reviews) from dominating established ratings (e.g. 4.7 from 100 reviews). Unrated doctors receive a neutral prior score (`0.80`).
* **Patient Preference (0.10)**: Explicitly supplied preferences only (`1.0` on match, `0.2` on mismatch, `0.5` neutral). Never inferred from demographics.
* **Language Match (0.05)**: Explicit language matching (`1.0` if doctor supports requested language, `0.5` neutral if unspecified).

### 3. Deterministic Tie-Breaking
1. Higher composite score
2. Higher availability score
3. Lower estimated wait minutes
4. Higher rating reliability score
5. Stable doctor ID string comparison

### 4. Structured Explanations (No LLMs)
Explanations are constructed deterministically from the internal `RecommendationFactorBreakdown`. No LLM is used for scoring or explanation generation. Prohibited superlatives ("best doctor", "medically superior", "most qualified") are strictly excluded.

### 5. Triage Integration & Emergency Escalation
When a `triage_session_id` is supplied:
- Validates patient ownership (cross-patient access is rejected with `403 Forbidden`).
- Automatically extracts the recommended clinical specialty.
- **Emergency Safety**: If triage assessment flagged `needs_escalation = True`, `red_flag_detected = True`, or `HIGH` urgency, the recommendation response flags `is_emergency_escalation = True` and attaches a prominent emergency safety notice advising immediate emergency care. Urgency is never silently downgraded.

### 6. Future Learning-to-Rank (LTR) Extension
Decoupled behind `DoctorRankingProvider` and `WaitEstimationProvider` interfaces (`app/ranking/interfaces.py`). The current implementation uses `DeterministicDoctorRankingProvider` and `BaselineWaitEstimationProvider`, allowing Stage 7 ML duration/wait models and future learned ranking models to plug in without altering the API contract.

### 7. Clinical Claim Restriction & Limitations
> **IMPORTANT NOTICE**: This is an explainable operational doctor-ranking prototype, not a measure of clinical quality or doctor superiority. It does not constitute clinical validation or medical diagnosis.
