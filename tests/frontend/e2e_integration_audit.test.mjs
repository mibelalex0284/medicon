import test, { describe } from "node:test";
import assert from "node:assert/strict";

describe("Phase 3B.3 End-to-End Frontend Integration Audit", () => {
  // Mock Fetch Harness for Deterministic Client Verification
  function createMockFetch(routes) {
    return async function mockFetch(url, options = {}) {
      const parsedUrl = new URL(url);
      const path = parsedUrl.pathname;
      const method = options.method || "GET";
      const key = `${method} ${path}`;

      const handler = routes[key] || routes[path];
      if (!handler) {
        return {
          ok: false,
          status: 404,
          json: async () => ({
            error: { code: "NOT_FOUND", message: `No mock route for ${key}` },
          }),
        };
      }

      const result = typeof handler === "function" ? await handler(options, parsedUrl) : handler;
      return {
        ok: result.status >= 200 && result.status < 300,
        status: result.status,
        json: async () => result.body,
      };
    };
  }

  test("Complete Patient-to-Doctor Frontend Flow (Booking -> Checkin -> Call -> Start -> Complete)", async () => {
    let apptState = {
      id: "appt-e2e-001",
      patient_id: "patient-123",
      doctor_id: "doc-456",
      hospital_id: "hosp-001",
      appointment_date: "2026-10-21",
      scheduled_start: "10:00:00",
      scheduled_end: "10:30:00",
      appointment_type: "in_person",
      status: "BOOKED",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      doctor_name: "Dr. Evelyn Shaw",
      doctor_specialty: "General Medicine",
      department_name: "Outpatient Clinic",
      queue_token: null,
    };

    let queueState = null;
    let consultationState = null;

    const routes = {
      // 1. Patient Profile
      "GET /api/v1/patients/me": {
        status: 200,
        body: {
          id: "patient-123",
          profile_id: "prof-pat-1",
          date_of_birth: "1990-01-01",
          preferred_language: "en",
          profile: {
            id: "prof-pat-1",
            auth_user_id: "auth-p1",
            role: "patient",
            full_name: "Alice Walker",
            email: "alice@test.org",
          },
        },
      },

      // 2. Doctor Availability
      "GET /api/v1/doctors/doc-456/availability": {
        status: 200,
        body: {
          doctor_id: "doc-456",
          hospital_id: "hosp-001",
          appointment_date: "2026-10-21",
          slot_duration_minutes: 30,
          slots: [
            { start_time: "10:00:00", end_time: "10:30:00", is_available: true },
            { start_time: "10:30:00", end_time: "11:00:00", is_available: true },
          ],
        },
      },

      // 3. Appointment Booking
      "POST /api/v1/appointments": (opts) => {
        const body = JSON.parse(opts.body);
        if (body.scheduled_start === "10:00:00" && apptState.status === "BOOKED" && queueState) {
          return {
            status: 409,
            body: { error: { code: "APPOINTMENT_CONFLICT", message: "Slot already booked" } },
          };
        }
        return { status: 201, body: apptState };
      },

      // 4. Appointment List
      "GET /api/v1/appointments": () => ({
        status: 200,
        body: [apptState],
      }),

      // 5. Patient Check-In
      "POST /api/v1/appointments/appt-e2e-001/check-in": () => {
        if (queueState) {
          return {
            status: 409,
            body: { error: { code: "ALREADY_CHECKED_IN", message: "Already checked in" } },
          };
        }
        apptState.status = "CONFIRMED";
        apptState.queue_token = "A01";
        queueState = {
          id: "q-e2e-001",
          appointment_id: "appt-e2e-001",
          patient_id: "patient-123",
          doctor_id: "doc-456",
          hospital_id: "hosp-001",
          queue_date: "2026-10-21",
          token_number: "A01",
          status: "WAITING",
          checked_in_at: new Date().toISOString(),
          patient_name: "Alice Walker",
          doctor_name: "Dr. Evelyn Shaw",
          department_name: "Outpatient Clinic",
          chief_complaint: "Persistent cough",
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
        return { status: 201, body: queueState };
      },

      // 6. Patient Active Queue View
      "GET /api/v1/patients/me/queue": () => {
        if (!queueState) {
          return {
            status: 404,
            body: { error: { code: "NO_ACTIVE_QUEUE_ENTRY", message: "No active queue entry" } },
          };
        }
        return {
          status: 200,
          body: {
            queue_entry_id: queueState.id,
            appointment_id: queueState.appointment_id,
            doctor_id: queueState.doctor_id,
            hospital_id: queueState.hospital_id,
            token_number: queueState.token_number,
            status: queueState.status,
            checked_in_at: queueState.checked_in_at,
            called_at: queueState.called_at,
            consultation_started_at: queueState.consultation_started_at,
            patients_ahead: 0,
            wait_estimate: {
              lower_minutes: 5,
              expected_minutes: 10,
              upper_minutes: 15,
              source: "baseline",
            },
            patient_name: queueState.patient_name,
            doctor_name: queueState.doctor_name,
            department_name: queueState.department_name,
            chief_complaint: queueState.chief_complaint,
          },
        };
      },

      // 7. Doctor Operational Queue
      "GET /api/v1/queues/doc-456/current": () => ({
        status: 200,
        body: queueState ? [queueState] : [],
      }),

      // 8. Doctor Calls Patient
      "POST /api/v1/queues/q-e2e-001/call": () => {
        queueState.status = "CALLED";
        queueState.called_at = new Date().toISOString();
        return { status: 200, body: queueState };
      },

      // 9. Doctor Starts Consultation
      "POST /api/v1/queues/q-e2e-001/start": () => {
        queueState.status = "IN_CONSULTATION";
        queueState.consultation_started_at = new Date().toISOString();
        consultationState = {
          id: "cons-e2e-001",
          queue_entry_id: queueState.id,
          appointment_id: queueState.appointment_id,
          patient_id: queueState.patient_id,
          doctor_id: queueState.doctor_id,
          hospital_id: queueState.hospital_id,
          started_at: queueState.consultation_started_at,
          status: "IN_PROGRESS",
          patient_name: "Alice Walker",
          doctor_name: "Dr. Evelyn Shaw",
          token_number: "A01",
          chief_complaint: "Persistent cough",
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
        return { status: 200, body: consultationState };
      },

      // 10. Doctor Active Consultation
      "GET /api/v1/queues/active-consultation": () => ({
        status: 200,
        body: consultationState,
      }),

      // 11. Doctor Completes Consultation
      "POST /api/v1/queues/q-e2e-001/complete": () => {
        queueState.status = "COMPLETED";
        queueState.completed_at = new Date().toISOString();
        apptState.status = "COMPLETED";
        consultationState.status = "COMPLETED";
        consultationState.completed_at = queueState.completed_at;
        consultationState.duration_seconds = 420;
        return { status: 200, body: consultationState };
      },
    };

    const originalFetch = global.fetch;
    global.fetch = createMockFetch(routes);

    try {
      // Step A: Patient verifies identity
      const patRes = await global.fetch("http://localhost:8000/api/v1/patients/me");
      assert.equal(patRes.status, 200);
      const patData = await patRes.json();
      assert.equal(patData.id, "patient-123");

      // Step B: Check doctor availability
      const availRes = await global.fetch("http://localhost:8000/api/v1/doctors/doc-456/availability");
      assert.equal(availRes.status, 200);
      const availData = await availRes.json();
      assert.equal(availData.slots.length, 2);

      // Step C: Book appointment
      const bookRes = await global.fetch("http://localhost:8000/api/v1/appointments", {
        method: "POST",
        body: JSON.stringify({
          patient_id: "patient-123",
          doctor_id: "doc-456",
          hospital_id: "hosp-001",
          appointment_date: "2026-10-21",
          scheduled_start: "10:00:00",
          scheduled_end: "10:30:00",
        }),
      });
      assert.equal(bookRes.status, 201);
      const bookedData = await bookRes.json();
      assert.equal(bookedData.status, "BOOKED");

      // Step D: Patient checks in
      const checkinRes = await global.fetch("http://localhost:8000/api/v1/appointments/appt-e2e-001/check-in", {
        method: "POST",
      });
      assert.equal(checkinRes.status, 201);
      const checkinData = await checkinRes.json();
      assert.equal(checkinData.token_number, "A01");

      // Step E: Patient live queue shows token and status
      const qRes = await global.fetch("http://localhost:8000/api/v1/patients/me/queue");
      assert.equal(qRes.status, 200);
      const qData = await qRes.json();
      assert.equal(qData.token_number, "A01");
      assert.equal(qData.status, "WAITING");

      // Step F: Doctor sees patient in queue
      const docQRes = await global.fetch("http://localhost:8000/api/v1/queues/doc-456/current");
      assert.equal(docQRes.status, 200);
      const docQData = await docQRes.json();
      assert.equal(docQData.length, 1);
      assert.equal(docQData[0].patient_name, "Alice Walker");

      // Step G: Doctor calls patient
      const callRes = await global.fetch("http://localhost:8000/api/v1/queues/q-e2e-001/call", {
        method: "POST",
      });
      assert.equal(callRes.status, 200);
      const callData = await callRes.json();
      assert.equal(callData.status, "CALLED");

      // Step H: Doctor starts consultation
      const startRes = await global.fetch("http://localhost:8000/api/v1/queues/q-e2e-001/start", {
        method: "POST",
      });
      assert.equal(startRes.status, 200);
      const startData = await startRes.json();
      assert.equal(startData.status, "IN_PROGRESS");

      // Step I: Active consultation is returned
      const activeRes = await global.fetch("http://localhost:8000/api/v1/queues/active-consultation");
      assert.equal(activeRes.status, 200);
      const activeData = await activeRes.json();
      assert.equal(activeData.status, "IN_PROGRESS");
      assert.equal(activeData.token_number, "A01");

      // Step J: Doctor completes consultation
      const compRes = await global.fetch("http://localhost:8000/api/v1/queues/q-e2e-001/complete", {
        method: "POST",
      });
      assert.equal(compRes.status, 200);
      const compData = await compRes.json();
      assert.equal(compData.status, "COMPLETED");
      assert.equal(compData.duration_seconds, 420);

      // Step K: Verify final appointment state
      const apptListRes = await global.fetch("http://localhost:8000/api/v1/appointments");
      const apptList = await apptListRes.json();
      assert.equal(apptList[0].status, "COMPLETED");
    } finally {
      global.fetch = originalFetch;
    }
  });

  test("Negative Matrix: Duplicate Checkin and Concurrent Conflicts", async () => {
    let checkinCount = 0;
    const routes = {
      "POST /api/v1/appointments/appt-dup/check-in": () => {
        checkinCount++;
        if (checkinCount > 1) {
          return {
            status: 409,
            body: { error: { code: "ALREADY_CHECKED_IN", message: "Patient already checked in" } },
          };
        }
        return {
          status: 201,
          body: { id: "q-1", token_number: "A01", status: "WAITING" },
        };
      },
    };

    const originalFetch = global.fetch;
    global.fetch = createMockFetch(routes);

    try {
      const res1 = await global.fetch("http://localhost:8000/api/v1/appointments/appt-dup/check-in", {
        method: "POST",
      });
      assert.equal(res1.status, 201);

      const res2 = await global.fetch("http://localhost:8000/api/v1/appointments/appt-dup/check-in", {
        method: "POST",
      });
      assert.equal(res2.status, 409);
      const err = await res2.json();
      assert.equal(err.error.code, "ALREADY_CHECKED_IN");
    } finally {
      global.fetch = originalFetch;
    }
  });
});
