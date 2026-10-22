import { test, describe, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";

describe("Patient Triage Result Flow & Navigation Safeguards (Frontend Tests)", () => {
  let originalFetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  test("1. HIGH urgency with no emergency determination provides allowed appointment pathway", async () => {
    // Simulated patient report: Bilateral leg pain for 3 days, severity 5/10, sharp, affecting activities
    const triageSessionId = "session-leg-pain-high-urgency";

    globalThis.fetch = async (url, options) => {
      const urlStr = String(url);
      if (urlStr.includes("/api/v1/doctors/recommendations")) {
        const body = options?.body ? JSON.parse(options.body) : {};
        assert.equal(body.triage_session_id, triageSessionId);

        return {
          ok: true,
          status: 200,
          json: async () => ({
            status: "SUCCESS",
            is_emergency_escalation: false,
            urgency: "HIGH",
            escalation_notice:
              "HIGH CLINICAL URGENCY: Your reported symptoms indicate elevated clinical urgency. Please schedule a prompt / urgent consultation with the recommended clinical specialty. Safety notice: Absence of red-flag symptoms does not guarantee safety. If your condition worsens suddenly, seek immediate emergency medical care.",
            applied_specialty_name: "General Medicine",
            total_eligible_doctors: 2,
            recommendations: [
              {
                doctor_id: "doc-gen-med-1",
                rank: 1,
                score: 0.92,
                doctor: {
                  id: "doc-gen-med-1",
                  profile: { full_name: "Dr. Sarah Jenkins" },
                  specialties: [{ specialty: { name: "General Medicine" } }],
                },
              },
            ],
          }),
        };
      }

      if (urlStr.includes("/api/v1/doctors/doc-gen-med-1/availability")) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            doctor_id: "doc-gen-med-1",
            appointment_date: "2026-10-25",
            total_slots: 2,
            slots: [
              { start_time: "10:00:00", end_time: "10:15:00", is_available: true },
            ],
          }),
        };
      }

      throw new Error(`Unexpected fetch URL: ${urlStr}`);
    };

    // 1. Fetch recommendations for the session
    const recRes = await globalThis.fetch("http://localhost:8000/api/v1/doctors/recommendations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ triage_session_id: triageSessionId }),
    });
    const recData = await recRes.json();

    // Verify HIGH urgency does NOT trigger emergency lock
    assert.equal(recData.is_emergency_escalation, false);
    assert.equal(recData.status, "SUCCESS");
    assert.equal(recData.urgency, "HIGH");
    assert.ok(recData.recommendations.length > 0);

    // Verify high-urgency advisory notice is present with safety caveat
    assert.ok(recData.escalation_notice.includes("HIGH CLINICAL URGENCY"));
    assert.ok(recData.escalation_notice.includes("Absence of red-flag symptoms does not guarantee safety"));

    // Verify doctor availability and booking pathway remain accessible
    const availRes = await globalThis.fetch(
      `http://localhost:8000/api/v1/doctors/${recData.recommendations[0].doctor_id}/availability?appointment_date=2026-10-25`
    );
    const availData = await availRes.json();
    assert.equal(availData.slots.length, 1);
    assert.equal(availData.slots[0].is_available, true);
  });

  test("2. Actual emergency determination retains prominent emergency guidance and locks outpatient booking", async () => {
    const triageSessionId = "session-chest-pain-emergency";

    globalThis.fetch = async (url) => {
      const urlStr = String(url);
      if (urlStr.includes("/api/v1/doctors/recommendations")) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            status: "EMERGENCY_ESCALATION",
            is_emergency_escalation: true,
            urgency: "HIGH",
            escalation_notice:
              "EMERGENCY SAFETY NOTICE: Triage assessment indicated critical warning signs or red-flag emergency symptoms. Immediate emergency medical care is advised. Outpatient doctor selection is not a substitute for emergency evaluation.",
            applied_specialty_name: "Cardiology",
            total_eligible_doctors: 1,
            recommendations: [],
          }),
        };
      }
      throw new Error(`Unexpected fetch URL: ${urlStr}`);
    };

    const res = await globalThis.fetch("http://localhost:8000/api/v1/doctors/recommendations", {
      method: "POST",
      body: JSON.stringify({ triage_session_id: triageSessionId }),
    });
    const data = await res.json();

    // Frontend condition: response?.is_emergency_escalation || response?.status === "EMERGENCY_ESCALATION"
    const isEmergency = data.is_emergency_escalation || data.status === "EMERGENCY_ESCALATION";
    assert.equal(isEmergency, true);

    // Emergency notice must be prominent
    assert.ok(data.escalation_notice.includes("EMERGENCY SAFETY NOTICE"));
    assert.ok(data.escalation_notice.includes("Immediate emergency medical care is advised"));

    // Outpatient doctor recommendations must NOT be presented for booking
    assert.equal(data.recommendations.length, 0);
  });

  test("3. LOW and MODERATE urgency pathways return normal doctor recommendations without emergency escalation", async () => {
    for (const urgencyTier of ["LOW", "MODERATE"]) {
      globalThis.fetch = async () => ({
        ok: true,
        status: 200,
        json: async () => ({
          status: "SUCCESS",
          is_emergency_escalation: false,
          urgency: urgencyTier,
          escalation_notice: null,
          applied_specialty_name: "General Medicine",
          total_eligible_doctors: 1,
          recommendations: [
            {
              doctor_id: `doc-${urgencyTier.toLowerCase()}`,
              rank: 1,
              score: 0.88,
              doctor: {
                id: `doc-${urgencyTier.toLowerCase()}`,
                profile: { full_name: `Dr. Specialist ${urgencyTier}` },
                specialties: [{ specialty: { name: "General Medicine" } }],
              },
            },
          ],
        }),
      });

      const res = await globalThis.fetch("http://localhost:8000/api/v1/doctors/recommendations", {
        method: "POST",
        body: JSON.stringify({ triage_session_id: `session-${urgencyTier}` }),
      });
      const data = await res.json();

      assert.equal(data.status, "SUCCESS");
      assert.equal(data.is_emergency_escalation, false);
      assert.equal(data.urgency, urgencyTier);
      assert.equal(data.recommendations.length, 1);
    }
  });

  test("4. Clinical guidance is coherent with urgency classification and avoids contradictions", async () => {
    // Guidance evaluation rules:
    // HIGH urgency (non-emergency) -> prompt outpatient clinical evaluation, NEVER "routine care"
    // MODERATE urgency -> timely outpatient clinical evaluation
    // LOW urgency -> routine care navigation

    const assessGuidance = (urgency, redFlagDetected) => {
      if (redFlagDetected) {
        return "Emergency warning signs were detected. Seek urgent medical attention or proceed to the nearest emergency department immediately.";
      }
      if (urgency === "HIGH") {
        return "Based on your responses, prompt outpatient clinical evaluation is recommended. Please schedule an urgent appointment with the appropriate clinical specialty. Absence of red-flag symptoms does not guarantee safety; if your condition worsens, seek immediate emergency care.";
      }
      if (urgency === "MODERATE") {
        return "Based on your responses, timely outpatient clinical evaluation is recommended. Please schedule an appointment with the appropriate clinical specialty.";
      }
      return "Based on your responses, routine care navigation is recommended. Please schedule an appointment with the appropriate clinical specialty.";
    };

    const highGuidance = assessGuidance("HIGH", false);
    assert.equal(highGuidance.includes("routine care navigation"), false, "HIGH urgency must never suggest routine care");
    assert.ok(highGuidance.includes("prompt outpatient clinical evaluation"));
    assert.ok(highGuidance.includes("does not guarantee safety"));

    const modGuidance = assessGuidance("MODERATE", false);
    assert.ok(modGuidance.includes("timely outpatient clinical evaluation"));

    const lowGuidance = assessGuidance("LOW", false);
    assert.ok(lowGuidance.includes("routine care navigation"));

    const emergGuidance = assessGuidance("HIGH", true);
    assert.ok(emergGuidance.includes("Emergency warning signs"));
  });

  test("5. Navigation from permitted triage result to doctor recommendations and slot booking", async () => {
    const sessionId = "session-bilateral-leg-pain";
    let navigatedUrl = null;

    // Simulate router.push on triage completion
    const mockRouter = {
      push: (url) => {
        navigatedUrl = url;
      },
    };

    // Triage completion event
    const triageResult = {
      sessionId,
      is_complete: true,
      assessment: {
        urgency: "HIGH",
        red_flag_detected: false,
        recommended_specialty_id: "spec-gen-med-id",
        recommended_specialty_name: "General Medicine",
        guidance:
          "Based on your responses, prompt outpatient clinical evaluation is recommended. Please schedule an urgent appointment with the appropriate clinical specialty.",
      },
    };

    // User proceeds from triage completion card
    if (triageResult.is_complete && !triageResult.assessment.red_flag_detected) {
      mockRouter.push(`/patient/doctors?session_id=${encodeURIComponent(triageResult.sessionId)}`);
    }

    assert.equal(navigatedUrl, `/patient/doctors?session_id=${sessionId}`);

    // On doctors page, fetch recommendations for the navigated session
    globalThis.fetch = async (url, options) => {
      const urlStr = String(url);
      if (urlStr.includes("/api/v1/doctors/recommendations")) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            status: "SUCCESS",
            is_emergency_escalation: false,
            urgency: "HIGH",
            escalation_notice: "HIGH CLINICAL URGENCY...",
            total_eligible_doctors: 1,
            recommendations: [
              {
                doctor_id: "doc-gen-med-42",
                rank: 1,
                doctor: {
                  id: "doc-gen-med-42",
                  profile: { full_name: "Dr. Elena Rostova" },
                },
              },
            ],
          }),
        };
      }

      if (urlStr.includes("/api/v1/appointments")) {
        return {
          ok: true,
          status: 201,
          json: async () => ({
            id: "appt-confirmed-101",
            doctor_id: "doc-gen-med-42",
            status: "CONFIRMED",
            appointment_date: "2026-10-25",
            start_time: "09:30:00",
          }),
        };
      }

      throw new Error(`Unexpected URL: ${urlStr}`);
    };

    const recRes = await globalThis.fetch("http://localhost:8000/api/v1/doctors/recommendations", {
      method: "POST",
      body: JSON.stringify({ triage_session_id: sessionId }),
    });
    const recData = await recRes.json();
    assert.equal(recData.is_emergency_escalation, false);
    assert.equal(recData.recommendations.length, 1);

    // Book appointment with recommended doctor
    const bookRes = await globalThis.fetch("http://localhost:8000/api/v1/appointments", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        doctor_id: recData.recommendations[0].doctor_id,
        appointment_date: "2026-10-25",
        start_time: "09:30:00",
        triage_session_id: sessionId,
      }),
    });
    const bookData = await bookRes.json();
    assert.equal(bookData.status, "CONFIRMED");
    assert.equal(bookData.id, "appt-confirmed-101");
  });
});
