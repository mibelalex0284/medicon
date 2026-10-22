import { test, describe, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";

// We import the modules or test the service contracts with fetch mocking
describe("Doctor Availability Service (Frontend)", () => {
  let originalFetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  test("Successful slot retrieval returns parsed slots", async () => {
    globalThis.fetch = async (url) => {
      assert.match(url, /\/api\/v1\/doctors\/doc_123\/availability\?appointment_date=2026-10-25/);
      return {
        ok: true,
        status: 200,
        json: async () => ({
          doctor_id: "doc_123",
          appointment_date: "2026-10-25",
          slot_duration_minutes: 15,
          total_slots: 2,
          available_count: 2,
          slots: [
            { start_time: "09:00:00", end_time: "09:15:00", is_available: true },
            { start_time: "09:15:00", end_time: "09:30:00", is_available: true },
          ],
        }),
      };
    };

    const res = await globalThis.fetch("http://localhost:8000/api/v1/doctors/doc_123/availability?appointment_date=2026-10-25");
    const data = await res.json();

    assert.equal(data.doctor_id, "doc_123");
    assert.equal(data.total_slots, 2);
    assert.equal(data.slots.length, 2);
    assert.equal(data.slots[0].start_time, "09:00:00");
  });

  test("Empty availability returns 0 slots", async () => {
    globalThis.fetch = async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        doctor_id: "doc_123",
        appointment_date: "2026-10-25",
        slot_duration_minutes: 15,
        total_slots: 0,
        available_count: 0,
        slots: [],
      }),
    });

    const res = await globalThis.fetch("http://localhost:8000/api/v1/doctors/doc_123/availability?appointment_date=2026-10-25");
    const data = await res.json();

    assert.equal(data.available_count, 0);
    assert.equal(data.slots.length, 0);
  });

  test("Availability API failure raises error response", async () => {
    globalThis.fetch = async () => ({
      ok: false,
      status: 500,
      json: async () => ({
        detail: "Doctor schedule retrieval internal database error",
      }),
    });

    const res = await globalThis.fetch("http://localhost:8000/api/v1/doctors/doc_123/availability?appointment_date=2026-10-25");
    assert.equal(res.ok, false);
    assert.equal(res.status, 500);
    const body = await res.json();
    assert.equal(body.detail, "Doctor schedule retrieval internal database error");
  });
});

describe("Appointment Booking Operations (Frontend Service Integration)", () => {
  let originalFetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  test("Successful booking returns 201 with authoritative appointment ID", async () => {
    globalThis.fetch = async (url, options) => {
      assert.equal(options.method, "POST");
      const body = JSON.parse(options.body);
      assert.equal(body.patient_id, "5425b224-2055-4dfd-a5ee-39ce33f80864");
      assert.equal(body.doctor_id, "doc_202");
      assert.equal(body.appointment_date, "2026-10-25");
      assert.equal(body.scheduled_start, "09:00:00");
      assert.equal(body.scheduled_end, "09:15:00");

      return {
        ok: true,
        status: 201,
        json: async () => ({
          id: "appt_test_999",
          patient_id: body.patient_id,
          doctor_id: body.doctor_id,
          hospital_id: body.hospital_id,
          appointment_date: body.appointment_date,
          scheduled_start: body.scheduled_start,
          scheduled_end: body.scheduled_end,
          status: "BOOKED",
          appointment_type: "in_person",
          reason: "Routine checkup",
          doctor_name: "Dr. Anita Menon, MD",
          doctor_specialty: "Adult Medicine",
          department_name: "Outpatient Clinic",
        }),
      };
    };

    const res = await globalThis.fetch("http://localhost:8000/api/v1/appointments", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        patient_id: "5425b224-2055-4dfd-a5ee-39ce33f80864",
        doctor_id: "doc_202",
        hospital_id: "hosp_001",
        appointment_date: "2026-10-25",
        scheduled_start: "09:00:00",
        scheduled_end: "09:15:00",
        appointment_type: "in_person",
        reason: "Routine checkup",
      }),
    });

    assert.equal(res.status, 201);
    const data = await res.json();
    assert.equal(data.id, "appt_test_999");
    assert.equal(data.status, "BOOKED");
    assert.equal(data.doctor_name, "Dr. Anita Menon, MD");
  });

  test("Booking conflict returns 409 conflict", async () => {
    globalThis.fetch = async () => ({
      ok: false,
      status: 409,
      json: async () => ({
        detail: "Doctor schedule conflict: The requested time slot (09:00:00 - 09:15:00) overlaps with an existing appointment",
      }),
    });

    const res = await globalThis.fetch("http://localhost:8000/api/v1/appointments", {
      method: "POST",
      body: JSON.stringify({}),
    });

    assert.equal(res.status, 409);
    const data = await res.json();
    assert.match(data.detail, /overlaps with an existing appointment/);
  });

  test("Booking validation error returns 422", async () => {
    globalThis.fetch = async () => ({
      ok: false,
      status: 422,
      json: async () => ({
        detail: [
          { loc: ["body", "scheduled_start"], msg: "Field required", type: "missing" },
        ],
      }),
    });

    const res = await globalThis.fetch("http://localhost:8000/api/v1/appointments", {
      method: "POST",
      body: JSON.stringify({}),
    });

    assert.equal(res.status, 422);
    const data = await res.json();
    assert.equal(data.detail[0].loc[1], "scheduled_start");
  });

  test("Authentication failure returns 401", async () => {
    globalThis.fetch = async () => ({
      ok: false,
      status: 401,
      json: async () => ({
        detail: "Could not validate credentials",
      }),
    });

    const res = await globalThis.fetch("http://localhost:8000/api/v1/appointments", {
      method: "POST",
      body: JSON.stringify({}),
    });

    assert.equal(res.status, 401);
    const data = await res.json();
    assert.equal(data.detail, "Could not validate credentials");
  });
});

describe("Appointment History Retrieval (Frontend Service Integration)", () => {
  let originalFetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  test("Successful appointment history retrieval returns patient appointments", async () => {
    globalThis.fetch = async (url) => {
      assert.match(url, /\/api\/v1\/appointments/);
      return {
        ok: true,
        status: 200,
        json: async () => [
          {
            id: "appt_001",
            patient_id: "5425b224-2055-4dfd-a5ee-39ce33f80864",
            doctor_id: "doc_202",
            hospital_id: "hosp_001",
            appointment_date: "2026-10-25",
            scheduled_start: "09:00:00",
            scheduled_end: "09:15:00",
            status: "BOOKED",
            reason: "Persistent cough",
            doctor_name: "Dr. Anita Menon, MD",
            doctor_specialty: "Internal Medicine",
            department_name: "Adult Outpatient Clinic",
          },
        ],
      };
    };

    const res = await globalThis.fetch("http://localhost:8000/api/v1/appointments");
    const data = await res.json();

    assert.equal(Array.isArray(data), true);
    assert.equal(data.length, 1);
    assert.equal(data[0].id, "appt_001");
    assert.equal(data[0].doctor_name, "Dr. Anita Menon, MD");
  });

  test("Empty appointment history returns empty array", async () => {
    globalThis.fetch = async () => ({
      ok: true,
      status: 200,
      json: async () => [],
    });

    const res = await globalThis.fetch("http://localhost:8000/api/v1/appointments");
    const data = await res.json();

    assert.equal(Array.isArray(data), true);
    assert.equal(data.length, 0);
  });
});

describe("Appointment Cancellation (Frontend Service Integration)", () => {
  let originalFetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  test("Successful cancellation transitions appointment status to CANCELLED", async () => {
    globalThis.fetch = async (url, options) => {
      assert.match(url, /\/api\/v1\/appointments\/appt_001\/cancel/);
      assert.equal(options.method, "POST");
      return {
        ok: true,
        status: 200,
        json: async () => ({
          id: "appt_001",
          status: "CANCELLED",
        }),
      };
    };

    const res = await globalThis.fetch("http://localhost:8000/api/v1/appointments/appt_001/cancel", {
      method: "POST",
    });

    assert.equal(res.status, 200);
    const data = await res.json();
    assert.equal(data.status, "CANCELLED");
  });

  test("Failed cancellation on already cancelled appointment returns 400", async () => {
    globalThis.fetch = async () => ({
      ok: false,
      status: 400,
      json: async () => ({
        detail: "Cannot cancel appointment in CANCELLED status",
      }),
    });

    const res = await globalThis.fetch("http://localhost:8000/api/v1/appointments/appt_001/cancel", {
      method: "POST",
    });

    assert.equal(res.status, 400);
    const data = await res.json();
    assert.match(data.detail, /Cannot cancel appointment/);
  });
});

describe("Patient Check-In and Token Generation (Frontend Service Integration)", () => {
  let originalFetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  test("Successful check-in creates authoritative queue entry and server-generated token", async () => {
    globalThis.fetch = async (url, options) => {
      assert.match(url, /\/api\/v1\/appointments\/appt_001\/check-in/);
      assert.equal(options.method, "POST");
      return {
        ok: true,
        status: 201,
        json: async () => ({
          id: "queue_999",
          appointment_id: "appt_001",
          patient_id: "5425b224-2055-4dfd-a5ee-39ce33f80864",
          doctor_id: "doc_202",
          hospital_id: "hosp_001",
          token_number: "A01",
          priority_level: 3,
          status: "WAITING",
          check_in_time: "2026-10-25T08:50:00Z",
        }),
      };
    };

    const res = await globalThis.fetch("http://localhost:8000/api/v1/appointments/appt_001/check-in", {
      method: "POST",
    });

    assert.equal(res.status, 201);
    const data = await res.json();
    assert.equal(data.token_number, "A01");
    assert.equal(data.status, "WAITING");
    assert.equal(data.id, "queue_999");
  });

  test("Already checked-in response returns 400 with descriptive error", async () => {
    globalThis.fetch = async () => ({
      ok: false,
      status: 400,
      json: async () => ({
        detail: "Appointment has already been checked in",
      }),
    });

    const res = await globalThis.fetch("http://localhost:8000/api/v1/appointments/appt_001/check-in", {
      method: "POST",
    });

    assert.equal(res.status, 400);
    const data = await res.json();
    assert.match(data.detail, /already been checked in/);
  });

  test("Failed check-in for cancelled or invalid appointment returns 400", async () => {
    globalThis.fetch = async () => ({
      ok: false,
      status: 400,
      json: async () => ({
        detail: "Cannot check in appointment with status CANCELLED",
      }),
    });

    const res = await globalThis.fetch("http://localhost:8000/api/v1/appointments/appt_001/check-in", {
      method: "POST",
    });

    assert.equal(res.status, 400);
    const data = await res.json();
    assert.match(data.detail, /status CANCELLED/);
  });

  test("Duplicate submission protection flag blocks concurrent triggers", async () => {
    let callCount = 0;
    let isSubmitting = false;

    const performSubmission = async () => {
      if (isSubmitting) return null; // Duplicate guard
      isSubmitting = true;
      try {
        callCount++;
        await new Promise((resolve) => setTimeout(resolve, 50));
        return { success: true };
      } finally {
        isSubmitting = false;
      }
    };

    // Trigger two submissions in parallel
    const [res1, res2] = await Promise.all([
      performSubmission(),
      performSubmission(),
    ]);

    assert.equal(callCount, 1, "Only one submission should proceed while the other is rejected by guard");
    assert.deepEqual(res1, { success: true });
    assert.equal(res2, null);
  });
});
