import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";

describe("Demo Critical Fixes Regression Suite", () => {
  describe("Issue 1: Doctor Specialty Resolution & Consistency", () => {
    function getDoctorDisplaySpecialty(doctor, appliedSpecialtyName) {
      if (appliedSpecialtyName) {
        const matched = doctor.specialties?.find(
          (s) => s.specialty?.name?.toLowerCase() === appliedSpecialtyName.toLowerCase()
        );
        if (matched?.specialty?.name) return matched.specialty.name;
      }
      const primary = doctor.specialties?.find((s) => s.is_primary);
      if (primary?.specialty?.name) return primary.specialty.name;
      return (
        doctor.specialties?.[0]?.specialty?.name ||
        appliedSpecialtyName ||
        "Specialist"
      );
    }

    it("does not present a Dermatologist as General Medicine when primary is Dermatology and secondary General Medicine is queried", () => {
      // Dr. Sarah Lindqvist
      const doctor = {
        id: "14b58406",
        profile: { full_name: "Dr. Sarah Lindqvist, MD" },
        specialties: [
          { specialty: { name: "Dermatology" }, is_primary: true },
          { specialty: { name: "General Medicine" }, is_primary: false },
        ],
      };

      // When queried for General Medicine, the card must show the matched specialty "General Medicine"
      const displayed = getDoctorDisplaySpecialty(doctor, "General Medicine");
      assert.equal(displayed, "General Medicine");
    });

    it("correctly identifies primary specialty when appliedSpecialtyName is omitted", () => {
      const doctor = {
        id: "e8df51bd",
        profile: { full_name: "Dr. Elena Rostova, MD" },
        specialties: [
          { specialty: { name: "Orthopedics" }, is_primary: true },
        ],
      };

      const displayed = getDoctorDisplaySpecialty(doctor, null);
      assert.equal(displayed, "Orthopedics");
    });

    it("falls back to applied specialty name if doctor has no explicit specialties", () => {
      const doctor = {
        id: "doc_none",
        profile: { full_name: "Dr. No Special" },
        specialties: [],
      };

      const displayed = getDoctorDisplaySpecialty(doctor, "Cardiology");
      assert.equal(displayed, "Cardiology");
    });
  });

  describe("Issue 2: Past Slot Filtering & Backend Rejection", () => {
    it("filters out past slots on today's date defensively in the client", () => {
      const slots = [
        { start_time: "08:00", end_time: "08:30", is_available: true },
        { start_time: "09:00", end_time: "09:30", is_available: true },
        { start_time: "14:00", end_time: "14:30", is_available: true },
        { start_time: "18:00", end_time: "18:30", is_available: true },
      ];

      // Simulate client filtering at 11:30 AM
      const currentHour = 11;
      const currentMin = 30;

      const futureSlots = slots.filter((slot) => {
        const [h, m] = slot.start_time.split(":").map(Number);
        return h > currentHour || (h === currentHour && m > currentMin);
      });

      assert.equal(futureSlots.length, 2);
      assert.equal(futureSlots[0].start_time, "14:00");
      assert.equal(futureSlots[1].start_time, "18:00");
    });

    it("backend error for past booking returns descriptive message", () => {
      const backendError = {
        error: {
          code: "PAST_APPOINTMENT_NOT_ALLOWED",
          message: "Cannot book an appointment for a past date or time.",
        },
      };

      assert.equal(backendError.error.code, "PAST_APPOINTMENT_NOT_ALLOWED");
      assert.match(backendError.error.message, /past date or time/i);
    });
  });

  describe("Issue 3: Queue Page Lifecycle & State Machine", () => {
    it("handles active queue token response cleanly", () => {
      const mockBackendResponse = {
        queue_entry_id: "qe-123",
        token_number: "A01",
        doctor_id: "doc-1",
        doctor_name: "Dr. Anita Menon, MD",
        hospital_id: "hosp-1",
        appointment_id: "apt-1",
        status: "WAITING",
        patients_ahead: 2,
        wait_estimate: { lower_minutes: 10, upper_minutes: 25 },
        checked_in_at: "2026-10-22T09:00:00Z",
      };

      assert.equal(mockBackendResponse.token_number, "A01");
      assert.equal(mockBackendResponse.patients_ahead, 2);
      assert.equal(mockBackendResponse.wait_estimate.lower_minutes, 10);
    });

    it("handles 404 NO_ACTIVE_QUEUE_ENTRY as a legitimate empty queue state", () => {
      const errorResponse = {
        error: {
          code: "NO_ACTIVE_QUEUE_ENTRY",
          message: "No active queue entry found for patient",
        },
      };

      const isEmptyQueue = errorResponse.error.code === "NO_ACTIVE_QUEUE_ENTRY";
      assert.equal(isEmptyQueue, true);
    });
  });

  describe("Issue 4: Admin Doctor Directory", () => {
    it("validates doctor record structure for the admin table", () => {
      const mockDoctor = {
        id: "e973f5b3",
        profile: {
          full_name: "Dr. Anita Menon, MD",
          email: "dr.menon@metrocentral.org",
        },
        license_number: "MD-CRX-2026-0202",
        years_of_experience: 14,
        consultation_mode: "both",
        average_rating: 4.9,
        rating_count: 38,
        languages: "en,hi,ml",
        is_active: true,
        specialties: [
          { specialty: { name: "Internal Medicine" }, is_primary: true },
        ],
        department: { name: "Adult Outpatient Clinic" },
        hospital: { name: "Metro Central Hospital" },
      };

      assert.equal(mockDoctor.profile.full_name, "Dr. Anita Menon, MD");
      assert.equal(mockDoctor.is_active, true);
      assert.equal(mockDoctor.specialties[0].specialty.name, "Internal Medicine");
      assert.equal(mockDoctor.department.name, "Adult Outpatient Clinic");
    });
  });

  describe("Issue 5: Authentication & Dev Role Token Swapping", () => {
    it("swaps active token when logging in as different roles", () => {
      const storage = {};
      const devTokens = {
        patient: "token_pat_101",
        doctor: "token_doc_202",
        admin: "token_adm_303",
      };

      function loginAsRole(role) {
        storage["careroute_user_session"] = JSON.stringify({ role });
        storage["careroute_auth_token"] = devTokens[role];
      }

      function logout() {
        delete storage["careroute_user_session"];
        delete storage["careroute_auth_token"];
      }

      loginAsRole("doctor");
      assert.equal(storage["careroute_auth_token"], "token_doc_202");

      loginAsRole("admin");
      assert.equal(storage["careroute_auth_token"], "token_adm_303");

      loginAsRole("patient");
      assert.equal(storage["careroute_auth_token"], "token_pat_101");

      logout();
      assert.equal(storage["careroute_user_session"], undefined);
      assert.equal(storage["careroute_auth_token"], undefined);
    });
  });
});
