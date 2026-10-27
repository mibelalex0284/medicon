import { test, describe, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";

describe("Doctor Appointment -> Check-in -> Queue -> Consultation Workflow", () => {
  let originalFetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  test("1. Appointment mapping preserves patient_name and queue_entry_id", async () => {
    const rawBackendAppt = {
      id: "appt_test_01",
      patient_id: "pat_uuid_101",
      doctor_id: "doc_uuid_202",
      hospital_id: "hosp_uuid_303",
      appointment_date: "2026-10-27",
      scheduled_start: "10:00:00",
      scheduled_end: "10:30:00",
      appointment_type: "in_person",
      reason: "Follow-up on blood pressure",
      status: "BOOKED",
      created_at: "2026-10-27T08:00:00Z",
      updated_at: "2026-10-27T08:00:00Z",
      patient_name: "Eleanor Vance",
      doctor_name: "Dr. Marcus Brody",
      doctor_specialty: "Cardiology",
      department_name: "Cardiology Outpatient",
      queue_token: "A12",
      queue_entry_id: "q_entry_uuid_999",
    };

    globalThis.fetch = async () => ({
      ok: true,
      status: 200,
      json: async () => [rawBackendAppt],
    });

    const res = await globalThis.fetch("http://localhost:8000/api/v1/appointments");
    const data = await res.json();
    assert.equal(data[0].patient_name, "Eleanor Vance");
    assert.equal(data[0].queue_entry_id, "q_entry_uuid_999");
    assert.equal(data[0].queue_token, "A12");
  });

  test("2. Doctor check-in authorizes assigned doctor and returns queue token", async () => {
    let capturedMethod = null;
    let capturedUrl = null;

    globalThis.fetch = async (url, options) => {
      capturedUrl = url;
      capturedMethod = options?.method || "GET";
      return {
        ok: true,
        status: 200,
        json: async () => ({
          id: "q_new_123",
          appointment_id: "appt_test_01",
          patient_id: "pat_uuid_101",
          doctor_id: "doc_uuid_202",
          hospital_id: "hosp_uuid_303",
          queue_date: "2026-10-27",
          token_number: "B03",
          status: "WAITING",
          checked_in_at: "2026-10-27T09:30:00Z",
          created_at: "2026-10-27T09:30:00Z",
          updated_at: "2026-10-27T09:30:00Z",
        }),
      };
    };

    const res = await globalThis.fetch(
      "http://localhost:8000/api/v1/appointments/appt_test_01/check-in",
      { method: "POST" }
    );
    assert.equal(capturedMethod, "POST");
    assert.match(capturedUrl, /\/api\/v1\/appointments\/appt_test_01\/check-in/);

    const body = await res.json();
    assert.equal(body.token_number, "B03");
    assert.equal(body.status, "WAITING");
    assert.equal(body.appointment_id, "appt_test_01");
  });

  test("3. Live queue lists checked-in patient and calling transitions status", async () => {
    let callInvoked = false;

    globalThis.fetch = async (url, options) => {
      if (options?.method === "POST" && url.includes("/call")) {
        callInvoked = true;
        return {
          ok: true,
          status: 200,
          json: async () => ({
            id: "q_new_123",
            token_number: "B03",
            patient_id: "pat_uuid_101",
            doctor_id: "doc_uuid_202",
            status: "CALLED",
            called_at: "2026-10-27T09:35:00Z",
          }),
        };
      }
      return {
        ok: true,
        status: 200,
        json: async () => [
          {
            id: "q_new_123",
            token_number: "B03",
            patient_name: "Eleanor Vance",
            status: "WAITING",
          },
        ],
      };
    };

    // First list queue
    const listRes = await globalThis.fetch("http://localhost:8000/api/v1/queues/me/current");
    const list = await listRes.json();
    assert.equal(list.length, 1);
    assert.equal(list[0].patient_name, "Eleanor Vance");
    assert.equal(list[0].status, "WAITING");

    // Call patient
    const callRes = await globalThis.fetch("http://localhost:8000/api/v1/queues/q_new_123/call", {
      method: "POST",
    });
    const calledData = await callRes.json();
    assert.equal(callInvoked, true);
    assert.equal(calledData.status, "CALLED");
  });

  test("4. Consultation endpoint fetches by queue_entry_id", async () => {
    let requestedQueueId = null;

    globalThis.fetch = async (url) => {
      const match = url.match(/\/api\/v1\/queues\/consultation\/([^/?]+)/);
      if (match) {
        requestedQueueId = match[1];
        return {
          ok: true,
          status: 200,
          json: async () => ({
            id: "c_rec_505",
            queue_entry_id: requestedQueueId,
            appointment_id: "appt_test_01",
            patient_id: "pat_uuid_101",
            doctor_id: "doc_uuid_202",
            status: "IN_PROGRESS",
            started_at: "2026-10-27T09:40:00Z",
            clinical_notes: "Prior BP was 140/90. Current exam shows improved compliance.",
            diagnosis: "Controlled Essential Hypertension",
            prescriptions: '["Lisinopril 10mg PO Daily","Hydralazine 25mg PRN"]',
            follow_up_instructions: "Return in 4 weeks for serum electrolytes check.",
            patient_name: "Eleanor Vance",
          }),
        };
      }
      return { ok: false, status: 404 };
    };

    const res = await globalThis.fetch(
      "http://localhost:8000/api/v1/queues/consultation/q_new_123"
    );
    assert.equal(res.status, 200);
    assert.equal(requestedQueueId, "q_new_123");

    const consult = await res.json();
    assert.equal(consult.patient_name, "Eleanor Vance");
    assert.equal(consult.clinical_notes, "Prior BP was 140/90. Current exam shows improved compliance.");
    assert.equal(consult.diagnosis, "Controlled Essential Hypertension");
    assert.equal(consult.follow_up_instructions, "Return in 4 weeks for serum electrolytes check.");
  });

  test("5. Saving draft notes calls PUT /api/v1/queues/consultation/{id}/notes", async () => {
    let capturedBody = null;
    let capturedUrl = null;

    globalThis.fetch = async (url, options) => {
      capturedUrl = url;
      capturedBody = JSON.parse(options.body);
      return {
        ok: true,
        status: 200,
        json: async () => ({
          id: "c_rec_505",
          queue_entry_id: "q_new_123",
          status: "IN_PROGRESS",
          started_at: "2026-10-27T09:40:00Z",
          clinical_notes: capturedBody.clinical_notes,
          diagnosis: capturedBody.diagnosis,
          prescriptions: capturedBody.prescriptions,
          follow_up_instructions: capturedBody.follow_up_instructions,
        }),
      };
    };

    const payload = {
      clinical_notes: "Auscultation clear. Heart rate regular.",
      diagnosis: "Stage 1 Hypertension",
      prescriptions: JSON.stringify(["Hydrochlorothiazide 12.5mg Daily"]),
      follow_up_instructions: "Low sodium diet advised.",
    };

    const res = await globalThis.fetch(
      "http://localhost:8000/api/v1/queues/consultation/c_rec_505/notes",
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }
    );

    assert.equal(res.status, 200);
    assert.match(capturedUrl, /\/api\/v1\/queues\/consultation\/c_rec_505\/notes/);
    assert.equal(capturedBody.clinical_notes, "Auscultation clear. Heart rate regular.");
    assert.equal(capturedBody.diagnosis, "Stage 1 Hypertension");
  });

  test("6. Completing consultation persists notes and transitions status to COMPLETED", async () => {
    let completedBody = null;

    globalThis.fetch = async (url, options) => {
      if (options?.body) {
        completedBody = JSON.parse(options.body);
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          id: "c_rec_505",
          queue_entry_id: "q_new_123",
          status: "COMPLETED",
          started_at: "2026-10-27T09:40:00Z",
          completed_at: "2026-10-27T09:55:00Z",
          duration_seconds: 900,
          clinical_notes: completedBody?.clinical_notes || "Finalized notes.",
          diagnosis: completedBody?.diagnosis || "Stage 1 Hypertension",
        }),
      };
    };

    const res = await globalThis.fetch(
      "http://localhost:8000/api/v1/queues/q_new_123/complete",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          clinical_notes: "Finalized notes.",
          diagnosis: "Stage 1 Hypertension",
          prescriptions: '["Hydrochlorothiazide 12.5mg"]',
          follow_up_instructions: "Check back in 1 month.",
        }),
      }
    );

    assert.equal(res.status, 200);
    const completed = await res.json();
    assert.equal(completed.status, "COMPLETED");
    assert.equal(completed.clinical_notes, "Finalized notes.");
  });
});
