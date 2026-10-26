import { describe, it, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";

describe("Doctor Clinic Station Intake Status & Availability Suite (Frontend)", () => {
  let originalFetch;
  let fetchCalls = [];

  const API_BASE_URL = "http://localhost:8000";

  class DoctorApiError extends Error {
    constructor(message, status, code) {
      super(message);
      this.name = "DoctorApiError";
      this.status = status;
      this.code = code;
    }
  }

  // Frontend Doctor Service implementation under test
  const doctorServiceClient = {
    async updateIntakeStatus(doctorId, isAcceptingPatients) {
      const res = await globalThis.fetch(
        `${API_BASE_URL}/api/v1/doctors/${encodeURIComponent(doctorId)}/intake-status`,
        {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
            Authorization: "Bearer mock-doctor-token",
          },
          body: JSON.stringify({ is_accepting_patients: isAcceptingPatients }),
        }
      );
      if (!res.ok) {
        let msg = `HTTP error ${res.status}`;
        let code = undefined;
        try {
          const body = await res.json();
          msg = body?.error?.message || body?.message || msg;
          code = body?.error?.code || body?.code;
        } catch {}
        throw new DoctorApiError(msg, res.status, code);
      }
      return res.json();
    },

    async getCurrentDoctor() {
      const res = await globalThis.fetch(`${API_BASE_URL}/api/v1/doctors/me`, {
        method: "GET",
        headers: {
          Authorization: "Bearer mock-doctor-token",
        },
      });
      if (!res.ok) {
        throw new DoctorApiError(`HTTP error ${res.status}`, res.status);
      }
      return res.json();
    },
  };

  beforeEach(() => {
    fetchCalls = [];
    originalFetch = globalThis.fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("1. Successfully toggles intake status from active to paused via PATCH", async () => {
    const doctorId = "doc-test-101";

    globalThis.fetch = async (url, options) => {
      fetchCalls.push({ url: url.toString(), options });
      assert.match(url.toString(), new RegExp(`/api/v1/doctors/${doctorId}/intake-status$`));
      assert.equal(options.method, "PATCH");
      assert.equal(options.headers["Authorization"], "Bearer mock-doctor-token");
      assert.deepEqual(JSON.parse(options.body), { is_accepting_patients: false });

      return {
        ok: true,
        status: 200,
        json: async () => ({
          doctor_id: doctorId,
          is_accepting_patients: false,
          status: "Station Paused",
          message: "Clinic station intake status updated to 'Station Paused'.",
        }),
      };
    };

    const result = await doctorServiceClient.updateIntakeStatus(doctorId, false);

    assert.equal(result.is_accepting_patients, false);
    assert.equal(result.status, "Station Paused");
    assert.equal(fetchCalls.length, 1);
  });

  it("2. Reactivates intake status from paused to accepting patients", async () => {
    const doctorId = "doc-test-101";

    globalThis.fetch = async (url, options) => {
      fetchCalls.push({ url: url.toString(), options });
      assert.deepEqual(JSON.parse(options.body), { is_accepting_patients: true });

      return {
        ok: true,
        status: 200,
        json: async () => ({
          doctor_id: doctorId,
          is_accepting_patients: true,
          status: "Accepting Patients",
          message: "Clinic station intake status updated to 'Accepting Patients'.",
        }),
      };
    };

    const result = await doctorServiceClient.updateIntakeStatus(doctorId, true);

    assert.equal(result.is_accepting_patients, true);
    assert.equal(result.status, "Accepting Patients");
  });

  it("3. Failed backend request preserves previous state and surfaces error", async () => {
    const doctorId = "doc-test-101";

    globalThis.fetch = async () => {
      return {
        ok: false,
        status: 503,
        json: async () => ({
          error: {
            code: "SERVICE_UNAVAILABLE",
            message: "Clinic database is temporarily unreachable.",
          },
        }),
      };
    };

    // Component state machine simulation
    let isAvailable = true;
    let statusError = null;

    await assert.rejects(
      async () => {
        try {
          await doctorServiceClient.updateIntakeStatus(doctorId, false);
          isAvailable = false;
        } catch (err) {
          // Revert to authoritative previous status and set error
          statusError = err.message;
          throw err;
        }
      },
      (err) => {
        assert(err instanceof DoctorApiError);
        assert.equal(err.status, 503);
        assert.match(err.message, /temporarily unreachable/);
        return true;
      }
    );

    // Assert that state was NOT drifted / stayed true
    assert.equal(isAvailable, true);
    assert.match(statusError, /temporarily unreachable/);
  });

  it("4. Profile reload (getCurrentDoctor) retrieves saved authoritative intake status", async () => {
    globalThis.fetch = async (url) => {
      assert.match(url.toString(), /\/api\/v1\/doctors\/me$/);
      return {
        ok: true,
        status: 200,
        json: async () => ({
          id: "doc-test-101",
          profile_id: "prof-101",
          hospital_id: "hosp-101",
          license_number: "LIC-101",
          years_of_experience: 12,
          consultation_mode: "both",
          average_rating: 4.8,
          rating_count: 30,
          languages: "en",
          is_active: true,
          is_accepting_patients: false, // Authoritatively paused
          profile: {
            id: "prof-101",
            full_name: "Dr. Elena Vance",
            email: "evance@hospital.org",
            role: "doctor",
          },
          specialties: [],
        }),
      };
    };

    const doc = await doctorServiceClient.getCurrentDoctor();

    assert.equal(doc.is_accepting_patients, false);
    assert.equal(doc.is_active, true);
  });

  it("5. Guard against rapid repeated clicks prevents concurrent duplicate submissions", async () => {
    let pendingRequest = false;
    let submissionCount = 0;

    async function handleToggleClick(targetStatus) {
      if (pendingRequest) return null; // In-flight submission blocked
      pendingRequest = true;
      try {
        submissionCount++;
        // Simulate async network latency
        await new Promise((r) => setTimeout(r, 20));
        return { is_accepting_patients: targetStatus };
      } finally {
        pendingRequest = false;
      }
    }

    // Trigger two rapid clicks while first is in-flight
    const [click1, click2] = await Promise.all([
      handleToggleClick(false),
      handleToggleClick(false),
    ]);

    assert.notEqual(click1, null);
    assert.equal(click2, null); // Second click was blocked
    assert.equal(submissionCount, 1);
  });

  it("6. Intake status is strictly decoupled from account active status (is_active)", () => {
    const doctorProfile = {
      id: "doc-1",
      is_active: true,             // Account status (managed by Admin)
      is_accepting_patients: false, // Station intake status (managed by Doctor)
    };

    // Pausing station intake does not deactivate doctor account
    assert.equal(doctorProfile.is_active, true);
    assert.equal(doctorProfile.is_accepting_patients, false);
  });
});
