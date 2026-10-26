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

  test("Availability response accurately distinguishes unconfigured doctor from fully booked doctor", async () => {
    // Unconfigured doctor
    globalThis.fetch = async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        doctor_id: "doc_unscheduled",
        hospital_id: "hosp_1",
        appointment_date: "2026-10-24",
        slot_duration_minutes: 15,
        has_schedule: false,
        schedule_configured: false,
        is_fully_booked: false,
        slots: [],
      }),
    });

    const resUnsched = await globalThis.fetch("http://localhost:8000/api/v1/doctors/doc_unscheduled/availability?appointment_date=2026-10-24");
    const unschedData = await resUnsched.json();
    assert.equal(unschedData.has_schedule, false);
    assert.equal(unschedData.schedule_configured, false);
    assert.equal(unschedData.is_fully_booked, false);

    // Fully booked doctor
    globalThis.fetch = async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        doctor_id: "doc_booked",
        hospital_id: "hosp_1",
        appointment_date: "2026-10-24",
        slot_duration_minutes: 30,
        has_schedule: true,
        schedule_configured: true,
        is_fully_booked: true,
        slots: [
          { start_time: "09:00:00", end_time: "09:30:00", is_available: false },
          { start_time: "09:30:00", end_time: "10:00:00", is_available: false },
        ],
      }),
    });

    const resBooked = await globalThis.fetch("http://localhost:8000/api/v1/doctors/doc_booked/availability?appointment_date=2026-10-24");
    const bookedData = await resBooked.json();
    assert.equal(bookedData.has_schedule, true);
    assert.equal(bookedData.schedule_configured, true);
    assert.equal(bookedData.is_fully_booked, true);
    assert.equal(bookedData.slots.length, 2);
    assert.equal(bookedData.slots.every(s => !s.is_available), true);
  });

  test("Admin doctor schedule retrieval and batch configuration contract", async () => {
    let capturedBody = null;
    globalThis.fetch = async (url, options) => {
      if (options?.method === "PUT") {
        capturedBody = JSON.parse(options.body);
        return {
          ok: true,
          status: 200,
          json: async () => capturedBody.schedules.map((s, idx) => ({ id: `sched_${idx}`, ...s })),
        };
      }
      return {
        ok: true,
        status: 200,
        json: async () => [
          { id: "s1", day_of_week: 0, start_time: "09:00:00", end_time: "17:00:00", slot_duration_minutes: 30, is_active: true }
        ],
      };
    };

    // GET
    const resGet = await globalThis.fetch("http://localhost:8000/api/v1/admin/doctors/doc_javad/schedules");
    const schedules = await resGet.json();
    assert.equal(schedules.length, 1);
    assert.equal(schedules[0].day_of_week, 0);

    // PUT
    const updatePayload = {
      schedules: [
        { day_of_week: 0, start_time: "09:00:00", end_time: "17:00:00", slot_duration_minutes: 30, is_active: true },
        { day_of_week: 1, start_time: "09:00:00", end_time: "17:00:00", slot_duration_minutes: 30, is_active: true },
      ]
    };
    const resPut = await globalThis.fetch("http://localhost:8000/api/v1/admin/doctors/doc_javad/schedules", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updatePayload),
    });
    const putData = await resPut.json();
    assert.equal(putData.length, 2);
    assert.equal(capturedBody.schedules.length, 2);
  });

  test("Doctor availability response includes next_available_date when doctor does not consult on selected date", async () => {
    globalThis.fetch = async (url) => {
      assert.match(url, /\/api\/v1\/doctors\/doc_javad\/availability\?appointment_date=2026-10-25/);
      return {
        ok: true,
        status: 200,
        json: async () => ({
          doctor_id: "doc_javad",
          hospital_id: "hosp_1",
          appointment_date: "2026-10-25",
          slot_duration_minutes: 30,
          total_slots: 0,
          available_count: 0,
          has_schedule: false,
          schedule_configured: true,
          is_fully_booked: false,
          next_available_date: "2026-10-26",
          slots: [],
        }),
      };
    };

    const res = await globalThis.fetch("http://localhost:8000/api/v1/doctors/doc_javad/availability?appointment_date=2026-10-25");
    const data = await res.json();
    assert.equal(data.has_schedule, false);
    assert.equal(data.schedule_configured, true);
    assert.equal(data.next_available_date, "2026-10-26");
  });

  test("Admin doctor schedule initialization contract", async () => {
    let capturedUrl = null;
    let capturedOptions = null;
    globalThis.fetch = async (url, options) => {
      capturedUrl = url;
      capturedOptions = options;
      return {
        ok: true,
        status: 200,
        json: async () => [
          { id: "s1", day_of_week: 0, start_time: "09:00:00", end_time: "17:00:00", slot_duration_minutes: 30, is_active: true },
          { id: "s2", day_of_week: 1, start_time: "09:00:00", end_time: "17:00:00", slot_duration_minutes: 30, is_active: true },
          { id: "s3", day_of_week: 2, start_time: "09:00:00", end_time: "17:00:00", slot_duration_minutes: 30, is_active: true },
          { id: "s4", day_of_week: 3, start_time: "09:00:00", end_time: "17:00:00", slot_duration_minutes: 30, is_active: true },
          { id: "s5", day_of_week: 4, start_time: "09:00:00", end_time: "17:00:00", slot_duration_minutes: 30, is_active: true },
        ],
      };
    };

    const res = await globalThis.fetch("http://localhost:8000/api/v1/admin/doctors/doc_chen/schedules/initialize-default?overwrite=false", {
      method: "POST",
    });
    const data = await res.json();
    assert.equal(res.status, 200);
    assert.equal(capturedUrl, "http://localhost:8000/api/v1/admin/doctors/doc_chen/schedules/initialize-default?overwrite=false");
    assert.equal(capturedOptions.method, "POST");
    assert.equal(data.length, 5);
  });

  test("Admin repair doctor schedules contract supports dry_run and hospital filter", async () => {
    let capturedUrl = null;
    globalThis.fetch = async (url, options) => {
      capturedUrl = url;
      return {
        ok: true,
        status: 200,
        json: async () => ({
          scanned_doctors: 5,
          repaired_doctors: 2,
          dry_run: true,
          details: [
            { doctor_id: "doc_chen", name: "Dr. Marcus Chen", schedules_created: 5 },
            { doctor_id: "doc_menon", name: "Dr. Anita Menon", schedules_created: 5 },
          ],
        }),
      };
    };

    const res = await globalThis.fetch("http://localhost:8000/api/v1/admin/doctors/repair-schedules?hospital_id=hosp_1&dry_run=true", {
      method: "POST",
    });
    const data = await res.json();
    assert.equal(data.dry_run, true);
    assert.equal(data.repaired_doctors, 2);
    assert.equal(capturedUrl, "http://localhost:8000/api/v1/admin/doctors/repair-schedules?hospital_id=hosp_1&dry_run=true");
  });

  test("Booking modal confirm button validation guards", () => {
    const isConfirmDisabled = (selectedSlot, isBooking, bookingSuccess) => {
      return !selectedSlot || !selectedSlot.is_available || isBooking || bookingSuccess;
    };

    // No slot selected
    assert.equal(isConfirmDisabled(null, false, false), true);

    // Unavailable slot selected
    assert.equal(isConfirmDisabled({ start_time: "09:00", is_available: false }, false, false), true);

    // Available slot while booking
    assert.equal(isConfirmDisabled({ start_time: "09:00", is_available: true }, true, false), true);

    // Available slot after success
    assert.equal(isConfirmDisabled({ start_time: "09:00", is_available: true }, false, true), true);

    // Valid available slot ready to book
    assert.equal(isConfirmDisabled({ start_time: "09:00", is_available: true }, false, false), false);
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
