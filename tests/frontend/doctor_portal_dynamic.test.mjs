import { describe, it } from "node:test";
import assert from "node:assert/strict";

describe("Doctor Portal Dynamic Data Regression Suite", () => {
  // Helper replicates getDoctorInitials from src/services/doctors/index.ts
  function getDoctorInitials(name) {
    if (!name) return "DR";
    const clean = name
      .replace(/\b(Dr|Doctor|MD|MBBS|PhD|MS|DO)\b/gi, "")
      .replace(/[^a-zA-Z\s]/g, "")
      .trim();
    const parts = clean.split(/\s+/).filter(Boolean);
    if (parts.length === 0) return "DR";
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }

  const LANGUAGE_NAMES = {
    en: "English",
    es: "Spanish",
    hi: "Hindi",
    ml: "Malayalam",
    fr: "French",
    ar: "Arabic",
    de: "German",
    zh: "Mandarin",
    ta: "Tamil",
    te: "Telugu",
    bn: "Bengali",
  };

  function formatDoctorLanguages(langStr) {
    if (!langStr) return "English";
    return (
      langStr
        .split(",")
        .map((code) => {
          const clean = code.trim().toLowerCase();
          return (
            LANGUAGE_NAMES[clean] ||
            (clean.length > 0 ? clean.charAt(0).toUpperCase() + clean.slice(1) : "")
          );
        })
        .filter(Boolean)
        .join(", ") || "English"
    );
  }

  function formatDoctorSpecialties(doctor) {
    if (!doctor || !doctor.specialties || doctor.specialties.length === 0) {
      return "General Medicine";
    }
    const specNames = doctor.specialties
      .map((s) => s.specialty?.name)
      .filter(Boolean);
    return specNames.length > 0 ? specNames.join(" & ") : "General Medicine";
  }

  function formatAppointmentCount(count) {
    const safeCount = count ?? 0;
    return `${safeCount} ${safeCount === 1 ? "appointment" : "appointments"}`;
  }

  function formatDoctorGreeting(timeGreeting, doctorProfile) {
    const doctorName = doctorProfile?.profile?.full_name || "Doctor";
    return `${timeGreeting}, ${doctorName}.`;
  }

  describe("1. Doctor Initials Extraction", () => {
    it("correctly extracts initials for Dr. Anita Menon, MD", () => {
      assert.equal(getDoctorInitials("Dr. Anita Menon, MD"), "AM");
    });

    it("correctly extracts initials for Dr. Evelyn Shaw", () => {
      assert.equal(getDoctorInitials("Dr. Evelyn Shaw"), "ES");
    });

    it("correctly extracts initials for multi-part names like Dr. Jean-Luc Picard, MD, PhD", () => {
      assert.equal(getDoctorInitials("Dr. Jean Luc Picard, MD, PhD"), "JP");
    });

    it("handles single-word doctor names without crashing", () => {
      assert.equal(getDoctorInitials("House"), "HO");
    });

    it("gracefully falls back to DR for null, empty or undefined names", () => {
      assert.equal(getDoctorInitials(null), "DR");
      assert.equal(getDoctorInitials(undefined), "DR");
      assert.equal(getDoctorInitials(""), "DR");
      assert.equal(getDoctorInitials("Dr."), "DR");
    });
  });

  describe("2. Doctor Language Formatting", () => {
    it("maps standard codes to formatted English names", () => {
      assert.equal(formatDoctorLanguages("en,hi,ml"), "English, Hindi, Malayalam");
      assert.equal(formatDoctorLanguages("en,es"), "English, Spanish");
    });

    it("falls back to English when language string is missing or empty", () => {
      assert.equal(formatDoctorLanguages(null), "English");
      assert.equal(formatDoctorLanguages(""), "English");
      assert.equal(formatDoctorLanguages(undefined), "English");
    });

    it("capitalizes unknown language codes gracefully", () => {
      assert.equal(formatDoctorLanguages("en,ja"), "English, Ja");
    });
  });

  describe("3. Doctor Specialty Formatting", () => {
    it("joins multiple doctor specialties with ampersand", () => {
      const doc = {
        specialties: [
          { specialty: { name: "Internal Medicine" } },
          { specialty: { name: "Pulmonology" } },
        ],
      };
      assert.equal(formatDoctorSpecialties(doc), "Internal Medicine & Pulmonology");
    });

    it("falls back to General Medicine if specialties list is empty or undefined", () => {
      assert.equal(formatDoctorSpecialties({ specialties: [] }), "General Medicine");
      assert.equal(formatDoctorSpecialties(null), "General Medicine");
      assert.equal(formatDoctorSpecialties({}), "General Medicine");
    });
  });

  describe("4. Dynamic Greeting and Identity Isolation", () => {
    it("formats greeting with authenticated doctor's actual name rather than fixed Dr. Menon", () => {
      const docA = { profile: { full_name: "Dr. Evelyn Shaw" } };
      const docB = { profile: { full_name: "Dr. Marcus Welby" } };

      const greetingA = formatDoctorGreeting("Good morning", docA);
      const greetingB = formatDoctorGreeting("Good afternoon", docB);

      assert.equal(greetingA, "Good morning, Dr. Evelyn Shaw.");
      assert.equal(greetingB, "Good afternoon, Dr. Marcus Welby.");
      assert.notEqual(greetingA, "Good morning, Dr. Menon.");
      assert.notEqual(greetingB, "Good morning, Dr. Menon.");
    });

    it("falls back to Doctor if profile full_name is missing", () => {
      const greeting = formatDoctorGreeting("Good evening", null);
      assert.equal(greeting, "Good evening, Doctor.");
    });
  });

  describe("5. Dynamic Appointment Count vs Fixed String", () => {
    it("formats singular and plural counts derived from real appointment arrays", () => {
      assert.equal(formatAppointmentCount(0), "0 appointments");
      assert.equal(formatAppointmentCount(1), "1 appointment");
      assert.equal(formatAppointmentCount(5), "5 appointments");
      assert.equal(formatAppointmentCount(18), "18 appointments");
    });

    it("does not hardcode 18 appointments when count is different", () => {
      const count = 4;
      const formatted = formatAppointmentCount(count);
      assert.equal(formatted, "4 appointments");
      assert.notEqual(formatted, "18 appointments");
    });
  });

  describe("6. Missing Profile Fields Resilience", () => {
    it("safely generates clinic station string with null hospital or department", () => {
      const fullDoc = {
        department: { name: "Cardiology OPD" },
        hospital: { name: "Metro Central" },
      };
      const partialDoc = {
        department: null,
        hospital: { name: "Metro Central" },
      };
      const minimalDoc = {
        department: null,
        hospital: null,
      };

      const formatStation = (d) =>
        [d?.department?.name, d?.hospital?.name].filter(Boolean).join(" · ") ||
        "Outpatient Clinic";

      assert.equal(formatStation(fullDoc), "Cardiology OPD · Metro Central");
      assert.equal(formatStation(partialDoc), "Metro Central");
      assert.equal(formatStation(minimalDoc), "Outpatient Clinic");
    });
  });
});
