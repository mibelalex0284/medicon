# CareRoute-X Pre-Demonstration Critical Fixes & Integration Report

**Date:** 22 October 2026  
**Repository:** `D:\medcon5`  
**Status:** All 5 Critical Issues Resolved & Verified  
**Test Suite Summary:** 52 Backend Tests Passed · 44 Frontend Tests Passed · 0 TypeScript Errors  

---

## Executive Summary

Prior to the final-year project demonstration, a focused debugging, stabilization, and integration pass was conducted across the CareRoute-X application in `D:\medcon5`. All changes strictly adhered to scope constraints: no remote Supabase migrations were run, deterministic clinical safety and red-flag rules were preserved, Gemini model configuration was untouched, and existing working features remained intact.

---

## 1. Root Cause Analysis of Identified Issues

### Issue 1: Incorrect Doctor Specialty Recommendation
* **Root Cause:**
  1. **Backend Candidate Filtering:** In `backend/app/services/doctor_recommendation_service.py`, `candidate_doctors` were retrieved by querying any doctor possessing a specialty record matching the requested specialty ID. However, doctors with secondary specialty affiliations in General Medicine but whose primary specialty belonged to an unrelated clinical domain (e.g., Dr. Sarah Lindqvist, primary: Dermatology, secondary: General Medicine) were treated as eligible.
  2. **Frontend Specialty Display Desynchronization:** In `src/app/patient/doctors/page.tsx`, the specialty label rendered on each physician card unconditionally extracted `doctor.specialties?.[0]?.specialty?.name`. Because Dermatology was `specialties[0]` for Dr. Lindqvist, the card displayed "Dermatology" under her name while the page header and explanation claimed she was matched for "General Medicine".
* **Resolution:**
  - In `doctor_recommendation_service.py`, enforced strict primary domain consistency. Physicians whose primary specialty is in an unrelated clinical domain (such as Dermatology when General Medicine is requested) are excluded from candidate recommendations.
  - When no primary specialists match the requested specialty in the facility, the service returns `status = "NO_ELIGIBLE_DOCTORS"` with total count 0, which triggers the clean empty state on the frontend.
  - In `src/app/patient/doctors/page.tsx`, implemented `getDoctorDisplaySpecialty()` to resolve the matched specialty name consistently and ensure card descriptions match the triage assessment recommendation.

### Issue 2: Past Appointment Slots Allowed for Booking
* **Root Cause:**
  1. **Availability Generation:** In `backend/app/services/appointment_service.py`, `get_doctor_availability` generated discrete time slots from doctor schedule windows without verifying whether `slot_start <= current_time` for the current date or if `requested_date < current_date`.
  2. **Backend Validation Gap:** `book_appointment` verified doctor schedule windows and existing booking conflicts, but did not validate whether the requested appointment date and start time had already elapsed.
  3. **Frontend Slot Display:** The frontend date picker and slot grid rendered all schedule intervals returned without filtering out elapsed slots for the current calendar day.
* **Resolution:**
  - In `backend/app/services/appointment_service.py`:
    - Added timezone-aware hospital resolution (`get_hospital_timezone`).
    - In `get_doctor_availability`, if `requested_date < today_in_hospital`, returns an empty slot list (`slots = []`). For `requested_date == today_in_hospital`, excludes any slot whose start time is before or equal to current hospital time.
    - In `book_appointment`, added authoritative timezone-aware validation checking `appointment_start_dt > now_dt`. If in the past, raises `InvalidStateTransitionError(message="Cannot book an appointment for a past date or time.", code="PAST_APPOINTMENT_NOT_ALLOWED")` (HTTP 400).
  - In `src/app/patient/doctors/page.tsx`, added client-side defensive slot filtering for current-day consultations and handled `PAST_APPOINTMENT_NOT_ALLOWED` gracefully.

### Issue 3: Queue Page Stuck on "Syncing with Outpatient Queue..."
* **Root Cause:**
  - In `src/app/patient/queue/page.tsx`, `loadQueueStatus` was declared with `[activeQueue]` in its `useCallback` dependency array, and `useEffect` depended on `[loadQueueStatus]`.
  - When `loadQueueStatus()` fetched the patient's queue entry, it executed `setActiveQueue(entry)`.
  - Updating `activeQueue` created a new object reference, causing `useCallback` to recreate `loadQueueStatus`.
  - The recreation of `loadQueueStatus` immediately re-triggered the `useEffect`, which called `setIsLoading(true)` and re-invoked `loadQueueStatus()`.
  - This created an infinite render/fetch loop where `isLoading` was continuously reset to `true`, leaving the page permanently frozen on the loading spinner.
* **Resolution:**
  - Refactored `loadQueueStatus` in `src/app/patient/queue/page.tsx` to use `prevQueueRef = React.useRef<QueueEntry | undefined>(undefined)` for tracking queue state changes (such as token calls).
  - Changed the `useCallback` dependency array to `[]`, ensuring a stable function reference.
  - Separated initial loading (`setIsLoading(true)`) from background polling (`setIsRefreshing(true)`).
  - Handled loading, active token, empty queue (404 `NO_ACTIVE_QUEUE_ENTRY`), expired session, and network error states explicitly.

### Issue 4: Admin Panel Must List Registered Doctors
* **Root Cause:**
  - The admin section lacked a dedicated physician directory view and had no navigation link for doctors in `ADMIN_NAV`.
  - While a public endpoint existed for patient doctor search, the backend lacked an admin-authorized directory endpoint enforcing role-based permissions (`require_admin`).
* **Resolution:**
  - Added `GET /api/v1/doctors/admin/list` in `backend/app/api/v1/doctors.py`, protected with `admin_user: AuthenticatedUser = Depends(require_admin)`.
  - Added `listDoctorsAdmin()` to `src/services/doctors/index.ts`.
  - Created `src/app/admin/doctors/page.tsx` rendering a responsive, searchable directory table displaying physician name, email, license number, primary/secondary specialties, department, hospital, years of clinical experience, average rating, consultation modes, languages, and active practicing status badges.
  - Added "Physicians" to `ADMIN_NAV` in `src/app/admin/layout.tsx` and linked from `src/app/admin/dashboard/page.tsx`.

### Issue 5: Portal Login Credentials & Authentication Architecture
* **Root Cause:**
  - The application provides a development role switcher on `/login` and the sidebar.
  - However, `loginAsRole()` only updated `localStorage.getItem("careroute_user_session")` without updating `careroute_auth_token`.
  - `getAuthHeaders()` continued sending `NEXT_PUBLIC_DEV_AUTH_TOKEN` (the patient token for `pat_101`).
  - Switching to "Doctor" or "Admin" caused subsequent backend API requests to fail with HTTP 403 Forbidden due to role mismatch.
  - In the database, while `pat_101` and `doc_202` existed, admin user `adm_303` had no record in `profiles`.
* **Resolution:**
  - Updated `src/services/auth/index.ts` to manage role-specific tokens via `DEV_ROLE_TOKENS`. When switching roles via `loginAsRole(role)`, `careroute_auth_token` is synchronized to the corresponding role token.
  - Updated `logout()` to clear all session keys (`careroute_user_session`, `careroute_auth_token`, and triage session keys).
  - Enhanced `backend/app/db/seed_dev.py` with `seed_all_dev_accounts()` to idempotently seed `pat_101` (Patient), `doc_202` (Doctor), and `adm_303` (Admin) with non-production safety guards.

---

## 2. Exact Files Changed

| File Path | Description of Changes |
| :--- | :--- |
| `backend/app/services/doctor_recommendation_service.py` | Added clinical domain eligibility filtering to prevent secondary specialty mismatches (e.g. Dermatologist for General Medicine). |
| `backend/app/services/appointment_service.py` | Added timezone-aware hospital time calculation, past slot exclusion in `get_doctor_availability`, and past booking validation (`PAST_APPOINTMENT_NOT_ALLOWED`) in `book_appointment`. |
| `backend/app/api/v1/doctors.py` | Added admin-authorized endpoint `GET /api/v1/doctors/admin/list` protected by `require_admin`. |
| `backend/app/db/seed_dev.py` | Implemented safe, idempotent development seeding for `pat_101` (Patient), `doc_202` (Doctor), and `adm_303` (Admin). |
| `backend/tests/unit/test_appointment_lifecycle.py` | Updated tests to use future dates and added regression tests for past date/time booking rejection and timezone boundaries. |
| `backend/tests/api/test_admin_doctors.py` | New API test suite verifying role authorization and data structure for `GET /api/v1/doctors/admin/list`. |
| `src/app/patient/doctors/page.tsx` | Added `getDoctorDisplaySpecialty`, defensive client-side past slot filtering, and clean empty state rendering. |
| `src/app/patient/queue/page.tsx` | Removed infinite re-render loop by decoupling `useCallback` from `activeQueue` using `prevQueueRef`. Handled all queue states explicitly. |
| `src/app/admin/doctors/page.tsx` | New administrative physician directory page with search, status filters, loading, error, and empty states. |
| `src/app/admin/layout.tsx` | Added "Physicians" route with `Stethoscope` icon to `ADMIN_NAV`. |
| `src/app/admin/dashboard/page.tsx` | Linked Doctor Directory metric card to `/admin/doctors`. |
| `src/services/doctors/index.ts` | Added `listDoctorsAdmin()` method to `DoctorService`. |
| `src/services/auth/index.ts` | Added `DEV_ROLE_TOKENS`, synchronized `careroute_auth_token` on role switch, and enhanced `logout()` session cleanup. |
| `.env.local` | Added `NEXT_PUBLIC_DEV_DOCTOR_AUTH_TOKEN` and `NEXT_PUBLIC_DEV_ADMIN_AUTH_TOKEN`. |
| `tests/frontend/demo_critical_fixes.test.mjs` | New frontend test suite covering all 5 critical issues. |

---

## 3. Tests Executed & Results

### Backend Automated Test Suites (pytest)
```bash
python -m pytest tests/unit/test_appointment_lifecycle.py tests/unit/test_doctor_recommendation.py tests/api/test_admin_doctors.py tests/api/test_auth_guard.py
```
* **Result:** **52 passed in 5.32s**
  - `test_appointment_lifecycle.py`: 11 passed (including past appointment rejection, slot exclusion, and timezone boundaries).
  - `test_doctor_recommendation.py`: 30 passed (including deterministic ranking and specialty eligibility).
  - `test_admin_doctors.py`: 4 passed (unauthenticated 401, patient 403, doctor 403, admin 200).
  - `test_auth_guard.py`: 7 passed (role-based security boundaries).

### Frontend Test Suites (Node Test Runner)
```bash
node --test tests/frontend/demo_critical_fixes.test.mjs tests/frontend/appointment_service.test.mjs tests/frontend/e2e_integration_audit.test.mjs tests/frontend/queue_service.test.mjs tests/frontend/triage_result_flow.test.mjs
```
* **Result:** **44 passed in 352ms**
  - `demo_critical_fixes.test.mjs`: 9 passed.
  - `appointment_service.test.mjs`: 10 passed.
  - `e2e_integration_audit.test.mjs`: 2 passed.
  - `queue_service.test.mjs`: 18 passed.
  - `triage_result_flow.test.mjs`: 5 passed.

### TypeScript Compilation Check
```bash
npx tsc --noEmit
```
* **Result:** **Exit code 0 (0 errors)**.

---

## 4. Verification: Admin Panel Doctor Retrieval

* **Verification Status:** **CONFIRMED**
* The Admin Doctors page at `/admin/doctors` now retrieves real physician records directly from `GET /api/v1/doctors/admin/list`.
* Hardcoded frontend mock doctor lists were eliminated from this view.
* Each row displays live backend data:
  - Doctor full name and contact email from `profiles`.
  - Medical license number from `doctors`.
  - Primary and secondary clinical specialties from `doctor_specialties` joined with `specialties`.
  - Department and Hospital facility names.
  - Years of clinical experience and patient rating statistics.
  - Consultation modes (`in_person`, `video`, `both`) and languages.
  - Practice status (`Active` vs `Inactive`).
* Role protection is active: non-administrators attempting to call the endpoint receive HTTP 403 `INSUFFICIENT_ROLE_PERMISSIONS`.

---

## 5. Steps Required to Log In as Admin and Doctor

The CareRoute-X demonstration environment employs development role switching that interacts with the backend JWT authentication middleware.

### To Log In as Administrator:
1. Navigate to `http://localhost:3000/login`.
2. Under **Demonstration Role Access**, click the **Administrator** role card (or click the **Admin** quick-switch button in the bottom navigation/sidebar).
3. The frontend sets:
   - User identity: `adm_303` (Mark Evans, Operations Director).
   - Local storage session: `careroute_user_session`.
   - Authorization header token: `careroute_auth_token` with claims `role: "admin"`.
4. You will be redirected to `http://localhost:3000/admin/dashboard`.
5. Click **Physicians** in the sidebar to view the live doctor directory at `http://localhost:3000/admin/doctors`.

### To Log In as Doctor:
1. Navigate to `http://localhost:3000/login`.
2. Under **Demonstration Role Access**, click the **Physician / Doctor** card.
3. The frontend sets:
   - User identity: `doc_202` (Dr. Anita Menon, MD).
   - Local storage session: `careroute_user_session`.
   - Authorization header token: `careroute_auth_token` with claims `role: "doctor"`.
4. You will be redirected to `http://localhost:3000/doctor/dashboard`.
5. Access the live outpatient queue at `http://localhost:3000/doctor/queue`.

### Production Authentication Note:
In a live production deployment, users log in via Supabase Auth email/password or OAuth. Supabase issues a signed JWT containing the user's UUID in `sub` and their assigned role in `app_metadata.role`. The backend middleware (`get_current_user` in `backend/app/core/dependencies.py`) decodes and verifies this token against `SUPABASE_JWT_SECRET`.

---

## 6. Development Credentials & Seeding Protocol

All development accounts are provisioned via `backend/app/db/seed_dev.py`.

### Configured Development Identities:

| Role | Auth User ID (`sub`) | Full Name | Associated Email | Access Area |
| :--- | :--- | :--- | :--- | :--- |
| **Patient** | `pat_101` | Sarah Jenkins | `sarah.jenkins@example.com` | `/patient/dashboard`, `/patient/triage`, `/patient/doctors`, `/patient/queue` |
| **Doctor** | `doc_202` | Dr. Anita Menon, MD | `dr.menon@metrocentral.org` | `/doctor/dashboard`, `/doctor/queue`, `/doctor/consultation` |
| **Admin** | `adm_303` | Mark Evans | `ops.admin@careroute.org` | `/admin/dashboard`, `/admin/doctors`, `/admin/queues`, `/admin/appointments` |

### To Re-Seed Development Accounts (Safe & Idempotent):
Execute from `D:\medcon5\backend`:
```bash
python -m app.db.seed_dev
```
*Non-production safeguard: The script explicitly verifies `settings.ENVIRONMENT != "production"` and aborts execution if run in a production environment.*

---

## 7. Remaining Manual Setup & Demo Readiness Checklist

1. **Backend Server Startup:**
   ```bash
   cd D:\medcon5\backend
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```
2. **Frontend Server Startup:**
   ```bash
   cd D:\medcon5
   npm run dev
   ```
3. **Pre-Demo Browser Reset:**
   - Clear browser `localStorage` or open an Incognito window to avoid cached demo tokens.
   - Click the role button corresponding to the scenario being presented (Patient, Doctor, or Admin).
4. **Demonstration Date Alignment:**
   - Doctor schedules in the database cover Monday through Sunday (`08:00` to `18:00`).
   - The slot booking interface defaults to the current calendar date (`today`). Any appointment booked must be for an upcoming time slot.
5. **No Blockers:** All 5 critical requirements have been verified with automated regression tests. The codebase is clean, type-safe, and ready for demonstration.
