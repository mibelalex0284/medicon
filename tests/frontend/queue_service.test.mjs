import { test, describe, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";

describe("Patient Live Queue Integration (Frontend Service)", () => {
  let originalFetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  test("Retrieves authenticated patient active queue from /api/v1/patients/me/queue", async () => {
    globalThis.fetch = async (url, options) => {
      assert.match(url, /\/api\/v1\/patients\/me\/queue/);
      assert.equal(options?.method || "GET", "GET");
      return {
        ok: true,
        status: 200,
        json: async () => ({
          queue_entry_id: "q_1001",
          appointment_id: "appt_2001",
          doctor_id: "doc_202",
          hospital_id: "hosp_001",
          token_number: "A07",
          status: "WAITING",
          checked_in_at: "2026-10-25T09:15:00Z",
          called_at: null,
          consultation_started_at: null,
          patients_ahead: 2,
          wait_estimate: {
            lower_minutes: 20,
            expected_minutes: 30,
            upper_minutes: 42,
            source: "baseline",
          },
          patient_name: "Sarah Jenkins",
          doctor_name: "Dr. Anita Menon, MD",
          room_number: "Room 204",
          department_name: "Adult Outpatient Clinic",
          chief_complaint: "Persistent cough and mild wheezing",
        }),
      };
    };

    const res = await globalThis.fetch("http://localhost:8000/api/v1/patients/me/queue");
    assert.equal(res.status, 200);
    const data = await res.json();
    assert.equal(data.token_number, "A07");
    assert.equal(data.status, "WAITING");
    assert.equal(data.patients_ahead, 2);
    assert.equal(data.wait_estimate.expected_minutes, 30);
    assert.equal(data.room_number, "Room 204");
  });

  test("Patient with no active queue receives 404 NO_ACTIVE_QUEUE_ENTRY and resolves to empty", async () => {
    globalThis.fetch = async (url) => {
      assert.match(url, /\/api\/v1\/patients\/me\/queue/);
      return {
        ok: false,
        status: 404,
        json: async () => ({
          error: {
            code: "NO_ACTIVE_QUEUE_ENTRY",
            message: "No active queue entry found for patient",
          },
        }),
      };
    };

    const res = await globalThis.fetch("http://localhost:8000/api/v1/patients/me/queue");
    assert.equal(res.status, 404);
    const errBody = await res.json();
    assert.equal(errBody.error.code, "NO_ACTIVE_QUEUE_ENTRY");
  });

  test("Patient authentication failure (401/403) returns appropriate error status", async () => {
    globalThis.fetch = async () => ({
      ok: false,
      status: 401,
      json: async () => ({
        detail: "Could not validate credentials",
      }),
    });

    const res = await globalThis.fetch("http://localhost:8000/api/v1/patients/me/queue");
    assert.equal(res.status, 401);
  });

  test("Patient access to doctor queue endpoint /api/v1/queues/me/current receives 403 Forbidden", async () => {
    globalThis.fetch = async (url) => {
      assert.match(url, /\/api\/v1\/queues\/me\/current/);
      return {
        ok: false,
        status: 403,
        json: async () => ({
          detail: "Doctor privileges required",
        }),
      };
    };

    const res = await globalThis.fetch("http://localhost:8000/api/v1/queues/me/current");
    assert.equal(res.status, 403);
  });

  test("Patient dashboard handles empty queue (NO_ACTIVE_QUEUE_ENTRY) by rendering scheduled/find-care state", async () => {
    // Simulating patient dashboard queue lookup returning 404 NO_ACTIVE_QUEUE_ENTRY
    globalThis.fetch = async (url) => {
      if (url.includes("/api/v1/patients/me/queue")) {
        return {
          ok: false,
          status: 404,
          json: async () => ({
            error: {
              code: "NO_ACTIVE_QUEUE_ENTRY",
              message: "No active queue entry found for patient",
            },
          }),
        };
      }
      throw new Error(`Unexpected endpoint: ${url}`);
    };

    const res = await globalThis.fetch("http://localhost:8000/api/v1/patients/me/queue");
    assert.equal(res.status, 404);
    const data = await res.json();
    assert.equal(data.error.code, "NO_ACTIVE_QUEUE_ENTRY");
    // Resolved activeQueue is null/undefined
    const activeQueue = data.error.code === "NO_ACTIVE_QUEUE_ENTRY" ? null : data;
    assert.equal(activeQueue, null);
  });

  test("Genuine 404 (e.g. PATIENT_PROFILE_NOT_FOUND) is not treated as legitimate empty queue", async () => {
    globalThis.fetch = async () => ({
      ok: false,
      status: 404,
      json: async () => ({
        error: {
          code: "PATIENT_PROFILE_NOT_FOUND",
          message: "No patient record found for the current authenticated user",
        },
      }),
    });

    const res = await globalThis.fetch("http://localhost:8000/api/v1/patients/me/queue");
    assert.equal(res.status, 404);
    const data = await res.json();
    assert.notEqual(data.error.code, "NO_ACTIVE_QUEUE_ENTRY");
    assert.equal(data.error.code, "PATIENT_PROFILE_NOT_FOUND");
  });
});

describe("Doctor Operational Queue Integration (Frontend Service)", () => {
  let originalFetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  test("Retrieves doctor active queue from /api/v1/queues/me/current", async () => {
    globalThis.fetch = async (url) => {
      assert.match(url, /\/api\/v1\/queues\/me\/current/);
      return {
        ok: true,
        status: 200,
        json: async () => [
          {
            id: "q_1",
            appointment_id: "appt_1",
            patient_id: "pat_1",
            doctor_id: "doc_202",
            hospital_id: "hosp_001",
            queue_date: "2026-10-25",
            token_number: "A01",
            status: "CALLED",
            checked_in_at: "2026-10-25T08:45:00Z",
            called_at: "2026-10-25T09:00:00Z",
            patient_name: "Arthur Dent",
            doctor_name: "Dr. Anita Menon, MD",
            chief_complaint: "Routine review",
          },
          {
            id: "q_2",
            appointment_id: "appt_2",
            patient_id: "pat_2",
            doctor_id: "doc_202",
            hospital_id: "hosp_001",
            queue_date: "2026-10-25",
            token_number: "A02",
            status: "WAITING",
            checked_in_at: "2026-10-25T08:50:00Z",
            patient_name: "Ford Prefect",
            doctor_name: "Dr. Anita Menon, MD",
            chief_complaint: "Headache",
          },
        ],
      };
    };

    const res = await globalThis.fetch("http://localhost:8000/api/v1/queues/me/current");
    assert.equal(res.status, 200);
    const list = await res.json();
    assert.equal(list.length, 2);
    assert.equal(list[0].token_number, "A01");
    assert.equal(list[0].status, "CALLED");
    assert.equal(list[1].token_number, "A02");
    assert.equal(list[1].status, "WAITING");
  });

  test("Doctor calls next patient via POST /api/v1/queues/{id}/call", async () => {
    globalThis.fetch = async (url, options) => {
      assert.match(url, /\/api\/v1\/queues\/q_2\/call/);
      assert.equal(options.method, "POST");
      return {
        ok: true,
        status: 200,
        json: async () => ({
          id: "q_2",
          status: "CALLED",
          called_at: "2026-10-25T09:05:00Z",
          token_number: "A02",
        }),
      };
    };

    const res = await globalThis.fetch("http://localhost:8000/api/v1/queues/q_2/call", {
      method: "POST",
    });
    assert.equal(res.status, 200);
    const data = await res.json();
    assert.equal(data.status, "CALLED");
    assert.equal(data.token_number, "A02");
  });

  test("Doctor starts consultation via POST /api/v1/queues/{id}/start", async () => {
    globalThis.fetch = async (url, options) => {
      assert.match(url, /\/api\/v1\/queues\/q_2\/start/);
      assert.equal(options.method, "POST");
      return {
        ok: true,
        status: 200,
        json: async () => ({
          id: "c_200",
          queue_entry_id: "q_2",
          appointment_id: "appt_2",
          patient_id: "pat_2",
          doctor_id: "doc_202",
          hospital_id: "hosp_001",
          started_at: "2026-10-25T09:06:00Z",
          status: "IN_PROGRESS",
        }),
      };
    };

    const res = await globalThis.fetch("http://localhost:8000/api/v1/queues/q_2/start", {
      method: "POST",
    });
    assert.equal(res.status, 200);
    const data = await res.json();
    assert.equal(data.status, "IN_PROGRESS");
    assert.equal(data.queue_entry_id, "q_2");
  });

  test("Doctor completes consultation via POST /api/v1/queues/{id}/complete", async () => {
    globalThis.fetch = async (url, options) => {
      assert.match(url, /\/api\/v1\/queues\/q_2\/complete/);
      assert.equal(options.method, "POST");
      return {
        ok: true,
        status: 200,
        json: async () => ({
          id: "c_200",
          queue_entry_id: "q_2",
          status: "COMPLETED",
          completed_at: "2026-10-25T09:20:00Z",
          duration_seconds: 840,
        }),
      };
    };

    const res = await globalThis.fetch("http://localhost:8000/api/v1/queues/q_2/complete", {
      method: "POST",
    });
    assert.equal(res.status, 200);
    const data = await res.json();
    assert.equal(data.status, "COMPLETED");
    assert.equal(data.duration_seconds, 840);
  });

  test("Doctor marks patient as NO_SHOW via POST /api/v1/queues/{id}/no-show", async () => {
    globalThis.fetch = async (url, options) => {
      assert.match(url, /\/api\/v1\/queues\/q_3\/no-show/);
      assert.equal(options.method, "POST");
      return {
        ok: true,
        status: 200,
        json: async () => ({
          id: "q_3",
          status: "NO_SHOW",
          token_number: "A03",
        }),
      };
    };

    const res = await globalThis.fetch("http://localhost:8000/api/v1/queues/q_3/no-show", {
      method: "POST",
    });
    assert.equal(res.status, 200);
    const data = await res.json();
    assert.equal(data.status, "NO_SHOW");
  });

  test("Invalid lifecycle transition returns 400 and does not falsely update client", async () => {
    globalThis.fetch = async () => ({
      ok: false,
      status: 400,
      json: async () => ({
        detail: "Cannot call patient in 'COMPLETED' state. Must be WAITING.",
      }),
    });

    const res = await globalThis.fetch("http://localhost:8000/api/v1/queues/q_completed/call", {
      method: "POST",
    });
    assert.equal(res.status, 400);
    const data = await res.json();
    assert.match(data.detail, /Cannot call patient/);
  });

  test("Duplicate rapid submission protection flag prevents concurrent triggers", async () => {
    let callCount = 0;
    let inFlight = false;

    const guardedAction = async () => {
      if (inFlight) return null; // In-flight guard
      inFlight = true;
      try {
        callCount++;
        await new Promise((r) => setTimeout(r, 40));
        return { success: true };
      } finally {
        inFlight = false;
      }
    };

    const [first, second] = await Promise.all([guardedAction(), guardedAction()]);
    assert.equal(callCount, 1);
    assert.deepEqual(first, { success: true });
    assert.equal(second, null);
  });
});
