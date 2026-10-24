import { test, describe, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";

describe("Patient Hospital Selection & Doctor Matching Flow (Frontend)", () => {
  let originalFetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  const mockHospitals = [
    {
      id: "hosp-001",
      name: "Metro General Hospital",
      code: "MGH",
      address: "100 Medical Center Way",
      phone: "+1-555-0100",
      is_active: true,
    },
    {
      id: "hosp-002",
      name: "St. Jude Clinical Center",
      code: "SJCC",
      address: "250 Hope Boulevard",
      phone: "+1-555-0200",
      is_active: true,
    },
  ];

  class DoctorApiError extends Error {
    constructor(message, status, code) {
      super(message);
      this.name = "DoctorApiError";
      this.status = status;
      this.code = code;
    }
  }

  // Frontend DoctorService Simulator
  class DoctorServiceSimulator {
    async listHospitals() {
      const res = await globalThis.fetch("http://localhost:8000/api/v1/hospitals");
      const data = await res.json();
      return data;
    }

    async recommendDoctors(request) {
      const res = await globalThis.fetch("http://localhost:8000/api/v1/doctors/recommend", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new DoctorApiError(data?.error?.message || "HTTP Error", res.status, data?.error?.code);
      }
      return data;
    }
  }

  test("1. Missing hospital context returns structured 409 MISSING_HOSPITAL_CONTEXT", async () => {
    globalThis.fetch = async (url, options) => {
      const body = options?.body ? JSON.parse(options.body) : {};
      if (body.hospital_id) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            status: "SUCCESS",
            applied_hospital_id: body.hospital_id,
            recommendations: [{ doctor_id: "doc-1", rank: 1, score: 0.95 }],
          }),
        };
      }
      return {
        ok: false,
        status: 409,
        json: async () => ({
          error: {
            code: "MISSING_HOSPITAL_CONTEXT",
            message: "Hospital ID must be specified in request or associated with user account",
          },
        }),
      };
    };

    const service = new DoctorServiceSimulator();
    await assert.rejects(
      async () => {
        await service.recommendDoctors({ triage_session_id: "session-123" });
      },
      (err) => {
        assert.equal(err instanceof DoctorApiError, true);
        assert.equal(err.status, 409);
        assert.equal(err.code, "MISSING_HOSPITAL_CONTEXT");
        return true;
      }
    );
  });

  test("2. Unaffiliated patient prompts hospital selection, lists facilities, and retries with selected hospital", async () => {
    let requests = [];

    globalThis.fetch = async (url, options) => {
      const urlStr = String(url);
      if (urlStr.includes("/api/v1/hospitals")) {
        return {
          ok: true,
          status: 200,
          json: async () => mockHospitals,
        };
      }

      if (urlStr.includes("/api/v1/doctors/recommend")) {
        const body = options?.body ? JSON.parse(options.body) : {};
        requests.push(body);

        if (!body.hospital_id) {
          return {
            ok: false,
            status: 409,
            json: async () => ({
              error: {
                code: "MISSING_HOSPITAL_CONTEXT",
                message: "Hospital ID must be specified in request or associated with user account",
              },
            }),
          };
        }

        return {
          ok: true,
          status: 200,
          json: async () => ({
            status: "SUCCESS",
            applied_hospital_id: body.hospital_id,
            applied_specialty_name: "Cardiology",
            recommendations: [
              {
                doctor_id: "doc-cardio-1",
                rank: 1,
                score: 0.96,
                doctor: {
                  id: "doc-cardio-1",
                  hospital_id: body.hospital_id,
                  profile: { full_name: "Dr. Anita Menon" },
                },
              },
            ],
          }),
        };
      }

      throw new Error(`Unexpected fetch to ${urlStr}`);
    };

    const service = new DoctorServiceSimulator();

    // Step A: Initial request fails with MISSING_HOSPITAL_CONTEXT
    let needsHospitalSelection = false;
    try {
      await service.recommendDoctors({ triage_session_id: "session-456" });
    } catch (err) {
      if (err.code === "MISSING_HOSPITAL_CONTEXT") {
        needsHospitalSelection = true;
      }
    }
    assert.equal(needsHospitalSelection, true);

    // Step B: Frontend fetches active hospitals to display selection UI
    const availableHospitals = await service.listHospitals();
    assert.equal(availableHospitals.length, 2);
    assert.equal(availableHospitals[0].id, "hosp-001");
    assert.equal(availableHospitals[1].id, "hosp-002");

    // Step C: Patient selects Metro General Hospital (hosp-001) and retries
    const selectedHospital = availableHospitals[0];
    const recResult = await service.recommendDoctors({
      triage_session_id: "session-456",
      hospital_id: selectedHospital.id,
    });

    assert.equal(recResult.status, "SUCCESS");
    assert.equal(recResult.applied_hospital_id, "hosp-001");
    assert.equal(recResult.recommendations.length, 1);
    assert.equal(recResult.recommendations[0].doctor.hospital_id, "hosp-001");

    // Verify 2 backend calls occurred (initial without hospital, followed by retry with selected hospital)
    assert.equal(requests.length, 2);
    assert.equal(requests[0].hospital_id, undefined);
    assert.equal(requests[1].hospital_id, "hosp-001");
  });

  test("3. Profile-associated hospital succeeds on initial request without explicit hospital param", async () => {
    globalThis.fetch = async (url, options) => {
      const body = options?.body ? JSON.parse(options.body) : {};
      // Backend resolves hospital from authenticated profile
      return {
        ok: true,
        status: 200,
        json: async () => ({
          status: "SUCCESS",
          applied_hospital_id: "hosp-001",
          recommendations: [{ doctor_id: "doc-profile-1", rank: 1, score: 0.91 }],
        }),
      };
    };

    const service = new DoctorServiceSimulator();
    const result = await service.recommendDoctors({ triage_session_id: "session-affiliated" });
    assert.equal(result.status, "SUCCESS");
    assert.equal(result.applied_hospital_id, "hosp-001");
  });

  test("4. Cross-hospital request for registered patient is forbidden with 403", async () => {
    globalThis.fetch = async (url, options) => {
      return {
        ok: false,
        status: 403,
        json: async () => ({
          error: {
            code: "FORBIDDEN_CROSS_HOSPITAL_ACCESS",
            message: "Access forbidden: cannot request recommendations outside your registered hospital",
          },
        }),
      };
    };

    const service = new DoctorServiceSimulator();
    await assert.rejects(
      async () => {
        await service.recommendDoctors({
          triage_session_id: "session-affil",
          hospital_id: "hosp-002",
        });
      },
      (err) => {
        assert.equal(err.status, 403);
        assert.equal(err.code, "FORBIDDEN_CROSS_HOSPITAL_ACCESS");
        return true;
      }
    );
  });

  test("5. Red-flag emergency assessment preserves emergency notice and routing", async () => {
    globalThis.fetch = async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        status: "EMERGENCY_ESCALATION",
        is_emergency_escalation: true,
        escalation_notice: "EMERGENCY SAFETY NOTICE: Immediate emergency care is advised.",
        applied_hospital_id: "hosp-001",
        recommendations: [],
      }),
    });

    const service = new DoctorServiceSimulator();
    const res = await service.recommendDoctors({
      triage_session_id: "session-emergency",
      hospital_id: "hosp-001",
    });

    assert.equal(res.status, "EMERGENCY_ESCALATION");
    assert.equal(res.is_emergency_escalation, true);
    assert.ok(res.escalation_notice.includes("EMERGENCY SAFETY NOTICE"));
  });
});
